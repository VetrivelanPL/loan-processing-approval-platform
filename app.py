"""Loan Processing and Approval Platform - academic demonstration application.

Run locally with: python app.py
The seeded accounts are for demonstration only. Change the SECRET_KEY and passwords
before deploying anywhere outside a local academic environment.
"""
from __future__ import annotations

import csv
import io
import os
import sqlite3
from datetime import date, datetime
from functools import wraps
from pathlib import Path
from typing import Optional

from flask import (Flask, Response, abort, flash, g, redirect, render_template,
                   request, send_from_directory, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

BASE_DIR = Path(__file__).resolve().parent
DATABASE = Path(os.environ.get("LOAN_DB_PATH", BASE_DIR / "loan_platform.db"))
UPLOAD_DIR = Path(os.environ.get("LOAN_UPLOAD_DIR", BASE_DIR / "uploads"))
ALLOWED_EXTENSIONS = {"pdf", "png", "jpg", "jpeg"}
MAX_UPLOAD_BYTES = 5 * 1024 * 1024

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get("SECRET_KEY", "dev-only-change-this-secret-key"),
    MAX_CONTENT_LENGTH=MAX_UPLOAD_BYTES,
    UPLOAD_FOLDER=str(UPLOAD_DIR),
)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS customers (
    customer_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
    phone TEXT NOT NULL,
    address TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS loan_products (
    product_id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_name TEXT NOT NULL UNIQUE,
    interest_rate REAL NOT NULL CHECK (interest_rate >= 0),
    max_amount REAL NOT NULL CHECK (max_amount > 0),
    tenure_months INTEGER NOT NULL CHECK (tenure_months > 0),
    status TEXT NOT NULL DEFAULT 'Active' CHECK (status IN ('Active', 'Inactive'))
);
CREATE TABLE IF NOT EXISTS administrators (
    admin_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS loan_officers (
    officer_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
    phone TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS loan_applications (
    application_id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER NOT NULL REFERENCES customers(customer_id),
    product_id INTEGER NOT NULL REFERENCES loan_products(product_id),
    application_date TEXT NOT NULL,
    requested_amount REAL NOT NULL CHECK (requested_amount > 0),
    status TEXT NOT NULL,
    remarks TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS documents (
    document_id INTEGER PRIMARY KEY AUTOINCREMENT,
    application_id INTEGER NOT NULL REFERENCES loan_applications(application_id) ON DELETE CASCADE,
    document_type TEXT NOT NULL,
    file_path TEXT NOT NULL,
    verification_status TEXT NOT NULL DEFAULT 'Pending',
    uploaded_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS eligibility_assessments (
    assessment_id INTEGER PRIMARY KEY AUTOINCREMENT,
    application_id INTEGER NOT NULL UNIQUE REFERENCES loan_applications(application_id),
    officer_id INTEGER NOT NULL REFERENCES loan_officers(officer_id),
    assessment_date TEXT NOT NULL,
    eligibility_status TEXT NOT NULL,
    remarks TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS approvals (
    approval_id INTEGER PRIMARY KEY AUTOINCREMENT,
    application_id INTEGER NOT NULL UNIQUE REFERENCES loan_applications(application_id),
    officer_id INTEGER NOT NULL REFERENCES loan_officers(officer_id),
    decision TEXT NOT NULL,
    decision_date TEXT NOT NULL,
    remarks TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS loans (
    loan_id INTEGER PRIMARY KEY AUTOINCREMENT,
    application_id INTEGER NOT NULL UNIQUE REFERENCES loan_applications(application_id),
    approved_amount REAL NOT NULL,
    interest_rate REAL NOT NULL,
    tenure_months INTEGER NOT NULL,
    emi_amount REAL NOT NULL,
    start_date TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS repayments (
    repayment_id INTEGER PRIMARY KEY AUTOINCREMENT,
    loan_id INTEGER NOT NULL REFERENCES loans(loan_id) ON DELETE CASCADE,
    due_date TEXT NOT NULL,
    amount REAL NOT NULL,
    payment_date TEXT,
    payment_status TEXT NOT NULL DEFAULT 'Pending' CHECK (payment_status IN ('Pending', 'Paid'))
);
"""


def connect_db() -> sqlite3.Connection:
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_db() -> None:
    # A sqlite3.Connection context manager commits/rolls back, but does not close
    # the connection. Explicitly close it so Windows can remove temporary test DBs.
    db = connect_db()
    try:
        with db:
            db.executescript(SCHEMA)
            if db.execute("SELECT COUNT(*) FROM administrators").fetchone()[0] == 0:
                db.execute(
                    "INSERT INTO administrators(name,email,password_hash) VALUES(?,?,?)",
                    ("System Administrator", "admin@loan.local", generate_password_hash("Admin@123")),
                )
            if db.execute("SELECT COUNT(*) FROM loan_officers").fetchone()[0] == 0:
                db.execute(
                    "INSERT INTO loan_officers(name,email,phone,password_hash) VALUES(?,?,?,?)",
                    ("Demo Loan Officer", "officer@loan.local", "9000000001", generate_password_hash("Officer@123")),
                )
            if db.execute("SELECT COUNT(*) FROM customers").fetchone()[0] == 0:
                db.execute(
                    "INSERT INTO customers(name,email,phone,address,password_hash) VALUES(?,?,?,?,?)",
                    ("Demo Customer", "customer@loan.local", "9000000002", "Chennai, Tamil Nadu", generate_password_hash("Customer@123")),
                )
            if db.execute("SELECT COUNT(*) FROM loan_products").fetchone()[0] == 0:
                db.executemany(
                    "INSERT INTO loan_products(product_name,interest_rate,max_amount,tenure_months,status) VALUES(?,?,?,?,?)",
                    [
                        ("Personal Loan", 10.5, 500000, 36, "Active"),
                        ("Education Loan", 8.25, 1500000, 120, "Active"),
                        ("Home Improvement Loan", 9.0, 1000000, 60, "Active"),
                    ],
                )
    finally:
        db.close()


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = connect_db()
    return g.db


@app.teardown_appcontext
def close_db(_error: Optional[BaseException] = None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def get_user_by_email(email: str) -> Optional[dict]:
    db = get_db()
    records = [
        ("Customer", "customers", "customer_id", "name, email, password_hash, is_active"),
        ("Loan Officer", "loan_officers", "officer_id", "name, email, password_hash, is_active"),
        ("Administrator", "administrators", "admin_id", "name, email, password_hash, is_active"),
    ]
    for role, table, id_col, fields in records:
        row = db.execute(f"SELECT {id_col} AS id, {fields} FROM {table} WHERE email = ? COLLATE NOCASE", (email,)).fetchone()
        if row:
            result = dict(row)
            result["role"] = role
            return result
    return None


def get_user_by_email_and_role(email: str, role: str) -> Optional[dict]:
    """Find an account only within the role explicitly selected on the login form."""
    role_tables = {
        "Customer": ("customers", "customer_id", "name, email, password_hash, is_active"),
        "Loan Officer": ("loan_officers", "officer_id", "name, email, password_hash, is_active"),
        "Administrator": ("administrators", "admin_id", "name, email, password_hash, is_active"),
    }
    if role not in role_tables:
        return None
    table, id_col, fields = role_tables[role]
    row = get_db().execute(
        f"SELECT {id_col} AS id, {fields} FROM {table} WHERE email = ? COLLATE NOCASE",
        (email,),
    ).fetchone()
    if not row:
        return None
    result = dict(row)
    result["role"] = role
    return result


def get_account_counts() -> dict[str, int]:
    """Return the total number of registered accounts for each supported role."""
    db = get_db()
    return {
        "Customer": db.execute("SELECT COUNT(*) FROM customers").fetchone()[0],
        "Loan Officer": db.execute("SELECT COUNT(*) FROM loan_officers").fetchone()[0],
        "Administrator": db.execute("SELECT COUNT(*) FROM administrators").fetchone()[0],
    }


def current_user() -> Optional[dict]:
    if "user" not in g:
        if session.get("user_id") and session.get("role"):
            role = session["role"]
            table_map = {
                "Customer": ("customers", "customer_id"),
                "Loan Officer": ("loan_officers", "officer_id"),
                "Administrator": ("administrators", "admin_id"),
            }
            table, id_col = table_map.get(role, (None, None))
            row = get_db().execute(f"SELECT {id_col} AS id, * FROM {table} WHERE {id_col} = ? AND is_active = 1", (session["user_id"],)).fetchone() if table else None
            g.user = dict(row) | {"role": role} if row else None
        else:
            g.user = None
    return g.user


@app.context_processor
def inject_user():
    return {"current_user": current_user(), "today": date.today().isoformat()}


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user():
            flash("Please sign in to continue.", "warning")
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def roles_required(*roles):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            user = current_user()
            if not user:
                flash("Please sign in to continue.", "warning")
                return redirect(url_for("login"))
            if user["role"] not in roles:
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorator


def application_with_details(application_id: int):
    return get_db().execute(
        """SELECT a.*, c.name AS customer_name, c.email AS customer_email, c.phone AS customer_phone,
                  p.product_name, p.interest_rate AS product_interest_rate, p.max_amount, p.tenure_months AS product_tenure
           FROM loan_applications a JOIN customers c ON c.customer_id=a.customer_id
           JOIN loan_products p ON p.product_id=a.product_id WHERE a.application_id=?""",
        (application_id,),
    ).fetchone()


def user_can_view_application(app_row) -> bool:
    user = current_user()
    return bool(user and (user["role"] in ("Administrator", "Loan Officer") or
                          (user["role"] == "Customer" and user["id"] == app_row["customer_id"])))


def calculate_emi(principal: float, annual_rate: float, months: int) -> float:
    """Calculate a fixed monthly EMI using the standard reducing-balance formula."""
    monthly_rate = annual_rate / 1200.0
    if months <= 0 or principal <= 0:
        raise ValueError("Principal and tenure must be positive.")
    if monthly_rate == 0:
        return round(principal / months, 2)
    factor = (1 + monthly_rate) ** months
    return round(principal * monthly_rate * factor / (factor - 1), 2)


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route("/")
def root():
    # The public landing page has been removed; start at sign-in.
    return redirect(url_for("login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        phone = request.form.get("phone", "").strip()
        address = request.form.get("address", "").strip()
        password = request.form.get("password", "")
        if not all([name, email, phone, address, password]):
            flash("Complete every field before registering.", "danger")
        elif len(password) < 8:
            flash("Password must contain at least 8 characters.", "danger")
        elif get_user_by_email(email):
            flash("An account with this email already exists.", "danger")
        else:
            get_db().execute(
                "INSERT INTO customers(name,email,phone,address,password_hash) VALUES(?,?,?,?,?)",
                (name, email, phone, address, generate_password_hash(password)),
            )
            get_db().commit()
            flash("Registration successful. You can now sign in.", "success")
            return redirect(url_for("login"))
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    account_counts = get_account_counts()
    if request.method == "POST":
        role = request.form.get("role", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        user = get_user_by_email_and_role(email, role)
        if not user or not user["is_active"] or not check_password_hash(user["password_hash"], password):
            flash("Invalid account type, email, or password, or the account is inactive.", "danger")
        else:
            session.clear()
            session["user_id"] = user["id"]
            session["role"] = user["role"]
            flash(f"Welcome, {user['name']}.", "success")
            destination = request.args.get("next", "")
            if destination.startswith("/") and not destination.startswith("//"):
                return redirect(destination)
            return redirect(url_for("dashboard"))
    return render_template("login.html", account_counts=account_counts)


@app.route("/logout")
def logout():
    session.clear()
    flash("You have signed out.", "info")
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():
    user = current_user()
    db = get_db()
    if user["role"] == "Customer":
        applications = db.execute(
            """SELECT a.*, p.product_name FROM loan_applications a JOIN loan_products p ON p.product_id=a.product_id
               WHERE a.customer_id=? ORDER BY a.application_id DESC""", (user["id"],)
        ).fetchall()
        loans = db.execute(
            """SELECT l.*, a.application_id, p.product_name FROM loans l JOIN loan_applications a ON a.application_id=l.application_id
               JOIN loan_products p ON p.product_id=a.product_id WHERE a.customer_id=? ORDER BY l.loan_id DESC""", (user["id"],)
        ).fetchall()
        return render_template("dashboard_customer.html", applications=applications, loans=loans)
    if user["role"] == "Loan Officer":
        applications = db.execute(
            """SELECT a.*, c.name AS customer_name, p.product_name FROM loan_applications a
               JOIN customers c ON c.customer_id=a.customer_id JOIN loan_products p ON p.product_id=a.product_id
               WHERE a.status NOT IN ('Draft','Approved','Rejected') ORDER BY a.application_id"""
        ).fetchall()
        return render_template("dashboard_officer.html", applications=applications)
    stats = {
        "customers": db.execute("SELECT COUNT(*) FROM customers").fetchone()[0],
        "products": db.execute("SELECT COUNT(*) FROM loan_products WHERE status='Active'").fetchone()[0],
        "applications": db.execute("SELECT COUNT(*) FROM loan_applications").fetchone()[0],
        "pending": db.execute("SELECT COUNT(*) FROM loan_applications WHERE status NOT IN ('Approved','Rejected')").fetchone()[0],
    }
    recent = db.execute(
        """SELECT a.*, c.name AS customer_name, p.product_name FROM loan_applications a
           JOIN customers c ON c.customer_id=a.customer_id JOIN loan_products p ON p.product_id=a.product_id
           ORDER BY a.application_id DESC LIMIT 8"""
    ).fetchall()
    return render_template("dashboard_admin.html", stats=stats, applications=recent)


@app.route("/apply", methods=["GET", "POST"])
@roles_required("Customer")
def apply_for_loan():
    db = get_db()
    products = db.execute("SELECT * FROM loan_products WHERE status='Active' ORDER BY product_name").fetchall()
    if request.method == "POST":
        try:
            product_id = int(request.form.get("product_id", "0"))
            amount = float(request.form.get("requested_amount", "0"))
        except ValueError:
            product_id, amount = 0, 0
        product = db.execute("SELECT * FROM loan_products WHERE product_id=? AND status='Active'", (product_id,)).fetchone()
        if not product:
            flash("Select a valid active loan product.", "danger")
        elif amount <= 0 or amount > product["max_amount"]:
            flash(f"Enter an amount greater than zero and no more than ₹{product['max_amount']:,.0f}.", "danger")
        else:
            cursor = db.execute(
                "INSERT INTO loan_applications(customer_id,product_id,application_date,requested_amount,status) VALUES(?,?,?,?,?)",
                (current_user()["id"], product_id, date.today().isoformat(), amount, "Draft"),
            )
            db.commit()
            application_id = cursor.lastrowid
            flash(f"Draft application #{application_id} created. Upload supporting documents, then submit it for review.", "success")
            return redirect(url_for("application_detail", application_id=application_id))
    return render_template("apply.html", products=products)


@app.route("/application/<int:application_id>/submit", methods=["POST"])
@roles_required("Customer")
def submit_application(application_id):
    db = get_db()
    app_row = application_with_details(application_id)
    if not app_row:
        abort(404)
    if app_row["customer_id"] != current_user()["id"]:
        abort(403)
    if app_row["status"] != "Draft":
        flash("Only a draft application can be submitted.", "warning")
    else:
        pending_count = db.execute("SELECT COUNT(*) FROM documents WHERE application_id=? AND verification_status='Pending'", (application_id,)).fetchone()[0]
        if pending_count == 0:
            flash("Upload at least one supporting document before submitting the application.", "danger")
        else:
            db.execute("UPDATE loan_applications SET status='Submitted' WHERE application_id=?", (application_id,))
            db.commit()
            flash("Application submitted. It is now waiting for document verification.", "success")
    return redirect(url_for("application_detail", application_id=application_id))


@app.route("/application/<int:application_id>")
@login_required
def application_detail(application_id):
    app_row = application_with_details(application_id)
    if not app_row:
        abort(404)
    if not user_can_view_application(app_row):
        abort(403)
    db = get_db()
    documents = db.execute("SELECT * FROM documents WHERE application_id=? ORDER BY document_id DESC", (application_id,)).fetchall()
    pending_document_count = db.execute("SELECT COUNT(*) FROM documents WHERE application_id=? AND verification_status='Pending'", (application_id,)).fetchone()[0]
    assessment = db.execute("SELECT * FROM eligibility_assessments WHERE application_id=?", (application_id,)).fetchone()
    approval = db.execute("SELECT * FROM approvals WHERE application_id=?", (application_id,)).fetchone()
    loan = db.execute("SELECT * FROM loans WHERE application_id=?", (application_id,)).fetchone()
    repayments = db.execute("SELECT * FROM repayments WHERE loan_id=? ORDER BY due_date", (loan["loan_id"],)).fetchall() if loan else []
    return render_template("application_detail.html", application=app_row, documents=documents,
                           pending_document_count=pending_document_count, assessment=assessment,
                           approval=approval, loan=loan, repayments=repayments)


@app.route("/application/<int:application_id>/upload", methods=["POST"])
@roles_required("Customer")
def upload_documents(application_id):
    app_row = application_with_details(application_id)
    if not app_row:
        abort(404)
    if app_row["customer_id"] != current_user()["id"]:
        abort(403)
    if app_row["status"] not in ("Submitted", "Draft", "Under Document Verification"):
        flash("Documents can no longer be changed at this stage.", "warning")
        return redirect(url_for("application_detail", application_id=application_id))
    files = [f for f in request.files.getlist("documents") if f and f.filename]
    if not files:
        flash("Choose at least one document to upload.", "danger")
        return redirect(url_for("application_detail", application_id=application_id))
    invalid = [f.filename for f in files if not allowed_file(f.filename)]
    if invalid:
        flash("Only PDF, PNG, JPG, and JPEG files are accepted.", "danger")
        return redirect(url_for("application_detail", application_id=application_id))
    folder = UPLOAD_DIR / f"application_{application_id}"
    folder.mkdir(parents=True, exist_ok=True)
    db = get_db()
    if app_row["status"] == "Draft":
        # Keep previously rejected files as history without treating them as current evidence.
        db.execute("UPDATE documents SET verification_status='Superseded' WHERE application_id=? AND verification_status='Correction Required'", (application_id,))
    for file in files:
        safe_name = secure_filename(file.filename)
        stored_name = f"{datetime.now().strftime('%Y%m%d%H%M%S%f')}_{safe_name}"
        file.save(folder / stored_name)
        doc_type = request.form.get("document_type", "Supporting Document").strip() or "Supporting Document"
        db.execute(
            "INSERT INTO documents(application_id,document_type,file_path,verification_status,uploaded_at) VALUES(?,?,?,?,?)",
            (application_id, doc_type, f"application_{application_id}/{stored_name}", "Pending", datetime.now().isoformat(timespec="seconds")),
        )
    # Preserve the explicit Draft → Submitted → Under Document Verification state sequence.
    # Uploads in Draft remain drafts until the customer submits; extra uploads on an already
    # submitted application do not skip the officer's start-verification action.
    db.commit()
    if app_row["status"] == "Draft":
        flash("Documents uploaded successfully. Submit the draft when the required files are ready.", "success")
    elif app_row["status"] == "Submitted":
        flash("Additional documents uploaded. The officer can start verification when ready.", "success")
    else:
        flash("Additional documents uploaded to the application.", "success")
    return redirect(url_for("application_detail", application_id=application_id))


@app.route("/uploads/<path:filename>")
@roles_required("Administrator", "Loan Officer")
def view_upload(filename):
    # Uploads are not publicly exposed; staff must be authenticated to retrieve them.
    return send_from_directory(UPLOAD_DIR, filename, as_attachment=False)


@app.route("/officer/application/<int:application_id>/action", methods=["POST"])
@roles_required("Loan Officer")
def officer_action(application_id):
    db = get_db()
    app_row = application_with_details(application_id)
    if not app_row:
        abort(404)
    action = request.form.get("action", "")
    remarks = request.form.get("remarks", "").strip()
    officer_id = current_user()["id"]
    current_status = app_row["status"]

    if action == "begin_verification":
        docs = db.execute("SELECT COUNT(*) FROM documents WHERE application_id=? AND verification_status='Pending'", (application_id,)).fetchone()[0]
        if current_status != "Submitted":
            flash("Document verification can only start after the customer submits the application.", "warning")
        elif docs == 0:
            flash("Cannot start verification without pending supporting documents.", "danger")
        else:
            db.execute("UPDATE loan_applications SET status='Under Document Verification', remarks=? WHERE application_id=?", (remarks, application_id))
            db.commit()
            flash("Document verification started.", "success")
    elif action == "verify_documents":
        docs = db.execute("SELECT COUNT(*) FROM documents WHERE application_id=? AND verification_status='Pending'", (application_id,)).fetchone()[0]
        if docs == 0:
            flash("Cannot verify an application without pending supporting documents.", "danger")
        elif current_status != "Under Document Verification":
            flash("This application is not waiting for document verification.", "warning")
        else:
            db.execute("UPDATE documents SET verification_status='Verified' WHERE application_id=? AND verification_status='Pending'", (application_id,))
            db.execute("UPDATE loan_applications SET status='Under Eligibility Assessment', remarks=? WHERE application_id=?", (remarks, application_id))
            db.commit()
            flash("Documents verified. The application moved to eligibility assessment.", "success")
    elif action == "request_correction":
        if current_status not in ("Submitted", "Under Document Verification"):
            flash("Document correction cannot be requested at this stage.", "warning")
        else:
            db.execute("UPDATE documents SET verification_status='Correction Required' WHERE application_id=?", (application_id,))
            db.execute("UPDATE loan_applications SET status='Draft', remarks=? WHERE application_id=?", (remarks or "Please upload corrected documents.", application_id))
            db.commit()
            flash("Correction requested. The customer can upload corrected documents.", "success")
    elif action in ("assess_eligible", "assess_ineligible"):
        if current_status != "Under Eligibility Assessment":
            flash("Eligibility can only be assessed after document verification.", "warning")
        else:
            eligible = action == "assess_eligible"
            status = "Under Review" if eligible else "Rejected"
            eligibility_status = "Eligible" if eligible else "Not Eligible"
            db.execute("INSERT INTO eligibility_assessments(application_id,officer_id,assessment_date,eligibility_status,remarks) VALUES(?,?,?,?,?)",
                       (application_id, officer_id, date.today().isoformat(), eligibility_status, remarks))
            db.execute("UPDATE loan_applications SET status=?, remarks=? WHERE application_id=?", (status, remarks, application_id))
            if not eligible:
                db.execute("INSERT INTO approvals(application_id,officer_id,decision,decision_date,remarks) VALUES(?,?,?,?,?)",
                           (application_id, officer_id, "Rejected", date.today().isoformat(), remarks or "Not eligible"))
            db.commit()
            flash("Eligibility assessment saved.", "success")
    elif action in ("approve", "reject"):
        if current_status != "Under Review":
            flash("A decision can only be made after eligibility assessment.", "warning")
        else:
            decision = "Approved" if action == "approve" else "Rejected"
            db.execute("INSERT INTO approvals(application_id,officer_id,decision,decision_date,remarks) VALUES(?,?,?,?,?)",
                       (application_id, officer_id, decision, date.today().isoformat(), remarks))
            db.execute("UPDATE loan_applications SET status=?, remarks=? WHERE application_id=?", (decision, remarks, application_id))
            if decision == "Approved":
                product = db.execute("SELECT * FROM loan_products WHERE product_id=?", (app_row["product_id"],)).fetchone()
                principal = float(app_row["requested_amount"])
                months = int(product["tenure_months"])
                emi = calculate_emi(principal, float(product["interest_rate"]), months)
                cursor = db.execute("INSERT INTO loans(application_id,approved_amount,interest_rate,tenure_months,emi_amount,start_date) VALUES(?,?,?,?,?,?)",
                                    (application_id, principal, product["interest_rate"], months, emi, date.today().isoformat()))
                loan_id = cursor.lastrowid
                # Schedule is a planning record; the payment gateway is not integrated.
                from calendar import monthrange
                start = date.today()
                for month_no in range(1, months + 1):
                    month_index = start.month - 1 + month_no
                    year = start.year + month_index // 12
                    month = month_index % 12 + 1
                    day = min(start.day, monthrange(year, month)[1])
                    due = date(year, month, day).isoformat()
                    db.execute("INSERT INTO repayments(loan_id,due_date,amount,payment_status) VALUES(?,?,?,'Pending')", (loan_id, due, emi))
            db.commit()
            flash(f"Application {decision.lower()}.", "success")
    else:
        flash("Unknown workflow action.", "danger")
    return redirect(url_for("application_detail", application_id=application_id))


@app.route("/repayment/<int:repayment_id>/pay", methods=["POST"])
@roles_required("Customer")
def mark_repayment_paid(repayment_id):
    db = get_db()
    row = db.execute(
        """SELECT r.*, a.customer_id FROM repayments r JOIN loans l ON l.loan_id=r.loan_id
           JOIN loan_applications a ON a.application_id=l.application_id WHERE r.repayment_id=?""", (repayment_id,)
    ).fetchone()
    if not row:
        abort(404)
    if row["customer_id"] != current_user()["id"]:
        abort(403)
    if row["payment_status"] != "Paid":
        db.execute("UPDATE repayments SET payment_status='Paid', payment_date=? WHERE repayment_id=?", (date.today().isoformat(), repayment_id))
        db.commit()
        flash("Repayment marked as paid in the demonstration system. No real payment was processed.", "success")
    return redirect(url_for("dashboard"))


@app.route("/admin/products", methods=["GET", "POST"])
@roles_required("Administrator")
def manage_products():
    db = get_db()
    if request.method == "POST":
        name = request.form.get("product_name", "").strip()
        try:
            rate = float(request.form.get("interest_rate", "0"))
            max_amount = float(request.form.get("max_amount", "0"))
            months = int(request.form.get("tenure_months", "0"))
        except ValueError:
            rate, max_amount, months = -1, 0, 0
        if not name or rate < 0 or max_amount <= 0 or months <= 0:
            flash("Enter a valid product name, non-negative interest rate, positive amount, and positive tenure.", "danger")
        else:
            try:
                db.execute("INSERT INTO loan_products(product_name,interest_rate,max_amount,tenure_months,status) VALUES(?,?,?,?, 'Active')",
                           (name, rate, max_amount, months))
                db.commit()
                flash("Loan product added.", "success")
                return redirect(url_for("manage_products"))
            except sqlite3.IntegrityError:
                db.rollback()
                flash("A product with this name already exists.", "danger")
    products = db.execute("SELECT * FROM loan_products ORDER BY product_id DESC").fetchall()
    return render_template("manage_products.html", products=products)


@app.route("/admin/products/<int:product_id>/toggle", methods=["POST"])
@roles_required("Administrator")
def toggle_product(product_id):
    db = get_db()
    product = db.execute("SELECT * FROM loan_products WHERE product_id=?", (product_id,)).fetchone()
    if not product:
        abort(404)
    new_status = "Inactive" if product["status"] == "Active" else "Active"
    db.execute("UPDATE loan_products SET status=? WHERE product_id=?", (new_status, product_id))
    db.commit()
    flash(f"Product marked {new_status.lower()}.", "success")
    return redirect(url_for("manage_products"))


@app.route("/admin/users")
@roles_required("Administrator")
def manage_users():
    rows = get_db().execute(
        """SELECT customer_id AS id, name, email, 'Customer' AS role, is_active FROM customers
           UNION ALL SELECT officer_id AS id, name, email, 'Loan Officer' AS role, is_active FROM loan_officers
           UNION ALL SELECT admin_id AS id, name, email, 'Administrator' AS role, is_active FROM administrators
           ORDER BY role, name"""
    ).fetchall()
    return render_template("manage_users.html", users=rows)


@app.route("/admin/users/<role>/<int:user_id>/toggle", methods=["POST"])
@roles_required("Administrator")
def toggle_user(role, user_id):
    table_map = {"customer": ("customers", "customer_id"), "officer": ("loan_officers", "officer_id"), "administrator": ("administrators", "admin_id")}
    if role not in table_map:
        abort(404)
    table, id_col = table_map[role]
    if role == "administrator" and user_id == current_user()["id"]:
        flash("You cannot deactivate your own active administrator account.", "warning")
        return redirect(url_for("manage_users"))
    db = get_db()
    row = db.execute(f"SELECT is_active FROM {table} WHERE {id_col}=?", (user_id,)).fetchone()
    if not row:
        abort(404)
    db.execute(f"UPDATE {table} SET is_active=? WHERE {id_col}=?", (0 if row["is_active"] else 1, user_id))
    db.commit()
    flash("User account status updated.", "success")
    return redirect(url_for("manage_users"))


@app.route("/admin/reports.csv")
@roles_required("Administrator")
def export_report():
    rows = get_db().execute(
        """SELECT a.application_id, c.name AS customer, c.email, p.product_name, a.application_date,
                  a.requested_amount, a.status, a.remarks FROM loan_applications a
           JOIN customers c ON c.customer_id=a.customer_id JOIN loan_products p ON p.product_id=a.product_id
           ORDER BY a.application_id"""
    ).fetchall()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Application ID", "Customer", "Email", "Loan Product", "Application Date", "Requested Amount", "Status", "Remarks"])
    writer.writerows([tuple(row) for row in rows])
    return Response(output.getvalue(), mimetype="text/csv", headers={"Content-Disposition": "attachment; filename=loan_application_report.csv"})


@app.errorhandler(403)
def forbidden(_error):
    return render_template("error.html", code=403, message="You do not have permission to access this page."), 403


@app.errorhandler(404)
def not_found(_error):
    return render_template("error.html", code=404, message="The requested page or record could not be found."), 404


@app.errorhandler(413)
def upload_too_large(_error):
    flash("Upload rejected: the combined upload size exceeds 5 MB.", "danger")
    return redirect(request.referrer or url_for("dashboard"))


with app.app_context():
    init_db()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "5000")), debug=os.environ.get("FLASK_DEBUG", "0") == "1")
