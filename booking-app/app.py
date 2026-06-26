import os
import sqlite3
import requests
from datetime import datetime
from functools import wraps
from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, g
)

app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "fallback-secret-key")

DATABASE = os.path.join(os.path.dirname(__file__), "bookings.db")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
GOOGLE_MEET_LINK = os.environ.get("GOOGLE_MEET_LINK", "https://meet.google.com/your-link")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")


def get_db():
    db = getattr(g, "_database", None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db


@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, "_database", None)
    if db is not None:
        db.close()


def init_db():
    with app.app_context():
        db = get_db()
        db.executescript("""
            CREATE TABLE IF NOT EXISTS slots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                slot_date TEXT NOT NULL,
                slot_time TEXT NOT NULL,
                is_booked INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS bookings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                slot_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                email TEXT NOT NULL,
                notes TEXT,
                booked_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (slot_id) REFERENCES slots(id)
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            );
        """)
        db.commit()


def send_telegram_notification(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        requests.post(url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "HTML"
        }, timeout=5)
    except Exception:
        pass


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("admin_logged_in"):
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return decorated


@app.route("/")
def index():
    import json
    db = get_db()
    today = datetime.now().strftime("%Y-%m-%d")
    slots = db.execute(
        "SELECT * FROM slots WHERE is_booked = 0 AND slot_date >= ? ORDER BY slot_date, slot_time",
        (today,)
    ).fetchall()

    slots_by_date = {}
    for slot in slots:
        date = slot["slot_date"]
        if date not in slots_by_date:
            slots_by_date[date] = []
        slots_by_date[date].append({"id": slot["id"], "time": slot["slot_time"]})

    return render_template(
        "index.html",
        slots_json=json.dumps(slots_by_date),
        meet_link=GOOGLE_MEET_LINK
    )


@app.route("/book/<int:slot_id>", methods=["GET", "POST"])
def book(slot_id):
    db = get_db()
    slot = db.execute(
        "SELECT * FROM slots WHERE id = ? AND is_booked = 0", (slot_id,)
    ).fetchone()

    if not slot:
        flash("This slot is no longer available.", "error")
        return redirect(url_for("index"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        notes = request.form.get("notes", "").strip()

        if not name or not email:
            flash("Name and email are required.", "error")
            return render_template("book.html", slot=slot)

        db.execute(
            "INSERT INTO bookings (slot_id, name, email, notes) VALUES (?, ?, ?, ?)",
            (slot_id, name, email, notes)
        )
        db.execute("UPDATE slots SET is_booked = 1 WHERE id = ?", (slot_id,))
        db.commit()

        slot_display = f"{slot['slot_date']} at {slot['slot_time']}"
        msg = (
            f"<b>New Booking!</b>\n"
            f"Name: {name}\n"
            f"Email: {email}\n"
            f"Slot: {slot_display}\n"
            f"Notes: {notes or 'None'}"
        )
        send_telegram_notification(msg)

        return redirect(url_for("confirmation", slot_id=slot_id, name=name, email=email))

    return render_template("book.html", slot=slot)


@app.route("/confirmation")
def confirmation():
    slot_id = request.args.get("slot_id")
    name = request.args.get("name", "")
    email = request.args.get("email", "")

    db = get_db()
    slot = db.execute("SELECT * FROM slots WHERE id = ?", (slot_id,)).fetchone()

    return render_template(
        "confirmation.html",
        slot=slot,
        name=name,
        email=email,
        meet_link=GOOGLE_MEET_LINK
    )


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if session.get("admin_logged_in"):
        return redirect(url_for("admin_dashboard"))
    if request.method == "POST":
        password = request.form.get("password", "")
        if password == ADMIN_PASSWORD:
            session["admin_logged_in"] = True
            return redirect(url_for("admin_dashboard"))
        flash("Incorrect password.", "error")
    return render_template("admin_login.html")


@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_logged_in", None)
    return redirect(url_for("admin_login"))


@app.route("/admin")
@login_required
def admin_dashboard():
    db = get_db()
    today = datetime.now().strftime("%Y-%m-%d")
    slots = db.execute(
        "SELECT s.*, b.name, b.email, b.notes, b.booked_at "
        "FROM slots s LEFT JOIN bookings b ON s.id = b.slot_id "
        "ORDER BY s.slot_date DESC, s.slot_time DESC"
    ).fetchall()
    upcoming = db.execute(
        "SELECT COUNT(*) as cnt FROM slots WHERE is_booked = 0 AND slot_date >= ?", (today,)
    ).fetchone()["cnt"]
    total_bookings = db.execute(
        "SELECT COUNT(*) as cnt FROM bookings"
    ).fetchone()["cnt"]
    return render_template(
        "admin.html",
        slots=slots,
        upcoming=upcoming,
        total_bookings=total_bookings
    )


@app.route("/admin/add-slot", methods=["POST"])
@login_required
def add_slot():
    db = get_db()
    slot_date = request.form.get("slot_date", "").strip()
    slot_time = request.form.get("slot_time", "").strip()

    if not slot_date or not slot_time:
        flash("Date and time are required.", "error")
        return redirect(url_for("admin_dashboard"))

    existing = db.execute(
        "SELECT id FROM slots WHERE slot_date = ? AND slot_time = ?",
        (slot_date, slot_time)
    ).fetchone()

    if existing:
        flash("This slot already exists.", "error")
        return redirect(url_for("admin_dashboard"))

    db.execute(
        "INSERT INTO slots (slot_date, slot_time) VALUES (?, ?)",
        (slot_date, slot_time)
    )
    db.commit()
    flash(f"Slot added: {slot_date} at {slot_time}", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/delete-slot/<int:slot_id>", methods=["POST"])
@login_required
def delete_slot(slot_id):
    db = get_db()
    slot = db.execute("SELECT * FROM slots WHERE id = ?", (slot_id,)).fetchone()
    if slot and slot["is_booked"]:
        flash("Cannot delete a slot that has already been booked.", "error")
    elif slot:
        db.execute("DELETE FROM slots WHERE id = ?", (slot_id,))
        db.commit()
        flash("Slot deleted.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/edit-slot/<int:slot_id>", methods=["POST"])
@login_required
def edit_slot(slot_id):
    db = get_db()
    slot = db.execute("SELECT * FROM slots WHERE id = ?", (slot_id,)).fetchone()
    if not slot:
        flash("Slot not found.", "error")
        return redirect(url_for("admin_dashboard"))
    if slot["is_booked"]:
        flash("Cannot edit a slot that has already been booked.", "error")
        return redirect(url_for("admin_dashboard"))

    new_date = request.form.get("slot_date", "").strip()
    new_time = request.form.get("slot_time", "").strip()
    if not new_date or not new_time:
        flash("Date and time are required.", "error")
        return redirect(url_for("admin_dashboard"))

    db.execute(
        "UPDATE slots SET slot_date = ?, slot_time = ? WHERE id = ?",
        (new_date, new_time, slot_id)
    )
    db.commit()
    flash("Slot updated.", "success")
    return redirect(url_for("admin_dashboard"))


@app.template_filter("format_date")
def format_date(value):
    try:
        dt = datetime.strptime(value, "%Y-%m-%d")
        return dt.strftime("%A, %B %-d, %Y")
    except Exception:
        return value


if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
