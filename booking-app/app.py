import json
import os
import sqlite3
import requests
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from functools import wraps
from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, g
)

app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "fallback-secret-key")

DATABASE           = os.path.join(os.path.dirname(__file__), "bookings.db")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID", "")
GOOGLE_MEET_LINK   = os.environ.get("GOOGLE_MEET_LINK", "https://meet.google.com/your-link")
ADMIN_PASSWORD     = os.environ.get("ADMIN_PASSWORD", "admin123")

IST = ZoneInfo("Asia/Kolkata")


# ── Timezone helpers ───────────────────────────────────────────────────────────

def now_utc() -> datetime:
    """Current moment as a UTC-aware datetime."""
    return datetime.now(timezone.utc)


def slot_to_utc_iso(date_str: str, time_str: str) -> str:
    """
    Convert an IST date ('YYYY-MM-DD') + time ('HH:MM') entered by the
    admin into a UTC ISO-8601 string for storage.
    """
    naive  = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
    ist_dt = naive.replace(tzinfo=IST)
    return ist_dt.astimezone(timezone.utc).isoformat()


def slot_is_past(utc_iso: str) -> bool:
    """Return True if the stored UTC timestamp is in the past."""
    return datetime.fromisoformat(utc_iso) <= now_utc()


# ── DB helpers ─────────────────────────────────────────────────────────────────

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

        # Create tables (idempotent)
        db.executescript("""
            CREATE TABLE IF NOT EXISTS slots (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                slot_date         TEXT NOT NULL,
                slot_time         TEXT NOT NULL,
                is_booked         INTEGER DEFAULT 0,
                created_at        TEXT DEFAULT (datetime('now')),
                slot_datetime_utc TEXT
            );

            CREATE TABLE IF NOT EXISTS bookings (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                slot_id   INTEGER NOT NULL,
                name      TEXT NOT NULL,
                email     TEXT NOT NULL,
                notes     TEXT,
                booked_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (slot_id) REFERENCES slots(id)
            );

            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT
            );
        """)

        # Migration: add column if it doesn't exist yet (safe on re-run)
        try:
            db.execute("ALTER TABLE slots ADD COLUMN slot_datetime_utc TEXT")
        except Exception:
            pass  # column already present

        # Backfill existing rows that have no UTC timestamp
        existing = db.execute(
            "SELECT id, slot_date, slot_time FROM slots WHERE slot_datetime_utc IS NULL"
        ).fetchall()
        for row in existing:
            try:
                utc_iso = slot_to_utc_iso(row["slot_date"], row["slot_time"])
                db.execute(
                    "UPDATE slots SET slot_datetime_utc = ? WHERE id = ?",
                    (utc_iso, row["id"])
                )
            except Exception:
                pass

        db.commit()


# ── Misc helpers ───────────────────────────────────────────────────────────────

def send_telegram_notification(message: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"},
            timeout=5
        )
    except Exception:
        pass


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("admin_logged_in"):
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return decorated


# ── Public routes ──────────────────────────────────────────────────────────────

@app.route("/")
def index():
    db = get_db()

    # Fetch all unbooked slots (no date pre-filter; JS handles grouping by local date)
    rows = db.execute(
        "SELECT id, slot_date, slot_time, slot_datetime_utc "
        "FROM slots WHERE is_booked = 0 AND slot_datetime_utc IS NOT NULL "
        "ORDER BY slot_datetime_utc"
    ).fetchall()

    # Only pass future slots; JS will group by visitor's local date
    slots_list = [
        {"id": slot["id"], "utc": slot["slot_datetime_utc"]}
        for slot in rows
        if not slot_is_past(slot["slot_datetime_utc"])
    ]

    return render_template(
        "index.html",
        slots_json=json.dumps(slots_list),
        meet_link=GOOGLE_MEET_LINK
    )


@app.route("/book/<int:slot_id>", methods=["GET", "POST"])
def book(slot_id):
    db = get_db()
    slot = db.execute(
        "SELECT * FROM slots WHERE id = ? AND is_booked = 0", (slot_id,)
    ).fetchone()

    if not slot or not slot["slot_datetime_utc"]:
        flash("This slot is no longer available.", "error")
        return redirect(url_for("index"))

    if slot_is_past(slot["slot_datetime_utc"]):
        flash("This slot has expired.", "error")
        return redirect(url_for("index"))

    if request.method == "POST":
        name  = request.form.get("name",  "").strip()
        email = request.form.get("email", "").strip()
        notes = request.form.get("notes", "").strip()

        if not name or not email:
            flash("Name and email are required.", "error")
            return render_template(
                "book.html", slot=slot,
                slot_utc_iso=slot["slot_datetime_utc"]
            )

        # ── Atomic transaction: lock → re-check → insert ───────────────────
        # BEGIN IMMEDIATE acquires a write lock immediately so no two requests
        # can race through this block concurrently.
        db.isolation_level = None          # switch to manual transaction mode
        try:
            db.execute("BEGIN IMMEDIATE")

            # Re-fetch inside the lock — authoritative availability check
            locked_slot = db.execute(
                "SELECT * FROM slots WHERE id = ? AND is_booked = 0", (slot_id,)
            ).fetchone()

            if not locked_slot or not locked_slot["slot_datetime_utc"]:
                db.execute("ROLLBACK")
                flash("This slot is no longer available.", "error")
                return redirect(url_for("index"))

            if slot_is_past(locked_slot["slot_datetime_utc"]):
                db.execute("ROLLBACK")
                flash("This slot has expired.", "error")
                return redirect(url_for("index"))

            db.execute(
                "INSERT INTO bookings (slot_id, name, email, notes) VALUES (?, ?, ?, ?)",
                (slot_id, name, email, notes)
            )
            db.execute("UPDATE slots SET is_booked = 1 WHERE id = ?", (slot_id,))
            db.execute("COMMIT")

        except Exception:
            try:
                db.execute("ROLLBACK")
            except Exception:
                pass
            flash("Something went wrong while saving your booking. Please try again.", "error")
            return redirect(url_for("index"))
        # ──────────────────────────────────────────────────────────────────────

        send_telegram_notification(
            f"<b>New Booking!</b>\n"
            f"Name: {name}\n"
            f"Email: {email}\n"
            f"Slot (IST): {slot['slot_date']} at {slot['slot_time']}\n"
            f"Notes: {notes or 'None'}"
        )

        return redirect(url_for("confirmation", slot_id=slot_id, name=name, email=email))

    return render_template(
        "book.html", slot=slot,
        slot_utc_iso=slot["slot_datetime_utc"]
    )


@app.route("/confirmation")
def confirmation():
    slot_id = request.args.get("slot_id")
    name    = request.args.get("name",  "")
    email   = request.args.get("email", "")
    db      = get_db()
    slot    = db.execute("SELECT * FROM slots WHERE id = ?", (slot_id,)).fetchone()
    utc_iso = slot["slot_datetime_utc"] if slot and slot["slot_datetime_utc"] else ""
    return render_template(
        "confirmation.html",
        slot=slot, name=name, email=email,
        meet_link=GOOGLE_MEET_LINK,
        slot_utc_iso=utc_iso
    )


# ── Admin auth ─────────────────────────────────────────────────────────────────

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if session.get("admin_logged_in"):
        return redirect(url_for("admin_dashboard"))
    if request.method == "POST":
        if request.form.get("password", "") == ADMIN_PASSWORD:
            session["admin_logged_in"] = True
            return redirect(url_for("admin_dashboard"))
        flash("Incorrect password.", "error")
    return render_template("admin_login.html")


@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_logged_in", None)
    return redirect(url_for("admin_login"))


# ── Admin dashboard ────────────────────────────────────────────────────────────

@app.route("/admin")
@login_required
def admin_dashboard():
    db = get_db()

    slots = db.execute(
        "SELECT s.*, b.name, b.email, b.notes, b.booked_at "
        "FROM slots s LEFT JOIN bookings b ON s.id = b.slot_id "
        "ORDER BY s.slot_date DESC, s.slot_time DESC"
    ).fetchall()

    # Upcoming = unbooked AND future (UTC-based)
    upcoming = sum(
        1 for s in slots
        if not s["is_booked"]
        and s["slot_datetime_utc"]
        and not slot_is_past(s["slot_datetime_utc"])
    )
    total_bookings = db.execute(
        "SELECT COUNT(*) as cnt FROM bookings"
    ).fetchone()["cnt"]

    return render_template(
        "admin.html",
        slots=slots,
        upcoming=upcoming,
        total_bookings=total_bookings
    )


# ── Admin slot management ──────────────────────────────────────────────────────

@app.route("/admin/add-slot", methods=["POST"])
@login_required
def add_slot():
    db        = get_db()
    slot_date = request.form.get("slot_date", "").strip()
    slot_time = request.form.get("slot_time", "").strip()

    if not slot_date or not slot_time:
        flash("Date and time are required.", "error")
        return redirect(url_for("admin_dashboard"))

    try:
        utc_iso = slot_to_utc_iso(slot_date, slot_time)
    except ValueError:
        flash("Invalid date or time format.", "error")
        return redirect(url_for("admin_dashboard"))

    if slot_is_past(utc_iso):
        flash("Cannot create a slot in the past.", "error")
        return redirect(url_for("admin_dashboard"))

    existing = db.execute(
        "SELECT id FROM slots WHERE slot_date = ? AND slot_time = ?",
        (slot_date, slot_time)
    ).fetchone()
    if existing:
        flash("This slot already exists.", "error")
        return redirect(url_for("admin_dashboard"))

    db.execute(
        "INSERT INTO slots (slot_date, slot_time, slot_datetime_utc) VALUES (?, ?, ?)",
        (slot_date, slot_time, utc_iso)
    )
    db.commit()
    flash(f"Slot added: {slot_date} at {slot_time} IST", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/delete-slot/<int:slot_id>", methods=["POST"])
@login_required
def delete_slot(slot_id):
    db   = get_db()
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
    db   = get_db()
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

    try:
        utc_iso = slot_to_utc_iso(new_date, new_time)
    except ValueError:
        flash("Invalid date or time format.", "error")
        return redirect(url_for("admin_dashboard"))

    if slot_is_past(utc_iso):
        flash("Cannot create a slot in the past.", "error")
        return redirect(url_for("admin_dashboard"))

    db.execute(
        "UPDATE slots SET slot_date = ?, slot_time = ?, slot_datetime_utc = ? WHERE id = ?",
        (new_date, new_time, utc_iso, slot_id)
    )
    db.commit()
    flash("Slot updated.", "success")
    return redirect(url_for("admin_dashboard"))


# ── Template filters ───────────────────────────────────────────────────────────

@app.template_filter("format_date")
def format_date(value):
    try:
        dt = datetime.strptime(value, "%Y-%m-%d")
        return dt.strftime("%A, %B %-d, %Y")
    except Exception:
        return value


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
