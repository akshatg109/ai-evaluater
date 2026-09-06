"""Environment-backed application configuration."""

import os
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


def _env_int(name, default, minimum=0):
    """Read a bounded integer setting without making startup fragile."""
    try:
        return max(minimum, int(os.getenv(name, default)))
    except (TypeError, ValueError):
        return default


def _env_float(name, default, minimum=0.0):
    """Read a bounded float setting without making startup fragile."""
    try:
        return max(minimum, float(os.getenv(name, default)))
    except (TypeError, ValueError):
        return default


def _env_bool(name, default=False):
    """Read a conventional boolean environment setting."""
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "change-this-secret")
    REQUIRE_STRONG_SECRET = _env_bool("REQUIRE_STRONG_SECRET") or _env_bool("RENDER")
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _env_bool("SESSION_COOKIE_SECURE") or _env_bool("RENDER")
    SUPABASE_URL = os.getenv("SUPABASE_URL")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY")
    SUPABASE_STORAGE_BUCKET = os.getenv(
        "SUPABASE_STORAGE_BUCKET", "evaluation-batches"
    ).strip() or "evaluation-batches"
    OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
    OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
    EVALUATION_MODEL = os.getenv(
        "EVALUATION_MODEL", "qwen/qwen3-vl-32b-instruct"
    )
    UPLOAD_FOLDER = str(PROJECT_ROOT / "uploads")
    MAX_FILE_SIZE = 20 * 1024 * 1024
    MAX_DOCUMENT_PAGES = _env_int("MAX_DOCUMENT_PAGES", 50, minimum=1)
    MAX_BATCH_SIZE = min(60, _env_int("MAX_BATCH_SIZE", 60, minimum=1))
    MAX_BATCHES_PER_HOUR = _env_int("MAX_BATCHES_PER_HOUR", 5, minimum=1)
    BATCH_DRAFT_RETENTION_HOURS = _env_int("BATCH_DRAFT_RETENTION_HOURS", 24, minimum=1)
    BATCH_TERMINAL_RETENTION_DAYS = _env_int("BATCH_TERMINAL_RETENTION_DAYS", 30, minimum=1)
    BATCH_CLEANUP_INTERVAL_SECONDS = _env_int("BATCH_CLEANUP_INTERVAL_SECONDS", 3600, minimum=60)
    BATCH_POLL_INTERVAL_SECONDS = _env_float(
        "BATCH_POLL_INTERVAL_SECONDS", 3.0, minimum=1.0
    )
    WORKER_POLL_SECONDS = _env_float("WORKER_POLL_SECONDS", 5.0, minimum=1.0)
    WORKER_MAX_RETRIES = _env_int("WORKER_MAX_RETRIES", 2, minimum=0)
    WORKER_RETRY_BACKOFF_SECONDS = _env_float(
        "WORKER_RETRY_BACKOFF_SECONDS", 2.0, minimum=0.0
    )
    WORKER_LEASE_SECONDS = _env_int("WORKER_LEASE_SECONDS", 900, minimum=60)
    # Flask applies this limit to the entire multipart request, not each file.
    # Leave room for three 20 MB uploads (question, answer, and optional key)
    # plus multipart form overhead.
    MAX_CONTENT_LENGTH = (3 * MAX_FILE_SIZE) + (1 * 1024 * 1024)
    ALLOWED_DOCUMENT_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg"}
