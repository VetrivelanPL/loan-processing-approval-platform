"""Fast, isolated route/database tests. Requires Flask (see requirements.txt)."""
import io
import tempfile
import unittest
from pathlib import Path

import app as loan_app_module


class LoanFlowRouteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="loanflow_test_")
        root = Path(self.temp.name)
        loan_app_module.DATABASE = root / "test.db"
        loan_app_module.UPLOAD_DIR = root / "uploads"
        loan_app_module.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        loan_app_module.app.config.update(TESTING=True, SECRET_KEY="test-secret", UPLOAD_FOLDER=str(loan_app_module.UPLOAD_DIR))
        loan_app_module.init_db()
        self.client = loan_app_module.app.test_client()

    def tearDown(self):
        self.temp.cleanup()

    def login(self, email, password, role="Customer"):
        return self.client.post("/login", data={"role": role, "email": email, "password": password}, follow_redirects=True)

    def test_root_redirects_to_login_page(self):
        response = self.client.get("/", follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.location.endswith("/login"))
        login_response = self.client.get(response.location)
        self.assertEqual(login_response.status_code, 200)
        self.assertIn(b"Sign in", login_response.data)
        self.assertIn(b"name=\"role\"", login_response.data)
        self.assertIn(b"Customer accounts", login_response.data)
        self.assertIn(b"Loan Officer accounts", login_response.data)
        self.assertIn(b"Administrator accounts", login_response.data)
        self.assertNotIn(b"A clearer path from application to approval", login_response.data)

    def test_invalid_login_is_rejected(self):
        response = self.login("missing@example.test", "wrong-password", "Customer")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Invalid account type, email, or password", response.data)

    def test_selected_role_must_match_the_account(self):
        response = self.login("customer@loan.local", "Customer@123", "Administrator")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Invalid account type, email, or password", response.data)

    def test_customer_cannot_open_admin_page(self):
        self.login("customer@loan.local", "Customer@123")
        response = self.client.get("/admin/products")
        self.assertEqual(response.status_code, 403)

    def test_requested_amount_above_product_limit_is_rejected(self):
        self.login("customer@loan.local", "Customer@123")
        response = self.client.post("/apply", data={"product_id": "1", "requested_amount": "999999"}, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Enter an amount greater than zero", response.data)
        with loan_app_module.app.app_context():
            count = loan_app_module.get_db().execute("SELECT COUNT(*) FROM loan_applications").fetchone()[0]
        self.assertEqual(count, 0)

    def test_customer_to_approved_loan_creates_emi_and_repayments(self):
        self.login("customer@loan.local", "Customer@123")
        response = self.client.post("/apply", data={"product_id": "1", "requested_amount": "120000"}, follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        application_id = int(response.location.rstrip("/").split("/")[-1])

        upload_response = self.client.post(
            f"/application/{application_id}/upload",
            data={
                "document_type": "Identity proof",
                "documents": (io.BytesIO(b"%PDF-1.4\nTest document\n%%EOF\n"), "identity.pdf"),
            },
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        self.assertEqual(upload_response.status_code, 200)
        self.assertIn(b"Documents uploaded successfully", upload_response.data)
        with loan_app_module.app.app_context():
            draft_status = loan_app_module.get_db().execute("SELECT status FROM loan_applications WHERE application_id=?", (application_id,)).fetchone()["status"]
        self.assertEqual(draft_status, "Draft")
        submit_response = self.client.post(f"/application/{application_id}/submit", follow_redirects=True)
        self.assertIn(b"Application submitted", submit_response.data)

        self.client.get("/logout")
        self.login("officer@loan.local", "Officer@123", "Loan Officer")
        response = self.client.post(f"/officer/application/{application_id}/action", data={"action": "begin_verification", "remarks": "Review started"}, follow_redirects=True)
        self.assertIn(b"Under Document Verification", response.data)
        response = self.client.post(f"/officer/application/{application_id}/action", data={"action": "verify_documents", "remarks": "Documents checked"}, follow_redirects=True)
        self.assertIn(b"Under Eligibility Assessment", response.data)
        response = self.client.post(f"/officer/application/{application_id}/action", data={"action": "assess_eligible", "remarks": "Eligible for review"}, follow_redirects=True)
        self.assertIn(b"Under Review", response.data)
        response = self.client.post(f"/officer/application/{application_id}/action", data={"action": "approve", "remarks": "Approved for demonstration"}, follow_redirects=True)
        self.assertIn(b"Approved", response.data)

        with loan_app_module.app.app_context():
            loan = loan_app_module.get_db().execute("SELECT * FROM loans WHERE application_id=?", (application_id,)).fetchone()
            repayment_count = loan_app_module.get_db().execute("SELECT COUNT(*) FROM repayments WHERE loan_id=?", (loan["loan_id"],)).fetchone()[0]
        self.assertGreater(loan["emi_amount"], 0)
        self.assertEqual(repayment_count, 36)

    def test_emi_calculation_handles_zero_interest(self):
        self.assertEqual(loan_app_module.calculate_emi(1200, 0, 12), 100.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
