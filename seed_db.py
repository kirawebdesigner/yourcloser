"""
Quick script to run the schema.sql against Supabase via the REST API.
Run once: python seed_db.py
"""
import httpx
import sys

SUPABASE_URL = "https://ptbdngvloynyqjodguks.supabase.co"
SERVICE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InB0YmRuZ3Zsb3lueXFqb2RndWtzIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3ODk0NjE1NiwiZXhwIjoyMDk0NTIyMTU2fQ.25GDRHPWZIbnH3g16slsR7PajzHkiyTGJkPLDGTu1aM"

# Read the SQL file
with open("schema.sql", "r") as f:
    sql = f.read()

# Split into individual statements to run them separately
# The Supabase REST SQL endpoint can handle multi-statement SQL
headers = {
    "apikey": SERVICE_KEY,
    "Authorization": f"Bearer {SERVICE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}

# Use the pg-meta SQL endpoint
url = f"{SUPABASE_URL}/rest/v1/rpc/exec_sql"

# Actually, let's use the raw SQL endpoint available via supabase-py
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
print(f"  1. Go to: {SUPABASE_URL.replace('.co', '.co').replace('https://', 'https://supabase.com/dashboard/project/').split('.')[0]}")
print(f"  1. Go to: https://supabase.com/dashboard/project/ptbdngvloynyqjodguks/sql/new")
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
