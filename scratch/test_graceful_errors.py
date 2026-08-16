"""
scratch/test_graceful_errors.py — Test suite for graceful error handling & OAuth-based eligibility.
"""

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app import app, get_db, voter_is_eligible


class TestGracefulErrors(unittest.TestCase):
    def setUp(self):
        self.app = app
        self.app.config["TESTING"] = True
        self.app.config["SECRET_KEY"] = "test-graceful-key"
        self.client = self.app.test_client()

    def test_case_1_non_charusat_email_rejection(self):
        """Case 1: Sign in with non-CHARUSAT email (e.g. @gmail.com) -> clean rejection, no crash."""
        resp = self.client.post("/dev/login", data={"voter_id": "testuser@gmail.com"}, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Please sign in with your official CHARUSAT email.", resp.data)
        print("  [OK] Case 1: Non-CHARUSAT email cleanly rejected.")

    def test_case_2_unparseable_charusat_email(self):
        """Case 2: Right domain but unparseable student ID -> clean rejection message."""
        resp = self.client.post("/dev/login", data={"voter_id": "randomperson999@charusat.edu.in"}, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"We couldn&#39;t verify your student ID from this account", resp.data)
        print("  [OK] Case 2: Unparseable CHARUSAT student ID cleanly rejected.")

    def test_case_3_ineligible_election_redirects_to_dashboard(self):
        """Case 3: Student signs in, attempts to vote in another dept's election -> redirected to dashboard with clean error."""
        with self.app.app_context():
            db = get_db()
            # Create a test election for CSPIT / CS
            admin = db.execute("SELECT id FROM admins LIMIT 1").fetchone()
            admin_id = admin["id"] if admin else 1
            code = "TSTCSE"
            db.execute("DELETE FROM voting_systems WHERE code = ?", (code,))
            db.execute(
                """INSERT INTO voting_systems (name, scope_type, scope_institute, scope_department, code, admin_id, is_open)
                   VALUES ('CSPIT CS Only Election', 'department', 'CSPIT', 'CS', ?, ?, 1)""",
                (code, admin_id),
            )
            db.commit()

        # Sign in as a DEPSTAR student (24DCE001)
        resp = self.client.post("/dev/login", data={"voter_id": "24DCE001"}, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Welcome", resp.data)

        # Attempt to access the CSPIT / CS election
        vote_resp = self.client.get(f"/vote/{code}", follow_redirects=True)
        self.assertEqual(vote_resp.status_code, 200)
        self.assertIn(b"This election isn&#39;t open to your institute/department.", vote_resp.data)
        self.assertIn(b"Voter Dashboard", vote_resp.data)
        print("  [OK] Case 3: Ineligible department access cleanly redirected to dashboard.")

    def test_case_4_valid_account_not_in_voters_table(self):
        """Case 4: Student from institute never imported (e.g. IIIM 24BBA001) signs in -> parsed directly from OAuth."""
        with self.app.app_context():
            db = get_db()
            db.execute("DELETE FROM voters WHERE voter_id = '24BBA001'")
            db.commit()

        # Sign in via dev/login as 24BBA001
        resp = self.client.post("/dev/login", data={"voter_id": "24bba001@charusat.edu.in"}, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"IIIM", resp.data)
        self.assertIn(b"BBA", resp.data)
        self.assertIn(b"24BBA001", resp.data)

        # Verify session
        with self.client.session_transaction() as sess:
            self.assertEqual(sess["voter_institute"], "IIIM")
            self.assertEqual(sess["voter_department"], "BBA")
            self.assertEqual(sess["voter_id"], "24BBA001")
        print("  [OK] Case 4: Student not in static roster identified purely via email parsing.")

    def test_case_5_display_name_captured(self):
        """Case 5: Google display name is captured and displayed in welcome header."""
        with self.client.session_transaction() as sess:
            sess["voter_id"] = "24AIML099"
            sess["voter_name"] = "Priya Patel"
            sess["voter_institute"] = "CSPIT"
            sess["voter_department"] = "AIML"

        resp = self.client.get("/dashboard")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Welcome, Priya Patel", resp.data)
        print("  [OK] Case 5: Custom Google display name rendered in welcome header.")


if __name__ == "__main__":
    unittest.main()
