import os
from flask import Flask
from flask_cors import CORS
from models.database import db


def create_app():
    app = Flask(__name__)

    # Config
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    db_path = os.path.join(base_dir, "surya.db")
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "surya-masterbatch-dev-key")

    # Extensions
    db.init_app(app)
    CORS(app)

    # Register blueprints
    from routes.search import search_bp
    from routes.products import products_bp
    from routes.lab import lab_bp
    from routes.materials import materials_bp

    app.register_blueprint(search_bp)
    app.register_blueprint(products_bp)
    app.register_blueprint(lab_bp)
    app.register_blueprint(materials_bp)

    # Start ML model training in background (non-blocking)
    from services.ml_engine import init_ml_model
    init_ml_model(app)

    return app


if __name__ == "__main__":
    app = create_app()
    with app.app_context():
        db.create_all()
    app.run(debug=True, port=5000)
