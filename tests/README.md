# Automated Test Suite

The project includes Flask route tests and Selenium end-to-end browser
tests for the Loan Processing and Approval Platform.

## Prerequisites

-   Python 3.10 or later
-   Dependencies installed from `requirements.txt`
-   Google Chrome or Chromium
-   A compatible Selenium WebDriver environment

## Installation

From the project root directory, install the dependencies:

``` bash
python -m pip install -r requirements.txt
```

## Running the Tests

Start the Flask application in one terminal:

``` bash
python app.py
```

Keep the application running. Open a second terminal in the project root
directory and execute:

``` bash
python -m unittest discover -s tests -v
```

The command runs the test suite and displays each test result.

## Test Coverage

The automated tests cover:

-   Flask route and application behavior
-   Login-first navigation and role selection
-   Invalid login handling
-   Administrator product management
-   Loan officer dashboard functionality
-   Loan amount-limit validation
-   Role-based access control
-   EMI calculation
-   End-to-end application submission, document verification,
    eligibility assessment, approval, and repayment schedule generation

Route tests use an isolated temporary SQLite database.

The Selenium end-to-end test creates a uniquely named test customer,
creates and submits an application, uploads a temporary PDF, completes
the loan officer review and approval workflow, and checks that the
approved loan and EMI details are displayed.

The end-to-end test may create persistent customer and application
records in the database used by the running application. Run it against
a separate test database when existing demonstration data must be
preserved. Temporary uploaded test documents are cleaned up by the test.

## Optional Configuration

  -------------------------------------------------------------------------
  Variable                Purpose                 Default
  ----------------------- ----------------------- -------------------------
  `BASE_URL`              Base URL of the running `http://127.0.0.1:5000`
                          application

  `HEADLESS`              Controls whether the    Headless mode
                          browser runs visibly

  `SELENIUM_WAIT`         Explicit wait duration  Configured test default
                          in seconds
  -------------------------------------------------------------------------

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

If browser startup fails, verify that Chrome or Chromium is installed
and that Selenium can obtain or access a compatible WebDriver.

## Reporting Results

Test outcomes must reflect actual execution. Record the test run
summary, failures, and reproducible defects in the project test records.
Investigate failed tests before reporting the corresponding
functionality as passing.
