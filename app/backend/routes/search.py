from flask import Blueprint, request, jsonify
from services.search_engine import search_recipes, get_eligible_pigments, get_product_cost_estimate
from services.ml_engine import get_ml_status
from models.database import RalPantoneShade

search_bp = Blueprint("search", __name__)


@search_bp.route("/api/search", methods=["POST"])
def color_search():
    """
    POST /api/search
    Body:
    {
      "target_L": 50.0,
      "target_a": 25.0,
      "target_b": 10.0,
      "polymer": "PE",
      "application": "FILM",          // optional
      "sub_application": "N.A.",       // optional
      "compliance": "REACH",           // optional
      "light_fastness": 6,             // optional minimum
      "weather_fastness": 4,           // optional minimum
      "heat_stability": 200,           // optional minimum °C
      "ral_pantone": "RAL 3020",       // optional
      "top_n": 10                      // optional
    }
    """
    data = request.get_json(force=True)
    if not data:
        return jsonify({"error": "Request body required"}), 400

    try:
        target_L = float(data["target_L"])
        target_a = float(data["target_a"])
        target_b = float(data["target_b"])
        polymer = str(data["polymer"]).upper()
    except (KeyError, ValueError, TypeError) as e:
        return jsonify({"error": f"Missing or invalid required fields: {e}"}), 400

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
        ral_pantone=data.get("ral_pantone"),
        top_n=int(data.get("top_n", 10)),
    )
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
    """GET /api/ral-pantone?q=red"""
    q = request.args.get("q", "").strip()
    query = RalPantoneShade.query
    if q:
        query = query.filter(
            RalPantoneShade.color_name.ilike(f"%{q}%") |
            RalPantoneShade.shade_code.ilike(f"%{q}%")
        )
    results = query.limit(100).all()
    return jsonify([r.to_dict() for r in results])


@search_bp.route("/api/cost/<product_id>", methods=["GET"])
def product_cost(product_id):
    """GET /api/cost/<product_id>"""
    result = get_product_cost_estimate(product_id)
    if result is None:
        return jsonify({"error": "Product not found or no recipe"}), 404
    return jsonify(result)
