# CampusVote — CHARUSAT Student Council Election

A rebuilt version of your terminal EVM project as a real website: Flask backend,
SQLite database, and an HTML/CSS frontend. Tested end-to-end (login, voting,
double-vote blocking, results, admin, audit) before handing this over.

## What changed from your original C++ version

- **Double voting is now blocked.** Your original code never marked a voter as
  "already voted" — the same ID could vote unlimited times. This was the most
  important fix.
- **Votes are structurally anonymous.** The `votes` table has no `voter_id`
  column at all. A separate `turnout_log` table proves *who* voted and *when*,
  for audit purposes, but nothing in the database links a person to their choices.
- **No hardcoded passwords in source code.** Admin/auditor passwords are hashed
  and stored in the database, seeded once via `init_db.py`.
- **A real database instead of fixed-size arrays.** No more `new Candidate[50]`
  silently breaking past 50 candidates, and data now survives a restart.
- **Two staff roles**: `admin` (manage candidates, open/close voting) and
  `auditor` (turnout log only — cannot see vote choices).

## Project structure

```
campus_vote/
├── app.py              # Flask backend (all routes/logic)
├── schema.sql           # database structure
├── init_db.py            # run once: creates campus_vote.db
├── import_voters.py      # run once: loads voters.txt into the database
├── voters.txt             # your voter roll (ID <TAB> Full Name)
├── requirements.txt
├── templates/            # HTML pages
└── static/css/style.css   # all styling
```

## Running it locally

```bash
cd campus_vote
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

python init_db.py               # creates campus_vote.db
python import_voters.py voters.txt

python app.py                   # starts at http://127.0.0.1:5000
```

Default staff logins (**change these — see "Before going live" below**):
- Admin: `admin` / `ChangeMe123!` → manage candidates, open/close voting
- Auditor: `auditor` / `ChangeMe456!` → turnout log only

Voting only works for students on the roll, and only while an admin has
switched voting to "OPEN" from the dashboard.

## Adding the official CHARUSAT logo

Once you have the image files:
1. Put the logo file in `static/img/` (e.g. `static/img/charusat-logo.png`).
2. In `templates/base.html`, replace the `<div class="crest">CU</div>` block with:
   ```html
   <img src="{{ url_for('static', filename='img/charusat-logo.png') }}" alt="CHARUSAT" style="height:40px;">
   ```
3. If you want official brand colors instead of the navy/maroon/brass palette
   I used, tell me the hex codes and I'll swap the tokens at the top of
   `static/css/style.css` — everything else references those variables, so
   it's a small change.

## Before this goes live for a real election

These are the honest gaps between "working demo" and "production-safe for
3000+ real voters" — worth doing in roughly this order:

1. **Change the default admin/auditor passwords immediately** (`init_db.py`
   seeds placeholders — update the account after first login, or edit the
   script before running it).
2. **Deploy behind HTTPS.** Right now this runs on plain HTTP for local
   testing. A real vote must not travel unencrypted. Cheapest path: deploy to
   a host like Render, Railway, or PythonAnywhere, which give you HTTPS for
   free, or put it behind your university's existing web server with a
   Let's Encrypt certificate.
3. **Use a production server**, not `python app.py`'s built-in dev server —
   e.g. `gunicorn app:app` behind Nginx.
4. **Switch `SESSION_COOKIE_SECURE = True`** in `app.py` once you're on HTTPS.
5. **Rate-limit the voter ID login** (e.g. with `Flask-Limiter`) so someone
   can't script through thousands of ID guesses.
6. **Back up `campus_vote.db` periodically** during the voting window — it's
   a single file, easy to copy, but easy to lose too.
7. Consider **getting a short security/process review from your faculty
   advisor or university IT** before treating results as official — that's
   a policy question as much as a technical one, given this decides a real
   election.

## Notes on the design

I gave it a deliberately "official ballot" identity rather than a generic
app look — navy ink, a brass rule, a maroon wax-seal-style stamp on the
confirmation screen, and monospace type for ID numbers and timestamps
(echoing how enrollment IDs are already formatted). Swap the palette in
`static/css/style.css` if you get real CHARUSAT brand colors.
