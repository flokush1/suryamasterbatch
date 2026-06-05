import os
from flask import Flask
from flask_cors import CORS
from models.database import db


def create_app():
    app = Flask(__name__)

    # Config — DB_PATH env var overrides the default (used in Docker)
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    default_db = os.path.join(base_dir, "surya.db")
    db_path = os.environ.get("DB_PATH", default_db)
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
    from routes.feedback import feedback_bp

    app.register_blueprint(search_bp)
    app.register_blueprint(products_bp)
    app.register_blueprint(lab_bp)
    app.register_blueprint(materials_bp)
    app.register_blueprint(feedback_bp)

    # Start ML model training in background (non-blocking)
    from services.ml_engine import init_ml_model
    init_ml_model(app)

    # ── Frontend Serving ──────────────────────────────────────────────────
    from flask import send_from_directory
    dist_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../frontend/dist"))

    if os.path.exists(dist_path):
        # Specific files in root
        @app.route("/favicon.svg")
        def favicon():
            return send_from_directory(dist_path, "favicon.svg")

        @app.route("/icons.svg")
        def icons():
            return send_from_directory(dist_path, "icons.svg")

        # SPA Catch-all and static asset serving
        @app.route("/", defaults={"path": ""})
        @app.route("/<path:path>")
        def serve_spa(path):
            if path.startswith("api/"):
                return {"detail": "Not Found"}, 404
            
            full_path = os.path.join(dist_path, path)
            if path and os.path.isfile(full_path):
                return send_from_directory(dist_path, path)
            
            return send_from_directory(dist_path, "index.html")
    else:
        @app.route("/")
        def index():
            return {"message": "Backend is running. Frontend build (dist) not found."}

    return app


if __name__ == "__main__":
    app = create_app()
    with app.app_context():
        db.create_all()
    app.run(debug=True, port=5000)
