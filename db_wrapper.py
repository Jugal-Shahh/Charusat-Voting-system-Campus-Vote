import os
import re
import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
DB_PATH = PROJECT_ROOT / "campus_vote.db"

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(dotenv_path=None):
        if dotenv_path is None:
            return
        p = Path(dotenv_path)
        if not p.exists():
            return
        try:
            with open(p, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip("'\""))
        except Exception:
            pass

load_dotenv(PROJECT_ROOT / ".env")

class PostgresCursorWrapper:
    def __init__(self, cursor):
        self.cursor = cursor

    def execute(self, query, params=None):
        # Translate SQLite placeholders to Postgres placeholders
        query = query.replace("?", "%s")
        
        # Handle PRAGMA queries
        if "pragma" in query.lower():
            if "foreign_keys" in query.lower():
                return self
            elif "table_info" in query.lower():
                match = re.search(r'table_info\((\w+)\)', query, re.IGNORECASE)
                if match:
                    table_name = match.group(1)
                    postgres_query = """
                        SELECT 0 as cid, column_name as name, data_type as type, 
                               CASE WHEN is_nullable = 'NO' THEN 1 ELSE 0 END as notnull, 
                               column_default as dflt_value, 0 as pk
                        FROM information_schema.columns 
                        WHERE table_name = %s
                    """
                    self.cursor.execute(postgres_query, (table_name,))
                    return self

        # Handle sqlite_master table queries
        if "sqlite_master" in query.lower():
            query = re.sub(
                r"SELECT\s+COUNT\(\*\)\s+FROM\s+sqlite_master\s+WHERE\s+type='table'\s+AND\s+name=%s",
                "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public' AND table_name = %s",
                query,
                flags=re.IGNORECASE
            )
            query = re.sub(
                r"FROM\s+sqlite_master",
                "FROM information_schema.tables",
                query,
                flags=re.IGNORECASE
            )

        # Handle INSERT OR IGNORE
        if "insert or ignore" in query.lower():
            query = re.sub(r'insert or ignore into', 'insert into', query, flags=re.IGNORECASE)
            if "institute_id_patterns" in query:
                query += " ON CONFLICT (institute_code) DO NOTHING"
            elif "admins" in query:
                if "username" in query:
                    query += " ON CONFLICT (username) DO NOTHING"
                else:
                    query += " ON CONFLICT (google_email) DO NOTHING"
            elif "settings" in query:
                query += " ON CONFLICT (key) DO NOTHING"
            else:
                query += " ON CONFLICT DO NOTHING"

        # Handle INSERT OR REPLACE
        if "insert or replace" in query.lower():
            query = re.sub(r'insert or replace into', 'insert into', query, flags=re.IGNORECASE)
            if "voters" in query:
                query += " ON CONFLICT (voter_id) DO UPDATE SET full_name = EXCLUDED.full_name, institute = EXCLUDED.institute, department = EXCLUDED.department, admission_year = EXCLUDED.admission_year, is_diploma = EXCLUDED.is_diploma"
            else:
                query += " ON CONFLICT DO NOTHING"

        if params is not None:
            if not isinstance(params, (tuple, list)):
                params = (params,)
            self.cursor.execute(query, params)
        else:
            self.cursor.execute(query)
        return self

    def fetchone(self):
        row = self.cursor.fetchone()
        if row is None:
            return None
        return row

    def fetchall(self):
        return self.cursor.fetchall()

    def __iter__(self):
        return iter(self.cursor)

    @property
    def rowcount(self):
        return self.cursor.rowcount


class PostgresConnectionWrapper:
    def __init__(self, conn):
        self.conn = conn

    def cursor(self):
        import psycopg2.extras
        return PostgresCursorWrapper(self.conn.cursor(cursor_factory=psycopg2.extras.DictCursor))

    def execute(self, query, params=None):
        return self.cursor().execute(query, params)

    def executescript(self, script_content):
        with self.conn.cursor() as cur:
            adapted = script_content
            # Replace INTEGER PRIMARY KEY AUTOINCREMENT with SERIAL PRIMARY KEY
            adapted = re.sub(
                r'INTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT',
                'SERIAL PRIMARY KEY',
                adapted,
                flags=re.IGNORECASE
            )
            # Remove sqlite-specific lines like PRAGMA
            lines = []
            for line in adapted.splitlines():
                if line.strip().lower().startswith("pragma"):
                    continue
                lines.append(line)
            adapted = "\n".join(lines)
            
            # Split by semicolon to execute individually
            statements = adapted.split(";")
            for stmt in statements:
                stmt_strip = stmt.strip()
                if not stmt_strip:
                    continue
                if "insert or ignore" in stmt_strip.lower():
                    stmt_strip = re.sub(r'insert or ignore into', 'insert into', stmt_strip, flags=re.IGNORECASE)
                    if "settings" in stmt_strip.lower():
                        stmt_strip += " ON CONFLICT (key) DO NOTHING"
                    elif "institute_id_patterns" in stmt_strip.lower():
                        stmt_strip += " ON CONFLICT (institute_code) DO NOTHING"
                    else:
                        stmt_strip += " ON CONFLICT DO NOTHING"
                
                if "insert or replace" in stmt_strip.lower():
                    stmt_strip = re.sub(r'insert or replace into', 'insert into', stmt_strip, flags=re.IGNORECASE)
                    if "institute_id_patterns" in stmt_strip.lower():
                        stmt_strip += " ON CONFLICT (institute_code) DO UPDATE SET regex_pattern = EXCLUDED.regex_pattern, department_codes = EXCLUDED.department_codes, diploma_marker_position = EXCLUDED.diploma_marker_position"
                    else:
                        stmt_strip += " ON CONFLICT DO NOTHING"

                cur.execute(stmt_strip)
        self.conn.commit()

    def commit(self):
        self.conn.commit()

    def rollback(self):
        self.conn.rollback()

    def close(self):
        self.conn.close()


def get_db_connection(db_path=None):
    db_url = os.environ.get("DATABASE_URL")
    if db_url and "paste-your-real" in db_url:
        db_url = None

    if db_url and (db_url.startswith("postgres://") or db_url.startswith("postgresql://")):
        import psycopg2
        import psycopg2.extras
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql://", 1)
        conn = psycopg2.connect(db_url)
        return PostgresConnectionWrapper(conn)
    else:
        path = db_path if db_path else str(DB_PATH)
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn
