import os
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

# --------------------
# Database helpers
# --------------------
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
                text_consent TEXT
            );
        """)
    db.commit()

# --------------------
# Auth helper
# --------------------
def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("admin"):
            return redirect("/admin/login")
        return f(*args, **kwargs)
    return wrapper

# --------------------
# Routes
# --------------------
@app.route("/", methods=["GET", "POST"])
def intake():
    ensure_table()

    if request.method == "POST":
        db = get_db()
        with db.cursor() as cur:
            cur.execute("""
                INSERT INTO requests
                (created_at, name, phone, address, occupancy, escrow, lockbox, meeting, text_consent)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (
                datetime.utcnow(),
                request.form["name"],
                request.form["phone"],
                request.form["address"],
                request.form.get("occupancy"),
                request.form.get("escrow"),
                request.form.get("lockbox"),
                request.form.get("meeting"),
                "Yes" if request.form.get("text_me") else "No"
            ))
        db.commit()
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
