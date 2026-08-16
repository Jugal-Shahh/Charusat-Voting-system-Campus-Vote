"""
id_parser.py — CharusatVote ID-parsing engine (Data-driven per department).

Architecture: parse-on-import, not parse-on-demand.
  - Pattern definitions live in the `institute_id_patterns` DB table (one row per department).
  - Shape: ^(d)?(\\d{2})(<department_code>)(\\d{3})?$
  - This module reads those definitions and applies them to raw voter IDs.
  - Eligibility checks downstream are plain SQL WHERE clauses on the
    pre-parsed columns (institute, department, admission_year, is_diploma).

Public API
----------
load_patterns(db_conn)  →  dict[str, list[DepartmentPattern]]
parse_voter_id(voter_id, patterns, restrict_to_institute=None)  →  ParseResult

Both functions have zero Flask dependency and are safe to call from
import scripts, tests, or any future CLI/API layer.
"""

from collections import defaultdict
from dataclasses import dataclass, field
import re
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class DepartmentPattern:
    """One row from institute_id_patterns, ready for regex matching."""
    institute_code: str
    department_code: str
    department_name: str
    has_numeric_suffix: bool = True
    diploma_allowed: bool = False
    _compiled: re.Pattern = field(default=None, init=False, repr=False)

    def __post_init__(self):
        dept_escaped = re.escape(self.department_code)
        suffix = r"(\d{3})" if self.has_numeric_suffix else r"(\d{3})?"
        if self.diploma_allowed:
            pattern = rf"^(d)?(\d{{2}})({dept_escaped}){suffix}$"
        else:
            pattern = rf"^(\d{{2}})({dept_escaped}){suffix}$"
        self._compiled = re.compile(pattern, re.IGNORECASE)

    def match(self, voter_id: str) -> Optional[re.Match]:
        return self._compiled.match(voter_id)


# Backward compatibility alias
InstitutePattern = DepartmentPattern


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

def load_patterns(db_conn) -> Dict[str, List[DepartmentPattern]]:
    """
    Load all rows from institute_id_patterns and return a dict keyed by
    institute_code (e.g. {'CSPIT': [DepartmentPattern(...), ...], ...}).

    Accepts any sqlite3.Connection (or object with an .execute method).
    """
    rows = db_conn.execute(
        "SELECT institute_code, department_code, department_name, "
        "       has_numeric_suffix, diploma_allowed "
        "FROM   institute_id_patterns"
    ).fetchall()

    patterns: Dict[str, List[DepartmentPattern]] = defaultdict(list)
    for row in rows:
        # row may be sqlite3.Row (subscript by name) or plain tuple
        if hasattr(row, "keys"):
            inst_code = row["institute_code"]
            dept_code = row["department_code"]
            dept_name = row["department_name"]
            has_num = bool(row["has_numeric_suffix"])
            diploma_ok = bool(row["diploma_allowed"])
        else:
            inst_code, dept_code, dept_name, has_num, diploma_ok = row
            has_num = bool(has_num)
            diploma_ok = bool(diploma_ok)

        inst_key = inst_code.strip().upper()
        patterns[inst_key].append(
            DepartmentPattern(
                institute_code=inst_key,
                department_code=dept_code.strip().upper(),
                department_name=dept_name,
                has_numeric_suffix=has_num,
                diploma_allowed=diploma_ok,
            )
        )

    return dict(patterns)


# ---------------------------------------------------------------------------
# Core parser
# ---------------------------------------------------------------------------

def parse_voter_id(
    voter_id: str,
    patterns: Dict[str, List[DepartmentPattern]],
    restrict_to_institute: Optional[str] = None,
) -> ParseResult:
    """
    Try to parse `voter_id` against the loaded institute/department patterns.

    Parameters
    ----------
    voter_id : str
        Raw voter ID string, e.g. '24AIML065', 'd25aiml001', '24bba001'.
    patterns : dict
        Dict returned by load_patterns().
    restrict_to_institute : str | None
        If provided, ONLY the patterns for that institute are tried.
        Non-matching IDs are flagged (matched=False) even if they
        would match a different institute's pattern.

    Returns
    -------
    ParseResult
        .matched=True with structured fields, or .matched=False if
        the ID doesn't fit the (restricted) pattern set.
    """
    voter_id = voter_id.strip()
    if not voter_id:
        return ParseResult(matched=False)

    if restrict_to_institute:
        inst_key = restrict_to_institute.strip().upper()
        candidate_lists = [patterns[inst_key]] if inst_key in patterns else []
    else:
        candidate_lists = list(patterns.values())

    for dept_list in candidate_lists:
        for pattern in dept_list:
            m = pattern.match(voter_id)
            if m is None:
                continue

            if pattern.diploma_allowed:
                # Group 1: optional 'd'/'D' prefix
                # Group 2: 2-digit year
                # Group 3: department code
                # Group 4: 3-digit student number
                is_diploma = 1 if (m.group(1) and m.group(1).upper() == "D") else 0
                year = int(m.group(2))
            else:
                # Group 1: 2-digit year
                # Group 2: department code
                # Group 3: 3-digit student number
                is_diploma = 0
                year = int(m.group(1))

            return ParseResult(
                matched=True,
                institute=pattern.institute_code,
                department=pattern.department_code,
                admission_year=year,
                is_diploma=is_diploma,
            )

    return ParseResult(matched=False)


# ---------------------------------------------------------------------------
# Convenience helpers (used by admin/query layer)
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
