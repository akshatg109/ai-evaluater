"""External service clients used by the application."""

from pathlib import Path

from openai import OpenAI
from supabase import create_client


def init_extensions(app):
    """Initialise shared clients once during app creation."""
    Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)
    url = app.config["SUPABASE_URL"]
    key = app.config["SUPABASE_KEY"]
    app.extensions["supabase"] = create_client(url, key) if url and key else None
    if app.extensions["supabase"] is None:
        app.logger.warning("Supabase is not configured; authentication and history are unavailable.")
    app.extensions["openrouter"] = OpenAI(
        api_key=app.config["OPENROUTER_API_KEY"],
        base_url=app.config["OPENROUTER_BASE_URL"],
        timeout=60,
    )
