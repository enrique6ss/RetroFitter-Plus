import os
import json
import threading
import urllib.request
from datetime import datetime
from functools import wraps
from flask import Flask, render_template, request, redirect, session, g
import psycopg
from psycopg.rows import dict_row

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
# SendGrid Email via HTTP API (no SMTP)
# -------------------------------------------------
def _sendgrid_send_email(payload: dict):
    """
    Runs in a background thread.
    Never raises.
    Uses SendGrid Web API (HTTPS) to avoid SMTP timeouts.
    """
    try:
        api_key = os.environ.get("SENDGRID_API_KEY")
        from_email = os.environ.get("FROM_EMAIL")
        to_email = os.environ.get("NOTIFY_EMAIL")

        if not api_key or not from_email or not to_email:
            print("EMAIL DEBUG: Missing SENDGRID_API_KEY / FROM_EMAIL / NOTIFY_EMAIL on WEB service")
            return

        subject = f"New Inspection Request #{payload.get('id','')} – RetroFitter Plus"

        text_body = (
            "New inspection request received:\n\n"
            f"Request ID: {payload.get('id','')}\n"
            f"Name: {payload.get('name')}\n"
            f"Phone: {payload.get('phone')}\n"
            f"Address: {payload.get('address')}\n"
            f"Occupied: {payload.get('occupancy')}\n"
            f"Escrow Date: {payload.get('escrow')}\n"
            f"Lockbox: {payload.get('lockbox')}\n"
            f"Meeting: {payload.get('meeting')}\n"
            f"Text Consent: {payload.get('text_consent')}\n"
        )

        sg_payload = {
            "personalizations": [{"to": [{"email": to_email}]}],
            "from": {"email": from_email},
            "subject": subject,
            "content": [{"type": "text/plain", "value": text_body}],
        }

        req = urllib.request.Request(
            url="https://api.sendgrid.com/v3/mail/send",
            data=json.dumps(sg_payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=10) as resp:
            # SendGrid returns 202 Accepted on success
            status = resp.status

        if status == 202:
            print("EMAIL DEBUG: ✅ Email sent via SendGrid API")
        else:
            print("EMAIL DEBUG: ❌ Unexpected SendGrid status:", status)

    except Exception as e:
        print("EMAIL DEBUG: ❌ SendGrid API email failed:", repr(e))

def send_email_async(payload: dict):
    t = threading.Thread(target=_sendgrid_send_email, args=(payload,), daemon=True)
    t.start()

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
        try:
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

            # Save request and get its ID
            db = get_db()
            with db.cursor() as cur:
                cur.execute("""
                    INSERT INTO requests
                    (created_at, name, phone, address, occupancy, escrow, lockbox, meeting, text_consent, status)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    RETURNING id
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
                new_id = cur.fetchone()["id"]
            db.commit()

            # Fire-and-forget email (does not block)
            data["id"] = new_id
            send_email_async(data)

            return redirect("/success")

        except Exception as e:
            print("SUBMIT ERROR:", repr(e))
            return "Submit failed. Please try again or contact RetroFitter Plus.", 500

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
