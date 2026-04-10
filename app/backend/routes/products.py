from flask import Blueprint, request, jsonify
from models.database import db, Product, ProductSpec, ProductRawMaterialMap, AlphaCode

products_bp = Blueprint("products", __name__)


@products_bp.route("/api/products", methods=["GET"])
def list_products():
    """GET /api/products?name=RED&polymer=PE&page=1&per_page=50"""
    name = request.args.get("name", "").strip()
    polymer = request.args.get("polymer", "").strip().upper()
    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("per_page", 50))

    query = Product.query
    if name:
        query = query.filter(Product.name.ilike(f"%{name}%"))
    if polymer:
        # Filter by products whose alphacode list contains the polymer prefix
        from services.search_engine import POLYMER_PREFIX
        prefix = POLYMER_PREFIX.get(polymer, polymer[0])
        query = query.filter(Product.alphacode.ilike(f"%'{prefix}%"))

    total = query.count()
    products = query.order_by(Product.id).offset((page - 1) * per_page).limit(per_page).all()
    return jsonify({
        "total": total,
        "page": page,
        "per_page": per_page,
        "products": [p.to_dict() for p in products],
    })


@products_bp.route("/api/products/<product_id>", methods=["GET"])
def get_product(product_id):
    prod = Product.query.get(product_id)
    if not prod:
        return jsonify({"error": "Not found"}), 404
    data = prod.to_dict()
    if prod.spec:
        data["spec"] = prod.spec.to_dict()
    data["recipe"] = [r.to_dict() for r in prod.recipe_items]
    return jsonify(data)


@products_bp.route("/api/products/<product_id>/recipe", methods=["GET"])
def get_recipe(product_id):
    items = ProductRawMaterialMap.query.filter_by(productid=product_id).all()
    if not items:
        return jsonify({"error": "No recipe found"}), 404
    return jsonify([i.to_dict() for i in items])


@products_bp.route("/api/alpha-codes", methods=["GET"])
def list_alpha_codes():
    """GET /api/alpha-codes?polymer=PE&application=FILM"""
    polymer = request.args.get("polymer", "").strip().upper()
    application = request.args.get("application", "").strip()
    compliance = request.args.get("compliance", "").strip()

    query = AlphaCode.query
    if polymer:
        query = query.filter(AlphaCode.polymer == polymer)
    if application:
        query = query.filter(AlphaCode.application.ilike(f"%{application}%"))
    if compliance:
        query = query.filter(AlphaCode.compliance == compliance)

    return jsonify([ac.to_dict() for ac in query.all()])
