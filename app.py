from datetime import date, datetime
from functools import wraps
import os
from pathlib import Path
import sqlite3

from flask import Flask, g, jsonify, request, send_from_directory, session
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = Path(__file__).resolve().parent
DATABASE = BASE_DIR / "clinic.db"
TIME_SLOTS = [
    "08:00", "08:30", "09:00", "09:30", "10:00", "10:30",
    "11:00", "11:30", "13:00", "13:30", "14:00", "14:30", "15:00", "15:30",
]

app = Flask(__name__, static_folder=str(BASE_DIR), static_url_path="")
app.config["SECRET_KEY"] = os.environ.get(
    "CLINIC_SECRET_KEY", "change-this-secret-key-in-production"
)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("RENDER", "") == "true"


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_error):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(DATABASE)
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('Student', 'Teacher', 'Staff', 'nurse'))
        );
        CREATE TABLE IF NOT EXISTS appointments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            time TEXT NOT NULL,
            type TEXT NOT NULL,
            reason TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK(status IN ('pending', 'approved', 'rejected')),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id),
            UNIQUE(date, time)
        );
        """
    )
    nurse = db.execute("SELECT id FROM users WHERE email = ?", ("nurse@school.ph",)).fetchone()
    if nurse is None:
        db.execute(
            "INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, ?)",
            ("School Nurse", "nurse@school.ph", generate_password_hash("nurse123"), "nurse"),
        )
    db.commit()
    db.close()


def current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    return get_db().execute(
        "SELECT id, name, email, role FROM users WHERE id = ?", (user_id,)
    ).fetchone()


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = current_user()
        if user is None:
            return jsonify(error="Please sign in first."), 401
        g.user = user
        return view(*args, **kwargs)
    return wrapped


def nurse_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if g.user["role"] != "nurse":
            return jsonify(error="Nurse access required."), 403
        return view(*args, **kwargs)
    return wrapped


def user_dict(user):
    return {"name": user["name"], "email": user["email"], "role": user["role"]}


def appointment_dict(row):
    return {
        "id": row["id"],
        "userId": row["email"],
        "userName": row["name"],
        "userRole": row["role"],
        "date": row["date"],
        "time": row["time"],
        "type": row["type"],
        "reason": row["reason"],
        "status": row["status"],
    }


@app.get("/")
def index():
    return send_from_directory(BASE_DIR, "clinic.html")


@app.post("/api/register")
def register():
    data = request.get_json(silent=True) or {}
    name = str(data.get("name", "")).strip()
    email = str(data.get("email", "")).strip().lower()
    password = str(data.get("password", ""))
    role = data.get("role")
    if not name or not email or len(password) < 6 or role not in {"Student", "Teacher", "Staff"}:
        return jsonify(error="Please provide valid registration details."), 400
    db = get_db()
    try:
        db.execute(
            "INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, ?)",
            (name, email, generate_password_hash(password), role),
        )
        db.commit()
    except sqlite3.IntegrityError:
        return jsonify(error="Email already registered."), 409
    return jsonify(message="Account created successfully."), 201


@app.post("/api/login")
def login():
    data = request.get_json(silent=True) or {}
    email = str(data.get("email", "")).strip().lower()
    password = str(data.get("password", ""))
    user = get_db().execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    if user is None or not check_password_hash(user["password_hash"], password):
        return jsonify(error="Incorrect email or password."), 401
    session.clear()
    session["user_id"] = user["id"]
    return jsonify(user=user_dict(user))


@app.post("/api/logout")
def logout():
    session.clear()
    return jsonify(message="Logged out.")


@app.get("/api/me")
def me():
    user = current_user()
    return jsonify(user=user_dict(user) if user else None)


@app.get("/api/appointments")
@login_required
def appointments():
    db = get_db()
    query = """
        SELECT a.*, u.name, u.email, u.role
        FROM appointments a JOIN users u ON u.id = a.user_id
    """
    params = []
    if g.user["role"] != "nurse":
        query += " WHERE a.user_id = ?"
        params.append(g.user["id"])
    query += " ORDER BY a.id DESC"
    rows = db.execute(query, params).fetchall()
    return jsonify(appointments=[appointment_dict(row) for row in rows])


@app.get("/api/appointments/slots")
@login_required
def available_slots():
    selected_date = request.args.get("date", "")
    try:
        chosen = date.fromisoformat(selected_date)
    except ValueError:
        return jsonify(error="Invalid date."), 400
    if chosen.weekday() >= 5:
        return jsonify(slots=[], message="Appointments are Monday-Friday only.")
    taken = get_db().execute(
        "SELECT time FROM appointments WHERE date = ?", (selected_date,)
    ).fetchall()
    taken_times = {row["time"] for row in taken}
    return jsonify(slots=[slot for slot in TIME_SLOTS if slot not in taken_times], taken=list(taken_times))


@app.post("/api/appointments")
@login_required
def create_appointment():
    data = request.get_json(silent=True) or {}
    selected_date = str(data.get("date", ""))
    selected_time = str(data.get("time", ""))
    reason = str(data.get("reason", "")).strip()
    visit_type = str(data.get("type", "")).strip()
    try:
        chosen = date.fromisoformat(selected_date)
    except ValueError:
        return jsonify(error="Please choose a valid date."), 400
    if chosen.weekday() >= 5 or selected_time not in TIME_SLOTS or not reason or not visit_type:
        return jsonify(error="Please select a weekday, available time, visit type, and purpose."), 400
    try:
        db = get_db()
        db.execute(
            "INSERT INTO appointments (user_id, date, time, type, reason) VALUES (?, ?, ?, ?, ?)",
            (g.user["id"], selected_date, selected_time, visit_type, reason),
        )
        db.commit()
    except sqlite3.IntegrityError:
        return jsonify(error="Sorry, that time slot was just taken."), 409
    return jsonify(message="Appointment submitted."), 201


@app.patch("/api/appointments/<int:appointment_id>/status")
@nurse_required
def update_appointment_status(appointment_id):
    data = request.get_json(silent=True) or {}
    status = data.get("status")
    if status not in {"approved", "rejected"}:
        return jsonify(error="Invalid appointment status."), 400
    db = get_db()
    cursor = db.execute(
        "UPDATE appointments SET status = ? WHERE id = ?", (status, appointment_id)
    )
    db.commit()
    if cursor.rowcount == 0:
        return jsonify(error="Appointment not found."), 404
    return jsonify(message="Appointment status updated.")


@app.get("/api/health")
def health():
    return jsonify(status="ok")


init_db()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
