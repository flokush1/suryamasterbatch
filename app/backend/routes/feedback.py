"""
Feedback routes — POST/GET/PATCH for suggestion feedback.

POST   /api/feedback              submit feedback on a suggestion
GET    /api/feedback              list all feedback records
PATCH  /api/feedback/<id>/confirm add a measured LAB to an existing record
"""
import json
import math
from datetime import datetime

from flask import Blueprint, request, jsonify
from models.database import db, FeedbackRecord, LabResult, Product, ProductRawMaterialMap

feedback_bp = Blueprint("feedback", __name__)

# ------------------------------------------------------------------
# helpers
# ------------------------------------------------------------------

def _delta_e(lab1, lab2):
    """Simple CIEDE2000 — import from color_engine to avoid duplication."""
    try:
        from services.color_engine import delta_e_cie2000
        return round(delta_e_cie2000(lab1, lab2), 3)
    except Exception:
        dL = lab1[0] - lab2[0]
        da = lab1[1] - lab2[1]
        db_ = lab1[2] - lab2[2]
        return round(math.sqrt(dL**2 + da**2 + db_**2), 3)


def _make_lab_result(product_id: str, polymer: str,
                     L: float, a: float, b: float, notes: str) -> LabResult:
    lr = LabResult(
        product_id=product_id,
        polymer=polymer.upper(),
        L=L,
        a=a,
        b=b,
        measured_date=datetime.utcnow().strftime("%Y-%m-%d"),
        notes=notes or "",
    )
    db.session.add(lr)
    return lr


def _auto_create_product(suggestion_type: str, polymer: str,
                         target_L: float, target_a: float, target_b: float,
                         pigments: list) -> str:
    """
    Create a minimal Product + recipe rows for pigment_km / ml feedback so the
    combination becomes a training sample for future ML retrains.
    Returns the new product_id.
    """
    ts = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    short = suggestion_type.replace("_", "").upper()[:2]   # PK or ML
    prod_id = f"FB{short}{ts}"

    # Colour hint for the product name
    c = math.sqrt(target_a**2 + target_b**2)
    if target_L < 25:
        color_hint = "Black"
    elif target_L > 85 and c < 15:
        color_hint = "White"
    elif c < 12:
        color_hint = "Grey"
    else:
        h = math.degrees(math.atan2(target_b, target_a))
        color_hint = (
            "Red"    if -20 <= h < 20   else
            "Orange" if 20  <= h < 55   else
            "Yellow" if 55  <= h < 100  else
            "Green"  if 100 <= h < 165  else
            "Cyan"   if 165 <= h < 220  else
            "Blue"   if 220 <= h < 290  else
            "Violet"
        )
    src = "K-M" if suggestion_type == "pigment_km" else "ML"
    prod_name = f"[FB-{src}] {color_hint} {polymer.upper()}"

    prod = Product(
        id=prod_id,
        name=prod_name,
        is_final_good=False,
        remark=f"Auto-created from {src} suggestion feedback",
        date_updated=datetime.utcnow().strftime("%Y-%m-%d"),
    )
    db.session.add(prod)

    # Build recipe — use RM IDs where they exist, otherwise skip
    total_pct = sum(p.get("percentage", 0) for p in pigments)
    if total_pct < 0.001:
        total_pct = 100.0
    # Normalise to 100 kg batch
    for p in pigments:
        rm_id = p.get("rm_id") or p.get("rawmaterialid")
        pct   = p.get("percentage") or p.get("pct") or 0.0
        if not rm_id or pct <= 0:
            continue
        qty_kg = (pct / 100.0) * 100.0   # kg in a 100 kg batch
        row = ProductRawMaterialMap(
            productid=prod_id,
            rawmaterialid=rm_id,
            qtyinkg=round(qty_kg, 4),
        )
        db.session.add(row)

    return prod_id


# ------------------------------------------------------------------
# POST /api/feedback
# ------------------------------------------------------------------

@feedback_bp.route("/api/feedback", methods=["POST"])
def submit_feedback():
    """
    Submit feedback on a search suggestion.

    Body fields (all required unless noted):
      suggestion_type   : "recipe" | "pigment_km" | "ml"
      target_lab        : { L, a, b }
      polymer           : "PE" | "PP" | "ABS" | "SAN" | "PVC" | "OTHER"
      delta_e           : float — ΔE of suggestion to target (from search response)

    For suggestion_type == "recipe":
      product_id        : str  — the existing product that was suggested
      recipe_snapshot   : list (optional) — copy of recipe rows from search result

    For suggestion_type == "pigment_km" or "ml":
      pigments          : list of { rm_id, name, percentage }
                          (use the pigment_system / pigments array from search result)

    Optional (confirmed measurement — provide when spectrophotometer reading is available):
      confirmed_L, confirmed_a, confirmed_b : float
      notes             : str
    """
    data = request.get_json(force=True)
    if not data:
        return jsonify({"error": "Body required"}), 400

    # ── Validate required fields ──────────────────────────────────────
    stype = str(data.get("suggestion_type", "")).strip().lower()
    if stype not in ("recipe", "pigment_km", "ml", "custom"):
        return jsonify({"error": "suggestion_type must be 'recipe', 'pigment_km', 'ml', or 'custom'"}), 400

    try:
        tlab = data["target_lab"]
        tL = float(tlab["L"])
        ta = float(tlab["a"])
        tb = float(tlab["b"])
        polymer = str(data["polymer"]).strip().upper()
        delta_e_sub = float(data.get("delta_e") or 0)
    except (KeyError, TypeError, ValueError) as exc:
        return jsonify({"error": f"Missing or invalid fields: {exc}"}), 400

    notes = str(data.get("notes") or "").strip()

    # ── Confirmed measurement (optional) ─────────────────────────────
    cL = ca = cb = de_conf = None
    try:
        if data.get("confirmed_L") is not None:
            cL = float(data["confirmed_L"])
            ca = float(data["confirmed_a"])
            cb = float(data["confirmed_b"])
            de_conf = _delta_e((tL, ta, tb), (cL, ca, cb))
    except (TypeError, ValueError):
        pass

    # ── Use confirmed LAB for training if available, else target LAB ──
    train_L = cL if cL is not None else tL
    train_a = ca if ca is not None else ta
    train_b = cb if cb is not None else tb

    # ── Type-specific logic ───────────────────────────────────────────
    product_id  = None
    recipe_snap = None
    lr          = None

    if stype == "recipe":
        product_id = str(data.get("product_id") or "").strip()
        if not product_id:
            return jsonify({"error": "product_id required for recipe feedback"}), 400

        # Snapshot of recipe rows (forwarded from search result)
        recipe_snap = json.dumps(data.get("recipe_snapshot") or [])

        # Verify product exists
        prod = Product.query.get(product_id)
        if prod is None:
            return jsonify({"error": f"Product '{product_id}' not found"}), 404

        # Only create a LabResult when the user has provided a confirmed measurement.
        # Without confirmed LAB, we do NOT store the target LAB — the product's recipe
        # does not produce exactly the target colour (just a close match), so recording
        # target_L/a/b as a measured result would introduce noise into ML training.
        if cL is not None:
            lr = _make_lab_result(
                product_id, polymer, cL, ca, cb,
                notes=f"[Feedback-confirmed] {notes}"
            )
        else:
            lr = None  # FeedbackRecord saved for audit; no LabResult until measured

    else:
        # pigment_km, ml, or custom
        pigments = data.get("pigments") or []
        if not pigments:
            return jsonify({"error": "pigments list required for pigment_km / ml / custom feedback"}), 400

        recipe_snap = json.dumps(pigments)

        # Auto-create a product + recipe so ML can retrain from it
        product_id = _auto_create_product(stype, polymer, tL, ta, tb, pigments)

        # Create a LabResult for the auto product
        lr = _make_lab_result(
            product_id, polymer, train_L, train_a, train_b,
            notes=f"[Feedback-{stype}] {notes}"
        )

    db.session.flush()   # get lr.id before commit

    # ── Save FeedbackRecord ───────────────────────────────────────────
    fb = FeedbackRecord(
        suggestion_type=stype,
        target_L=tL,
        target_a=ta,
        target_b=tb,
        polymer=polymer,
        product_id=product_id,
        recipe_snapshot=recipe_snap,
        delta_e_at_submission=delta_e_sub,
        confirmed_L=cL,
        confirmed_a=ca,
        confirmed_b=cb,
        delta_e_confirmed=de_conf,
        notes=notes,
        lab_result_id=lr.id if lr else None,
    )
    db.session.add(fb)
    db.session.commit()

    return jsonify({
        "status": "ok",
        "feedback_id": fb.id,
        "product_id": product_id,
        "lab_result_id": lr.id if lr else None,
        "message": (
            f"Feedback saved. LabResult created for product '{product_id}'. "
            "Run POST /api/retrain to incorporate into ML model."
        ),
    }), 201


# ------------------------------------------------------------------
# GET /api/feedback
# ------------------------------------------------------------------

@feedback_bp.route("/api/feedback", methods=["GET"])
def list_feedback():
    """
    GET /api/feedback?suggestion_type=recipe&polymer=PE&limit=50

    Optional filters: suggestion_type, polymer, limit (default 100)
    """
    stype   = request.args.get("suggestion_type", "").strip().lower() or None
    polymer = request.args.get("polymer", "").strip().upper() or None
    limit   = min(int(request.args.get("limit", 100)), 500)

    q = FeedbackRecord.query
    if stype:
        q = q.filter(FeedbackRecord.suggestion_type == stype)
    if polymer:
        q = q.filter(FeedbackRecord.polymer == polymer)

    records = q.order_by(FeedbackRecord.created_at.desc()).limit(limit).all()
    return jsonify([r.to_dict() for r in records])


# ------------------------------------------------------------------
# PATCH /api/feedback/<id>/confirm
# ------------------------------------------------------------------

@feedback_bp.route("/api/feedback/<int:fb_id>/confirm", methods=["PATCH"])
def confirm_feedback(fb_id):
    """
    Add or update the measured LAB reading for an existing feedback record.
    Use this when the spectrophotometer result becomes available after production.

    Body: { "confirmed_L": 50.2, "confirmed_a": 9.8, "confirmed_b": -19.5,
            "notes": "optional" }
    """
    fb = FeedbackRecord.query.get(fb_id)
    if not fb:
        return jsonify({"error": "Feedback record not found"}), 404

    data = request.get_json(force=True)
    try:
        cL = float(data["confirmed_L"])
        ca = float(data["confirmed_a"])
        cb = float(data["confirmed_b"])
    except (KeyError, TypeError, ValueError) as exc:
        return jsonify({"error": f"confirmed_L/a/b required: {exc}"}), 400

    fb.confirmed_L = cL
    fb.confirmed_a = ca
    fb.confirmed_b = cb
    fb.delta_e_confirmed = _delta_e(
        (fb.target_L, fb.target_a, fb.target_b), (cL, ca, cb)
    )
    if data.get("notes"):
        fb.notes = (fb.notes or "") + " | " + str(data["notes"]).strip()

    # Also update the linked LabResult with the confirmed measurement
    if fb.lab_result_id:
        lr = LabResult.query.get(fb.lab_result_id)
        if lr:
            lr.L = cL
            lr.a = ca
            lr.b = cb
            lr.notes = (lr.notes or "") + " [confirmed measurement]"

    db.session.commit()
    return jsonify({
        "status": "ok",
        "feedback_id": fb.id,
        "delta_e_confirmed": fb.delta_e_confirmed,
        "message": "Confirmed measurement saved. Run POST /api/retrain to retrain ML.",
    })
