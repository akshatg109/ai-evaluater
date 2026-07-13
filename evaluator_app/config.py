"""Environment-backed application configuration."""

import os
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "change-this-secret")
    SUPABASE_URL = os.getenv("SUPABASE_URL")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY")
    OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
    OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
    EVALUATION_MODEL = "qwen/qwen3-vl-32b-instruct"
    UPLOAD_FOLDER = str(PROJECT_ROOT / "uploads")
    MAX_FILE_SIZE = 20 * 1024 * 1024
    MAX_CONTENT_LENGTH = MAX_FILE_SIZE
    ALLOWED_DOCUMENT_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg"}
