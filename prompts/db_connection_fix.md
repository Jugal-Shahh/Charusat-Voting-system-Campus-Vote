# Fix: import_voters.py (and init_db.py) never load .env, so DATABASE_URL is invisible to them

## Root cause (confirmed, not a guess)

`app.py` explicitly calls `load_dotenv(PROJECT_ROOT / ".env")` before reading any environment
variables (see near the top of `app.py`). `import_voters.py` has no such call anywhere in it —
it just does `os.environ.get("DATABASE_URL")` directly via `db_wrapper.get_db_connection()`,
which only sees real environment variables, not anything sitting in a `.env` file. Since the
`.env` file was never loaded into the process, `DATABASE_URL` is empty every time this script
runs standalone from the terminal, so `db_wrapper.py`'s fallback logic (intentionally, and
correctly, falls back to SQLite when no `DATABASE_URL` is present) kicks in every time —
silently, with no error, which is why it's been so hard to spot.

## Fix

1. In `import_voters.py`, add the same `.env` loading logic that already exists in `app.py`,
   near the top of the file, before anything reads `os.environ`:
   ```python
   from dotenv import load_dotenv
   load_dotenv(PROJECT_ROOT / ".env")
   ```
   (Match whatever exact loading approach `app.py` uses, including its fallback if
   `python-dotenv` isn't installed — don't diverge into a second implementation, reuse the
   same logic, ideally by importing it from a shared location instead of duplicating it.)

2. **Open `init_db.py` and check for the exact same missing `load_dotenv()` call.** Given the
   identical symptom pattern, it's very likely present there too. Fix it the same way if so.

3. **Ideally, share ONE `load_dotenv` call across all three entry points** (`app.py`,
   `init_db.py`, `import_voters.py`) rather than repeating the same few lines in three places —
   e.g. put it in `db_wrapper.py` itself, called once at import time, so any script that
   imports `get_db_connection` automatically gets `.env` loaded too, and this exact class of
   bug can't recur in a fourth script later.

4. **Add one diagnostic print** right after `.env` loading in `import_voters.py` and
   `init_db.py`: print whether `DATABASE_URL` was found in the environment at all (just
   whether it's present/non-empty, never print the actual value, since it contains a
   password). This makes this specific failure mode ("silently using SQLite because the env
   var never loaded") visible immediately in the terminal output next time, instead of only
   showing up as "Database: SQLite" several lines later with no explanation why.

## Verification — do this yourself, don't just report the fix as correct

1. Run `python init_db.py` — confirm the output now explicitly shows `DATABASE_URL` was found,
   and that it's connecting to Postgres, not SQLite.
2. Run `python import_voters.py voters.txt` — confirm the printed `Database:` line says
   `PostgreSQL (via DATABASE_URL)`, not `SQLite`.
3. Confirm this by an independent method too, not just trusting the printed line: query the
   Postgres database directly (e.g. `SELECT COUNT(*) FROM voters;` via psql or a quick Python
   script using the same `DATABASE_URL`) and confirm ~3397 rows are actually there.
