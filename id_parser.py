"""
id_parser.py — CharusatVote ID-parsing engine (Phase 1).

Architecture: parse-on-import, not parse-on-demand.
  - Pattern definitions live in the `institute_id_patterns` DB table.
  - This module reads those definitions and applies them to raw voter IDs.
  - Eligibility checks downstream are plain SQL WHERE clauses on the
    pre-parsed columns (institute, department, admission_year, is_diploma).

Public API
----------
load_patterns(db_conn)  →  dict[str, InstitutePattern]
parse_voter_id(voter_id, patterns)  →  ParseResult

Both functions have zero Flask dependency and are safe to call from
import scripts, tests, or any future CLI/API layer.
"""

import json
import re
from dataclasses import dataclass, field
from typing import Dict, Optional


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class InstitutePattern:
    """One row from institute_id_patterns, ready for regex matching."""
    institute_code: str
    regex_pattern: str
    department_codes: list          # parsed from JSON
    diploma_marker_position: str   # 'before_year' | 'after_year' | 'none'
    _compiled: re.Pattern = field(default=None, init=False, repr=False)

    def __post_init__(self):
        self._compiled = re.compile(self.regex_pattern)

    def match(self, voter_id: str) -> Optional[re.Match]:
        return self._compiled.match(voter_id)


@dataclass
class ParseResult:
    """
    Result of attempting to parse a single voter ID.

    If `matched` is False, all other fields are None/0 and the ID
    should be flagged in the import report — not silently dropped
    or silently included.
    """
    matched: bool
    institute: Optional[str] = None
    department: Optional[str] = None
    admission_year: Optional[int] = None
    is_diploma: int = 0

    def as_dict(self) -> dict:
        return {
            "matched":        self.matched,
            "institute":      self.institute,
            "department":     self.department,
            "admission_year": self.admission_year,
            "is_diploma":     self.is_diploma,
        }


# ---------------------------------------------------------------------------
# Pattern loader
# ---------------------------------------------------------------------------

def load_patterns(db_conn) -> Dict[str, InstitutePattern]:
    """
    Load all rows from institute_id_patterns and return a dict keyed by
    institute_code (e.g. {'CSPIT': InstitutePattern(...), ...}).

    Accepts any sqlite3.Connection (or object with an .execute method).
    """
    rows = db_conn.execute(
        "SELECT institute_code, regex_pattern, department_codes, "
        "       diploma_marker_position "
        "FROM   institute_id_patterns"
    ).fetchall()

    patterns: Dict[str, InstitutePattern] = {}
    for row in rows:
        # row may be sqlite3.Row (subscript by name) or plain tuple
        if hasattr(row, "keys"):
            code = row["institute_code"]
            regex = row["regex_pattern"]
            depts = json.loads(row["department_codes"])
            dmp = row["diploma_marker_position"]
        else:
            code, regex, depts_json, dmp = row
            depts = json.loads(depts_json)

        patterns[code] = InstitutePattern(
            institute_code=code,
            regex_pattern=regex,
            department_codes=depts,
            diploma_marker_position=dmp,
        )

    return patterns


# ---------------------------------------------------------------------------
# Core parser
# ---------------------------------------------------------------------------

def parse_voter_id(
    voter_id: str,
    patterns: Dict[str, InstitutePattern],
    restrict_to_institute: Optional[str] = None,
) -> ParseResult:
    """
    Try to parse `voter_id` against the loaded institute patterns.

    Parameters
    ----------
    voter_id : str
        Raw voter ID string, e.g. '24AIML065' or 'D25AIML001'.
    patterns : dict
        Dict returned by load_patterns().
    restrict_to_institute : str | None
        If provided, ONLY the pattern for that institute is tried.
        Non-matching IDs are flagged (matched=False) even if they
        would match a different institute's pattern.

    Returns
    -------
    ParseResult
        .matched=True with structured fields, or .matched=False if
        the ID doesn't fit the (restricted) pattern set.
    """
    voter_id = voter_id.strip()

    candidates = (
        {restrict_to_institute: patterns[restrict_to_institute]}
        if restrict_to_institute and restrict_to_institute in patterns
        else patterns
    )

    for institute_code, pattern in candidates.items():
        m = pattern.match(voter_id)
        if m is None:
            continue

        # Extract structured fields based on diploma_marker_position.
        # The regex groups differ between institutes — this is intentional
        # per spec §3.1: "implement it as a distinct per-institute pattern".
        dmp = pattern.diploma_marker_position

        if dmp == "before_year":
            # CSPIT: ^(D)?(\d{2})(CS|CE|IT|EC|ME|EE|CL|AIML)(\d{3})$
            #  group 1 = optional 'D'
            #  group 2 = 2-digit year
            #  group 3 = department code
            #  group 4 = roll number (ignored for parsed fields)
            is_diploma = 1 if m.group(1) == "D" else 0
            year = int(m.group(2))
            dept = m.group(3)

        elif dmp == "after_year":
            # DEPSTAR: ^(D)?(\d{2})(D)(CE|CS|IT)(\d{3})$
            #  group 1 = optional leading 'D' (diploma marker)
            #  group 2 = 2-digit year
            #  group 3 = 'D' (DEPSTAR prefix)
            #  group 4 = department code
            #  group 5 = roll number
            year = int(m.group(2))
            is_diploma = 1 if m.group(1) == "D" else 0
            dept = m.group(4)

        else:
            # 'none' — no diploma variant; simple year + dept extraction
            # Pattern expected: ^(\d{2})(DEPT)(\d{3})$ — generic fallback
            year = int(m.group(1))
            is_diploma = 0
            dept = m.group(2)

        # Validate extracted department against the pattern's declared list
        # (the regex already enforces this, but we double-check for safety)
        if dept not in pattern.department_codes:
            return ParseResult(matched=False)

        return ParseResult(
            matched=True,
            institute=institute_code,
            department=dept,
            admission_year=year,
            is_diploma=is_diploma,
        )

    return ParseResult(matched=False)


# ---------------------------------------------------------------------------
# Convenience helpers (used by admin/query layer later)
# ---------------------------------------------------------------------------

def get_available_institutes(db_conn) -> list:
    """
    Return list of institute_codes that have at least one voter imported.
    Used by the UI to decide which institutes are selectable vs disabled.
    """
    rows = db_conn.execute(
        "SELECT DISTINCT institute FROM voters WHERE institute IS NOT NULL"
    ).fetchall()
    return [row[0] if not hasattr(row, "keys") else row["institute"] for row in rows]


def get_available_departments(db_conn, institute_code: str) -> list:
    """
    Return list of departments within an institute that have imported voters.
    """
    rows = db_conn.execute(
        "SELECT DISTINCT department FROM voters "
        "WHERE institute = ? AND department IS NOT NULL",
        (institute_code,),
    ).fetchall()
    return [row[0] if not hasattr(row, "keys") else row["department"] for row in rows]


def get_available_years(db_conn, institute_code: str, department: Optional[str] = None) -> list:
    """
    Return list of admission years with actual voter data for a given
    institute (and optionally department).
    """
    if department:
        rows = db_conn.execute(
            "SELECT DISTINCT admission_year FROM voters "
            "WHERE institute = ? AND department = ? AND admission_year IS NOT NULL "
            "ORDER BY admission_year",
            (institute_code, department),
        ).fetchall()
    else:
        rows = db_conn.execute(
            "SELECT DISTINCT admission_year FROM voters "
            "WHERE institute = ? AND admission_year IS NOT NULL "
            "ORDER BY admission_year",
            (institute_code,),
        ).fetchall()
    return [row[0] if not hasattr(row, "keys") else row["admission_year"] for row in rows]
