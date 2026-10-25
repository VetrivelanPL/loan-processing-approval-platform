# Loan Processing and Approval Platform

A database-backed web application developed for the Software
Engineering project. The platform supports customer registration, loan
product management, loan applications, document verification,
eligibility assessment, approval decisions, and repayment tracking. The
project follows the Agile Software Development Life Cycle (SDLC).

## Features

### Customer

-   Register and log in using password hashing.
-   Browse active loan products and submit applications.
-   Upload supporting PDF, JPG, JPEG, and PNG documents.
-   Track application status and loan officer remarks.
-   View approved loan details, monthly Equated Monthly Installments
    (EMI), and repayment schedules.
-   Update repayment status for demonstration purposes only.

### Loan Officer

-   Review submitted applications.
-   Verify documents or request corrections.
-   Record eligibility assessments.
-   Approve or reject applications after assessment.
-   Generate a loan record and repayment schedule after approval.

### Administrator

-   Add loan products and activate or deactivate products.
-   Review users and manage account access.
-   View platform metrics and export application records to CSV.

## Application Workflow

`Draft → Submitted → Under Document Verification → Under Eligibility Assessment → Under Review → Approved / Rejected`

When corrections are requested, the application returns to the draft
stage. The customer can upload corrected documents and resubmit the
application for verification.

## Technology Stack

-   Python 3.10 or later
-   Flask for routing, sessions, and server-side functionality
-   SQLite for relational data storage
-   HTML, CSS, and Jinja templates for the user interface
-   Selenium WebDriver for automated browser testing
-   Jira for task, sprint, and defect tracking

## Project Structure

``` text
loan-processing-approval-platform/
├── app.py
├── requirements.txt
├── README.md
├── static/
├── templates/
└── tests/
    ├── README.md
    ├── test_routes.py
    └── test_selenium_e2e.py
```

The local virtual environment, database, uploaded documents, private
screenshots, and generated report drafts are kept separate from the
public source repository.

## Installation and Setup

### Prerequisites

-   Python 3.10 or later
-   pip
-   Google Chrome or Chromium for Selenium tests

### 1. Create a Virtual Environment

Windows PowerShell:

``` powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
```

macOS or Linux:

``` bash
python3 -m venv .venv
source .venv/bin/activate
```

### 2. Install Dependencies

``` bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 3. Configure the Flask Secret Key

Set a strong secret through the `SECRET_KEY` environment variable before
running the application outside a local development environment.

Windows PowerShell:

``` powershell
$env:SECRET_KEY = "replace-with-a-strong-random-secret"
```

macOS or Linux:

``` bash
export SECRET_KEY="replace-with-a-strong-random-secret"
```

Replace the example value with a securely generated secret. Never commit
real secrets or production credentials.

### 4. Run the Application

``` bash
python app.py
```

Open `http://127.0.0.1:5000` in a browser. The root URL redirects to the
sign-in page. Database initialization and demonstration account setup
are handled by the application.

## Demonstration Accounts

  Role            Email                   Password
  --------------- ----------------------- ----------------
  Customer        `customer@loan.local`   `Customer@123`
  Loan Officer    `officer@loan.local`    `Officer@123`
  Administrator   `admin@loan.local`      `Admin@123`

These credentials are intended for local academic demonstrations only.
They must not be used for a publicly accessible deployment. Production
use requires secure account provisioning, strong credentials, and
appropriate security controls.

## Automated Testing

The project includes Flask route tests and Selenium end-to-end browser
tests. Coverage includes application navigation, role selection, login
validation, administrator product management, loan officer
functionality, amount-limit validation, role-based authorization, EMI
calculation, and the loan approval workflow.

Start the application in one terminal:

``` bash
python app.py
```

Keep it running and execute the tests from a second terminal in the
project directory:

``` bash
python -m unittest discover -s tests -v
```

Optional Selenium configuration:

Windows PowerShell:

``` powershell
$env:BASE_URL = "http://127.0.0.1:5000"
$env:HEADLESS = "0"
$env:SELENIUM_WAIT = "15"
python -m unittest discover -s tests -v
```

macOS or Linux:

``` bash
BASE_URL=http://127.0.0.1:5000 HEADLESS=0 SELENIUM_WAIT=15 python -m unittest discover -s tests -v
```

Setting `HEADLESS` to `0` enables visible browser execution. Selenium
requires a compatible browser and WebDriver environment.

Route tests use an isolated temporary SQLite database. The end-to-end
test exercises the customer-to-approval workflow and may create
additional customer and application records in the database used by the
running application. Use a separate test database when existing
demonstration records must be preserved. Test results must reflect
actual execution.

## Jira Project Management

The `jira/` directory contains a starter backlog, import notes, and a
project setup guide. Jira is used to organize tasks, manage sprint
progress, record testing activities, and track reproducible defects. The
live Jira workspace is maintained separately from the application source
code.

Defect records should include reproducible steps, expected and actual
results, severity, and supporting evidence where available.

## Documentation

The `docs/` directory contains report content, evidence and submission
checklists, test cases, a bug log template, a screenshot capture guide,
validation status, source diagrams, and a report generation script.
Final report files, application screenshots, Jira evidence, and the
demonstration video are maintained separately from the source code.

## Data Model

The application uses ten core entities: Customers, Loan Products,
Administrators, Loan Officers, Loan Applications, Documents, Eligibility
Assessments, Approvals, Loans, and Repayments. Product tenure is stored
in months to support EMI calculations and repayment scheduling.

## Limitations

-   This is an academic prototype, not a production lending system.
-   Eligibility decisions are recorded by loan officers; no external
    credit bureau or automated credit-scoring service is integrated.
-   Repayment status is simulated. No real financial transactions or
    payment gateway are connected.
-   Notifications are limited to application feedback and workflow
    messages; email and SMS delivery are not integrated.
-   Upload validation uses file-extension and request-size restrictions.
    Production deployment would require stronger content validation,
    malware scanning, secure storage, and retention controls.
-   Additional production security measures include CSRF protection,
    audit logging, hardened session configuration, secure deployment
    settings, and a security review.
-   The Flask development server and demonstration credentials are
    intended for local development only.
