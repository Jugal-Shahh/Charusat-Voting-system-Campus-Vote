"""
scratch/test_recover_password.py — Test suite for admin password recovery.
"""

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app import app, get_db
from werkzeug.security import check_password_hash, generate_password_hash


class TestRecoverPassword(unittest.TestCase):
    def setUp(self):
        self.app = app
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    def test_recover_password_flow(self):
        test_email = "admin_recovery_test@charusat.edu.in"
        test_username = "admin_recovery_user"
        initial_pw = "OldPassword123!"

        with self.app.app_context():
            db = get_db()
            db.execute("DELETE FROM admins WHERE LOWER(google_email) = LOWER(?)", (test_email,))
            db.execute(
                """INSERT INTO admins (google_email, username, password_hash, role)
                   VALUES (?, ?, ?, 'admin')""",
                (test_email, test_username, generate_password_hash(initial_pw)),
            )
            db.commit()

        # Simulate authenticated Google email in session
        with self.client.session_transaction() as sess:
            sess["google_email"] = test_email
            sess["google_name"] = test_username

        # Step 1: Access recover password form
        r1 = self.client.get("/admin/recover-password")
        self.assertEqual(r1.status_code, 200)
        self.assertIn(b"Password Recovery", r1.data)
        self.assertIn(test_email.encode(), r1.data)

        # Step 2: Submit new password
        new_pw = "BrandNewPassword2026!"
        r2 = self.client.post(
            "/admin/recover-password",
            data={"password": new_pw, "confirm_password": new_pw},
            follow_redirects=True,
        )
        self.assertEqual(r2.status_code, 200)
        self.assertIn(b"Password updated successfully", r2.data)

        # Step 3: Verify new password in DB
        with self.app.app_context():
            db = get_db()
            admin = db.execute("SELECT password_hash FROM admins WHERE LOWER(google_email) = LOWER(?)", (test_email,)).fetchone()
            self.assertTrue(check_password_hash(admin["password_hash"], new_pw))
            # Clean up
            db.execute("DELETE FROM admins WHERE LOWER(google_email) = LOWER(?)", (test_email,))
            db.commit()

        print("  [OK] Admin password recovery flow verified.")


if __name__ == "__main__":
    unittest.main()
