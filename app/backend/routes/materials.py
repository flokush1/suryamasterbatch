from flask import Blueprint, request, jsonify
from models.database import db, RawMaterial, Stock

materials_bp = Blueprint("materials", __name__)


@materials_bp.route("/api/raw-materials", methods=["GET"])
def list_raw_materials():
    """GET /api/raw-materials?type=PG&compliance=REACH&q=yellow"""
    rm_type = request.args.get("type", "").strip().upper()
    compliance = request.args.get("compliance", "").strip()
    q = request.args.get("q", "").strip()

    query = RawMaterial.query
    if rm_type:
        query = query.filter(RawMaterial.type == rm_type)
    if compliance:
        query = query.filter(RawMaterial.compliance == compliance)
    if q:
        query = query.filter(
            RawMaterial.rawmaterialname.ilike(f"%{q}%") |
            RawMaterial.chemical_name.ilike(f"%{q}%")
        )
    return jsonify([r.to_dict() for r in query.order_by(RawMaterial.rawmaterialname).all()])


@materials_bp.route("/api/raw-materials/<rm_id>", methods=["GET"])
def get_raw_material(rm_id):
    rm = RawMaterial.query.get(rm_id)
    if not rm:
        return jsonify({"error": "Not found"}), 404
    data = rm.to_dict()
    stock = Stock.query.filter_by(rawmaterialid=rm_id).first()
    data["stock"] = stock.to_dict() if stock else None
    return jsonify(data)


@materials_bp.route("/api/stocks", methods=["GET"])
def list_stocks():
    """GET /api/stocks?q=carbon"""
    q = request.args.get("q", "").strip()
    query = Stock.query
    if q:
        query = query.filter(
            Stock.rawmaterialname.ilike(f"%{q}%") |
            Stock.particulars_name.ilike(f"%{q}%")
        )
    return jsonify([s.to_dict() for s in query.all()])
