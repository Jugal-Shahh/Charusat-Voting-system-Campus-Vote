# CampusVote

**Official multi-tenant election platform for CHARUSAT University.**

CampusVote lets any verified CHARUSAT student or staff member create and run their own
scoped election — from a single department to the whole university — with real identity
verification, structurally anonymous voting, and live results.

---

## Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Setup — Local Development](#setup--local-development)
- [Setup — Google OAuth](#setup--google-oauth)
- [Deployment](#deployment)
- [Institute & Department ID Patterns](#institute--department-id-patterns)
- [Anonymity & Security Design](#anonymity--security-design)
- [Known Limitations](#known-limitations)
- [Roadmap](#roadmap)

---

## Features

### Identity & eligibility
- **Google OAuth sign-in**, restricted to `@charusat.edu.in` and `@charusat.ac.in` accounts
  only — no separate password to manage, no custom email verification system.
- **Automatic eligibility detection** — a signed-in student's institute, department, and
  admission year are parsed directly from their verified CHARUSAT email address, no manual
  roster lookup required.
- **Graceful rejection, never a crash** — any ineligible sign-in (wrong domain, unrecognized
  ID format, wrong department for a given election) shows a clear message and returns the
  person to a normal page.

### Creating an election
- Any verified user can create a voting system after signing in.
- Three scopes to choose from:
  - **University-wide** — every eligible CHARUSAT student.
  - **Institutional** — scoped to one of CHARUSAT's institutes.
  - **Departmental** — scoped to one specific department within an institute.
- Institutes/departments without a configured ID pattern are shown as **"not available"**
  rather than silently allowing a broken election to be created.
- Configurable **votes-per-ballot** (default: 1) — not hardcoded to any fixed number, so a
  single-position election and a multi-seat election both work correctly.
- On creation, a unique **code and shareable link** are generated for voters to join.

### Voting
- Personal voter dashboard listing every currently open election the signed-in person is
  eligible for.
- **Join by code/link** for elections not automatically listed.
- NOTA available on every ballot.
- **One vote per eligible voter per election**, enforced atomically — reload, back button,
  multiple tabs, or resubmission cannot produce a duplicate vote.

### Admin tools
- Add/remove candidates, open/close voting, per-election dashboard.
- Live turnout count while voting is open.
- **Step-up authentication**: viewing the turnout/audit log requires re-entering the account
  password, even within an active session.
- A single admin account can own and manage multiple voting systems.

### Results & audit
- Results visible to voters once the admin closes voting; admin can see live turnout counts
  (not vote content) at any time while open.
- Turnout/audit log shows **who voted and when only** — never what they voted for.

---

## Architecture

CampusVote is a **multi-tenant** system: one deployment can run many independent, concurrent
elections, each fully isolated from the others (candidates, votes, and turnout are all scoped
per voting-system-instance).

```
┌─────────────┐      ┌──────────────┐      ┌────────────────┐
│   Browser    │ ───▶ │  Flask App   │ ───▶ │  PostgreSQL     │
│ (voter/admin)│      │  (Render)    │      │  (Neon)         │
└─────────────┘      └──────┬───────┘      └────────────────┘
                             │
                             ▼
                     ┌───────────────┐
                     │  Google OAuth  │
                     │ (identity only)│
                     └───────────────┘
```

The identity provider (Google) only confirms *who someone is*. Eligibility (*what they can
vote in*) is derived independently, by parsing their verified email against a configurable
table of institute/department ID patterns — it does not depend on a pre-imported voter roster.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python, Flask |
| Database | PostgreSQL (hosted on [Neon](https://neon.tech), free tier) |
| Auth | Google OAuth 2.0 (Authlib), domain-restricted |
| Hosting | [Render](https://render.com) (free tier, persistent web service) |
| Frontend | Server-rendered HTML/Jinja templates, custom CSS |
| Uptime | [UptimeRobot](https://uptimerobot.com), free tier |

---

## Project Structure

```
campus_vote/
├── app.py                  # Main Flask application, routes
├── db_wrapper.py            # Database connection layer (SQLite locally / Postgres in prod)
├── id_parser.py              # Institute/department ID pattern matching
├── init_db.py                 # One-time DB schema setup + seeding
├── import_voters.py            # Optional: import a backup voter roster (see below)
├── schema.sql                   # Database schema
├── requirements.txt
├── .env.example                  # Template for required environment variables
├── static/
│   ├── css/style.css              # Shared design tokens and styling
│   └── img/                        # Logos, backgrounds
├── templates/
│   ├── base.html                    # Shared layout, navbar
│   ├── home.html                     # Landing page (sign in / join election)
│   ├── voter_login.html, voter_dashboard.html
│   ├── admin_login.html, admin_register.html, admin_dashboard.html
│   ├── admin_create_system.html, admin_my_systems.html, admin_stepup_auth.html
│   ├── admin_system_dashboard.html
│   ├── vote.html, results.html, thank_you.html
│   └── audit_log.html
└── voters.txt                        # Backup roster (CSPIT/DEPSTAR only — see below)
```

---

## Setup — Local Development

```bash
git clone <your-repo-url>
cd campus_vote

python -m venv venv
venv\Scripts\activate           # Windows
# source venv/bin/activate      # Mac/Linux

pip install -r requirements.txt
```

Create a `.env` file (copy `.env.example`) and fill in:
```
DATABASE_URL=postgresql://...          # from Neon, or omit to fall back to local SQLite
SECRET_KEY=<generate with: python -c "import secrets; print(secrets.token_hex(32))">
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
```

Then:
```bash
python init_db.py
python app.py
```
Visit `http://127.0.0.1:5000`.

---

## Setup — Google OAuth

1. Create a project at [console.cloud.google.com](https://console.cloud.google.com).
2. **APIs & Services → OAuth consent screen** → User Type: External → fill in app details →
   add scopes `email`, `profile`, `openid` → add CHARUSAT test-user emails.
3. **APIs & Services → Credentials → Create Credentials → OAuth client ID** → Web application
   → add redirect URIs for both local (`http://127.0.0.1:5000/auth/google/callback`) and
   production (`https://your-app.onrender.com/auth/google/callback`).
4. Copy the Client ID and Secret into `.env` (local) and Render's Environment tab (production).

**Note**: while unpublished, only accounts added as test users can sign in, and each
test-user session expires after 7 days. For a real campus-wide launch, submit for Google's
brand verification (typically ~2–3 business days for non-sensitive scopes like these).

---

## Deployment

Deployed on **Render** (free tier) with a **Neon** Postgres database.

- **Build Command**: `pip install -r requirements.txt`
- **Start Command**: `gunicorn app:app --bind 0.0.0.0:$PORT`
- **Environment Variables** (set in Render's dashboard, never committed):
  `DATABASE_URL`, `SECRET_KEY`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`

Render's free tier sleeps after 15 minutes of inactivity; a free UptimeRobot monitor pings
the live URL every 5 minutes to prevent this.

---

## Institute & Department ID Patterns

Eligibility is determined by parsing each voter's CHARUSAT email against a data-driven
pattern table (`institute_id_patterns`) — adding a new institute later is a data insert, not
a code change.

**General shape**: `[d]<2-digit year><department code><3-digit number>@charusat.edu.in`
— an optional lowercase `d` prefix marks a diploma student; the same rule applies uniformly
across every institute (no institute-specific exceptions).

| Institute | Departments configured | Notes |
|---|---|---|
| CSPIT | CS, CE, IT, AIML, CL, EC, ME, EE | Full diploma support |
| DEPSTAR | DCS, DCE, DIT | Full diploma support |
| IIIM | BBA, MBA | |
| RPCP | B.Pharm, M.Pharm | |
| PDPIAS | B.Sc | |
| CMPICA | BCA, MCA, B.Sc IT, M.Sc IT | |
| BDIAS | BSMT, BMIT | |
| ARIP | BPT, MPT | |
| MTIN | *(not yet configured)* | Shown as "not available" until patterns are added |

`voters.txt` / the `voters` table holds a **backup roster for CSPIT and DEPSTAR only** — it
is not the live source of truth for eligibility once OAuth is active. It exists for
cross-checking turnout and capturing names for the two institutes it covers; the other
institutes' student names are captured live from their Google profile on first sign-in.

---

## Anonymity & Security Design

These properties are foundational and must be preserved in any future change:

- **No database table, join, or query anywhere links a specific voter to their specific vote
  choice.** The `votes` table has no `voter_id` column at all.
- Turnout is tracked separately (`turnout_log`), proving *who* voted and *when* without
  revealing *what* they chose — this is what the audit log shows, and all it ever shows.
- Vote recording and marking a voter as having voted happen **atomically**, scoped per
  election, preventing double-voting even under concurrent requests.
- Identity is verified by Google, not stored as a password anywhere in this system.
- Server-side domain verification on every OAuth callback — the `hd` parameter alone is a UI
  hint, not a security boundary, and is not relied upon as one.

---

## Known Limitations

- Render's free tier has a cold-start delay (~30–60s) if the uptime pinger ever lapses.
- Google OAuth is capped at 100 test users / 7-day session expiry until the app is verified.
- MTIN institute data is not yet available.
- PostgreSQL/SQLite compatibility is handled by a custom translation layer (`db_wrapper.py`)
  rather than an ORM — new query patterns should be tested against both backends.

## Roadmap

- [ ] Add MTIN institute ID patterns once available
- [ ] Submit for Google OAuth brand verification
- [ ] Consider migrating `db_wrapper.py`'s manual SQL translation to a proper ORM if the
      project continues to grow
