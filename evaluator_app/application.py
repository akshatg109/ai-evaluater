"""Flask application factory used by the root app.py entry point."""

from flask import Flask, jsonify, render_template, request
from werkzeug.exceptions import RequestEntityTooLarge

from .config import Config
from .extensions import init_extensions
from .routes.auth import auth_bp
from .routes.batches import batches_bp
from .routes.evaluations import evaluations_bp
from .routes.main import main_bp


def create_app(config_override=None):
    """Create and configure the AI answer-sheet evaluator."""
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config.from_object(Config)
    if config_override:
        app.config.update(config_override)
    if (
        app.config.get("REQUIRE_STRONG_SECRET")
        and (not app.config.get("SECRET_KEY") or len(app.config["SECRET_KEY"]) < 32
             or app.config["SECRET_KEY"] == "change-this-secret"
             or "replace-with" in app.config["SECRET_KEY"])
        and not app.testing
    ):
        raise RuntimeError("Set a strong SECRET_KEY before running in production.")

    init_extensions(app)
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(evaluations_bp)
    app.register_blueprint(batches_bp)

    @app.errorhandler(RequestEntityTooLarge)
    def handle_large_upload(_error):
        if request.path.startswith("/batches"):
            return jsonify({
                "error": "This file is too large. Please keep each file below 20MB.",
            }), 413
        return render_template(
            "error.html",
            error="The combined upload is too large. Please keep each file below 20MB.",
        ), 413

    return app
