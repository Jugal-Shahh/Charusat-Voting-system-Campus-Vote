"""
init_db.py -- Initialise (or migrate) the campus_vote.db database.

Safe to run multiple times:
  - Uses CREATE TABLE IF NOT EXISTS for all tables.
  - Uses INSERT OR IGNORE for seed data.
  - Checks PRAGMA table_info before ALTER TABLE.

Phase 2+3 migration: if the old single-election schema is detected,
this script will:
  1. Back up the old DB
  2. Drop old tables that have structurally changed (candidates, votes,
     turnout_log, admins) and recreate them with the new schema
  3. Preserve the voters table and its data
  4. Create new tables (voting_systems)

Usage:
    python init_db.py
"""
import os
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from werkzeug.security import generate_password_hash
from db_wrapper import get_db_connection

PROJECT_ROOT = Path(__file__).resolve().parent
DB_PATH = PROJECT_ROOT / "campus_vote.db"
SCHEMA_PATH = PROJECT_ROOT / "schema.sql"


def _table_has_column(conn, table, column):
    """Check if a column exists in a table."""
    cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    return column in cols


def _table_exists(conn, table):
    """Check if a table exists."""
    row = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row[0] > 0


def _backup_db():
    """Create a timestamped backup of the existing database."""
    db_url = os.environ.get("DATABASE_URL")
    if db_url and ("postgres://" in db_url or "postgresql://" in db_url) and "paste-your-real" not in db_url:
        print("  [info] Remote Postgres database detected; skipping local file backup.")
        return None
    if DB_PATH.exists():
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = DB_PATH.with_name(f"campus_vote_backup_{ts}.db")
        shutil.copy2(DB_PATH, backup)
        print(f"  [ok] Backed up existing DB to {backup.name}")
        return backup
    return None


def _needs_migration(conn):
    """
    Detect if the old single-election schema is in place.
    Old schema: candidates table has no voting_system_id column.
    """
    if not _table_exists(conn, "candidates"):
        return False  # Fresh install, no migration needed
    return not _table_has_column(conn, "candidates", "voting_system_id")


def _migrate_to_multi_tenant(conn):
    """
    Migrate from single-election schema to multi-tenant.
    Drops and recreates tables that have structurally changed.
    Preserves voters table.
    """
    print("  [!!] Old single-election schema detected. Migrating to multi-tenant...")

    # Drop old tables that will be recreated with new structure
    # NOTE: This loses existing candidates, votes, turnout_log, and admin data.
    # The backup (created before this runs) preserves everything.
    old_tables = ["votes", "turnout_log", "candidates", "admins"]
    for table in old_tables:
        if _table_exists(conn, table):
            conn.execute(f"DROP TABLE {table}")
            print(f"  [ok] Dropped old {table} table (backed up)")

    conn.commit()


def _ensure_voter_columns(conn):
    """Add Phase 1 structured columns to voters if missing."""
    existing = {row[1] for row in conn.execute("PRAGMA table_info(voters)")}
    new_cols = [
        ("institute",      "TEXT"),
        ("department",     "TEXT"),
        ("admission_year", "INTEGER"),
        ("is_diploma",     "INTEGER NOT NULL DEFAULT 0"),
    ]
    migrated = []
    for col, typedef in new_cols:
        if col not in existing:
            conn.execute(f"ALTER TABLE voters ADD COLUMN {col} {typedef}")
            migrated.append(col)
    if migrated:
        conn.commit()
        print(f"  [ok] Added columns to voters: {', '.join(migrated)}")
    else:
        print("  [ok] Voters columns already up-to-date.")


def _apply_schema(conn):
    """Run schema.sql to create all tables."""
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.commit()
    print("  [ok] Schema applied (all tables created).")


def _seed_default_admin(conn):
    """Create a default admin account if none exist."""
    count = conn.execute("SELECT COUNT(*) FROM admins").fetchone()[0]
    if count == 0:
        conn.execute(
            "INSERT INTO admins (username, password_hash, role) VALUES (?, ?, ?)",
            ("admin", generate_password_hash("ChangeMe123!"), "admin"),
        )
        conn.commit()
        print("  [ok] Created default admin -> username: admin | password: ChangeMe123!")
        print("       IMPORTANT: change this password before any real election.")


def main():
    print(f"\n{'='*55}")
    print(f"  CharusatVote -- Database Init / Migration")
    print(f"{'='*55}\n")

    # Back up existing DB before any changes
    _backup_db()

    conn = get_db_connection()

    try:
        # Check if migration from old schema is needed
        if _needs_migration(conn):
            _migrate_to_multi_tenant(conn)

        # Apply the new schema (CREATE IF NOT EXISTS is safe)
        _apply_schema(conn)

        # Ensure voter columns from Phase 1
        _ensure_voter_columns(conn)

        # Seed default admin
        _seed_default_admin(conn)

    finally:
        conn.close()

    print(f"\n  Database ready at {DB_PATH.name}\n")


if __name__ == "__main__":
    main()
