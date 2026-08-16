"""
CharusatVote -- Multi-tenant university voting platform.

Run locally with:
    python init_db.py
    python import_voters.py voters.txt
    python app.py

Then open http://127.0.0.1:5000 in a browser.
"""
import os
import secrets
import sqlite3
import string
from functools import wraps
from pathlib import Path
from db_wrapper import get_db_connection

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(dotenv_path=None):
        if dotenv_path is None:
            return
        p = Path(dotenv_path)
        if not p.exists():
            return
        try:
            with open(p, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip("'\""))
        except Exception:
            pass

from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash, g, jsonify, abort
)
from werkzeug.security import check_password_hash, generate_password_hash

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(PROJECT_ROOT / ".env")

DB_PATH = PROJECT_ROOT / "campus_vote.db"
SECRET_KEY_FILE = PROJECT_ROOT / ".secret_key"

# All 9 CHARUSAT institutes (for UI display)
ALL_INSTITUTES = ["IIIM", "RPCP", "CSPIT", "DEPSTAR", "PDPIAS", "CMPICA", "ARIP", "MTIN", "BDIAS"]

# OAuth config
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
CHARUSAT_DOMAIN = os.environ.get("CHARUSAT_DOMAIN", "charusat.edu.in")
OAUTH_CONFIGURED = bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET)

app = Flask(__name__)

# Secret key
if os.environ.get("SECRET_KEY"):
    app.secret_key = os.environ["SECRET_KEY"]
elif SECRET_KEY_FILE.exists():
    with open(SECRET_KEY_FILE, "rb") as f:
        app.secret_key = f.read()
else:
    key = os.urandom(32)
    try:
        with open(SECRET_KEY_FILE, "wb") as f:
            f.write(key)
    except Exception:
        pass
    app.secret_key = key

app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

# ---------------------------------------------------------------------------
# OAuth setup (Authlib)
# ---------------------------------------------------------------------------
oauth = None
if OAUTH_CONFIGURED:
    from authlib.integrations.flask_client import OAuth
    oauth = OAuth(app)
    oauth.register(
        name="google",
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET,
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={
            "scope": "openid email profile",
            "prompt": "select_account",
        },
    )

# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------
def get_db():
    if "db" not in g:
        g.db = get_db_connection()
        # Ensure max_choices column exists in voting_systems
        try:
            cols = [r["name"] for r in g.db.execute("PRAGMA table_info(voting_systems)").fetchall()]
            if cols and "max_choices" not in cols:
                g.db.execute("ALTER TABLE voting_systems ADD COLUMN max_choices INTEGER NOT NULL DEFAULT 1")
                g.db.commit()
        except Exception:
            pass
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def get_setting(key, default=None):
    row = get_db().execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def generate_system_code():
    """Generate a unique 6-character alphanumeric code."""
    chars = string.ascii_uppercase + string.digits
    db = get_db()
    for _ in range(100):
        code = ''.join(secrets.choice(chars) for _ in range(6))
        existing = db.execute(
            "SELECT 1 FROM voting_systems WHERE code = ?", (code,)
        ).fetchone()
        if not existing:
            return code
    raise RuntimeError("Could not generate unique code after 100 attempts")


def parse_voter_id_from_email(email):
    """
    Extract voter_id from CHARUSAT email.
    e.g. '24aiml065@charusat.edu.in' -> '24AIML065'
    e.g. 'd25aiml077@charusat.edu.in' -> 'D25AIML077'
    e.g. '24dce001@charusat.edu.in' -> '24DCE001'
    """
    if not email:
        return None
    local_part = email.split("@")[0]
    return local_part.upper()


def get_eligible_voter_count(db, scope_type, scope_institute=None, scope_department=None):
    """Count voters eligible for a given scope."""
    if scope_type == "university":
        return db.execute(
            "SELECT COUNT(*) as n FROM voters WHERE institute IS NOT NULL"
        ).fetchone()["n"]
    elif scope_type == "institute":
        return db.execute(
            "SELECT COUNT(*) as n FROM voters WHERE institute = ?",
            (scope_institute,)
        ).fetchone()["n"]
    elif scope_type == "department":
        return db.execute(
            "SELECT COUNT(*) as n FROM voters WHERE institute = ? AND department = ?",
            (scope_institute, scope_department)
        ).fetchone()["n"]
    return 0


def voter_is_eligible(db, voter_id, vs):
    """Check if a voter is eligible for a voting system based on its scope."""
    voter = db.execute("SELECT * FROM voters WHERE voter_id = ?", (voter_id,)).fetchone()
    if not voter or not voter["institute"]:
        return False

    if vs["scope_type"] == "university":
        return True
    elif vs["scope_type"] == "institute":
        return voter["institute"] == vs["scope_institute"]
    elif vs["scope_type"] == "department":
        return (voter["institute"] == vs["scope_institute"] and
                voter["department"] == vs["scope_department"])
    return False


def has_voted_in_system(db, voter_id, voting_system_id):
    """Check if voter has already voted in a specific voting system."""
    row = db.execute(
        "SELECT 1 FROM turnout_log WHERE voter_id = ? AND voting_system_id = ?",
        (voter_id, voting_system_id)
    ).fetchone()
    return row is not None


# ---------------------------------------------------------------------------
# Auth decorators
# ---------------------------------------------------------------------------
def voter_login_required(f):
    """Require Google OAuth voter sign-in."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if "voter_id" not in session:
            # Store the intended destination
            session["next_url"] = request.url
            return redirect(url_for("home"))
        return f(*args, **kwargs)
    return decorated


def admin_login_required(f):
    """Require admin login (username/password session)."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if "admin_id" not in session:
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return decorated


# ---------------------------------------------------------------------------
# Context processor
# ---------------------------------------------------------------------------
@app.context_processor
def inject_globals():
    return {
        "oauth_configured": OAUTH_CONFIGURED,
        "voter_signed_in": "voter_id" in session,
        "voter_name": session.get("voter_name", ""),
        "voter_email": session.get("voter_email", ""),
        "admin_signed_in": "admin_id" in session,
        "admin_username": session.get("admin_username", ""),
    }


# ===================================================================
# PHASE 2: GOOGLE OAUTH ROUTES
# ===================================================================

@app.route("/auth/google")
def auth_google():
    """Initiate Google OAuth flow."""
    if not OAUTH_CONFIGURED or oauth is None:
        flash("Google OAuth is not configured. See .env.example for setup instructions.", "error")
        return redirect(url_for("home"))

    # Store where to redirect after login
    redirect_uri = url_for("auth_google_callback", _external=True)
    google_client = oauth.create_client('google')
    return google_client.authorize_redirect(
        redirect_uri,
        hd=CHARUSAT_DOMAIN,  # UI hint: restrict account picker to CHARUSAT domain
    )


@app.route("/auth/google/callback")
def auth_google_callback():
    """Handle Google OAuth callback."""
    if not OAUTH_CONFIGURED or oauth is None:
        return redirect(url_for("home"))

    try:
        google_client = oauth.create_client('google')
        token = google_client.authorize_access_token()
    except Exception:
        flash("Google sign-in failed. Please try again.", "error")
        return redirect(url_for("home"))

    userinfo = token.get("userinfo", {})
    email = userinfo.get("email", "")
    name = userinfo.get("name", "")

    # SERVER-SIDE domain verification (hd param is a UI hint only)
    if not email.lower().endswith("@" + CHARUSAT_DOMAIN):
        flash(f"Only @{CHARUSAT_DOMAIN} accounts can sign in.", "error")
        return redirect(url_for("home"))

    # Parse voter_id from email
    voter_id = parse_voter_id_from_email(email)

    # Look up voter record
    db = get_db()
    voter = db.execute("SELECT * FROM voters WHERE voter_id = ?", (voter_id,)).fetchone()

    # Store OAuth info in session regardless of voter match
    session["google_email"] = email.lower()
    session["google_name"] = name

    if voter:
        session["voter_id"] = voter["voter_id"]
        session["voter_name"] = voter["full_name"]
        session["voter_institute"] = voter["institute"]
        session["voter_department"] = voter["department"]
    else:
        # Valid CHARUSAT user but not on any voter roll
        session["voter_id"] = voter_id
        session["voter_name"] = name or voter_id
        session["voter_institute"] = None
        session["voter_department"] = None

    # Check if they were trying to go somewhere specific
    flow = session.pop("auth_flow", None)
    next_url = session.pop("next_url", None)

    if flow == "admin_register":
        return redirect(url_for("admin_register"))
    elif next_url:
        return redirect(next_url)
    else:
        return redirect(url_for("voter_dashboard"))


@app.route("/auth/logout")
def auth_logout():
    """Clear all session data."""
    session.clear()
    flash("You have been signed out.", "success")
    return redirect(url_for("home"))


# ===================================================================
# HOME & VOTER DASHBOARD
# ===================================================================

@app.route("/")
def home():
    """Landing page: sign in, join by code, or create a voting system."""
    if "voter_id" in session:
        return redirect(url_for("voter_dashboard"))
    return render_template("home.html")


@app.route("/dashboard")
@voter_login_required
def voter_dashboard():
    """Show voting systems the signed-in voter is eligible for."""
    db = get_db()
    voter_id = session["voter_id"]
    voter = db.execute("SELECT * FROM voters WHERE voter_id = ?", (voter_id,)).fetchone()

    # Find all open voting systems
    all_systems = db.execute(
        "SELECT * FROM voting_systems WHERE is_open = 1 ORDER BY created_at DESC"
    ).fetchall()

    # Filter to ones this voter is eligible for
    eligible_systems = []
    for vs in all_systems:
        if voter and voter_is_eligible(db, voter_id, vs):
            already_voted = has_voted_in_system(db, voter_id, vs["id"])
            eligible_systems.append({
                "id": vs["id"],
                "name": vs["name"],
                "code": vs["code"],
                "scope_type": vs["scope_type"],
                "scope_institute": vs["scope_institute"],
                "scope_department": vs["scope_department"],
                "already_voted": already_voted,
            })

    return render_template(
        "voter_dashboard.html",
        voter=voter,
        eligible_systems=eligible_systems,
        voter_on_roll=voter is not None,
    )


@app.route("/join", methods=["POST"])
def join_by_code():
    """Join a voting system by entering its code."""
    code = request.form.get("code", "").strip().upper()
    if not code:
        flash("Please enter a voting system code.", "error")
        return redirect(url_for("home"))

    db = get_db()
    vs = db.execute("SELECT * FROM voting_systems WHERE code = ?", (code,)).fetchone()
    if not vs:
        flash("No voting system found with that code.", "error")
        return redirect(url_for("home"))

    return redirect(url_for("vote_page", code=code))


# ===================================================================
# PHASE 3: ADMIN ACCOUNT ROUTES
# ===================================================================

@app.route("/admin/register", methods=["GET", "POST"])
def admin_register():
    """Register a new admin account (requires Google sign-in first)."""
    # Must have Google email in session
    if "google_email" not in session:
        session["auth_flow"] = "admin_register"
        if OAUTH_CONFIGURED:
            return redirect(url_for("auth_google"))
        else:
            return redirect(url_for("dev_login"))

    db = get_db()
    email = session["google_email"]

    # Check if already has admin account
    existing = db.execute(
        "SELECT * FROM admins WHERE google_email = ?", (email,)
    ).fetchone()
    if existing:
        session["admin_id"] = existing["id"]
        session["admin_username"] = existing["username"]
        flash(f"Welcome back, {existing['username']}! You already have an admin account.", "success")
        return redirect(url_for("admin_my_systems"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")

        errors = []
        if not username or len(username) < 3:
            errors.append("Username must be at least 3 characters.")
        if not password or len(password) < 6:
            errors.append("Password must be at least 6 characters.")
        if password != confirm:
            errors.append("Passwords do not match.")

        # Check username uniqueness
        if not errors:
            dup = db.execute("SELECT 1 FROM admins WHERE username = ?", (username,)).fetchone()
            if dup:
                errors.append("That username is already taken.")

        if errors:
            for err in errors:
                flash(err, "error")
            return render_template("admin_register.html", email=email, username=username)

        db.execute(
            """INSERT INTO admins (google_email, username, password_hash, role)
               VALUES (?, ?, ?, 'admin')""",
            (email, username, generate_password_hash(password)),
        )
        db.commit()

        admin = db.execute("SELECT * FROM admins WHERE google_email = ?", (email,)).fetchone()
        session["admin_id"] = admin["id"]
        session["admin_username"] = admin["username"]
        flash(f"Admin account created! Welcome, {username}.", "success")
        return redirect(url_for("admin_my_systems"))

    return render_template("admin_register.html", email=email, username="")


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    """Username/password login for returning admins."""
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        db = get_db()
        admin = db.execute(
            "SELECT * FROM admins WHERE username = ?", (username,)
        ).fetchone()

        if admin and check_password_hash(admin["password_hash"], password):
            session["admin_id"] = admin["id"]
            session["admin_username"] = admin["username"]
            return redirect(url_for("admin_my_systems"))

        flash("Incorrect username or password.", "error")

    return render_template("admin_login.html")


@app.route("/admin/logout")
def admin_logout():
    """Log out of admin session."""
    session.pop("admin_id", None)
    session.pop("admin_username", None)
    flash("Logged out of admin panel.", "success")
    return redirect(url_for("admin_login"))


# ===================================================================
# PHASE 3: VOTING SYSTEM CRUD
# ===================================================================

@app.route("/admin/systems")
@admin_login_required
def admin_my_systems():
    """List all voting systems owned by this admin."""
    db = get_db()
    systems = db.execute(
        """SELECT vs.*, COUNT(c.id) as candidate_count
           FROM voting_systems vs
           LEFT JOIN candidates c ON c.voting_system_id = vs.id AND c.is_active = 1
           WHERE vs.admin_id = ?
           GROUP BY vs.id
           ORDER BY vs.created_at DESC""",
        (session["admin_id"],)
    ).fetchall()

    # Get turnout for each system
    system_data = []
    for vs in systems:
        turnout = db.execute(
            "SELECT COUNT(*) as n FROM turnout_log WHERE voting_system_id = ?",
            (vs["id"],)
        ).fetchone()["n"]
        eligible = get_eligible_voter_count(
            db, vs["scope_type"], vs["scope_institute"], vs["scope_department"]
        )
        system_data.append({
            **dict(vs),
            "turnout": turnout,
            "eligible": eligible,
        })

    return render_template("admin_my_systems.html", systems=system_data)


@app.route("/admin/create", methods=["GET", "POST"])
@admin_login_required
def admin_create_system():
    """Create a new voting system."""
    db = get_db()

    # Get institutes with actual data
    available_institutes = [
        row["institute"] for row in
        db.execute("SELECT DISTINCT institute FROM voters WHERE institute IS NOT NULL ORDER BY institute").fetchall()
    ]

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        scope_type = request.form.get("scope_type", "")
        scope_institute = request.form.get("scope_institute", "").strip() or None
        scope_department = request.form.get("scope_department", "").strip() or None

        try:
            max_choices = int(request.form.get("max_choices", 1))
            if max_choices < 1:
                max_choices = 1
        except (ValueError, TypeError):
            max_choices = 1

        errors = []
        if not name:
            errors.append("Election name is required.")
        if scope_type not in ("university", "institute", "department"):
            errors.append("Invalid scope type.")
        if scope_type == "institute" and not scope_institute:
            errors.append("Please select an institute.")
        if scope_type == "department" and (not scope_institute or not scope_department):
            errors.append("Please select both an institute and department.")

        # Verify data exists for selected scope
        if not errors:
            eligible = get_eligible_voter_count(db, scope_type, scope_institute, scope_department)
            if eligible == 0:
                errors.append("No voter data available for the selected scope. Cannot create election.")

        if errors:
            for err in errors:
                flash(err, "error")
            return render_template(
                "admin_create_system.html",
                all_institutes=ALL_INSTITUTES,
                available_institutes=available_institutes,
                name=name, scope_type=scope_type,
                scope_institute=scope_institute,
                scope_department=scope_department,
                max_choices=max_choices,
            )

        allow_live_results = 1 if request.form.get("allow_live_results") else 0
        code = generate_system_code()
        db.execute(
            """INSERT INTO voting_systems
               (name, scope_type, scope_institute, scope_department, code, admin_id, max_choices, allow_live_results)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (name, scope_type, scope_institute, scope_department, code, session["admin_id"], max_choices, allow_live_results),
        )
        db.commit()

        flash(f"Voting system created! Code: {code}", "success")
        return redirect(url_for("admin_system_dashboard", code=code))

    return render_template(
        "admin_create_system.html",
        all_institutes=ALL_INSTITUTES,
        available_institutes=available_institutes,
        name="", scope_type="", scope_institute="", scope_department="",
    )


@app.route("/admin/system/<code>/manage", methods=["GET", "POST"])
@admin_login_required
def admin_system_dashboard(code):
    """Per-voting-system admin dashboard."""
    db = get_db()
    vs = db.execute("SELECT * FROM voting_systems WHERE code = ?", (code,)).fetchone()
    if not vs or vs["admin_id"] != session["admin_id"]:
        abort(404)

    if request.method == "POST":
        action = request.form.get("action")

        if action == "add_candidate":
            name = request.form.get("name", "").strip()
            role = request.form.get("role", "").strip()
            if name:
                db.execute(
                    "INSERT INTO candidates (voting_system_id, name, party_or_role) VALUES (?, ?, ?)",
                    (vs["id"], name, role),
                )
                db.commit()
                flash(f"Added candidate: {name}", "success")

        elif action == "remove_candidate":
            cand_id = request.form.get("candidate_id")
            db.execute(
                "UPDATE candidates SET is_active = 0 WHERE id = ? AND voting_system_id = ?",
                (cand_id, vs["id"]),
            )
            db.commit()
            flash("Candidate removed.", "success")

        elif action == "toggle_voting":
            new_state = 0 if vs["is_open"] else 1
            db.execute(
                "UPDATE voting_systems SET is_open = ? WHERE id = ?",
                (new_state, vs["id"]),
            )
            db.commit()
            flash(f"Voting is now {'OPEN' if new_state else 'CLOSED'}.", "success")

        elif action == "toggle_live_results":
            current = vs["allow_live_results"] if "allow_live_results" in vs.keys() else 0
            new_state = 0 if current else 1
            db.execute(
                "UPDATE voting_systems SET allow_live_results = ? WHERE id = ?",
                (new_state, vs["id"]),
            )
            db.commit()
            flash(f"Public Live Results are now {'ENABLED' if new_state else 'DISABLED'}.", "success")

        return redirect(url_for("admin_system_dashboard", code=code))

    candidates = db.execute(
        "SELECT * FROM candidates WHERE voting_system_id = ? AND is_active = 1 ORDER BY name",
        (vs["id"],)
    ).fetchall()

    turnout = db.execute(
        "SELECT COUNT(*) as n FROM turnout_log WHERE voting_system_id = ?",
        (vs["id"],)
    ).fetchone()["n"]

    eligible = get_eligible_voter_count(
        db, vs["scope_type"], vs["scope_institute"], vs["scope_department"]
    )

    share_link = request.url_root.rstrip("/") + url_for("vote_page", code=code)

    return render_template(
        "admin_system_dashboard.html",
        vs=vs, candidates=candidates,
        turnout=turnout, eligible=eligible,
        share_link=share_link,
    )


@app.route("/admin/system/<code>/audit", methods=["GET", "POST"])
@admin_login_required
def admin_audit(code):
    """Turnout audit (requires step-up password re-entry on each access)."""
    db = get_db()
    vs = db.execute("SELECT * FROM voting_systems WHERE code = ?", (code,)).fetchone()
    if not vs or vs["admin_id"] != session["admin_id"]:
        abort(404)

    # Step-up auth: require password re-entry on each access
    if request.method == "POST" and "audit_password" in request.form:
        password = request.form.get("audit_password", "")
        admin = db.execute(
            "SELECT * FROM admins WHERE id = ?", (session["admin_id"],)
        ).fetchone()
        if not (admin and check_password_hash(admin["password_hash"], password)):
            flash("Incorrect password.", "error")
            return render_template("admin_stepup_auth.html", vs=vs)
    else:
        return render_template("admin_stepup_auth.html", vs=vs)

    log = db.execute(
        """SELECT t.voter_id, v.full_name, v.institute, v.department, t.voted_at
           FROM turnout_log t
           JOIN voters v ON v.voter_id = t.voter_id
           WHERE t.voting_system_id = ?
           ORDER BY t.voted_at DESC""",
        (vs["id"],)
    ).fetchall()

    return render_template("audit_log.html", log=log, vs=vs)


# ===================================================================
# API: DYNAMIC SCOPE DATA
# ===================================================================

@app.route("/api/departments/<institute>")
def api_departments(institute):
    """Return departments with voter data for a given institute."""
    db = get_db()
    rows = db.execute(
        "SELECT DISTINCT department FROM voters WHERE institute = ? AND department IS NOT NULL ORDER BY department",
        (institute,)
    ).fetchall()
    return jsonify([row["department"] for row in rows])


# ===================================================================
# VOTING ROUTES (SCOPED PER VOTING SYSTEM)
# ===================================================================

@app.route("/vote/<code>", methods=["GET", "POST"])
def vote_page(code):
    """Cast a vote in a specific voting system."""
    db = get_db()
    vs = db.execute("SELECT * FROM voting_systems WHERE code = ?", (code,)).fetchone()
    if not vs:
        abort(404)

    # Must be signed in
    if "voter_id" not in session:
        session["next_url"] = request.url
        if OAUTH_CONFIGURED:
            flash("Please sign in with your CHARUSAT Google account to vote.", "error")
        return redirect(url_for("home"))

    voter_id = session["voter_id"]
    voter = db.execute("SELECT * FROM voters WHERE voter_id = ?", (voter_id,)).fetchone()

    # Check eligibility
    if not voter or not voter_is_eligible(db, voter_id, vs):
        flash("You are not eligible to vote in this election.", "error")
        return redirect(url_for("voter_dashboard"))

    # Check if voting is open
    if not vs["is_open"]:
        flash("Voting is not currently open for this election.", "error")
        return redirect(url_for("vote_results", code=code))

    # Check if already voted
    if has_voted_in_system(db, voter_id, vs["id"]):
        flash("You have already voted in this election.", "error")
        return redirect(url_for("vote_results", code=code))

    candidates = db.execute(
        "SELECT * FROM candidates WHERE voting_system_id = ? AND is_active = 1 ORDER BY name",
        (vs["id"],)
    ).fetchall()

    if request.method == "POST":
        choices = request.form.getlist("vote")
        if not choices and request.form.get("vote"):
            choices = [request.form.get("vote")]

        max_allowed = vs["max_choices"] if "max_choices" in vs.keys() and vs["max_choices"] else 1

        if not choices:
            flash("Please make a selection before submitting.", "error")
            return render_template("vote.html", vs=vs, voter=voter, candidates=candidates)

        if "NOTA" in choices:
            # NOTA selected -> 1 NOTA vote cast
            vote_entries = [(None, 1)]
        else:
            if len(choices) > max_allowed:
                flash(f"You can select at most {max_allowed} choice(s).", "error")
                return render_template("vote.html", vs=vs, voter=voter, candidates=candidates)

            vote_entries = []
            for cid in choices:
                cand = db.execute(
                    "SELECT id FROM candidates WHERE id = ? AND voting_system_id = ? AND is_active = 1",
                    (cid, vs["id"])
                ).fetchone()
                if not cand:
                    flash("Invalid candidate selection.", "error")
                    return render_template("vote.html", vs=vs, voter=voter, candidates=candidates)
                vote_entries.append((cand["id"], 0))

        # Atomic: record vote entries + 1 turnout log entry
        try:
            cur = db.cursor()
            for cand_id, is_nota in vote_entries:
                cur.execute(
                    "INSERT INTO votes (voting_system_id, candidate_id, is_nota) VALUES (?, ?, ?)",
                    (vs["id"], cand_id, is_nota),
                )
            cur.execute(
                "INSERT INTO turnout_log (voting_system_id, voter_id) VALUES (?, ?)",
                (vs["id"], voter_id),
            )
            db.commit()
        except Exception:
            db.rollback()
            flash("Something went wrong recording your vote. Please try again.", "error")
            return render_template("vote.html", vs=vs, voter=voter, candidates=candidates)

        return redirect(url_for("vote_thank_you", code=code))

    return render_template("vote.html", vs=vs, voter=voter, candidates=candidates)


@app.route("/vote/<code>/thank-you")
def vote_thank_you(code):
    """Confirmation page after voting."""
    db = get_db()
    vs = db.execute("SELECT * FROM voting_systems WHERE code = ?", (code,)).fetchone()
    if not vs:
        abort(404)
    return render_template("thank_you.html", vs=vs)


@app.route("/vote/<code>/results")
def vote_results(code):
    """Results page for a specific voting system."""
    db = get_db()
    vs = db.execute("SELECT * FROM voting_systems WHERE code = ?", (code,)).fetchone()
    if not vs:
        abort(404)

    # Results Visibility Rule:
    # Visible if voting is closed OR if admin enabled allow_live_results.
    # The owning admin can always view live results anytime.
    allow_live = vs["allow_live_results"] if "allow_live_results" in vs.keys() else 0
    is_owner = (session.get("admin_id") == vs["admin_id"])
    if vs["is_open"] and not is_owner and not allow_live:
        flash("Results are hidden while voting is open. Please check back after voting closes.", "error")
        if "voter_id" in session:
            return redirect(url_for("voter_dashboard"))
        return redirect(url_for("home"))

    candidates_results = db.execute(
        """SELECT c.id, c.name, c.party_or_role, COUNT(v.id) AS vote_count
           FROM candidates c
           LEFT JOIN votes v ON v.candidate_id = c.id AND v.voting_system_id = ?
           WHERE c.voting_system_id = ? AND c.is_active = 1
           GROUP BY c.id
           ORDER BY vote_count DESC, c.name""",
        (vs["id"], vs["id"])
    ).fetchall()

    nota_count = db.execute(
        "SELECT COUNT(*) AS n FROM votes WHERE voting_system_id = ? AND is_nota = 1",
        (vs["id"],)
    ).fetchone()["n"]

    eligible = get_eligible_voter_count(
        db, vs["scope_type"], vs["scope_institute"], vs["scope_department"]
    )

    turnout = db.execute(
        "SELECT COUNT(*) as n FROM turnout_log WHERE voting_system_id = ?",
        (vs["id"],)
    ).fetchone()["n"]

    return render_template(
        "results.html",
        vs=vs,
        candidates=candidates_results,
        nota_count=nota_count,
        eligible=eligible,
        turnout=turnout,
    )


# ===================================================================
# DEV-MODE: BYPASS OAUTH FOR LOCAL TESTING
# ===================================================================

@app.route("/dev/login", methods=["GET", "POST"])
def dev_login():
    """
    Development-only: simulate Google sign-in by entering a voter_id directly.
    Only available when OAuth is NOT configured.
    """
    if OAUTH_CONFIGURED:
        abort(404)

    if request.method == "POST":
        voter_id = request.form.get("voter_id", "").strip().upper()
        if not voter_id:
            flash("Please enter a voter ID.", "error")
            return render_template("dev_login.html")

        db = get_db()
        voter = db.execute("SELECT * FROM voters WHERE voter_id = ?", (voter_id,)).fetchone()

        session["google_email"] = f"{voter_id.lower()}@{CHARUSAT_DOMAIN}"
        session["google_name"] = voter["full_name"] if voter else voter_id

        if voter:
            session["voter_id"] = voter["voter_id"]
            session["voter_name"] = voter["full_name"]
            session["voter_institute"] = voter["institute"]
            session["voter_department"] = voter["department"]
        else:
            session["voter_id"] = voter_id
            session["voter_name"] = voter_id
            session["voter_institute"] = None
            session["voter_department"] = None

        next_url = session.pop("next_url", None)
        flow = session.pop("auth_flow", None)
        if flow == "admin_register":
            return redirect(url_for("admin_register"))
        elif next_url:
            return redirect(next_url)
        return redirect(url_for("voter_dashboard"))

    return render_template("dev_login.html")


# ===================================================================
# MAIN
# ===================================================================

if __name__ == "__main__":
    app.run(debug=True)
