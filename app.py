import os
from datetime import datetime
from functools import wraps
from flask import Flask, render_template, request, redirect, session
import psycopg
from psycopg.rows import dict_row

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret")

DATABASE_URL = os.environ.get("DATABASE_URL")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin")

# ---------- DB ----------
def get_db():
    if not hasattr(app, "db"):
        app.db = psycopg.connect(DATABASE_URL, row_factory=dict_row)
    return app.db

def ensure_table():
    db = get_db()
    db.execute("""
        CREATE TABLE IF NOT EXISTS requests (
            id SERIAL PRIMARY KEY,
            created_at TIMESTAMP,
            name TEXT,
            phone TEXT,
            address TEXT,
            occupancy TEXT,
            escrow TEXT,
            lockbox TEXT,
            meeting TEXT,
            text_consent TEXT
        )
    """)
    db.commit()

# ---------- AUTH ----------
def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("admin"):
            return redirect("/admin/login")
        return f(*args, **kwargs)
    return wrapper

# ---------- ROUTES ----------
@app.route("/", methods=["GET", "POST"])
def intake():
    ensure_table()
    if request.method == "POST":
        db = get_db()
        db.execute("""
            INSERT INTO requests
            (created_at, name, phone, address, occupancy, escrow, lockbox, meeting, text_consent)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (
            datetime.utcnow(),
            request.form["name"],
            request.form["phone"],
            request.form["address"],
            request.form["occupancy"],
            request.form.get("escrow"),
            request.form["lockbox"],
            request.form["meeting"],
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
        if request.form["password"] == ADMIN_PASSWORD:
            session["admin"] = True
            return redirect("/admin")
    return render_template("admin_login.html")

@app.route("/admin")
@admin_required
def admin():
    ensure_table()
    db = get_db()
    rows = db.execute("SELECT * FROM requests ORDER BY id DESC").fetchall()
    return render_template("admin.html", rows=rows)

@app.route("/health")
def health():
    return "OK", 200
