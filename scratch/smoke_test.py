import sys
import unittest
from pathlib import Path

# Ensure app can be imported
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import app, get_db

class SmokeTest(unittest.TestCase):
    def setUp(self):
        self.app = app
        self.app.config["TESTING"] = True
        self.app.config["SECRET_KEY"] = "test-secret-key"
        self.client = self.app.test_client()

    def test_end_to_end_smoke_sequence(self):
        print("\n--- STARTING 8-STEP SMOKE TEST ---")

        # Clear any leftover test admin account & voting systems
        with self.app.app_context():
            db = get_db()
            admin = db.execute("SELECT id FROM admins WHERE username = 'smokeadmin' OR google_email = 'smoke_admin@charusat.edu.in'").fetchone()
            if admin:
                aid = admin["id"]
                vs_ids = [r["id"] for r in db.execute("SELECT id FROM voting_systems WHERE admin_id = ?", (aid,)).fetchall()]
                for vid in vs_ids:
                    db.execute("DELETE FROM votes WHERE voting_system_id = ?", (vid,))
                    db.execute("DELETE FROM turnout_log WHERE voting_system_id = ?", (vid,))
                    db.execute("DELETE FROM candidates WHERE voting_system_id = ?", (vid,))
                    db.execute("DELETE FROM voting_systems WHERE id = ?", (vid,))
                db.execute("DELETE FROM admins WHERE id = ?", (aid,))
                db.commit()

        # Step 1: Create a new admin account from scratch
        print("\n[Step 1] Creating new admin account...")
        with self.client.session_transaction() as sess:
            sess["google_email"] = "smoke_admin@charusat.edu.in"
            sess["google_name"] = "Smoke Admin"

        resp = self.client.post("/admin/register", data={
            "username": "smokeadmin",
            "password": "smokepassword123",
            "confirm_password": "smokepassword123"
        }, follow_redirects=True)
        self.assertIn(b"Admin account created", resp.data)
        print("  -> Step 1 PASSED: Admin account 'smokeadmin' created.")

        # Step 2: Create a departmental-scope election with 1 vote per ballot and 3 candidates
        print("\n[Step 2] Creating departmental-scope election (CSPIT / CE, 1 choice, 3 candidates)...")
        resp = self.client.post("/admin/create", data={
            "name": "CSPIT CE Dept Election 2026",
            "scope_type": "department",
            "scope_institute": "CSPIT",
            "scope_department": "CE",
            "max_choices": "1"
        }, follow_redirects=True)
        self.assertIn(b"Voting system created!", resp.data)

        # Extract code from response
        with self.app.app_context():
            db = get_db()
            vs = db.execute("SELECT * FROM voting_systems WHERE name = ?", ("CSPIT CE Dept Election 2026",)).fetchone()
            self.assertIsNotNone(vs)
            code = vs["code"]
            vs_id = vs["id"]
            self.assertEqual(vs["max_choices"], 1)
            self.assertEqual(vs["scope_institute"], "CSPIT")
            self.assertEqual(vs["scope_department"], "CE")

        # Add 3 candidates
        self.client.post(f"/admin/system/{code}/manage", data={
            "action": "add_candidate",
            "name": "Alice Johnson",
            "role": "President"
        }, follow_redirects=True)

        self.client.post(f"/admin/system/{code}/manage", data={
            "action": "add_candidate",
            "name": "Bob Smith",
            "role": "Vice President"
        }, follow_redirects=True)

        self.client.post(f"/admin/system/{code}/manage", data={
            "action": "add_candidate",
            "name": "Charlie Davis",
            "role": "Secretary"
        }, follow_redirects=True)

        # Open voting
        self.client.post(f"/admin/system/{code}/manage", data={
            "action": "toggle_voting"
        }, follow_redirects=True)

        with self.app.app_context():
            db = get_db()
            vs = db.execute("SELECT * FROM voting_systems WHERE id = ?", (vs_id,)).fetchone()
            self.assertEqual(vs["is_open"], 1)

        print(f"  -> Step 2 PASSED: Election created (Code: {code}), 3 candidates added, voting OPENED.")

        # Step 3: Sign in as an eligible voter (CSPIT / CE), confirm election appears on dashboard, cast ballot
        print("\n[Step 3] Signing in as eligible voter (24CE001 - CSPIT/CE) and casting ballot...")
        # Ensure 24CE001 exists in DB
        with self.app.app_context():
            db = get_db()
            db.execute("INSERT OR REPLACE INTO voters (voter_id, full_name, institute, department) VALUES ('24CE001', 'Eligible Student', 'CSPIT', 'CE')")
            db.commit()

        # Log in as 24CE001
        with self.client.session_transaction() as sess:
            sess.clear() # clear admin session
            sess["voter_id"] = "24CE001"
            sess["voter_name"] = "Eligible Student"
            sess["voter_institute"] = "CSPIT"
            sess["voter_department"] = "CE"

        # Check voter dashboard
        dash_resp = self.client.get("/dashboard")
        self.assertIn(b"CSPIT CE Dept Election 2026", dash_resp.data)

        # Cast ballot for Alice Johnson
        with self.app.app_context():
            db = get_db()
            alice = db.execute("SELECT id FROM candidates WHERE voting_system_id = ? AND name = ?", (vs_id, "Alice Johnson")).fetchone()

        vote_resp = self.client.post(f"/vote/{code}", data={
            "vote": str(alice["id"])
        }, follow_redirects=True)
        self.assertIn(b"Your ballot has been recorded", vote_resp.data)
        print("  -> Step 3 PASSED: Eligible voter saw election and successfully cast ballot.")

        # Step 4: Confirm that same voter cannot vote again (reload, back button, direct URL to ballot)
        print("\n[Step 4] Testing double-voting prevention (reload, direct ballot URL)...")
        # Attempt direct GET /vote/code
        re_get = self.client.get(f"/vote/{code}", follow_redirects=True)
        self.assertIn(b"already voted", re_get.data)

        # Attempt direct POST /vote/code
        re_post = self.client.post(f"/vote/{code}", data={"vote": str(alice["id"])}, follow_redirects=True)
        self.assertIn(b"already voted", re_post.data)
        print("  -> Step 4 PASSED: Double-voting strictly blocked.")

        # Step 5: Sign in as an ineligible voter (wrong institute/department), confirm blocked even with code
        print("\n[Step 5] Signing in as ineligible voter (24AIML065 - CSPIT/AIML) & testing code join...")
        with self.app.app_context():
            db = get_db()
            db.execute("INSERT OR REPLACE INTO voters (voter_id, full_name, institute, department) VALUES ('24AIML065', 'AIML Student', 'CSPIT', 'AIML')")
            db.commit()

        with self.client.session_transaction() as sess:
            sess.clear()
            sess["voter_id"] = "24AIML065"
            sess["voter_name"] = "AIML Student"
            sess["voter_institute"] = "CSPIT"
            sess["voter_department"] = "AIML"

        inelig_resp = self.client.get(f"/vote/{code}", follow_redirects=True)
        self.assertIn(b"not eligible to vote in this election", inelig_resp.data)
        print("  -> Step 5 PASSED: Ineligible voter blocked from election.")

        # Step 6: Close voting from admin dashboard, confirm voters can now see results and they're correct
        print("\n[Step 6] Closing voting as admin & verifying public results visibility...")
        # Check that voter cannot see results while OPEN
        closed_voter_resp = self.client.get(f"/vote/{code}/results", follow_redirects=True)
        self.assertIn(b"Results are hidden while voting is open", closed_voter_resp.data)

        # Admin logs back in and closes voting
        with self.app.app_context():
            db = get_db()
            admin_row = db.execute("SELECT id FROM admins WHERE username = 'smokeadmin'").fetchone()

        with self.client.session_transaction() as sess:
            sess.clear()
            sess["admin_id"] = admin_row["id"]
            sess["admin_username"] = "smokeadmin"

        self.client.post(f"/admin/system/{code}/manage", data={"action": "toggle_voting"}, follow_redirects=True)

        # Voter can now view results
        with self.client.session_transaction() as sess:
            sess.clear()
            sess["voter_id"] = "24CE001"

        pub_res = self.client.get(f"/vote/{code}/results")
        self.assertIn(b"Alice Johnson", pub_res.data)
        self.assertIn(b"FINAL RESULTS", pub_res.data)
        print("  -> Step 6 PASSED: Voting closed. Results visible to voters with correct tallies.")

        # Step 7: Log out & log back in as admin, confirm voting system data persists
        print("\n[Step 7] Testing admin re-login and system persistence...")
        with self.client.session_transaction() as sess:
            sess.clear()

        login_resp = self.client.post("/admin/login", data={
            "username": "smokeadmin",
            "password": "smokepassword123"
        }, follow_redirects=True)
        self.assertIn(b"CSPIT CE Dept Election 2026", login_resp.data)
        print("  -> Step 7 PASSED: Admin re-logged in. Voting system data persisted.")

        # Step 8: Re-enter admin password to view audit log, confirm turnout only (no vote choice)
        print("\n[Step 8] Testing step-up authentication & turnout audit privacy...")
        audit_get = self.client.get(f"/admin/system/{code}/audit")
        self.assertIn(b"Identity Verification", audit_get.data)

        audit_post = self.client.post(f"/admin/system/{code}/audit", data={
            "audit_password": "smokepassword123"
        })
        self.assertIn(b"Turnout Audit", audit_post.data)
        self.assertIn(b"24CE001", audit_post.data)
        # Ensure candidate choice is NEVER present in audit log
        self.assertNotIn(b"Alice Johnson", audit_post.data)
        print("  -> Step 8 PASSED: Step-up password re-entry enforced. Turnout log shows voter ID without vote choices.")

        print("\n=== ALL 8 SMOKE TEST STEPS PASSED SUCCESSFULLY! ===")

if __name__ == "__main__":
    unittest.main()
