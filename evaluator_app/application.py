"""Flask application factory used by the root app.py entry point."""

from flask import Flask, render_template
from werkzeug.exceptions import RequestEntityTooLarge

from .config import Config
from .extensions import init_extensions
from .routes.auth import auth_bp
from .routes.evaluations import evaluations_bp
from .routes.main import main_bp


def create_app(config_override=None):
    """Create and configure the AI answer-sheet evaluator."""
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config.from_object(Config)
    if config_override:
        app.config.update(config_override)

    init_extensions(app)
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(evaluations_bp)

    @app.errorhandler(RequestEntityTooLarge)
    def handle_large_upload(_error):
        return render_template(
            "error.html",
            error="The combined upload is too large. Please use files below 20MB each.",
        ), 413

    return app
