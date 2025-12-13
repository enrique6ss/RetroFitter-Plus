import os
import psycopg
from psycopg.rows import dict_row
from datetime import datetime
from functools import wraps
from flask import (
    Flask, g, render_template, request,
    redirect, session, send_file
)
import io, csv

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret")

DATABASE_URL = os.environ.get("DATABASE_URL")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin")


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


def init_db():
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


@app.before_request
def before():
    init_db()


# -----------------------------
# Auth
# -----------------------------
def admin_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if not session.get("admin"):
            return redirect("/admin/login")
        return f(*args, **kwargs)
    return wrapped


# -----------------------------
# Public Intake
# -----------------------------
@app.route("/", methods=["GET", "POST"])
def intake():
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


@app.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect("/admin/login")


@app.route("/admin")
@admin_required
def admin_dashboard():
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT * FROM requests ORDER BY id DESC")
    rows = cur.fetchall()
    return render_template("admin_dashboard.html", rows=rows)


@app.route("/admin/request/<int:id>", methods=["GET", "POST"])
@admin_required
def admin_request(id):
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
            id
        ))
        db.commit()

    cur.execute("SELECT * FROM requests WHERE id=%s", (id,))
    row = cur.fetchone()
    return render_template("admin_view.html", row=row)


@app.route("/admin/export.csv")
@admin_required
def export_csv():
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
    return send_file(
        mem,
        mimetype="text/csv",
        as_attachment=True,
        download_name="retrofitter_plus_requests.csv"
    )


if __name__ == "__main__":
    app.run()
