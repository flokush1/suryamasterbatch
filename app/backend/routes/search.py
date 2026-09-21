from flask import Blueprint, request, jsonify, current_app
from services.search_engine import search_recipes, get_eligible_pigments, get_product_cost_estimate
from services.ml_engine import get_ml_status, retrain_ml_model
from services.ral_pantone import resolve_shade
from models.database import RalPantoneShade

search_bp = Blueprint("search", __name__)


def _optional_float(data, key):
    val = data.get(key)
    if val is None or val == "":
        return None
    return float(val)


@search_bp.route("/api/search", methods=["POST"])
def color_search():
    """
    POST /api/search
    Body:
    {
      "target_L": 50.0,               // optional if ral_pantone is set
      "target_a": 25.0,
      "target_b": 10.0,
      "polymer": "PE",
      "application": "FILM",          // optional
      "sub_application": "N.A.",       // optional
      "compliance": "REACH",           // optional
      "light_fastness": 6,             // optional minimum
      "weather_fastness": 4,           // optional minimum
      "heat_stability": 200,           // optional minimum °C
      "ral_pantone": "RAL 3020",       // optional; used as target LAB if L*a*b* omitted
      "top_n": 10                      // optional
    }
    """
    data = request.get_json(force=True)
    if not data:
        return jsonify({"error": "Request body required"}), 400

    try:
        polymer = str(data["polymer"]).upper()
        target_L = _optional_float(data, "target_L")
        target_a = _optional_float(data, "target_a")
        target_b = _optional_float(data, "target_b")
    except (KeyError, ValueError, TypeError) as e:
        return jsonify({"error": f"Missing or invalid required fields: {e}"}), 400

    ral_pantone = (data.get("ral_pantone") or "").strip() or None
    has_lab = all(v is not None for v in (target_L, target_a, target_b))
    if not has_lab and not ral_pantone:
        return jsonify({
            "error": "Provide target L*, a*, b* or a RAL/Pantone code"
        }), 400

    results = search_recipes(
        target_L=target_L,
        target_a=target_a,
        target_b=target_b,
        polymer=polymer,
        application=data.get("application"),
        sub_application=data.get("sub_application"),
        compliance=data.get("compliance"),
        light_fastness=float(data["light_fastness"]) if data.get("light_fastness") else None,
        weather_fastness=float(data["weather_fastness"]) if data.get("weather_fastness") else None,
        heat_stability=float(data["heat_stability"]) if data.get("heat_stability") else None,
        ral_pantone=ral_pantone,
        top_n=int(data.get("top_n", 10)),
    )
    if results.get("error"):
        status = 404 if ral_pantone and not has_lab else 400
        return jsonify(results), status
    return jsonify(results)


@search_bp.route("/api/ml-status", methods=["GET"])
def ml_status():
    """GET /api/ml-status  — check if ML model is trained yet."""
    return jsonify(get_ml_status())


@search_bp.route("/api/pigments", methods=["GET"])
def list_pigments():
    """GET /api/pigments?compliance=REACH"""
    compliance = request.args.get("compliance")
    pigments = get_eligible_pigments(compliance=compliance)
    return jsonify([p.to_dict() for p in pigments])


@search_bp.route("/api/ral-pantone", methods=["GET"])
def list_ral_pantone():
    """
    GET /api/ral-pantone?q=red          — search list
    GET /api/ral-pantone?code=RAL 3020  — resolve one code to LAB
    """
    code = request.args.get("code", "").strip()
    if code:
        shade = resolve_shade(code)
        if shade is None:
            return jsonify({"error": f"Unknown RAL/Pantone code: {code}"}), 404
        return jsonify(shade)

    q = request.args.get("q", "").strip()
    query = RalPantoneShade.query
    if q:
        query = query.filter(
            RalPantoneShade.color_name.ilike(f"%{q}%") |
            RalPantoneShade.shade_code.ilike(f"%{q}%")
        )
    results = query.limit(100).all()
    payload = [r.to_dict() for r in results]
    resolved = resolve_shade(q) if q else None
    if resolved and resolved["shade_code"] not in {p["shade_code"] for p in payload}:
        payload.insert(0, resolved)
    return jsonify(payload)


@search_bp.route("/api/cost/<product_id>", methods=["GET"])
def product_cost(product_id):
    """GET /api/cost/<product_id>"""
    result = get_product_cost_estimate(product_id)
    if result is None:
        return jsonify({"error": "Product not found or no recipe"}), 404
    return jsonify(result)


@search_bp.route("/api/retrain", methods=["POST"])
def trigger_retrain():
    """
    POST /api/retrain
    Triggers an on-demand ML model retrain using all current LabResult + recipe data.
    Returns immediately. Poll GET /api/ml-status to check when it is ready again.

    Use after adding new spectrophotometer readings via POST /api/lab-results so that
    the ML model incorporates the new data without restarting the server.

    Response:
      { "status": "started",  "message": "..." }
      { "status": "already_retraining", "message": "..." }
    """
    app = current_app._get_current_object()
    result = retrain_ml_model(app)
    return jsonify(result)
