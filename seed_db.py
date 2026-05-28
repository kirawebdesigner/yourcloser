"""
Quick helper for Supabase schema setup verification.
Run once after applying schema.sql in the Supabase SQL Editor: python seed_db.py
"""
import sys
from config import settings

SUPABASE_URL = settings.SUPABASE_URL
SERVICE_KEY = settings.SUPABASE_SERVICE_KEY

settings.validate()

# Read the SQL file
with open("schema.sql", "r") as f:
    sql = f.read()

from supabase import create_client
client = create_client(SUPABASE_URL, SERVICE_KEY)

# Split SQL into logical blocks and execute via rpc
# Supabase doesn't have a direct "run raw SQL" REST endpoint for arbitrary DDL
# So let's use the postgrest approach: create tables via individual API calls

# Better approach: use the Supabase Management API or just print instructions
print("=" * 60)
print("SUPABASE SCHEMA SETUP")
print("=" * 60)
print()
print("Please run the schema.sql file in your Supabase SQL Editor:")
print("  1. Open your Supabase project SQL Editor")
print("  2. Paste the contents of schema.sql")
print("  3. Click 'Run'")
print()
print("After that, let's verify the connection works...")
print()

# Test connection
try:
    result = client.table("products").select("id, name").limit(1).execute()
    if result.data:
        print(f"[SUCCESS] Connection works! Found {len(result.data)} product(s)")
        for p in result.data:
            print(f"   - {p['name']}")
    else:
        print("[WARNING] Connection works but no products found.")
        print("   -> Run schema.sql in the SQL Editor first!")
except Exception as e:
    error_msg = str(e)
    if "does not exist" in error_msg or "relation" in error_msg:
        print("[WARNING] 'products' table doesn't exist yet.")
        print("   -> Run schema.sql in the SQL Editor first!")
    else:
        print(f"[ERROR] Connection error: {e}")
        sys.exit(1)
