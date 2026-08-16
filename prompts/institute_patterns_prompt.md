# Add remaining institute ID patterns, and simplify diploma-marker handling

## Correction to earlier assumption — please apply this first

An earlier prompt assumed DEPSTAR needed a special "diploma marker after year" pattern
distinct from CSPIT's "diploma marker before year" pattern. That assumption was wrong, now
that real data confirms the actual rule. **There is only one diploma rule, used identically
across every institute**: a lowercase `d` prefix goes immediately before the 2-digit year,
full stop. DEPSTAR's department codes (`DCS`, `DCE`, `DIT`) simply already start with the
letter `D` themselves — that's a coincidence of the department code, not a second diploma
marker position. `D25DCE153` decomposes as: diploma-`d` + year `25` + department code `dce`
+ number `153` — same shape as CSPIT's `D23AIML001`.

**Simplify accordingly**: if the previous pass added a distinct "diploma-after-year" pattern
specifically for DEPSTAR, remove it and replace with the same single diploma-prefix rule used
everywhere else, just applied to DEPSTAR's own department code list.

## Recommended shape: make this fully data-driven per department, not per institute

Rather than one regex string per institute, store one row per **department code**, since
every department across every institute follows the exact same shape:
```
^(d)?(\d{2})(<department_code>)(\d{3})?$
```
— optional lowercase `d` diploma prefix, 2-digit year, the department's letter code, and
(usually) a 3-digit student number. A table like:

```
institute_code | department_code | department_name       | has_numeric_suffix
IIIM           | bba             | BBA                    | true
IIIM           | mba             | MBA                    | true
RPCP           | bph             | B.Pharm                | true
RPCP           | mph             | M.Pharm                | true
PDPIAS         | bsc             | B.Sc                   | true   -- ASSUMPTION, see note below
CSPIT          | cs              | Computer Science        | true
CSPIT          | ce              | Civil Engineering       | true
CSPIT          | it              | Information Technology  | true
CSPIT          | aiml            | AI & ML                 | true
CSPIT          | cl              | Chemical Engineering    | true
CSPIT          | ec              | Electronics & Comm.     | true
CSPIT          | me              | Mechanical Engineering  | true
CSPIT          | ee              | Electrical Engineering  | true
DEPSTAR        | dcs             | DEPSTAR CS               | true
DEPSTAR        | dce             | DEPSTAR CE               | true
DEPSTAR        | dit             | DEPSTAR IT               | true
CMPICA         | bca             | BCA                     | true
CMPICA         | mca             | MCA                     | true
CMPICA         | bsit            | B.Sc IT                 | true   -- ASSUMPTION, see note below
CMPICA         | msit            | M.Sc IT                 | true   -- ASSUMPTION, see note below
BDIAS          | bsmt            | BSMT                    | true
BDIAS          | bmit            | BMIT                    | true
ARIP           | bpt             | BPT (Bachelors)          | true
ARIP           | mpt             | MPT (Masters)            | true
```

Every department gets `diploma_allowed = true` except where the user confirms otherwise —
CSPIT and DEPSTAR are confirmed to have diploma variants; the others weren't mentioned as
having diploma programs, so treat diploma as not applicable for IIIM, RPCP, PDPIAS, CMPICA,
BDIAS, ARIP unless told otherwise.

**MTIN is not included** — confirmed by the user there's no data for it yet. Keep it showing
as "not available" in the UI, same treatment as before, until the user provides its pattern
later (this is expected to happen in a future pass, so keep the pattern table data-driven
enough that adding it later is just a new row, not a code change).

**Confirmed, not an assumption**: PDPIAS's `bsc` and CMPICA's `bsit`/`msit` follow the exact
same 3-digit-suffix shape as every other department (`has_numeric_suffix = true`) — the
missing digits in the original notes were just an oversight when the user wrote them up, not
a real format difference. Implement all departments in the table above with
`has_numeric_suffix = true` uniformly, no special-casing needed.

## Domain check

All example emails end in `@charusat.edu.in`. The earlier OAuth-prep work already planned to
accept both `@charusat.edu.in` and `@charusat.ac.in` — keep that as-is, this data doesn't
change that plan, just confirms `.edu.in` is the one actually seen in practice so far.

## Verification steps

1. Re-run the import (or a dry-run parse check) against `voters.txt` and confirm CSPIT/DEPSTAR
   IDs still parse identically to before — this change must not regress the two institutes
   that already worked.
2. Since there's no roster file for the other 7 institutes yet, write a small standalone test
   (or reuse `test_id_parser.py` if that already exists in the project) that feeds a handful of
   example IDs from this prompt through the parser — e.g. `24bba001`, `d24aiml001`,
   `24dce001`, `d24dce001`, `24bph045` — and confirms each resolves to the correct institute
   and department. Show the results.
