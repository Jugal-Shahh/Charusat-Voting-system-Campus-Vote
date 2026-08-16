"""
import_voters.py — Import a voter roll into campus_vote.db.

Usage
-----
  # Import with explicit institute (recommended — flags IDs that don't match)
  python import_voters.py --institute CSPIT voters.txt
  python import_voters.py --institute DEPSTAR voters_depstar.txt

  # Auto-detect institute per row (tries all loaded patterns, first match wins)
  python import_voters.py voters.txt

Input format
------------
  One voter per line, tab-separated:
      <voter_id><TAB><Full Name>

  Example:
      24AIML065<TAB>SHAH JUGAL RAJESHBHAI
      D25AIML001<TAB>PRAJAPATI PRUTHAVI NILESHKUMAR

Behaviour
---------
  - Voter IDs that DO match the expected pattern: stored with all
    structured columns (institute, department, admission_year, is_diploma).
  - Voter IDs that DON'T match: flagged in the import report and SKIPPED —
    never silently dropped into the table with NULL structured fields,
    and never silently accepted as if they were valid.
  - Re-running mid-election is safe: existing has_voted / voted_at are
    left untouched; only full_name and structured fields are refreshed.

Security note: this script must only be run by an authorised admin on
the server; it does no Flask/web auth of its own.
"""

import argparse
import os
import sqlite3
import sys
from pathlib import Path

# Allow running from any directory by inserting the project root onto sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from id_parser import load_patterns, parse_voter_id
from db_wrapper import get_db_connection

DB_PATH = PROJECT_ROOT / "campus_vote.db"


# ---------------------------------------------------------------------------
# Migration helper: add new columns to voters if they don't exist yet.
# SQLite doesn't support "ADD COLUMN IF NOT EXISTS", so we check manually.
# ---------------------------------------------------------------------------
def _ensure_voter_columns(conn) -> None:
    """Add new structured columns to voters if missing (safe to call repeatedly)."""
    existing = {row[1] for row in conn.execute("PRAGMA table_info(voters)")}
    new_cols = {
        "institute":      "TEXT",
        "department":     "TEXT",
        "admission_year": "INTEGER",
        "is_diploma":     "INTEGER NOT NULL DEFAULT 0",
    }
    for col, typedef in new_cols.items():
        if col not in existing:
            conn.execute(f"ALTER TABLE voters ADD COLUMN {col} {typedef}")
    conn.commit()


def _ensure_patterns_table(conn) -> None:
    """Create institute_id_patterns and seed it if the table doesn't exist yet."""
    schema_path = PROJECT_ROOT / "schema.sql"
    if not schema_path.exists():
        print("WARNING: schema.sql not found; skipping pattern table creation.")
        return
    # Re-running the schema is safe — it uses CREATE TABLE IF NOT EXISTS
    # and INSERT OR IGNORE, so existing data is never overwritten.
    conn.executescript(schema_path.read_text(encoding="utf-8"))
    conn.commit()


# ---------------------------------------------------------------------------
# Core import logic
# ---------------------------------------------------------------------------

def import_voters(
    file_path: str,
    restrict_to_institute: str | None,
    db_path: str = str(DB_PATH),
) -> dict:
    """
    Read a voter-roll file and upsert into the voters table.

    Returns a summary dict:
        {added, updated, flagged, skipped_blank, skipped_format}
    """
    conn = get_db_connection(db_path)

    # Ensure schema is up-to-date
    _ensure_patterns_table(conn)
    _ensure_voter_columns(conn)

    # Load ID patterns from DB
    patterns = load_patterns(conn)
    if not patterns:
        print("ERROR: No institute ID patterns found in the database.")
        print("       Run  python init_db.py  first to seed the patterns.")
        conn.close()
        sys.exit(1)

    if restrict_to_institute and restrict_to_institute not in patterns:
        known = ", ".join(sorted(patterns.keys()))
        print(f"ERROR: Unknown institute '{restrict_to_institute}'.")
        print(f"       Known institutes: {known}")
        conn.close()
        sys.exit(1)

    added = updated = flagged = skipped_blank = skipped_format = 0
    flagged_ids: list[tuple[int, str, str]] = []   # (line_num, voter_id, reason)

    cur = conn.cursor()

    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        for line_num, raw_line in enumerate(f, start=1):
            line = raw_line.strip("\r\n")

            if not line.strip():
                skipped_blank += 1
                continue

            parts = line.split("\t", 1)
            if len(parts) != 2:
                print(f"  [line {line_num}] FORMAT ERROR (no tab separator): {line!r}")
                skipped_format += 1
                continue

            voter_id = parts[0].strip()
            full_name = parts[1].strip()

            if not voter_id or not full_name:
                skipped_blank += 1
                continue

            # --- Parse the voter ID ---
            result = parse_voter_id(voter_id, patterns, restrict_to_institute)

            if not result.matched:
                reason = (
                    f"does not match pattern for {restrict_to_institute}"
                    if restrict_to_institute
                    else "does not match any known institute pattern"
                )
                flagged_ids.append((line_num, voter_id, reason))
                flagged += 1
                continue

            # --- Upsert into voters table ---
            existing = cur.execute(
                "SELECT 1 FROM voters WHERE voter_id = ?", (voter_id,)
            ).fetchone()

            if existing:
                cur.execute(
                    """UPDATE voters
                       SET full_name = ?,
                           institute = ?,
                           department = ?,
                           admission_year = ?,
                           is_diploma = ?
                       WHERE voter_id = ?""",
                    (
                        full_name,
                        result.institute,
                        result.department,
                        result.admission_year,
                        result.is_diploma,
                        voter_id,
                    ),
                )
                updated += 1
            else:
                cur.execute(
                    """INSERT INTO voters
                           (voter_id, full_name, institute, department,
                            admission_year, is_diploma)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        voter_id,
                        full_name,
                        result.institute,
                        result.department,
                        result.admission_year,
                        result.is_diploma,
                    ),
                )
                added += 1

    conn.commit()
    conn.close()

    return {
        "added":          added,
        "updated":        updated,
        "flagged":        flagged,
        "skipped_blank":  skipped_blank,
        "skipped_format": skipped_format,
        "flagged_ids":    flagged_ids,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Import voter roll into campus_vote.db",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "voters_file",
        help="Path to the tab-separated voter roll file (voter_id<TAB>Full Name)",
    )
    parser.add_argument(
        "--institute",
        metavar="CODE",
        default=None,
        help=(
            "Restrict import to a specific institute (e.g. CSPIT, DEPSTAR). "
            "IDs that don't match that institute's pattern are flagged, not imported. "
            "If omitted, auto-detection tries all loaded patterns."
        ),
    )
    parser.add_argument(
        "--db",
        default=str(DB_PATH),
        help=f"Path to local SQLite database (only used when DATABASE_URL is not set). Default: {DB_PATH}",
    )
    args = parser.parse_args()

    file_path = args.voters_file
    institute = args.institute.upper() if args.institute else None

    # Show which database will actually be used
    db_url = os.environ.get("DATABASE_URL", "")
    
    if db_url:
        print(f"  [info] DATABASE_URL found in environment (length: {len(db_url)})")
    else:
        print("  [info] DATABASE_URL not found or empty in environment")

    if db_url and (db_url.startswith("postgres://") or db_url.startswith("postgresql://")) and "paste-your-real" not in db_url:
        db_label = "PostgreSQL (via DATABASE_URL)"
    else:
        db_label = f"SQLite ({Path(args.db).name})"

    print(f"\n{'='*60}")
    print(f"  CharusatVote — Voter Import")
    print(f"  File     : {file_path}")
    print(f"  Institute: {institute or '(auto-detect)'}")
    print(f"  Database : {db_label}")
    print(f"{'='*60}\n")

    summary = import_voters(file_path, institute, db_path=args.db)

    print(f"\n{'='*60}")
    print(f"  IMPORT COMPLETE")
    print(f"{'='*60}")
    print(f"  Added          : {summary['added']}")
    print(f"  Updated        : {summary['updated']}")
    print(f"  Flagged (bad)  : {summary['flagged']}")
    print(f"  Skipped blank  : {summary['skipped_blank']}")
    print(f"  Skipped format : {summary['skipped_format']}")
    print(f"{'='*60}")

    if summary["flagged_ids"]:
        print(f"\n  [WARNING] FLAGGED IDs (not imported -- pattern mismatch):")
        for line_num, vid, reason in summary["flagged_ids"]:
            print(f"    [line {line_num}] {vid!r:20s}  -- {reason}")
    else:
        print("\n  [OK] All IDs matched their expected pattern.")

    print()


if __name__ == "__main__":
    main()
