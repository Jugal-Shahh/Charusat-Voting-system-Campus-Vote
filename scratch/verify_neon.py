import os
import psycopg2
from dotenv import load_dotenv

load_dotenv(".env")
url = os.environ.get("DATABASE_URL")
if not url:
    print("No DATABASE_URL found.")
    exit(1)

print(f"Connecting to: {url[:30]}...")

conn = psycopg2.connect(url)
cur = conn.cursor()
cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
tables = cur.fetchall()

print("Tables in Postgres public schema:")
for t in tables:
    print(f" - {t[0]}")
    
    # Optional: fetch column count or row count
    cur.execute(f"SELECT COUNT(*) FROM {t[0]}")
    count = cur.fetchone()[0]
    print(f"   (Rows: {count})")
