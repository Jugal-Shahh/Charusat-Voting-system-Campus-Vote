"""
test_id_parser.py — Standalone test suite for the ID-parsing engine.

No pytest required — runs with plain `python test_id_parser.py`.
Uses assert statements; failures print the failing case and exit non-zero.

Test coverage:
  - All 8 CSPIT departments (regular + diploma)
  - All 3 DEPSTAR departments (diploma form only, as per the data)
  - Year extraction correctness
  - is_diploma flag correctness
  - Invalid / malformed IDs → matched=False
  - Wrong-institute restriction → matched=False
  - Edge cases: wrong length, mixed case, extra chars, empty string
"""

import json
import re
import sqlite3
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

# ---------------------------------------------------------------------------
# Bootstrap: import id_parser from the project root regardless of cwd
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from id_parser import InstitutePattern, ParseResult, load_patterns, parse_voter_id


# ---------------------------------------------------------------------------
# Lightweight in-memory DB seeded with the same patterns as schema.sql
# ---------------------------------------------------------------------------

def _build_in_memory_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE institute_id_patterns (
            institute_code          TEXT PRIMARY KEY,
            regex_pattern           TEXT NOT NULL,
            department_codes        TEXT NOT NULL,
            diploma_marker_position TEXT NOT NULL
        )
    """)
    conn.executemany(
        "INSERT INTO institute_id_patterns VALUES (?, ?, ?, ?)",
        [
            (
                "CSPIT",
                r"^(D)?(\d{2})(CS|CE|IT|EC|ME|EE|CL|AIML)(\d{3})$",
                '["CS","CE","IT","EC","ME","EE","CL","AIML"]',
                "before_year",
            ),
            (
                "DEPSTAR",
                r"^(D)?(\d{2})(D)(CE|CS|IT)(\d{3})$",
                '["CE","CS","IT"]',
                "after_year",
            ),
        ],
    )
    conn.commit()
    return conn


# ---------------------------------------------------------------------------
# Test runner helpers
# ---------------------------------------------------------------------------

PASS = 0
FAIL = 0
_failures: list[str] = []


def check(desc: str, condition: bool):
    global PASS, FAIL
    if condition:
        PASS += 1
    else:
        FAIL += 1
        _failures.append(f"  FAIL: {desc}")
        print(f"  [FAIL] {desc}")


def expect_match(
    voter_id: str,
    patterns: Dict[str, InstitutePattern],
    *,
    institute: str,
    dept: str,
    year: int,
    is_diploma: int,
    restrict: Optional[str] = None,
):
    r = parse_voter_id(voter_id, patterns, restrict)
    prefix = f"{voter_id!r:20s}"
    check(f"{prefix} → matched",                r.matched)
    check(f"{prefix} → institute={institute}",   r.institute == institute)
    check(f"{prefix} → department={dept}",       r.department == dept)
    check(f"{prefix} → admission_year={year}",   r.admission_year == year)
    check(f"{prefix} → is_diploma={is_diploma}", r.is_diploma == is_diploma)


def expect_no_match(
    voter_id: str,
    patterns: Dict[str, InstitutePattern],
    *,
    restrict: Optional[str] = None,
    desc: str = "",
):
    r = parse_voter_id(voter_id, patterns, restrict)
    label = desc or voter_id
    check(f"{label!r:30s} → matched=False", not r.matched)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def run_tests():
    db = _build_in_memory_db()
    patterns = load_patterns(db)

    print("\n" + "=" * 60)
    print("  ID Parser — Test Suite")
    print("=" * 60)

    # -----------------------------------------------------------------------
    print("\n[1] CSPIT regular IDs — all 8 departments")
    # -----------------------------------------------------------------------
    expect_match("24AIML065", patterns, institute="CSPIT", dept="AIML", year=24, is_diploma=0)
    expect_match("25CS001",   patterns, institute="CSPIT", dept="CS",   year=25, is_diploma=0)
    expect_match("24CE010",   patterns, institute="CSPIT", dept="CE",   year=24, is_diploma=0)
    expect_match("23IT099",   patterns, institute="CSPIT", dept="IT",   year=23, is_diploma=0)
    expect_match("22EC050",   patterns, institute="CSPIT", dept="EC",   year=22, is_diploma=0)
    expect_match("24ME003",   patterns, institute="CSPIT", dept="ME",   year=24, is_diploma=0)
    expect_match("25EE100",   patterns, institute="CSPIT", dept="EE",   year=25, is_diploma=0)
    expect_match("24CL007",   patterns, institute="CSPIT", dept="CL",   year=24, is_diploma=0)

    # -----------------------------------------------------------------------
    print("\n[2] CSPIT diploma IDs — D prefix before year")
    # -----------------------------------------------------------------------
    expect_match("D25AIML001", patterns, institute="CSPIT", dept="AIML", year=25, is_diploma=1)
    expect_match("D23CE010",   patterns, institute="CSPIT", dept="CE",   year=23, is_diploma=1)
    expect_match("D24CS005",   patterns, institute="CSPIT", dept="CS",   year=24, is_diploma=1)
    expect_match("D22EE200",   patterns, institute="CSPIT", dept="EE",   year=22, is_diploma=1)

    # -----------------------------------------------------------------------
    print("\n[3] DEPSTAR IDs — plain and diploma forms")
    # -----------------------------------------------------------------------
    expect_match("24DCE001", patterns, institute="DEPSTAR", dept="CE",  year=24, is_diploma=0)
    expect_match("25DCS010", patterns, institute="DEPSTAR", dept="CS",  year=25, is_diploma=0)
    expect_match("23DIT099", patterns, institute="DEPSTAR", dept="IT",  year=23, is_diploma=0)
    expect_match("22DCE200", patterns, institute="DEPSTAR", dept="CE",  year=22, is_diploma=0)
    expect_match("D25DCE153", patterns, institute="DEPSTAR", dept="CE", year=25, is_diploma=1)
    expect_match("D25DCS101", patterns, institute="DEPSTAR", dept="CS", year=25, is_diploma=1)

    # -----------------------------------------------------------------------
    print("\n[4] Restrict-to-institute enforcement")
    # -----------------------------------------------------------------------
    # A valid DEPSTAR ID, but restricted to CSPIT → must not match
    expect_no_match("24DCE001", patterns, restrict="CSPIT",
                    desc="24DCE001 restricted to CSPIT")
    # A valid CSPIT ID, but restricted to DEPSTAR → must not match
    expect_no_match("24AIML065", patterns, restrict="DEPSTAR",
                    desc="24AIML065 restricted to DEPSTAR")
    # Restrict + correct institute → must match normally
    expect_match("24AIML065", patterns, institute="CSPIT", dept="AIML", year=24,
                 is_diploma=0, restrict="CSPIT")
    expect_match("24DCE001",  patterns, institute="DEPSTAR", dept="CE",  year=24,
                 is_diploma=0, restrict="DEPSTAR")

    # -----------------------------------------------------------------------
    print("\n[5] Invalid / malformed IDs — all must return matched=False")
    # -----------------------------------------------------------------------
    bad_ids = [
        ("",               "empty string"),
        ("   ",            "whitespace only"),
        ("AIML24001",      "wrong order: dept before year"),
        ("24AIML",         "missing roll number"),
        ("24AIML0650",     "roll number too long (4 digits)"),
        ("24XY065",        "unknown department code XY"),
        ("24aiml065",      "lowercase dept code"),
        ("DD24AIML065",    "double D prefix"),
        ("2AIML065",       "single-digit year"),
        ("24 AIML065",     "space in middle"),
        ("25DCE",          "DEPSTAR missing roll number"),
        ("24CE0",          "roll number too short"),
        ("25MTECH001",     "dept code not in any institute"),
    ]
    for vid, desc in bad_ids:
        expect_no_match(vid, patterns, desc=f"Invalid: {desc}")

    # -----------------------------------------------------------------------
    print("\n[6] Year boundary values")
    # -----------------------------------------------------------------------
    expect_match("20AIML001", patterns, institute="CSPIT", dept="AIML", year=20, is_diploma=0)
    expect_match("99CE999",   patterns, institute="CSPIT", dept="CE",   year=99, is_diploma=0)
    expect_match("00CS001",   patterns, institute="CSPIT", dept="CS",   year=0,  is_diploma=0)

    # -----------------------------------------------------------------------
    print("\n[7] load_patterns returns both institutes")
    # -----------------------------------------------------------------------
    check("patterns has CSPIT",   "CSPIT"   in patterns)
    check("patterns has DEPSTAR", "DEPSTAR" in patterns)
    check("patterns has 2 keys",  len(patterns) == 2)
    check("CSPIT has 8 depts",    len(patterns["CSPIT"].department_codes) == 8)
    check("DEPSTAR has 3 depts",  len(patterns["DEPSTAR"].department_codes) == 3)
    check("CSPIT diploma = before_year",  patterns["CSPIT"].diploma_marker_position  == "before_year")
    check("DEPSTAR diploma = after_year", patterns["DEPSTAR"].diploma_marker_position == "after_year")

    # -----------------------------------------------------------------------
    # Summary
    # -----------------------------------------------------------------------
    print("\n" + "=" * 60)
    total = PASS + FAIL
    print(f"  Results: {PASS}/{total} passed,  {FAIL} failed")
    print("=" * 60)

    if _failures:
        print("\nFailed assertions:")
        for f in _failures:
            print(f)
        print()
        sys.exit(1)
    else:
        print("\n  [PASS] All tests passed!\n")
        sys.exit(0)


if __name__ == "__main__":
    run_tests()
