# Build prompt: CharusatVote — multi-tenant university voting platform

## 0. Context (existing system)

There is already a working single-election prototype:
- **Stack:** Python Flask backend, SQLite database, server-rendered HTML/CSS (Jinja templates), no JS framework.
- **Current schema:** `voters` (voter_id, full_name, has_voted, voted_at), `candidates`, `votes` (deliberately has NO voter_id column — votes are structurally anonymous), `turnout_log` (voter_id, voted_at — proves who voted without revealing what they voted for), `admins` (username, password_hash, role: admin/auditor), `settings`.
- **Current flow:** one hardcoded election. Voter types their ID with no verification it's actually them. Admin logs in, adds candidates, opens/closes voting. Auditor sees turnout only.

**This prompt describes a major rebuild** on top of that foundation: instead of one hardcoded election, this becomes a platform where any authenticated member of the university can create their own scoped election.

---

## 1. Product vision

CharusatVote lets anyone with a verified CHARUSAT email:
1. **Create a voting system** scoped to the whole university, one institute, or one department — and get a shareable code/link for it.
2. **Join a voting system** via that code/link, or **sign in** to see all voting systems currently open to them, and cast a verified vote.

The university has 9 institutes: **IIIM, RPCP, CSPIT, DEPSTAR, PDPIAS, CMPICA, ARIP, MTIN, BDIAS**. Each institute has its own departments. Voter rolls currently only exist for **CSPIT** and **DEPSTAR** — the other 7 institutes must appear in the UI (so the product feels complete) but be visibly disabled/"Data not available yet," never silently broken.

---

## 2. Non-negotiable design constraints

These carry over from the current system and must NOT be weakened by this rebuild:

- **Votes stay structurally anonymous.** No table, join, or admin view may ever connect a specific voter to their specific candidate choice. If a feature request implies "see who voted for whom," treat that as **turnout/eligibility auditing only** — who voted and when — never vote content. Flag this to the user explicitly if a requirement seems to ask for the opposite.
- **One vote per eligible voter per voting system**, enforced atomically (already solved once in the current schema — reuse that pattern per voting-system-instance).
- **Every institute/department/year option shown in the UI must be derived from what's actually been imported into the database**, never hardcoded as "available." If no voters exist for a given institute, department, or admission year, the UI must show it as unavailable rather than letting someone create a voting system that silently has zero eligible voters.

---

## 3. Identity & ID-parsing engine

### 3.1 Known ID patterns (seed data — more will be added later per institute)

CSPIT departments (as of now): **CS, CE, IT, EC, ME, EE, CL, AIML**
DEPSTAR departments (as of now): **CE, CS, IT**

CSPIT ID pattern (note: `D` prefix comes **before** the year for diploma students):
```
^(D)?(\d{2})(CS|CE|IT|EC|ME|EE|CL|AIML)(\d{3})$
examples: 24AIML065, 25CE001, D23AIML001, D24CE010
```

DEPSTAR ID pattern (note: `D` comes **after** the year, before the department code — this is a different position than CSPIT's diploma marker, and it's easy to get this wrong, so implement it as a distinct per-institute pattern, not a shared regex with a flag):
```
^(\d{2})(D)(CE|CS|IT)(\d{3})$
examples: 25DCE001, 24DCS010
```

Admission-year digits and department codes will vary by which years/departments actually have data loaded — do not assume all of 22–26 exist for every department.

### 3.2 Required architecture: parse-on-import, not parse-on-demand

When a voter roll (voters.txt or similar) is imported for an institute:
1. Look up that institute's ID pattern definition (see 3.3).
2. For each voter ID, extract: `institute`, `department`, `admission_year`, `is_diploma` (boolean), and store these as structured columns on the voter record — do not re-derive them with regex at vote-eligibility-check time. This makes eligibility checks a simple `WHERE` query and makes "what data do we actually have" queries trivial (`SELECT DISTINCT institute, department, admission_year FROM voters`).
3. Any ID that doesn't match the institute's known pattern should be flagged in the import report, not silently dropped or silently included.

### 3.3 Pattern definitions must be data, not code

Create an `institute_id_patterns` table (or config file) holding one row per institute with its regex/template and department code list, so adding IIIM, RPCP, etc. later is a data insert, not a code change. Example shape:

```
institute_id_patterns(
  institute_code TEXT,      -- e.g. 'CSPIT', 'DEPSTAR'
  regex_pattern TEXT,       -- the pattern as described above
  department_codes TEXT,    -- JSON list, e.g. ["CS","CE","IT","EC","ME","EE","CL","AIML"]
  diploma_marker_position TEXT  -- 'before_year' | 'after_year' | 'none'
)
```

---

## 4. Voter identity verification (this replaces "type your ID and go")

The current system's biggest gap: anyone can type someone else's ID and vote as them. Fix with **Google OAuth sign-in against the university's Google Workspace domain — do not build a custom email OTP/magic-link system.**

Confirmed:
- CHARUSAT student email runs on **Google Workspace for Education** (login page matches Gmail's sign-in screen).
- CHARUSAT student email addresses embed the enrollment ID predictably (e.g. `25aiml065@charusat.edu.in`), so identity verification and ID lookup are the same step.

- Implement **"Sign in with Google"**, restricted to the university's Workspace domain only:
  - Use the `hd` (hosted domain) parameter in the OAuth request to restrict the account picker to the CHARUSAT domain.
  - **Re-verify the returned email's domain server-side after login** — the `hd` parameter is a UI hint only and can be bypassed client-side, so the backend must independently check the verified email ends in the correct domain before treating the sign-in as valid.
- On successful sign-in, extract the verified email, parse the enrollment ID out of it using the pattern from section 3, and look up the matching voter record. If the email's embedded ID doesn't match any record in the imported roll, treat as ineligible (not an error) — they may be real but not yet on an imported roll, or from an institute without data yet.
- This requires registering an OAuth app in **Google Cloud Console** and obtaining a client ID/secret — flag this as a one-time setup step for the user (free, takes a few minutes: create a project, configure the OAuth consent screen, add the CHARUSAT domain as authorized, generate credentials). No email-sending infrastructure, no SMTP, no OTP codes needed at all.
- Once signed in, a voter should see a **personal dashboard**: every voting system currently open for which their parsed institute/department makes them eligible.
- The **"Join voting"** path (entering a code/link directly) must still require this same Google sign-in before a ballot is shown — no bypassing identity check just because someone has the link.
- After sign-in, tie the verified session to that one voter_id for the duration of casting that one vote, then the session should not be reusable to vote again (reuses the existing has_voted-style guard, now scoped per voting-system-instance instead of globally).

---

## 5. Creating a voting system (admin-facing)

### 5.1 Admin accounts require verification too

To create a voting system, a user must first sign in with Google (same mechanism as section 4, restricted to the CHARUSAT Workspace domain) — this ties every voting system to a real accountable person, not just a username. The username/password set up afterward (5.2 step 2) is only a convenience login for returning to manage that system later; the original Google sign-in is what proves accountability.

### 5.2 Creation flow

1. User chooses **"Create a Voting System"** on the home page.
2. If they don't have an admin account yet: verify college email → set a username and password for that admin account.
3. If they already have an account: log in with username + password (this is just to identify *which person* is managing *which voting systems* — it is not the identity check for voting itself, which always goes through email verification per section 4).
4. In the creation form, the admin:
   - Names the election (e.g. "Sports Coordinator Election").
   - Chooses the **scope**:
     - **University-wide** — every verified voter across all institutes with available data is eligible.
     - **Institutional** — pick one of the 9 institutes. If that institute has no imported voter data, show it disabled/greyed out with a "Data not available yet" label, not selectable.
     - **Departmental** — pick an institute, then pick one of its departments (again, only departments with actual imported data are selectable).
5. On creation, the system generates a **unique voting-system code and shareable link**. This is how it must be found later — via `admin login` (to manage it) or via `code/link + voter email verification` (to vote or view results in it).

### 5.3 Admin dashboard (per voting system)

- Standard controls carried over from the current system: add/remove candidates, open/close voting, live turnout stats.
- **Viewing sensitive data (turnout audit) requires re-entering the account password**, even within an active session — treat this as a step-up-auth gate on the audit view, not as a way to see vote content (see section 2 — vote content must never become visible to anyone, including the creating admin).
- Because a person may create multiple voting systems over time, the dashboard after login should list all voting systems owned by that admin account, each linking to its own management page.

---

## 6. Voter-facing results

- Once an admin closes a voting system, anyone who accesses it via its code/link (still going through email verification) should be able to see the final anonymized tally — same as the current public `/results` page, just scoped to that specific voting-system-instance rather than a single global election.

---

## 7. Data model implications (summary for planning, not exhaustive)

This moves from a single-election schema to a multi-tenant one. Expect to introduce something like a `voting_systems` table (id, name, scope_type: university/institute/department, scope_institute, scope_department, code, admin_owner_id, is_open, created_at) and to scope `candidates`, `votes`, and `turnout_log` by `voting_system_id` instead of being global singletons. Preserve the existing anonymity property (no voter_id on the votes table) inside this new scoping.

---

## 8. Open questions to resolve before/while building (do not silently guess on these)

1. What is the exact email domain (e.g. `charusat.edu.in`) and the exact ID-to-email pattern (e.g. does `25AIML065` become `25aiml065@...` lowercase, with/without dots)? Needed to write the parsing regex correctly.
2. For institute-wide and university-wide elections, is "every currently-imported voter regardless of department" the correct eligibility rule, or should some departments be excluded even within an institute that has data?
3. Should an admin be allowed to create more than one *open* voting system at a time, or is that fine to allow freely?
4. Should past (closed) voting systems remain permanently viewable, or should there be a retention/expiry policy?

---

## 9. Explicitly out of scope for this pass

- Institutes beyond CSPIT and DEPSTAR remain visibly present but disabled until their voter rolls are imported later.
- No mobile app — responsive web only.
- No production deployment/hosting setup in this pass — focus on a correct, secure local/dev-ready implementation first.
