import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).parent / ".env")

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

SECRET_KEY = os.getenv(
    "SECRET_KEY",
    "change-this-secret"
)

UPLOAD_FOLDER = "uploads"

MAX_FILE_SIZE = 20 * 1024 * 1024