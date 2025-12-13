import os
import io
import csv
import psycopg
from psycopg.rows import dict_row
from datetime import datetime
from functools import wraps
from flask import Flask, g, render_template, request, redirect, session, send_file

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret")

DATABASE_URL = os.environ.get("DATABASE_URL")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")

# -----------------------------
# Database
# -----------------------------
def get_db():
    if "db" not in g:
        g.db = psycopg.connect(DATABASE_URL, row_factory=dict_row)
    return g.db


@app.teardown_appcontext
def close_db(_):
    db = g.pop("db", None)
    if db:
        db.close()


def ensure_tables():
    db = get_db()
    cur = db.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS requests (
            id SERIAL PRIMARY KEY,
            created_at TIMESTAMPTZ NOT NULL,
            name TEXT NOT NULL,
            phone TEXT NOT NULL,
            address TEXT NOT NULL,
            occupancy TEXT NOT NULL,
            escrow_date DATE,
            lockbox TEXT NOT NULL,
            meeting_someone TEXT NOT NULL,
            text_consent TEXT NOT NULL DEFAULT 'No',
            status TEXT NOT NULL DEFAULT 'New',
            admin_notes TEXT
        )
    """)
    db.commit()


# -----------------------------
# Health check (CRITICAL)
# -----------------------------
@app.route("/health")
def health():
    return "OK", 200


# -----------------------------
# Auth
# -----------------------------
def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("admin"):
            return redirect("/admin/login")
        return f(*args, **kwargs)
    return wrapper


# -----------------------------
# Public Intake
# -----------------------------
@app.route("/", methods=["GET", "POST"])
def intake():
    ensure_tables()

    if request.method == "POST":
        text_consent = "Yes" if request.form.get("text_consent") else "No"

        db = get_db()
        cur = db.cursor()
        cur.execute("""
            INSERT INTO requests
            (created_at, name, phone, address, occupancy,
             escrow_date, lockbox, meeting_someone, text_consent)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (
            datetime.utcnow(),
            request.form["name"],
            request.form["phone"],
            request.form["address"],
            request.form["occupancy"],
            request.form.get("escrow_date") or None,
            request.form["lockbox"],
            request.form["meeting_someone"],
            text_consent
        ))
        db.commit()
        return redirect("/success")

    return render_template("intake.html")


@app.route("/success")
def success():
    return render_template("success.html")


# -----------------------------
# Admin
# -----------------------------
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        if request.form["password"] == ADMIN_PASSWORD:
            session["admin"] = True
            return redirect("/admin")
    return render_template("admin_login.html")


@app.route("/admin")
@admin_required
def admin_dashboard():
    ensure_tables()
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT * FROM requests ORDER BY id DESC")
    rows = cur.fetchall()
    return render_template("admin_dashboard.html", rows=rows)


@app.route("/admin/request/<int:req_id>", methods=["GET", "POST"])
@admin_required
def admin_request(req_id):
    ensure_tables()
    db = get_db()
    cur = db.cursor()

    if request.method == "POST":
        cur.execute("""
            UPDATE requests
            SET status=%s, admin_notes=%s
            WHERE id=%s
        """, (
            request.form["status"],
            request.form["admin_notes"],
            req_id
        ))
        db.commit()

    cur.execute("SELECT * FROM requests WHERE id=%s", (req_id,))
    row = cur.fetchone()
    return render_template("admin_view.html", row=row)


@app.route("/admin/export.csv")
@admin_required
def export_csv():
    ensure_tables()
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT * FROM requests ORDER BY id DESC")
    rows = cur.fetchall()

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=rows[0].keys())
    writer.writeheader()
    writer.writerows(rows)

    mem = io.BytesIO(output.getvalue().encode("utf-8"))
    mem.seek(0)
    return send_file(mem, mimetype="text/csv", as_attachment=True)
