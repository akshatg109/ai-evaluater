from supabase import create_client

from config import (
    SUPABASE_KEY,
    SUPABASE_URL
)

supabase = create_client(
    SUPABASE_URL,
    SUPABASE_KEY
)

try:
    supabase.table("evaluations").select("*").limit(1).execute()
    print("✅ Supabase Connected")
except Exception as e:
    print("❌ Supabase Error:", e)