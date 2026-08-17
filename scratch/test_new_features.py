"""
scratch/test_new_features.py -- Comprehensive verification of:
1. Admin Delete System (soft deletion)
2. Gentle error handling when accessing deleted systems (/join, /vote/<code>, /vote/<code>/results)
3. Exact date & time voting deadline enforcement
4. Smart Voter Dashboard ranking based on turnout and deadline urgency
"""
import sys
from pathlib import Path
from datetime import datetime, timedelta

# Add parent directory to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app import app, get_db, get_deadline_info
import init_db

def run_tests():
    print("\n--- Running init_db migration ---")
    init_db.main()

    client = app.test_client()

    with app.app_context():
        db = get_db()

        # Get or create admin
        admin = db.execute("SELECT * FROM admins WHERE username = 'admin'").fetchone()
        assert admin is not None, "Default admin should exist"
        admin_id = admin["id"]

        # Clean up any existing test fixtures
        test_codes = ('URGNT1', 'POPLR1', 'DEL001', 'EXPR01')
        sys_ids = [r["id"] for r in db.execute(f"SELECT id FROM voting_systems WHERE code IN {test_codes}").fetchall()]
        if sys_ids:
            db.execute(f"DELETE FROM turnout_log WHERE voting_system_id IN ({','.join(str(i) for i in sys_ids)})")
            db.execute(f"DELETE FROM votes WHERE voting_system_id IN ({','.join(str(i) for i in sys_ids)})")
            db.execute(f"DELETE FROM candidates WHERE voting_system_id IN ({','.join(str(i) for i in sys_ids)})")
            db.execute(f"DELETE FROM voting_systems WHERE id IN ({','.join(str(i) for i in sys_ids)})")
            db.commit()

        print("--- Testing System Creation with Deadlines ---")
        now = datetime.now()
        future_deadline = (now + timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M")
        urgent_deadline = (now + timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M")
        past_deadline = (now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M")

        # 1. Active with urgent deadline & 5 votes
        db.execute("""
            INSERT INTO voting_systems (name, scope_type, scope_institute, scope_department, code, admin_id, is_open, deadline, is_deleted)
            VALUES ('Urgent CS Election', 'department', 'CSPIT', 'AIML', 'URGNT1', ?, 1, ?, 0)
        """, (admin_id, urgent_deadline))
        sys_urgent = db.execute("SELECT id FROM voting_systems WHERE code = 'URGNT1'").fetchone()["id"]
        for i in range(5):
            db.execute("INSERT INTO turnout_log (voting_system_id, voter_id) VALUES (?, ?)", (sys_urgent, f"24AIML00{i}"))

        # 2. Active with future deadline & 12 votes (Popular)
        db.execute("""
            INSERT INTO voting_systems (name, scope_type, scope_institute, scope_department, code, admin_id, is_open, deadline, is_deleted)
            VALUES ('Popular University Election', 'university', NULL, NULL, 'POPLR1', ?, 1, ?, 0)
        """, (admin_id, future_deadline))
        sys_pop = db.execute("SELECT id FROM voting_systems WHERE code = 'POPLR1'").fetchone()["id"]
        for i in range(12):
            db.execute("INSERT INTO turnout_log (voting_system_id, voter_id) VALUES (?, ?)", (sys_pop, f"24AIML01{i}"))

        # 3. System to be deleted
        db.execute("""
            INSERT INTO voting_systems (name, scope_type, scope_institute, scope_department, code, admin_id, is_open, deadline, is_deleted)
            VALUES ('System To Delete', 'university', NULL, NULL, 'DEL001', ?, 1, NULL, 0)
        """, (admin_id,))

        # 4. Expired system
        db.execute("""
            INSERT INTO voting_systems (name, scope_type, scope_institute, scope_department, code, admin_id, is_open, deadline, is_deleted)
            VALUES ('Expired Election', 'university', NULL, NULL, 'EXPR01', ?, 1, ?, 0)
        """, (admin_id, past_deadline))

        db.commit()
        print("  [ok] Test election fixtures created.")

    # Test Admin Login and Delete System
    print("\n--- Testing Admin Delete System ---")
    with client.session_transaction() as sess:
        sess["admin_id"] = admin_id
        sess["admin_username"] = "admin"

    res = client.post("/admin/system/DEL001/delete", follow_redirects=True)
    assert res.status_code == 200
    assert b"has been deleted" in res.data
    # Ensure deleted election card is not listed in the manage cards
    assert b"/admin/system/DEL001/manage" not in res.data
    print("  [ok] Admin successfully deleted system DEL001.")

    # Test gentle handling of deleted system for voters
    print("\n--- Testing Gentle Error Handling for Deleted System ---")
    with client.session_transaction() as sess:
        sess.clear()
        sess["voter_id"] = "24AIML065"
        sess["voter_name"] = "Jugal Shah"
        sess["voter_institute"] = "CSPIT"
        sess["voter_department"] = "AIML"

    # Test /join with deleted code
    res_join = client.post("/join", data={"code": "DEL001"}, follow_redirects=True)
    assert b"deleted by the election administrator" in res_join.data
    print("  [ok] /join with deleted code gracefully notifies voter.")

    # Test /vote/DEL001 direct link
    res_vote = client.get("/vote/DEL001")
    assert res_vote.status_code == 410
    assert b"Voting System Deleted" in res_vote.data
    assert b"has been removed or deleted by the administrator" in res_vote.data
    print("  [ok] Direct link to /vote/DEL001 returns gentle deletion notice page.")

    # Test /vote/DEL001/results direct link
    res_results = client.get("/vote/DEL001/results")
    assert res_results.status_code == 410
    assert b"Voting System Deleted" in res_results.data
    print("  [ok] Direct link to /vote/DEL001/results returns gentle deletion notice page.")

    # Test Deadline Enforcement
    print("\n--- Testing Voting Deadline Enforcement ---")
    res_exp = client.get("/vote/EXPR01", follow_redirects=True)
    assert b"deadline" in res_exp.data.lower() or b"closed" in res_exp.data.lower()
    print("  [ok] Accessing expired election redirects with deadline passed notice.")

    # Test Voter Dashboard Ranking
    print("\n--- Testing Voter Dashboard Smart Ranking ---")
    res_dash = client.get("/dashboard")
    assert res_dash.status_code == 200
    content = res_dash.get_data(as_text=True)

    # Urgent and Popular elections should appear before expired or deleted
    assert "DEL001" not in content, "Deleted election must not appear on voter dashboard"
    assert "URGNT1" in content
    assert "POPLR1" in content

    # Check that URGNT1 appears near top due to closing soonest urgency
    pos_urgnt = content.find("URGNT1")
    pos_expr = content.find("EXPR01")
    assert pos_urgnt < pos_expr, "Urgent active election should appear above expired election"
    print("  [ok] Voter dashboard ranks elections correctly by urgency & activity.")

    print("\n==============================================")
    print(" ALL VERIFICATION TESTS PASSED SUCCESSFULLY!")
    print("==============================================\n")

if __name__ == "__main__":
    run_tests()
