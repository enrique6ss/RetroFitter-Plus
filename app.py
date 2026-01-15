import os
from datetime import datetime
from functools import wraps
from flask import Flask, render_template, request, redirect, session, g
import psycopg
from psycopg.rows import dict_row
import smtplib
from email.message import EmailMessage

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret")

DATABASE_URL = os.environ.get("DATABASE_URL")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is missing")

# -------------------------------------------------
# Database helpers
# -------------------------------------------------
def get_db():
    if "db" not in g:
        g.db = psycopg.connect(DATABASE_URL, row_factory=dict_row)
    return g.db

@app.teardown_appcontext
def close_db(error):
    db = g.pop("db", None)
    if db:
        db.close()

def ensure_table():
    db = get_db()
    with db.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS requests (
                id SERIAL PRIMARY KEY,
                created_at TIMESTAMP NOT NULL,
                name TEXT NOT NULL,
                phone TEXT NOT NULL,
                address TEXT NOT NULL,
                occupancy TEXT,
                escrow TEXT,
                lockbox TEXT,
                meeting TEXT,
                text_consent TEXT,
                status TEXT DEFAULT 'New'
            );
            ALTER TABLE requests
            ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'New';
        """)
    db.commit()

# -------------------------------------------------
# Email notification (SendGrid SMTP)
# -------------------------------------------------
def send_notification_email(data):
    try:
        from_email = os.environ["FROM_EMAIL"]
        notify_email = os.environ["NOTIFY_EMAIL"]
        api_key = os.environ["SENDGRID_API_KEY"]

        print("EMAIL DEBUG: FROM_EMAIL =", from_email)
        print("EMAIL DEBUG: NOTIFY_EMAIL =", notify_email)
        print("EMAIL DEBUG: API KEY starts with =", api_key[:6], "...")

        msg = EmailMessage()
        msg["Subject"] = "New Inspection Request – RetroFitter Plus"
        msg["From"] = from_email
        msg["To"] = notify_email

        msg.set_content(
            "New inspection request received:\n\n"
            f"Name: {data['name']}\n"
            f"Phone: {data['phone']}\n"
            f"Address: {data['address']}\n"
            f"Occupied: {data['occupancy']}\n"
            f"Escrow Date: {data['escrow']}\n"
            f"Lockbox: {data['lockbox']}\n"
            f"Meeting: {data['meeting']}\n"
            f"Text Consent: {data['text_consent']}\n"
        )

        with smtplib.SMTP("smtp.sendgrid.net", 587, timeout=20) as server:
            server.set_debuglevel(1)  # shows SMTP conversation in Railway logs
            server.starttls()
            server.login("apikey", api_key)
            server.send_message(msg)

        print("EMAIL DEBUG: ✅ Email sent successfully")

    except Exception as e:
        print("EMAIL DEBUG: ❌ Email failed:", repr(e))
        raise

# -------------------------------------------------
# Auth helper
# -------------------------------------------------
def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("admin"):
            return redirect("/admin/login")
        return f(*args, **kwargs)
    return wrapper

# -------------------------------------------------
# Routes
# -------------------------------------------------
@app.route("/", methods=["GET", "POST"])
def intake():
    ensure_table()

    if request.method == "POST":
        data = {
            "name": request.form["name"],
            "phone": request.form["phone"],
            "address": request.form["address"],
            "occupancy": request.form.get("occupancy"),
            "escrow": request.form.get("escrow"),
            "lockbox": request.form.get("lockbox"),
            "meeting": request.form.get("meeting"),
            "text_consent": "Yes" if request.form.get("text_me") else "No"
        }

        db = get_db()
        with db.cursor() as cur:
            cur.execute("""
                INSERT INTO requests
                (created_at, name, phone, address, occupancy, escrow, lockbox, meeting, text_consent, status)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (
                datetime.utcnow(),
                data["name"],
                data["phone"],
                data["address"],
                data["occupancy"],
                data["escrow"],
                data["lockbox"],
                data["meeting"],
                data["text_consent"],
                "New"
            ))
        db.commit()

        # Send email notification
        send_notification_email(data)

        return redirect("/success")

    return render_template("intake.html")

@app.route("/success")
def success():
    return render_template("success.html")

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        if request.form.get("password") == ADMIN_PASSWORD:
            session["admin"] = True
            return redirect("/admin")
    return render_template("admin_login.html")

@app.route("/admin")
@admin_required
def admin_dashboard():
    ensure_table()
    db = get_db()
    with db.cursor() as cur:
        cur.execute("SELECT * FROM requests ORDER BY id DESC")
        rows = cur.fetchall()
    return render_template("admin_dashboard.html", rows=rows)

@app.route("/health")
def health():
    return "OK", 200