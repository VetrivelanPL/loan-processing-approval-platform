"""Browser automation for LoanFlow.

Start the Flask server first, then run:
  BASE_URL=http://127.0.0.1:5000 python -m unittest discover -s tests -v

Requires Chrome/Chromium and a compatible Selenium WebDriver setup.
"""
import os
import tempfile
import time
import unittest
from pathlib import Path

from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait

BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:5000")
WAIT_SECONDS = int(os.environ.get("SELENIUM_WAIT", "10"))


class LoanFlowBrowserTests(unittest.TestCase):
    def setUp(self):
        options = webdriver.ChromeOptions()
        if os.environ.get("HEADLESS", "1") != "0":
            options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1440,1000")
        try:
            self.driver = webdriver.Chrome(options=options)
        except WebDriverException as exc:
            self.skipTest(f"Chrome/WebDriver could not start in this environment: {exc}")
        self.wait = WebDriverWait(self.driver, WAIT_SECONDS)

    def tearDown(self):
        if getattr(self, "driver", None):
            self.driver.quit()

    def open(self, path="/"):
        self.driver.get(BASE_URL.rstrip("/") + path)

    def wait_for_status(self, expected):
        """Wait for a workflow status and print useful evidence if it times out."""
        try:
            self.wait.until(EC.text_to_be_present_in_element((By.CLASS_NAME, "status-large"), expected))
        except TimeoutException:
            status_nodes = self.driver.find_elements(By.CLASS_NAME, "status-large")
            actual_status = status_nodes[0].text.strip() if status_nodes else "<status element missing>"
            flash_nodes = self.driver.find_elements(By.CSS_SELECTOR, ".flash-danger, .flash-warning, .flash-success, .flash-info")
            flash_messages = [node.text.strip() for node in flash_nodes if node.text.strip()]
            print(f"\nSELENIUM STATUS DEBUG: expected={expected!r}; actual={actual_status!r}")
            print(f"SELENIUM URL: {self.driver.current_url}")
            print(f"SELENIUM FLASH MESSAGES: {flash_messages!r}")
            screenshot_path = Path.cwd() / "selenium_failure.png"
            self.driver.save_screenshot(str(screenshot_path))
            print(f"SELENIUM SCREENSHOT: {screenshot_path}")
            raise

    def login(self, email, password, role="Customer"):
        self.open("/login")

        self.wait.until(
            EC.visibility_of_element_located((By.ID, "login-form"))
        )

        role_field = Select(self.driver.find_element(By.ID, "role"))
        role_field.select_by_value(role)

        email_value = email.strip().lower()

        self.driver.execute_script("""
            const email = document.getElementById('email');
            const password = document.getElementById('password');

            email.value = arguments[0];
            email.dispatchEvent(new Event('input', {bubbles: true}));
            email.dispatchEvent(new Event('change', {bubbles: true}));

            password.value = arguments[1];
            password.dispatchEvent(new Event('input', {bubbles: true}));
            password.dispatchEvent(new Event('change', {bubbles: true}));
        """, email_value, password)

        diagnostics = self.driver.execute_script("""
            const form = document.getElementById('login-form');
            return {
                emailFilled: !!document.getElementById('email').value,
                passwordLength: document.getElementById('password').value.length,
                role: document.getElementById('role').value,
                valid: form.checkValidity(),
                invalidFields: Array.from(form.querySelectorAll(':invalid'))
                    .map(el => el.id || el.name)
            };
        """)

        print("Login form diagnostics:", diagnostics)

        if not diagnostics["valid"]:
            self.fail(f"Login form is invalid: {diagnostics}")

        form = self.driver.find_element(By.ID, "login-form")
        submit_button = form.find_element(
            By.CSS_SELECTOR, "button[type='submit']"
        )

        self.driver.execute_script(
            "arguments[0].requestSubmit(arguments[1]);",
            form,
            submit_button
        )

        try:
            self.wait.until(
                lambda d: "/login" not in d.current_url
                or bool(d.find_elements(By.CLASS_NAME, "flash-danger"))
            )
        except TimeoutException:
            print("Login timed out.")
            print("URL:", self.driver.current_url)
            print(
                "Page:",
                self.driver.find_element(By.TAG_NAME, "body").text
            )
            raise

        if "/login" in self.driver.current_url:
            messages = [
                element.text
                for element in self.driver.find_elements(
                    By.CLASS_NAME, "flash-danger"
                )
                if element.text.strip()
            ]
            self.fail(
                f"Login failed for {email_value} ({role}). "
                f"Messages: {messages}"
            )
    def test_01_root_opens_login_page_without_landing_page(self):
        self.open("/")
        self.wait.until(EC.visibility_of_element_located((By.ID, "login-form")))
        self.assertTrue(self.driver.current_url.rstrip("/").endswith("/login"))
        self.assertEqual(len(self.driver.find_elements(By.CLASS_NAME, "product-card")), 0)
        self.assertNotIn("A clearer path", self.driver.page_source)

    def test_02_invalid_login_is_rejected(self):
        self.open("/login")
        Select(self.driver.find_element(By.ID, "role")).select_by_value("Customer")
        self.driver.find_element(By.ID, "email").send_keys("not-a-user@example.com")
        self.driver.find_element(By.ID, "password").send_keys("wrong-password")
        self.driver.find_element(By.CSS_SELECTOR, "#login-form button[type='submit']").click()
        alert = self.wait.until(EC.visibility_of_element_located((By.CLASS_NAME, "flash-danger")))
        self.assertIn("Invalid account type, email, or password", alert.text)

    def test_03_admin_can_open_product_management(self):
        self.login("admin@loan.local", "Admin@123", "Administrator")
        self.open("/admin/products")
        self.wait.until(EC.visibility_of_element_located((By.ID, "product-form")))
        self.assertIn("Loan product management", self.driver.find_element(By.TAG_NAME, "h1").text)
        self.assertGreaterEqual(len(self.driver.find_elements(By.CSS_SELECTOR, "table tbody tr")), 1)

    def test_04_officer_dashboard_displays_review_queue(self):
        self.login("officer@loan.local", "Officer@123", "Loan Officer")
        self.wait.until(EC.visibility_of_element_located((By.TAG_NAME, "h1")))
        self.assertIn("Application review queue", self.driver.find_element(By.TAG_NAME, "h1").text)

    def test_05_customer_application_to_approval_workflow(self):
        suffix = str(int(time.time() * 1000))
        email = f"selenium_{suffix}@example.test"
        self.open("/register")
        self.driver.find_element(By.ID, "name").send_keys("Selenium Test Customer")
        self.driver.find_element(By.ID, "email").send_keys(email)
        self.driver.find_element(By.ID, "phone").send_keys("9000012345")
        self.driver.find_element(By.ID, "address").send_keys("Chennai, Tamil Nadu")
        self.driver.find_element(By.ID, "password").send_keys("TestPass@123")
        self.driver.find_element(By.CSS_SELECTOR, "#register-form button[type='submit']").click()
        self.wait.until(EC.visibility_of_element_located((By.CLASS_NAME, "flash-success")))

        self.login(email, "TestPass@123")
        self.open("/apply")
        self.wait.until(EC.visibility_of_element_located((By.ID, "application-form")))
        select = Select(self.driver.find_element(By.ID, "product_id"))
        select.select_by_index(1)
        self.driver.find_element(By.ID, "requested_amount").send_keys("120000")
        self.driver.find_element(By.CSS_SELECTOR, "#application-form button[type='submit']").click()
        self.wait.until(EC.url_contains("/application/"))
        application_url = self.driver.current_url
        self.assertIn("Application #", self.driver.find_element(By.TAG_NAME, "h1").text)

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as sample:
            sample.write(b"%PDF-1.4\n% Selenium test document\n%%EOF\n")
            sample_path = sample.name
        try:
            self.driver.find_element(By.ID, "documents").send_keys(sample_path)

            upload_button = self.wait.until(
                EC.element_to_be_clickable(
                    (By.CSS_SELECTOR, "form[action*='/upload'] button[type='submit']")
                )
            )
            upload_button.click()

            self.wait.until(
                EC.visibility_of_element_located((By.CLASS_NAME, "flash-success"))
            )

            print("\n=== DEBUG: PAGE AFTER DOCUMENT UPLOAD ===")
            print("Current URL:", self.driver.current_url)
            print("Page text:")
            print(self.driver.find_element(By.TAG_NAME, "body").text)
            print(
                "Submit button count:",
                len(self.driver.find_elements(By.ID, "submit-application-button"))
            )

            submit_button = self.wait.until(
                EC.element_to_be_clickable((By.ID, "submit-application-button"))
            )
            submit_button.click()

            self.wait_for_status("Submitted")
        finally:
            Path(sample_path).unlink(missing_ok=True)

        self.open("/logout")
        self.login("officer@loan.local", "Officer@123", "Loan Officer")
        self.driver.get(application_url)
        self.wait.until(EC.visibility_of_element_located((By.ID, "officer-action-form")))
        self.driver.find_element(By.CSS_SELECTOR, "button[name='action'][value='begin_verification']").click()
        self.wait_for_status("Under Document Verification")
        verify_button = self.wait.until(
            EC.element_to_be_clickable(
                (By.CSS_SELECTOR, "button[name='action'][value='verify_documents']")
            )
        )
        self.driver.execute_script(
            "arguments[0].scrollIntoView({block: 'center'});",
            verify_button
        )
        self.driver.execute_script(
            "arguments[0].form.requestSubmit(arguments[0]);",
            verify_button
        )
        self.wait_for_status("Under Eligibility Assessment")
        eligible_button = self.wait.until(
            EC.element_to_be_clickable(
                (By.CSS_SELECTOR, "button[name='action'][value='assess_eligible']")
            )
        )
        self.driver.execute_script(
            "arguments[0].scrollIntoView({block: 'center'});",
            eligible_button
        )
        self.driver.execute_script(
            "arguments[0].form.requestSubmit(arguments[0]);",
            eligible_button
        )
        self.wait_for_status("Under Review")
        approve_button = self.wait.until(
            EC.element_to_be_clickable(
                (By.CSS_SELECTOR, "button[name='action'][value='approve']")
            )
        )
        self.driver.execute_script(
            "arguments[0].scrollIntoView({block: 'center'});",
            approve_button
        )
        self.driver.execute_script(
            "arguments[0].form.requestSubmit(arguments[0]);",
            approve_button
        )
        self.wait_for_status("Approved")
        self.assertIn("Monthly EMI", self.driver.page_source)
        self.assertIn("Loan and repayment schedule", self.driver.page_source)
        self.open("/logout")
        self.login(email, "TestPass@123")
        self.wait.until(EC.visibility_of_element_located((By.TAG_NAME, "h1")))
        self.assertIn("Your loan dashboard", self.driver.find_element(By.TAG_NAME, "h1").text)
        self.assertIn("monthly EMI", self.driver.page_source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
