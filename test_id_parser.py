"""
test_id_parser.py — Standalone test suite for the ID-parsing engine.

No pytest required — runs with plain `python test_id_parser.py`.
Uses assert statements; failures print the failing case and exit non-zero.

Test coverage:
  - All 8 CHARUSAT institutes with patterns (24 departments)
  - All 8 CSPIT departments (regular + diploma)
  - All 3 DEPSTAR departments (regular + diploma, DCS/DCE/DIT)
  - Other 6 institutes: IIIM, RPCP, PDPIAS, CMPICA, BDIAS, ARIP
  - Non-diploma rejection (e.g. d24bba001 -> matched=False)
  - Case-insensitivity (uppercase & lowercase IDs)
  - Year extraction correctness
  - is_diploma flag correctness
  - Invalid / malformed IDs → matched=False
  - Wrong-institute restriction → matched=False
  - Edge cases: wrong length, extra chars, empty string
"""

import sqlite3
import sys
from pathlib import Path
from typing import Dict, List, Optional

# ---------------------------------------------------------------------------
# Bootstrap: import id_parser from the project root regardless of cwd
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from id_parser import DepartmentPattern, ParseResult, load_patterns, parse_voter_id


# ---------------------------------------------------------------------------
# Lightweight in-memory DB seeded with the 24 department rows from schema.sql
# ---------------------------------------------------------------------------

def _build_in_memory_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE institute_id_patterns (
            institute_code      TEXT NOT NULL,
            department_code     TEXT NOT NULL,
            department_name     TEXT NOT NULL,
            has_numeric_suffix  INTEGER NOT NULL DEFAULT 1,
            diploma_allowed     INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (institute_code, department_code)
        )
    """)
    conn.executemany(
        "INSERT INTO institute_id_patterns VALUES (?, ?, ?, ?, ?)",
        [
            ("IIIM",    "BBA",  "BBA",                    1, 0),
            ("IIIM",    "MBA",  "MBA",                    1, 0),
            ("RPCP",    "BPH",  "B.Pharm",                1, 0),
            ("RPCP",    "MPH",  "M.Pharm",                1, 0),
            ("PDPIAS",  "BSC",  "B.Sc",                   1, 0),
            ("CSPIT",   "CS",   "Computer Science",       1, 1),
            ("CSPIT",   "CE",   "Computer Engineering",   1, 1),
            ("CSPIT",   "IT",   "Information Technology", 1, 1),
            ("CSPIT",   "AIML", "AI & ML",                1, 1),
            ("CSPIT",   "CL",   "Civil Engineering",      1, 1),
            ("CSPIT",   "EC",   "Electronics & Comm.",     1, 1),
            ("CSPIT",   "ME",   "Mechanical Engineering", 1, 1),
            ("CSPIT",   "EE",   "Electrical Engineering", 1, 1),
            ("DEPSTAR", "DCS",  "DEPSTAR CS",             1, 1),
            ("DEPSTAR", "DCE",  "DEPSTAR CE",             1, 1),
            ("DEPSTAR", "DIT",  "DEPSTAR IT",             1, 1),
            ("CMPICA",  "BCA",  "BCA",                    1, 0),
            ("CMPICA",  "MCA",  "MCA",                    1, 0),
            ("CMPICA",  "BSIT", "B.Sc IT",                1, 0),
            ("CMPICA",  "MSIT", "M.Sc IT",                1, 0),
            ("BDIAS",   "BSMT", "BSMT",                   1, 0),
            ("BDIAS",   "BMIT", "BMIT",                   1, 0),
            ("ARIP",    "BPT",  "BPT (Bachelors)",        1, 0),
            ("ARIP",    "MPT",  "MPT (Masters)",          1, 0),
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
    patterns: Dict[str, List[DepartmentPattern]],
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
    patterns: Dict[str, List[DepartmentPattern]],
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
    print("  ID Parser — Test Suite (Data-Driven Per Department)")
    print("=" * 60)

    # -----------------------------------------------------------------------
    print("\n[1] CSPIT regular IDs — all 8 departments (upper & lowercase)")
    # -----------------------------------------------------------------------
    expect_match("24AIML065", patterns, institute="CSPIT", dept="AIML", year=24, is_diploma=0)
    expect_match("25CS001",   patterns, institute="CSPIT", dept="CS",   year=25, is_diploma=0)
    expect_match("24CE010",   patterns, institute="CSPIT", dept="CE",   year=24, is_diploma=0)
    expect_match("23IT099",   patterns, institute="CSPIT", dept="IT",   year=23, is_diploma=0)
    expect_match("22EC050",   patterns, institute="CSPIT", dept="EC",   year=22, is_diploma=0)
    expect_match("24ME003",   patterns, institute="CSPIT", dept="ME",   year=24, is_diploma=0)
    expect_match("25EE100",   patterns, institute="CSPIT", dept="EE",   year=25, is_diploma=0)
    expect_match("24CL007",   patterns, institute="CSPIT", dept="CL",   year=24, is_diploma=0)
    expect_match("24aiml065", patterns, institute="CSPIT", dept="AIML", year=24, is_diploma=0)

    # -----------------------------------------------------------------------
    print("\n[2] CSPIT diploma IDs — D prefix before year (upper & lowercase)")
    # -----------------------------------------------------------------------
    expect_match("D25AIML001", patterns, institute="CSPIT", dept="AIML", year=25, is_diploma=1)
    expect_match("d24aiml001", patterns, institute="CSPIT", dept="AIML", year=24, is_diploma=1)
    expect_match("D23CE010",   patterns, institute="CSPIT", dept="CE",   year=23, is_diploma=1)
    expect_match("D24CS005",   patterns, institute="CSPIT", dept="CS",   year=24, is_diploma=1)
    expect_match("D22EE200",   patterns, institute="CSPIT", dept="EE",   year=22, is_diploma=1)

    # -----------------------------------------------------------------------
    print("\n[3] DEPSTAR IDs — plain and diploma forms (DCS/DCE/DIT)")
    # -----------------------------------------------------------------------
    expect_match("24DCE001",  patterns, institute="DEPSTAR", dept="DCE", year=24, is_diploma=0)
    expect_match("24dce001",  patterns, institute="DEPSTAR", dept="DCE", year=24, is_diploma=0)
    expect_match("25DCS010",  patterns, institute="DEPSTAR", dept="DCS", year=25, is_diploma=0)
    expect_match("23DIT099",  patterns, institute="DEPSTAR", dept="DIT", year=23, is_diploma=0)
    expect_match("D25DCE153", patterns, institute="DEPSTAR", dept="DCE", year=25, is_diploma=1)
    expect_match("d24dce001", patterns, institute="DEPSTAR", dept="DCE", year=24, is_diploma=1)
    expect_match("D25DCS101", patterns, institute="DEPSTAR", dept="DCS", year=25, is_diploma=1)
    expect_match("D24DIT085", patterns, institute="DEPSTAR", dept="DIT", year=24, is_diploma=1)

    # -----------------------------------------------------------------------
    print("\n[4] Other Institutes — IIIM, RPCP, PDPIAS, CMPICA, BDIAS, ARIP")
    # -----------------------------------------------------------------------
    # IIIM (BBA, MBA)
    expect_match("24bba001", patterns, institute="IIIM", dept="BBA", year=24, is_diploma=0)
    expect_match("24BBA001", patterns, institute="IIIM", dept="BBA", year=24, is_diploma=0)
    expect_match("24mba002", patterns, institute="IIIM", dept="MBA", year=24, is_diploma=0)

    # RPCP (B.Pharm, M.Pharm)
    expect_match("24bph045", patterns, institute="RPCP", dept="BPH", year=24, is_diploma=0)
    expect_match("24mph010", patterns, institute="RPCP", dept="MPH", year=24, is_diploma=0)

    # PDPIAS (B.Sc)
    expect_match("24bsc001", patterns, institute="PDPIAS", dept="BSC", year=24, is_diploma=0)

    # CMPICA (BCA, MCA, B.Sc IT, M.Sc IT)
    expect_match("24bca001",  patterns, institute="CMPICA", dept="BCA",  year=24, is_diploma=0)
    expect_match("24mca002",  patterns, institute="CMPICA", dept="MCA",  year=24, is_diploma=0)
    expect_match("24bsit003", patterns, institute="CMPICA", dept="BSIT", year=24, is_diploma=0)
    expect_match("24msit004", patterns, institute="CMPICA", dept="MSIT", year=24, is_diploma=0)

    # BDIAS (BSMT, BMIT)
    expect_match("24bsmt001", patterns, institute="BDIAS", dept="BSMT", year=24, is_diploma=0)
    expect_match("24bmit002", patterns, institute="BDIAS", dept="BMIT", year=24, is_diploma=0)

    # ARIP (BPT, MPT)
    expect_match("24bpt001", patterns, institute="ARIP", dept="BPT", year=24, is_diploma=0)
    expect_match("24mpt002", patterns, institute="ARIP", dept="MPT", year=24, is_diploma=0)

    # -----------------------------------------------------------------------
    print("\n[5] Diploma disallowed for non-diploma institutes")
    # -----------------------------------------------------------------------
    expect_no_match("d24bba001",  patterns, desc="IIIM diploma not allowed")
    expect_no_match("d24bph045",  patterns, desc="RPCP diploma not allowed")
    expect_no_match("d24bsc001",  patterns, desc="PDPIAS diploma not allowed")
    expect_no_match("d24bca001",  patterns, desc="CMPICA diploma not allowed")
    expect_no_match("d24bsmt001", patterns, desc="BDIAS diploma not allowed")
    expect_no_match("d24bpt001",  patterns, desc="ARIP diploma not allowed")

    # -----------------------------------------------------------------------
    print("\n[6] Restrict-to-institute enforcement")
    # -----------------------------------------------------------------------
    # A valid DEPSTAR ID, but restricted to CSPIT → must not match
    expect_no_match("24DCE001", patterns, restrict="CSPIT",
                    desc="24DCE001 restricted to CSPIT")
    # A valid CSPIT ID, but restricted to DEPSTAR → must not match
    expect_no_match("24AIML065", patterns, restrict="DEPSTAR",
                    desc="24AIML065 restricted to DEPSTAR")
    # A valid IIIM ID, but restricted to CSPIT → must not match
    expect_no_match("24bba001", patterns, restrict="CSPIT",
                    desc="24bba001 restricted to CSPIT")
    # Restrict + correct institute → must match normally
    expect_match("24AIML065", patterns, institute="CSPIT", dept="AIML", year=24,
                 is_diploma=0, restrict="CSPIT")
    expect_match("24DCE001",  patterns, institute="DEPSTAR", dept="DCE", year=24,
                 is_diploma=0, restrict="DEPSTAR")
    expect_match("24bba001",  patterns, institute="IIIM", dept="BBA", year=24,
                 is_diploma=0, restrict="IIIM")

    # -----------------------------------------------------------------------
    print("\n[7] Invalid / malformed IDs — all must return matched=False")
    # -----------------------------------------------------------------------
    bad_ids = [
        ("",               "empty string"),
        ("   ",            "whitespace only"),
        ("AIML24001",      "wrong order: dept before year"),
        ("24AIML",         "missing roll number"),
        ("24AIML0650",     "roll number too long (4 digits)"),
        ("24XY065",        "unknown department code XY"),
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
    print("\n[8] Year boundary values")
    # -----------------------------------------------------------------------
    expect_match("20AIML001", patterns, institute="CSPIT", dept="AIML", year=20, is_diploma=0)
    expect_match("99CE999",   patterns, institute="CSPIT", dept="CE",   year=99, is_diploma=0)
    expect_match("00CS001",   patterns, institute="CSPIT", dept="CS",   year=0,  is_diploma=0)

    # -----------------------------------------------------------------------
    print("\n[9] Pattern registry validation")
    # -----------------------------------------------------------------------
    expected_institutes = ["IIIM", "RPCP", "PDPIAS", "CSPIT", "DEPSTAR", "CMPICA", "BDIAS", "ARIP"]
    for inst in expected_institutes:
        check(f"patterns has {inst}", inst in patterns)
    check("patterns has 8 institutes", len(patterns) == 8)
    check("CSPIT has 8 depts", len(patterns["CSPIT"]) == 8)
    check("DEPSTAR has 3 depts", len(patterns["DEPSTAR"]) == 3)
    total_depts = sum(len(depts) for depts in patterns.values())
    check("Total departments == 24", total_depts == 24)

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
