from flask import Blueprint, request, jsonify
from models.database import db, LabResult, Product
from datetime import datetime

lab_bp = Blueprint("lab", __name__)


@lab_bp.route("/api/lab-results", methods=["GET"])
def list_lab_results():
    """GET /api/lab-results?product_id=30016&polymer=PE"""
    product_id = request.args.get("product_id", "").strip()
    polymer = request.args.get("polymer", "").strip().upper()

    query = LabResult.query
    if product_id:
        query = query.filter(LabResult.product_id == product_id)
    if polymer:
        query = query.filter(LabResult.polymer == polymer)
    return jsonify([r.to_dict() for r in query.order_by(LabResult.created_at.desc()).all()])


@lab_bp.route("/api/lab-results", methods=["POST"])
def add_lab_result():
    """
    POST /api/lab-results
    {
      "product_id": "30016",
      "polymer": "PE",
      "L": 40.5,
      "a": 35.2,
      "b": 22.1,
      "measured_date": "2026-04-01",
      "notes": "Batch trial #5"
    }
    """
    data = request.get_json(force=True)
    if not data:
        return jsonify({"error": "Body required"}), 400

    try:
        lr = LabResult(
            product_id=str(data["product_id"]).strip(),
            polymer=str(data["polymer"]).strip().upper(),
            L=float(data["L"]),
            a=float(data["a"]),
            b=float(data["b"]),
            measured_date=data.get("measured_date", datetime.utcnow().strftime("%Y-%m-%d")),
            notes=data.get("notes", ""),
        )
        db.session.add(lr)
        db.session.commit()
        return jsonify(lr.to_dict()), 201
    except (KeyError, ValueError, TypeError) as e:
        return jsonify({"error": f"Invalid data: {e}"}), 400


@lab_bp.route("/api/lab-results/<int:result_id>", methods=["DELETE"])
def delete_lab_result(result_id):
    lr = LabResult.query.get(result_id)
    if not lr:
        return jsonify({"error": "Not found"}), 404
    db.session.delete(lr)
    db.session.commit()
    return jsonify({"deleted": result_id})
