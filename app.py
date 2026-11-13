from datetime import datetime
from functools import wraps
from html import escape
from email.message import EmailMessage
import os
import smtplib
import threading
from pathlib import Path

import psycopg2
from flask import Flask, Response, g, jsonify, request, session
from werkzeug.security import check_password_hash, generate_password_hash

# === DATABASE CONFIGURATION ===
DATABASE_URL = os.environ.get("DATABASE_URL")

# === EMAIL (GMAIL SMTP) CONFIGURATION ===
# Gumamit ng Gmail App Password (hindi ang normal na password).
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER")          # Gmail ng clinic
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD")  # Gmail App Password
MAIL_FROM = os.environ.get("MAIL_FROM", SMTP_USER)

BASE_DIR = Path(__file__).resolve().parent
app = Flask(__name__, static_folder=str(BASE_DIR), static_url_path="")
app.config["SECRET_KEY"] = os.environ.get(
    "CLINIC_SECRET_KEY", "change-this-secret-key-in-production"
)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"


# === ISA LANG NA GET_DB FUNCTION — PARA SA POSTGRESQL ===
def get_db():
    if "db" not in g:
        try:
            g.db = psycopg2.connect(DATABASE_URL)
            g.db.autocommit = False
        except Exception as e:
            print(f"DB Connection Error: {e}")
            return None
    return g.db


@app.teardown_appcontext
def close_db(_error):
    db = g.pop("db", None)
    if db is not None and not db.closed:
        db.close()


TIME_SLOTS = [
    "08:00", "08:30", "09:00", "09:30", "10:00", "10:30",
    "11:00", "11:30", "13:00", "13:30", "14:00", "14:30", "15:00", "15:30",
]


# === EMAIL HELPERS ===
def _pretty_date(d):
    try:
        return datetime.strptime(d, "%Y-%m-%d").strftime("%A, %B %d, %Y")
    except Exception:
        return d


def _pretty_time(t):
    try:
        return datetime.strptime(t, "%H:%M").strftime("%I:%M %p").lstrip("0")
    except Exception:
        return t


def _send_email(to_email, subject, text_body, html_body):
    if not (SMTP_USER and SMTP_PASSWORD):
        print("Email skipped: SMTP_USER / SMTP_PASSWORD not set.")
        return
    try:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = f"School Clinic <{MAIL_FROM}>"
        msg["To"] = to_email
        msg.set_content(text_body)
        msg.add_alternative(html_body, subtype="html")
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)
        print(f"Email sent to {to_email}")
    except Exception as e:
        print(f"Email error: {e}")


def notify_user(kind, to_email, name, date, time, visit_type,
                reason=None, old_date=None, old_time=None):
    """kind = 'approved' | 'rescheduled'. Tumatakbo sa background thread."""
    when = f"{_pretty_date(date)} at {_pretty_time(time)}"
    if kind == "approved":
        subject = "Your clinic appointment is APPROVED"
        color, title = "#16a34a", "Appointment Approved ?"
        intro = "Good news! The school nurse has approved your appointment."
        extra_text, extra_html = "", ""
    else:
        subject = "Your clinic appointment was RESCHEDULED"
        color, title = "#2563eb", "Appointment Rescheduled"
        intro = "The school nurse has moved your appointment to a new schedule."
        prev = f"{_pretty_date(old_date)} at {_pretty_time(old_time)}" if old_date else "—"
        extra_text = f"\nPrevious schedule: {prev}\nReason: {reason}\n"
        extra_html = (
            f"<tr><td style='padding:6px 0;color:#6b7280'>Previous</td><td>{escape(prev)}</td></tr>"
            f"<tr><td style='padding:6px 0;color:#6b7280'>Reason</td><td>{escape(reason or '')}</td></tr>"
        )

    text_body = (
        f"Hello {name},\n\n{intro}\n\nSchedule: {when}\nVisit type: {visit_type}\n"
        f"{extra_text}\nPlease arrive 5-10 minutes early and bring your school ID.\n\n- School Clinic"
    )
    html_body = f"""
    <div style="font-family:Arial,sans-serif;max-width:520px;margin:auto;border:1px solid #e5e7eb;border-radius:12px;overflow:hidden">
      <div style="background:{color};color:#fff;padding:18px 22px"><h2 style="margin:0">{title}</h2></div>
      <div style="padding:22px;color:#111827">
        <p>Hello <b>{escape(name)}</b>,</p>
        <p>{intro}</p>
        <table style="width:100%;border-collapse:collapse;font-size:14px">
          <tr><td style="padding:6px 0;color:#6b7280;width:110px">Schedule</td><td><b>{escape(when)}</b></td></tr>
          <tr><td style="padding:6px 0;color:#6b7280">Visit type</td><td>{escape(visit_type)}</td></tr>
          {extra_html}
        </table>
        <p style="margin-top:18px;font-size:13px;color:#4b5563">Please arrive 5-10 minutes early and bring your school ID.</p>
      </div>
      <div style="background:#f9fafb;padding:12px 22px;font-size:12px;color:#9ca3af">School Clinic Appointment System</div>
    </div>"""
    threading.Thread(
        target=_send_email, args=(to_email, subject, text_body, html_body), daemon=True
    ).start()


# === DATABASE INITIALIZATION — POSTGRESQL SYNTAX ===
def init_db():
    conn = get_db()
    if not conn:
        print("Hindi makakonekta sa database!")
        return
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('Student', 'Teacher', 'Staff', 'nurse'))
        );
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS appointments (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            date TEXT NOT NULL,
            time TEXT NOT NULL,
            type TEXT NOT NULL,
            reason TEXT NOT NULL,
            rejection_reason TEXT,
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK(status IN ('pending', 'approved', 'rejected')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(date, time)
        );
    """)
    cur.execute("ALTER TABLE appointments ADD COLUMN IF NOT EXISTS rejection_reason TEXT")

    # para sa reschedule (reason ng nurse + dating schedule)
    cur.execute("ALTER TABLE appointments ADD COLUMN IF NOT EXISTS reschedule_reason TEXT")
    cur.execute("ALTER TABLE appointments ADD COLUMN IF NOT EXISTS old_date TEXT")
    cur.execute("ALTER TABLE appointments ADD COLUMN IF NOT EXISTS old_time TEXT")

    cur.execute("SELECT id FROM users WHERE email = %s", ("nurse@school.ph",))
    nurse = cur.fetchone()
    if nurse is None:
        cur.execute(
            "INSERT INTO users (name, email, password_hash, role) VALUES (%s, %s, %s, %s)",
            ("School Nurse", "nurse@school.ph", generate_password_hash("nurse123"), "nurse"),
        )
    conn.commit()
    cur.close()
    print("Database ready!")


# === AUTH HELPERS ===
def current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    conn = get_db()
    if not conn:
        return None
    cur = conn.cursor()
    cur.execute("SELECT id, name, email, role FROM users WHERE id = %s", (user_id,))
    user = cur.fetchone()
    cur.close()
    if not user:
        return None
    return {"id": user[0], "name": user[1], "email": user[2], "role": user[3]}


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
    return {"id": user["id"], "name": user["name"], "email": user["email"], "role": user["role"]}


def appointment_dict(row):
    return {
        "id": row[0],
        "userId": row[2],
        "userName": row[1],
        "userRole": row[3],
        "date": row[4],
        "time": row[5],
        "type": row[6],
        "reason": row[7],
        "status": row[8],
    }


def appointment_rows_to_list(rows):
    return [
        {
            "id": row[0],
            "userName": row[1],
            "userRole": row[2],
            "date": row[3],
            "time": row[4],
            "type": row[5],
            "reason": row[6],
            "status": row[7],
            "rejectionReason": row[8],
            "rescheduleReason": row[9],
            "oldDate": row[10],
            "oldTime": row[11],
        }
        for row in rows
    ]


# === HTML CONTENT ===
HTML_CONTENT = r"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>School Clinic - Appointment System</title>
<script src="https://cdn.tailwindcss.com"></script>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.7.2/css/all.min.css">
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
* { font-family: 'Inter', sans-serif; }
html { scroll-behavior: smooth; }

/* ===== BACKGROUND ===== */
.school-bg {
    background: linear-gradient(rgba(255,255,255,0.15), rgba(255,255,255,0.15)), url('clinic.jpg');
    background-size: cover;
    background-position: center;
    background-attachment: fixed;
    background-repeat: no-repeat;
}

/* ===== GLASS LOGIN CARD ===== */
.glass {
    background: rgba(255,255,255,0.35);
    backdrop-filter: blur(14px);
    -webkit-backdrop-filter: blur(14px);
    border: 1px solid rgba(255,255,255,0.5);
    color: #000000 !important;
    box-shadow: 0 8px 40px rgba(0,0,0,0.12);
    transition: all 0.4s ease;
}
.glass:hover { box-shadow: 0 12px 50px rgba(0,0,0,0.18); }

/* Lahat ng text sa login form ay itim */
.glass, .glass label, .glass h1, .glass p, .glass span, .glass button.auth-tab, .glass input, .glass select {
    color: #000000;
}
.glass input::placeholder { color: #6b7280; }
.glass input, .glass select { background: rgba(255,255,255,0.85); }

/* ===== BLUE ROTATING LIGHTS AROUND LOGIN FORM ===== */
@property --angle {
    syntax: '<angle>';
    initial-value: 0deg;
    inherits: false;
}
.login-wrap { position: relative; width: 100%; max-width: 28rem; }
.glow-ring {
    position: absolute;
    inset: -3px;
    border-radius: 20px;
    padding: 3px;
    background: conic-gradient(from var(--angle),
        transparent 0deg, transparent 40deg,
        #1d4ed8 90deg, #3b82f6 130deg, #60a5fa 160deg, #22d3ee 180deg,
        transparent 220deg, transparent 220deg,
        #2563eb 270deg, #60a5fa 310deg, #93c5fd 330deg, transparent 360deg);
    -webkit-mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0);
    -webkit-mask-composite: xor;
    mask: linear-gradient(#000 0 0) content-box exclude, linear-gradient(#000 0 0);
    mask-composite: exclude;
    animation: spinLight 4s linear infinite;
    pointer-events: none;
}
.glow-ring.blur { filter: blur(10px); opacity: 0.9; inset: -6px; padding: 6px; }
@keyframes spinLight { to { --angle: 360deg; } }

/* Fallback kapag walang @property support */
@supports not (background: conic-gradient(from var(--angle), red, blue)) {
    .glow-ring { animation: none; }
}

/* ===== DASHBOARD ===== */
.dashboard-card {
    background: #ffffff;
    border: 1px solid #e5e7eb;
    border-radius: 16px;
    box-shadow: 0 2px 12px rgba(0,0,0,0.04);
    transition: all 0.35s ease;
}
.dashboard-card:hover { box-shadow: 0 8px 30px rgba(0,0,0,0.08); transform: translateY(-2px); }
.sidebar-link { transition: all 0.3s ease; border-left: 4px solid transparent; }
.sidebar-link:hover, .sidebar-link.active { background: rgba(255,255,255,0.18); border-left: 4px solid #fbbf24; }
.stat-card { border-radius: 16px; transition: all 0.35s ease; }
.stat-card:hover { transform: translateY(-6px); box-shadow: 0 15px 35px rgba(0,0,0,0.15); }
.fade-in { animation: fadeIn 0.5s ease-out; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(20px); } to { opacity: 1; transform: translateY(0); } }

/* ===== SIGN IN / CREATE ACCOUNT TABS — ITIM PALAGI ===== */
.auth-tab {
    color: #000000 !important;
    font-weight: 500;
    border-bottom: 3px solid transparent;
    transition: border-color 0.25s ease, background 0.25s ease, font-weight 0.25s ease;
    border-radius: 8px 8px 0 0;
}
.auth-tab:hover { background: rgba(59,130,246,0.10); color: #000000 !important; }
.auth-tab:focus, .auth-tab:active { color: #000000 !important; outline: none; }
.auth-tab i { color: #000000 !important; }
.tab-active { border-bottom: 3px solid #3b82f6 !important; color: #000000 !important; font-weight: 700 !important; }

.status-pending { background: #fef08a; color: #854d0e; }
.status-approved { background: #bbf7d0; color: #166534; }
.status-rejected { background: #fecaca; color: #991b1b; }
.status-rescheduled { background: #bfdbfe; color: #1e40af; }
.history-panel { max-height: 550px; overflow-y: auto; }

.password-wrapper { position: relative; }
.eye-icon { position: absolute; right: 12px; top: 50%; transform: translateY(-50%); cursor: pointer; color: #374151; }
.eye-icon:hover { color: #000000; }
.password-wrapper input { padding-right: 40px !important; }

@keyframes pulse-glow {
    0%, 100% { box-shadow: 0 0 4px rgba(251,191,36,0.4); }
    50% { box-shadow: 0 0 15px rgba(251,191,36,0.7); }
}
.animate-pulse { animation: pulse-glow 1.5s ease-in-out infinite; }

.time-slot { transition: all 0.25s ease; cursor: pointer; }
.time-slot:hover:not(.taken) { background-color: #dbeafe; border-color: #3b82f6; transform: scale(1.03); }
.time-slot.taken { background-color: #f3f4f6; color: #9ca3af; border-color: #e5e7eb; cursor: not-allowed; text-decoration: line-through; }
.time-slot.selected { background-color: #dbeafe; border-color: #2563eb; border-width: 2px; font-weight: 600; color: #1e40af; }

/* Input focus + button polish */
input:focus, select:focus, textarea:focus { box-shadow: 0 0 0 3px rgba(59,130,246,0.25); }
button { transition: transform 0.15s ease, background-color 0.2s ease, opacity 0.2s ease; }
button:not(:disabled):active { transform: scale(0.97); }
tbody tr { transition: background-color 0.2s ease; }

/* Spinner */
.spinner { display:inline-block; width:14px; height:14px; border:2px solid rgba(255,255,255,0.5); border-top-color:#fff; border-radius:50%; animation: spin 0.7s linear infinite; vertical-align:-2px; margin-right:6px; }
@keyframes spin { to { transform: rotate(360deg); } }

@media (prefers-reduced-motion: reduce) {
    .glow-ring { animation-duration: 12s; }
    .fade-in { animation: none; }
}
</style>
</head>
<body class="bg-gray-50 min-h-screen">

<!-- LOGIN PAGE -->
<div id="authSection" class="school-bg flex items-center justify-center min-h-screen p-4">
  <div class="login-wrap fade-in">
    <div class="glow-ring blur"></div>
    <div class="glow-ring"></div>

    <div class="glass rounded-2xl shadow-2xl p-8 w-full relative">
      <div class="text-center mb-8">
        <img src="slsu.png.png" class="w-20 h-20 object-contain mx-auto mb-3 bg-transparent p-0 border-0" alt="SLSU Logo">
        <h1 class="text-2xl font-bold">Clinic Appointment System</h1>
        <p>School Clinic Appointment System</p>
      </div>

      <div class="flex mb-6 border-b border-black/20">
        <button id="tabLogin" class="auth-tab flex-1 py-3 text-center tab-active" onclick="showAuthTab('login')">
          <i class="fa-solid fa-right-to-bracket mr-2"></i> Sign In
        </button>
        <button id="tabRegister" class="auth-tab flex-1 py-3 text-center" onclick="showAuthTab('register')">
          <i class="fa-solid fa-user-plus mr-2"></i> Create Account
        </button>
      </div>

      <!-- LOGIN FORM -->
      <div id="formLogin">
        <div class="space-y-4">
          <div>
            <label class="block font-medium mb-1">Email</label>
            <input type="email" id="loginEmail" autocomplete="username" class="w-full px-4 py-2.5 border border-gray-400 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500" placeholder="your@gmail.com">
          </div>
          <div>
            <label class="block font-medium mb-1">Password</label>
            <div class="password-wrapper">
              <input type="password" id="loginPass" autocomplete="current-password" class="w-full px-4 py-2.5 border border-gray-400 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500" placeholder="At least 6 characters">
              <i class="fa-solid fa-eye eye-icon" id="eyeLogin" onclick="togglePassword('loginPass', 'eyeLogin')"></i>
            </div>
          </div>
          <button id="loginButton" onclick="loginUser()" class="w-full bg-blue-600 hover:bg-blue-700 text-white py-3 rounded-lg font-semibold shadow-lg shadow-blue-500/30">
            Sign In
          </button>
        </div>
      </div>

      <!-- REGISTER FORM -->
      <div id="formRegister" class="hidden">
        <div class="space-y-4">
          <div>
            <label class="block font-medium mb-1">Full Name</label>
            <input type="text" id="regName" class="w-full px-4 py-2.5 border border-gray-400 rounded-lg focus:outline-none focus:ring-2 focus:ring-green-500" placeholder="Juan Dela Cruz">
          </div>
          <div>
            <label class="block font-medium mb-1">Email</label>
            <input type="email" id="regEmail" autocomplete="username" class="w-full px-4 py-2.5 border border-gray-400 rounded-lg focus:outline-none focus:ring-2 focus:ring-green-500" placeholder="your@gmail.com">
          </div>
          <div>
            <label class="block font-medium mb-1">Password</label>
            <div class="password-wrapper">
              <input type="password" id="regPass" autocomplete="new-password" class="w-full px-4 py-2.5 border border-gray-400 rounded-lg focus:outline-none focus:ring-2 focus:ring-green-500" placeholder="At least 6 characters">
              <i class="fa-solid fa-eye eye-icon" id="eyeReg" onclick="togglePassword('regPass', 'eyeReg')"></i>
            </div>
          </div>
          <div>
            <label class="block font-medium mb-1">You are a...</label>
            <select id="regRole" class="w-full px-4 py-2.5 border border-gray-400 rounded-lg focus:outline-none focus:ring-2 focus:ring-green-500">
              <option value="Student">Student</option>
              <option value="Teacher">Teacher</option>
              <option value="Staff">Staff</option>
            </select>
          </div>
          <button id="registerButton" onclick="registerUser()" class="w-full bg-green-600 hover:bg-green-700 text-white py-3 rounded-lg font-semibold shadow-lg shadow-green-500/30">
            Create Account
          </button>
        </div>
      </div>

      <p id="authMsg" class="mt-4 text-center font-medium"></p>
    </div>
  </div>
</div>

<!-- USER DASHBOARD -->
<div id="userDashboard" class="hidden min-h-screen flex flex-col md:flex-row">
  <div class="md:hidden bg-blue-900 text-white p-3 flex justify-between items-center">
    <span class="font-bold">Clinic</span>
    <button id="userMenuBtn" class="text-xl"><i class="fa-solid fa-bars"></i></button>
  </div>

  <aside id="userSidebar" class="w-64 bg-blue-900 text-white fixed md:sticky top-0 left-0 h-screen z-40 transform -translate-x-full md:translate-x-0 transition-transform duration-300">
    <div class="p-4">
      <div class="flex items-center gap-3 mb-8 mt-2">
        <i class="fa-solid fa-heart-pulse text-2xl text-red-400"></i>
        <span class="font-bold text-lg">Clinic</span>
      </div>
      <nav class="space-y-1">
        <a href="#" class="sidebar-link active flex items-center gap-3 px-4 py-3 rounded-lg text-white">
          <i class="fa-solid fa-house w-5 text-center"></i> Dashboard
        </a>
        <a href="#" class="sidebar-link flex items-center gap-3 px-4 py-3 rounded-lg text-blue-100">
          <i class="fa-solid fa-calendar-check w-5 text-center"></i> My Appointments
        </a>
        <a href="#" class="sidebar-link flex items-center gap-3 px-4 py-3 rounded-lg text-blue-100" onclick="logoutSystem()">
          <i class="fa-solid fa-right-from-bracket w-5 text-center"></i> Log Out
        </a>
      </nav>
    </div>
  </aside>

  <div id="userOverlay" class="md:hidden fixed inset-0 bg-black/50 hidden z-30" onclick="toggleUserSidebar()"></div>

  <main class="flex-1 p-4 md:p-6 bg-gray-50">
    <div class="dashboard-card p-4 mb-6 flex justify-between items-center fade-in">
      <div>
        <h2 class="text-xl font-bold text-gray-800">Welcome, <span id="displayName"></span>!</h2>
        <p class="text-gray-500 text-sm" id="displayRole"></p>
      </div>
      <button onclick="logoutSystem()" class="md:hidden bg-red-500 text-white px-3 py-2 rounded-lg text-sm">
        <i class="fa-solid fa-right-from-bracket"></i>
      </button>
    </div>

    <div class="dashboard-card p-6 mb-6 fade-in">
      <h3 class="text-lg font-bold text-gray-800 mb-4"><i class="fa-solid fa-calendar-plus text-blue-600 mr-2"></i>Book an Appointment</h3>
      <div class="grid md:grid-cols-2 gap-4 mb-4">
        <div>
          <label class="block text-gray-600 text-sm font-medium mb-1">Select Date (Monday–Friday only)</label>
          <input type="date" id="aptDate" class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500" onchange="loadAvailableTimeSlots()">
        </div>
        <div>
          <label class="block text-gray-600 text-sm font-medium mb-1">Available Time Slot</label>
          <input type="hidden" id="aptTime">
          <div id="timeSlotsContainer" class="grid grid-cols-3 gap-2">
            <span class="text-gray-400 text-sm col-span-3">Select a date first...</span>
          </div>
        </div>
      </div>
      <div class="mb-4">
        <label class="block text-gray-600 text-sm font-medium mb-1">Visit Type</label>
        <select id="aptType" class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500">
          <option>General Consultation</option>
          <option>First Aid / Minor Injury</option>
          <option>Headache</option>
          <option>Fever / Flu Symptoms</option>
          <option>Stomach / Abdominal Pain</option>
          <option>Medicine Request</option>
          <option>Other Medical Concern</option>
        </select>
      </div>
      <div>
        <label class="block text-gray-600 text-sm font-medium mb-1">Purpose / Symptoms</label>
        <textarea id="aptReason" rows="3" class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500" placeholder="Describe your symptoms..."></textarea>
      </div>
      <button id="submitAppointmentButton" onclick="submitAppointment()" class="mt-4 bg-blue-600 hover:bg-blue-700 text-white px-6 py-2.5 rounded-lg font-semibold">
        <i class="fa-solid fa-paper-plane mr-2"></i> Submit Request
      </button>
    </div>

    <div class="dashboard-card p-6 fade-in">
      <h3 class="text-lg font-bold text-gray-800 mb-4"><i class="fa-solid fa-list-check text-blue-600 mr-2"></i>My Appointments</h3>
      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="text-left text-gray-500 border-b">
              <th class="py-2 px-2">#</th>
              <th class="py-2 px-2">Date</th>
              <th class="py-2 px-2">Time</th>
              <th class="py-2 px-2">Type</th>
              <th class="py-2 px-2">Purpose</th>
              <th class="py-2 px-2">Status</th>
              <th class="py-2 px-2">Rejection / Reschedule Reason</th>
            </tr>
          </thead>
          <tbody id="myAppointmentsTable">
            <tr><td colspan="7" class="py-4 text-center text-gray-400 italic">No appointments yet.</td></tr>
          </tbody>
        </table>
      </div>
    </div>
  </main>
</div>

<!-- NURSE DASHBOARD -->
<div id="nurseDashboard" class="hidden min-h-screen flex flex-col md:flex-row">
  <div class="md:hidden bg-blue-900 text-white p-3 flex justify-between items-center">
    <div>
      <span class="font-bold">NURSE PANEL</span>
      <p class="text-xs text-blue-200">Clinic Management</p>
    </div>
    <button id="nurseMenuBtn" class="text-xl"><i class="fa-solid fa-bars"></i></button>
  </div>

  <aside id="nurseSidebar" class="w-64 bg-blue-900 text-white fixed md:sticky top-0 left-0 h-screen z-40 transform -translate-x-full md:translate-x-0 transition-transform duration-300">
    <div class="p-4">
      <div class="flex items-center gap-3 mb-8 mt-2">
        <i class="fa-solid fa-user-nurse text-2xl text-yellow-400"></i>
        <div>
          <span class="font-bold text-lg">NURSE PANEL</span>
          <p class="text-xs text-blue-200">Clinic Management</p>
        </div>
      </div>
      <nav class="space-y-1">
        <a href="#" class="sidebar-link active flex items-center gap-3 px-4 py-3 rounded-lg text-white" id="navDashboard" onclick="showNurseTab('dashboard')">
          <i class="fa-solid fa-chart-pie w-5 text-center"></i> Dashboard
        </a>
        <a href="#" class="sidebar-link flex items-center gap-3 px-4 py-3 rounded-lg text-blue-100" id="navHistory" onclick="showNurseTab('history')">
          <i class="fa-solid fa-clock-rotate-left w-5 text-center"></i> Appointment History
        </a>
        <a href="#" class="sidebar-link flex items-center gap-3 px-4 py-3 rounded-lg text-blue-100" id="navAppointments" onclick="showNurseTab('appointments')">
          <i class="fa-solid fa-calendar-check w-5 text-center"></i> All Appointments
        </a>
        <a href="#" class="sidebar-link flex items-center gap-3 px-4 py-3 rounded-lg text-blue-100" onclick="logoutSystem()">
          <i class="fa-solid fa-right-from-bracket w-5 text-center"></i> Log Out
        </a>
      </nav>
    </div>
  </aside>

  <div id="nurseOverlay" class="md:hidden fixed inset-0 bg-black/50 hidden z-30" onclick="toggleNurseSidebar()"></div>

  <main class="flex-1 p-4 md:p-6 bg-gray-50">

    <!-- DASHBOARD VIEW -->
    <div id="nurseViewDashboard" class="fade-in">
      <div class="dashboard-card p-4 mb-6 flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
        <div class="flex items-center gap-4">
          <div class="w-12 h-12 rounded-full bg-blue-100 flex items-center justify-center">
            <i class="fa-solid fa-user-nurse text-blue-700 text-xl"></i>
          </div>
          <div>
            <h2 class="text-xl font-bold text-gray-800">Nurse Dashboard</h2>
            <p class="text-gray-500 text-sm">Manage all clinic appointment requests</p>
          </div>
        </div>
        <div class="flex items-center gap-2">
          <span class="bg-yellow-100 text-yellow-800 px-3 py-1 rounded-full text-sm font-semibold flex items-center gap-2">
            <span class="w-2 h-2 bg-yellow-500 rounded-full animate-pulse"></span>
            <span id="pendingBadge">0</span> Pending
          </span>
          <button onclick="logoutSystem()" class="bg-red-500 hover:bg-red-600 text-white px-4 py-2 rounded-lg text-sm font-medium">
            <i class="fa-solid fa-right-from-bracket mr-1"></i> Log Out
          </button>
        </div>
      </div>

      <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <div class="stat-card bg-blue-500 text-white p-4">
          <div class="flex items-center justify-between">
            <div><p class="text-blue-100 text-sm">All Patients</p><p class="text-3xl font-bold" id="statTotal">0</p></div>
            <i class="fa-solid fa-users text-3xl text-blue-200"></i>
          </div>
        </div>
        <div class="stat-card bg-cyan-500 text-white p-4">
          <div class="flex items-center justify-between">
            <div><p class="text-cyan-100 text-sm">New Requests</p><p class="text-3xl font-bold" id="statNew">0</p></div>
            <i class="fa-solid fa-calendar-plus text-3xl text-cyan-200"></i>
          </div>
        </div>
        <div class="stat-card bg-yellow-500 text-white p-4">
          <div class="flex items-center justify-between">
            <div><p class="text-yellow-100 text-sm">Pending</p><p class="text-3xl font-bold" id="statPending">0</p></div>
            <i class="fa-solid fa-clock text-3xl text-yellow-200"></i>
          </div>
        </div>
        <div class="stat-card bg-green-500 text-white p-4">
          <div class="flex items-center justify-between">
            <div><p class="text-green-100 text-sm">Approved</p><p class="text-3xl font-bold" id="statApproved">0</p></div>
            <i class="fa-solid fa-check-circle text-3xl text-green-200"></i>
          </div>
        </div>
      </div>

      <div class="dashboard-card p-4 mb-6">
        <h3 class="text-lg font-bold text-gray-800 mb-3"><i class="fa-solid fa-magnifying-glass text-blue-600 mr-2"></i>Search Patient History</h3>
        <div class="flex flex-col sm:flex-row gap-3 mb-4">
          <input type="text" id="searchPatientName" placeholder="Type patient name..." class="flex-1 px-4 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 w-full">
          <button onclick="searchPatientHistory()" class="bg-blue-600 hover:bg-blue-700 text-white px-5 py-2.5 rounded-lg font-semibold whitespace-nowrap w-full sm:w-auto">
            <i class="fa-solid fa-magnifying-glass mr-2"></i> Search
          </button>
        </div>
        <div id="patientHistoryResult" class="mt-4 hidden">
          <h4 class="font-bold text-gray-700 mb-2">Appointment History:</h4>
          <div class="history-panel overflow-x-auto border rounded-lg">
            <table class="w-full min-w-max text-sm">
              <thead class="bg-gray-100">
                <tr>
                  <th class="py-2 px-3 text-left whitespace-nowrap">#</th>
                  <th class="py-2 px-3 text-left whitespace-nowrap">Date</th>
                  <th class="py-2 px-3 text-left whitespace-nowrap">Time</th>
                  <th class="py-2 px-3 text-left whitespace-nowrap">Type</th>
                  <th class="py-2 px-3 text-left whitespace-nowrap">Symptoms</th>
                  <th class="py-2 px-3 text-left whitespace-nowrap">Status</th>
                </tr>
              </thead>
              <tbody id="patientHistoryTable"></tbody>
            </table>
          </div>
        </div>
      </div>
    </div>

    <!-- APPOINTMENT HISTORY VIEW -->
    <div id="nurseViewHistory" class="hidden fade-in">
      <div class="dashboard-card p-4 sm:p-6">
        <div class="flex flex-col sm:flex-row justify-between items-start sm:items-center mb-6 gap-3">
          <h3 class="text-lg font-bold text-gray-800">
            <i class="fa-solid fa-clock-rotate-left mr-2 text-blue-600"></i>
            Appointment History
            <span class="text-sm font-normal text-gray-500 ml-2">(Chronological Order)</span>
          </h3>
          <div class="flex gap-2 w-full sm:w-auto">
            <button onclick="renderHistory(true)" class="flex-1 sm:flex-none px-3 py-1.5 bg-gray-100 text-gray-700 rounded-lg text-sm font-medium hover:bg-gray-200">
              <i class="fa-solid fa-arrow-up-short-wide mr-1"></i> Oldest First
            </button>
            <button onclick="renderHistory(false)" class="flex-1 sm:flex-none px-3 py-1.5 bg-gray-100 text-gray-700 rounded-lg text-sm font-medium hover:bg-gray-200">
              <i class="fa-solid fa-arrow-down-wide-short mr-1"></i> Newest First
            </button>
          </div>
        </div>

        <div class="w-full overflow-x-auto rounded-lg border border-gray-200 shadow-sm">
          <table class="w-full text-sm min-w-max">
            <thead class="bg-gray-50">
              <tr class="text-left text-gray-600 border-b-2 border-gray-200">
                <th class="py-3 px-3 font-semibold text-center whitespace-nowrap">#</th>
                <th class="py-3 px-3 font-semibold whitespace-nowrap">Name</th>
                <th class="py-3 px-3 font-semibold whitespace-nowrap">Role</th>
                <th class="py-3 px-3 font-semibold whitespace-nowrap">Date</th>
                <th class="py-3 px-3 font-semibold whitespace-nowrap">Time</th>
                <th class="py-3 px-3 font-semibold whitespace-nowrap">Visit Type</th>
                <th class="py-3 px-3 font-semibold whitespace-nowrap">Purpose</th>
                <th class="py-3 px-3 font-semibold text-center whitespace-nowrap">Status</th>
                <th class="py-3 px-3 font-semibold text-center whitespace-nowrap">Action</th>
              </tr>
            </thead>
            <tbody id="historyTable">
              <tr><td colspan="9" class="py-8 text-center text-gray-400 italic">No appointment history yet.</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- ALL APPOINTMENTS VIEW -->
    <div id="nurseViewAppointments" class="hidden fade-in">
      <div class="dashboard-card p-6">
        <div class="flex flex-col md:flex-row justify-between items-start md:items-center mb-6 gap-3">
          <h3 class="text-lg font-bold text-gray-800"><i class="fa-solid fa-calendar-check text-blue-600 mr-2"></i>ALL Clinic Appointments</h3>
          <div class="flex gap-2">
            <select id="filterRole" onchange="renderAllAppointments()" class="px-3 py-1.5 border rounded-lg text-sm">
              <option value="all">All Roles</option>
              <option value="Student">Student</option>
              <option value="Teacher">Teacher</option>
              <option value="Staff">Staff</option>
            </select>
            <select id="filterStatus" onchange="renderAllAppointments()" class="px-3 py-1.5 border rounded-lg text-sm">
              <option value="all">All Status</option>
              <option value="pending">Pending</option>
              <option value="approved">Approved</option>
              <option value="rescheduled">Rescheduled</option>
            </select>
          </div>
        </div>
        <div class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead>
              <tr class="text-left text-gray-600 border-b-2 border-gray-100">
                <th class="py-3 px-3 font-semibold">#</th>
                <th class="py-3 px-3 font-semibold">Name</th>
                <th class="py-3 px-3 font-semibold">Role</th>
                <th class="py-3 px-3 font-semibold">Date</th>
                <th class="py-3 px-3 font-semibold">Time</th>
                <th class="py-3 px-3 font-semibold">Visit Type</th>
                <th class="py-3 px-3 font-semibold">Concern</th>
                <th class="py-3 px-3 font-semibold text-center">Status</th>
                <th class="py-3 px-3 font-semibold text-center">Action</th>
              </tr>
            </thead>
            <tbody id="allAppointmentsTable">
              <tr><td colspan="9" class="py-8 text-center text-gray-400 italic">No appointment requests yet.</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </main>
</div>

<!-- RESCHEDULE MODAL (NURSE) -->
<div id="rescheduleModal" class="hidden fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50">
  <div class="bg-white rounded-2xl shadow-2xl w-full max-w-md p-6">
    <h3 class="text-lg font-bold text-gray-800 mb-1">
      <i class="fa-solid fa-calendar-days text-blue-600 mr-2"></i> Reschedule Appointment
    </h3>
    <p class="text-sm text-gray-500 mb-4" id="rsInfo"></p>
    <div class="space-y-3">
      <div>
        <label class="block text-gray-600 text-sm font-medium mb-1">Reason for rescheduling <span class="text-red-500">*</span></label>
        <textarea id="rsReason" rows="3" class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500" placeholder="Ilagay ang dahilan kung bakit nire-reschedule..."></textarea>
      </div>
      <div>
        <label class="block text-gray-600 text-sm font-medium mb-1">New Date (Monday–Friday only) <span class="text-red-500">*</span></label>
        <input type="date" id="rsDate" class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500" onchange="loadRescheduleSlots()">
      </div>
      <div>
        <label class="block text-gray-600 text-sm font-medium mb-1">New Time <span class="text-red-500">*</span></label>
        <select id="rsTime" class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500">
          <option value="">Select a date first...</option>
        </select>
      </div>
    </div>
    <div class="flex justify-end gap-2 mt-5">
      <button onclick="closeRescheduleModal()" class="px-4 py-2 bg-gray-100 hover:bg-gray-200 text-gray-700 rounded-lg text-sm font-medium">Cancel</button>
      <button id="rsSubmitBtn" onclick="submitReschedule()" class="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-semibold">
        <i class="fa-solid fa-calendar-check mr-1"></i> Confirm Reschedule
      </button>
    </div>
  </div>
</div>

<!-- JAVASCRIPT: Sidebar Toggle -->
<script>
// ===== USER SIDEBAR =====
function toggleUserSidebar() {
    document.getElementById('userSidebar').classList.toggle('-translate-x-full');
    document.getElementById('userOverlay').classList.toggle('hidden');
}
// ===== NURSE SIDEBAR =====
function toggleNurseSidebar() {
    document.getElementById('nurseSidebar').classList.toggle('-translate-x-full');
    document.getElementById('nurseOverlay').classList.toggle('hidden');
}
document.addEventListener('DOMContentLoaded', () => {
    const u = document.getElementById('userMenuBtn');
    if (u) u.onclick = toggleUserSidebar;
    const n = document.getElementById('nurseMenuBtn');
    if (n) n.onclick = toggleNurseSidebar;
});
</script>

<script>
// === PASSWORD TOGGLE ===
function togglePassword(inputId, eyeId) {
    const input = document.getElementById(inputId);
    const eye = document.getElementById(eyeId);
    if (input.type === "password") {
        input.type = "text";
        eye.classList.remove("fa-eye");
        eye.classList.add("fa-eye-slash");
    } else {
        input.type = "password";
        eye.classList.remove("fa-eye-slash");
        eye.classList.add("fa-eye");
    }
}

let currentUser = null;
let selectedTimeSlot = null;
let isSubmittingAppointment = false;
let aptCache = {};
let rescheduleId = null;

// AVAILABLE TIME SLOTS (Fixed schedule)
const ALL_TIME_SLOTS = [
    '08:00', '08:30', '09:00', '09:30', '10:00', '10:30',
    '11:00', '11:30', '13:00', '13:30', '14:00', '14:30', '15:00', '15:30'
];

async function api(url, options = {}) {
    const response = await fetch(url, {
        headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
        ...options
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || 'Something went wrong.');
    return data;
}

// === HELPERS (escape, status label) ===
function esc(s) {
    return String(s === null || s === undefined ? '' : s)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;')
        .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function statusInfo(a) {
    if (a.status === 'approved' && a.rescheduleReason) {
        return { cls: 'status-rescheduled', text: 'Rescheduled' };
    }
    const cls = { pending: 'status-pending', approved: 'status-approved', rejected: 'status-rejected' };
    const txt = { pending: 'Pending', approved: 'Approved', rejected: 'Rejected' };
    return { cls: cls[a.status], text: txt[a.status] };
}

// === PREVENT PAST / WEEKEND DATES ===
function setDateRestrictions() {
    const today = new Date().toISOString().split('T')[0];
    document.getElementById('aptDate').min = today;
}

// === LOAD AVAILABLE TIME SLOTS BASED ON SELECTED DATE ===
async function loadAvailableTimeSlots() {
    const selectedDate = document.getElementById('aptDate').value;
    const container = document.getElementById('timeSlotsContainer');
    selectedTimeSlot = null;
    document.getElementById('aptTime').value = '';

    if (!selectedDate) {
        container.innerHTML = '<span class="text-gray-400 text-sm col-span-3">Select a date first...</span>';
        return;
    }

    const dayOfWeek = new Date(selectedDate + 'T00:00:00').getDay();
    if (dayOfWeek === 0 || dayOfWeek === 6) {
        container.innerHTML = '<span class="text-orange-500 text-sm col-span-3">Appointments are Monday–Friday only.</span>';
        return;
    }

    let takenTimes;
    try {
        const data = await api(`/api/appointments/slots?date=${encodeURIComponent(selectedDate)}`);
        takenTimes = data.taken;
    } catch (error) {
        container.innerHTML = `<span class="text-red-500 text-sm col-span-3">${esc(error.message)}</span>`;
        return;
    }

    container.innerHTML = ALL_TIME_SLOTS.map(time => {
        if (takenTimes.includes(time)) {
            return `<div class="time-slot taken border rounded px-2 py-1 text-center text-sm">${time}</div>`;
        }
        return `<div class="time-slot border border-blue-300 rounded px-2 py-1 text-center text-sm bg-white" onclick="selectTimeSlot('${time}', event)">${time}</div>`;
    }).join('');
}

// === SELECT TIME SLOT ===
function selectTimeSlot(time, clickEvent) {
    selectedTimeSlot = time;
    document.getElementById('aptTime').value = time;
    document.querySelectorAll('.time-slot').forEach(el => el.classList.remove('selected'));
    clickEvent.currentTarget.classList.add('selected');
}

// === SWITCH LOGIN/REGISTER TABS (itim palagi ang text) ===
function showAuthTab(tab) {
    const tabLogin = document.getElementById('tabLogin');
    const tabReg = document.getElementById('tabRegister');
    if (tab === 'login') {
        tabLogin.classList.add('tab-active');
        tabReg.classList.remove('tab-active');
        document.getElementById('formLogin').classList.remove('hidden');
        document.getElementById('formRegister').classList.add('hidden');
    } else {
        tabReg.classList.add('tab-active');
        tabLogin.classList.remove('tab-active');
        document.getElementById('formRegister').classList.remove('hidden');
        document.getElementById('formLogin').classList.add('hidden');
    }
    document.getElementById('authMsg').textContent = '';
}

// === REGISTER USER ===
async function registerUser() {
    const name = document.getElementById('regName').value.trim();
    const email = document.getElementById('regEmail').value.trim().toLowerCase();
    const pass = document.getElementById('regPass').value;
    const role = document.getElementById('regRole').value;
    const msg = document.getElementById('authMsg');
    const btn = document.getElementById('registerButton');

    if (!name || !email || !pass) {
        msg.textContent = 'Please fill in all fields!';
        msg.className = 'mt-4 text-center font-medium text-orange-600';
        return;
    }
    if (!email.endsWith('@gmail.com')) {
        msg.textContent = 'Email must end with @gmail.com';
        msg.className = 'mt-4 text-center font-medium text-orange-600';
        return;
    }
    if (pass.length < 6) {
        msg.textContent = 'Password must be at least 6 characters!';
        msg.className = 'mt-4 text-center font-medium text-orange-600';
        return;
    }

    btn.disabled = true;
    btn.classList.add('opacity-60', 'cursor-not-allowed');
    try {
        await api('/api/register', { method: 'POST', body: JSON.stringify({ name, email, password: pass, role }) });
        msg.textContent = 'Account created! Please sign in.';
        msg.className = 'mt-4 text-center font-medium text-green-700';
        setTimeout(() => showAuthTab('login'), 1500);
    } catch (error) {
        msg.textContent = error.message;
        msg.className = 'mt-4 text-center font-medium text-red-600';
    } finally {
        btn.disabled = false;
        btn.classList.remove('opacity-60', 'cursor-not-allowed');
    }
}

// === LOGIN USER ===
async function loginUser() {
    const email = document.getElementById('loginEmail').value.trim().toLowerCase();
    const pass = document.getElementById('loginPass').value;
    const msg = document.getElementById('authMsg');
    const loginButton = document.getElementById('loginButton');

    if (!email || !pass) {
        msg.textContent = 'Enter your email and password.';
        msg.className = 'mt-4 text-center font-medium text-orange-600';
        return;
    }
    if (!email.endsWith('@gmail.com') && email !== 'nurse@school.ph') {
        msg.textContent = 'Email must end with @gmail.com';
        msg.className = 'mt-4 text-center font-medium text-orange-600';
        return;
    }

    loginButton.disabled = true;
    loginButton.classList.add('opacity-60', 'cursor-not-allowed');
    try {
        const data = await api('/api/login', { method: 'POST', body: JSON.stringify({ email, password: pass }) });
        currentUser = data.user;
        openDashboard();
    } catch (error) {
        const message = error.message === 'Failed to fetch'
            ? 'Cannot connect to the clinic server. Run "py app.py" and open http://127.0.0.1:5050.'
            : error.message;
        msg.textContent = message;
        msg.className = 'mt-4 text-center font-medium text-red-600';
    } finally {
        loginButton.disabled = false;
        loginButton.classList.remove('opacity-60', 'cursor-not-allowed');
    }
}

// === SWITCH NURSE TABS ===
function showNurseTab(tab) {
    document.getElementById('nurseViewDashboard').classList.add('hidden');
    document.getElementById('nurseViewAppointments').classList.add('hidden');
    document.getElementById('nurseViewHistory').classList.add('hidden');
    document.getElementById('navDashboard').classList.remove('active');
    document.getElementById('navHistory').classList.remove('active');
    document.getElementById('navAppointments').classList.remove('active');

    if (tab === 'dashboard') {
        document.getElementById('nurseViewDashboard').classList.remove('hidden');
        document.getElementById('navDashboard').classList.add('active');
        updateStats();
    } else if (tab === 'history') {
        document.getElementById('nurseViewHistory').classList.remove('hidden');
        document.getElementById('navHistory').classList.add('active');
        renderHistory(true);
    } else if (tab === 'appointments') {
        document.getElementById('nurseViewAppointments').classList.remove('hidden');
        document.getElementById('navAppointments').classList.add('active');
        renderAllAppointments();
    }
}

// === OPEN DASHBOARD ===
function openDashboard() {
    document.getElementById('authSection').classList.add('hidden');
    if (currentUser.role === 'nurse') {
        document.getElementById('nurseDashboard').classList.remove('hidden');
        showNurseTab('dashboard');
    } else {
        document.getElementById('userDashboard').classList.remove('hidden');
        document.getElementById('displayName').textContent = currentUser.name;
        const labels = { Student: 'Student', Teacher: 'Teacher', Staff: 'Staff' };
        document.getElementById('displayRole').textContent = labels[currentUser.role];
        renderMyAppointments();
        setDateRestrictions();
    }
}

// === SUBMIT APPOINTMENT WITH TIME SLOT VALIDATION ===
async function submitAppointment() {
    if (isSubmittingAppointment) return;

    const date = document.getElementById('aptDate').value;
    const time = selectedTimeSlot;
    const type = document.getElementById('aptType').value;
    const reason = document.getElementById('aptReason').value.trim();

    if (!date || !time || !reason) {
        alert('Please select a date, available time slot, and fill in purpose!');
        return;
    }

    const submitButton = document.getElementById('submitAppointmentButton');
    isSubmittingAppointment = true;
    submitButton.disabled = true;
    submitButton.classList.add('opacity-60', 'cursor-not-allowed');

    try {
        await api('/api/appointments', { method: 'POST', body: JSON.stringify({ date, time, type, reason }) });
        alert('Appointment submitted!');
    } catch (error) {
        alert(error.message);
        loadAvailableTimeSlots();
        return;
    } finally {
        isSubmittingAppointment = false;
        submitButton.disabled = false;
        submitButton.classList.remove('opacity-60', 'cursor-not-allowed');
    }

    document.getElementById('aptDate').value = '';
    document.getElementById('aptTime').value = '';
    document.getElementById('aptReason').value = '';
    document.getElementById('timeSlotsContainer').innerHTML = '<span class="text-gray-400 text-sm col-span-3">Select a date first...</span>';
    selectedTimeSlot = null;
    renderMyAppointments();
}

// === RENDER USER'S APPOINTMENTS ===
async function renderMyAppointments() {
    let apts;
    try {
        apts = (await api('/api/appointments')).appointments;
    } catch (error) {
        document.getElementById('myAppointmentsTable').innerHTML =
            `<tr><td colspan="7" class="py-4 text-center text-red-500">${esc(error.message)}</td></tr>`;
        return;
    }

    const tbody = document.getElementById('myAppointmentsTable');
    if (apts.length === 0) {
        tbody.innerHTML = '<tr><td colspan="7" class="py-4 text-center text-gray-400 italic">No appointments yet.</td></tr>';
        return;
    }

    tbody.innerHTML = apts.map((a, i) => {
        const st = statusInfo(a);
        let remarks = '—';
        if (a.status === 'rejected') {
            remarks = esc(a.rejectionReason || 'No reason provided.');
        } else if (a.rescheduleReason) {
            remarks = '<b>Rescheduled by nurse:</b> ' + esc(a.rescheduleReason) +
                (a.oldDate ? '<br><span class="text-xs text-gray-500">Previous schedule: ' + esc(a.oldDate) + ' ' + esc(a.oldTime) + '</span>' : '');
        }
        return `
        <tr class="border-b hover:bg-blue-50">
            <td class="py-2 px-2">${i + 1}</td>
            <td class="py-2 px-2">${esc(a.date)}</td>
            <td class="py-2 px-2">${esc(a.time)}</td>
            <td class="py-2 px-2">${esc(a.type)}</td>
            <td class="py-2 px-2 max-w-xs truncate">${esc(a.reason)}</td>
            <td class="py-2 px-2"><span class="px-2 py-0.5 rounded-full text-xs font-medium ${st.cls}">${st.text}</span></td>
            <td class="py-2 px-2 max-w-xs">${remarks}</td>
        </tr>`;
    }).join('');
}

// === UPDATE STATISTICS ===
async function updateStats() {
    try {
        const data = await api('/api/stats');
        document.getElementById('statTotal').textContent = data.total;
        document.getElementById('statNew').textContent = data.newToday;
        document.getElementById('statPending').textContent = data.pending;
        document.getElementById('statApproved').textContent = data.approved;
        document.getElementById('pendingBadge').textContent = data.pending;
    } catch (error) {
        console.error('Failed to load stats:', error);
    }
}

// === RENDER ALL APPOINTMENTS (NURSE PANEL) ===
async function renderAllAppointments() {
    const filterRole = document.getElementById('filterRole').value;
    const filterStatus = document.getElementById('filterStatus').value;

    try {
        const data = await api('/api/appointments/all');
        let apts = data.appointments;
        apts.forEach(a => { aptCache[a.id] = a; });

        if (filterRole !== 'all') apts = apts.filter(a => a.userRole === filterRole);
        if (filterStatus === 'rescheduled') apts = apts.filter(a => a.rescheduleReason);
        else if (filterStatus !== 'all') apts = apts.filter(a => a.status === filterStatus);

        const tbody = document.getElementById('allAppointmentsTable');
        if (apts.length === 0) {
            tbody.innerHTML = '<tr><td colspan="9" class="py-8 text-center text-gray-400 italic">No appointment requests found.</td></tr>';
            return;
        }

        tbody.innerHTML = apts.map((a, i) => {
            const st = statusInfo(a);
            return `
            <tr class="border-b hover:bg-blue-50">
                <td class="py-2 px-2 text-center">${i + 1}</td>
                <td class="py-2 px-2">${esc(a.userName)}</td>
                <td class="py-2 px-2">${esc(a.userRole)}</td>
                <td class="py-2 px-2">${esc(a.date)}</td>
                <td class="py-2 px-2">${esc(a.time)}</td>
                <td class="py-2 px-2">${esc(a.type)}</td>
                <td class="py-2 px-2 max-w-xs truncate">${esc(a.reason)}</td>
                <td class="py-2 px-2 text-center">
                    <span class="px-2 py-0.5 rounded-full text-xs font-medium ${st.cls}">${st.text}</span>
                </td>
                <td class="py-2 px-2 text-center whitespace-nowrap">
                    ${a.status === 'pending' ? `
                    <button onclick="approveAppointment(${a.id})" class="text-green-600 hover:text-green-800 mr-2" title="Approve">
                        <i class="fa-solid fa-check"></i>
                    </button>
                    <button onclick="openRescheduleModal(${a.id})" class="text-blue-600 hover:text-blue-800 mr-2" title="Reschedule">
                        <i class="fa-solid fa-calendar-days"></i>
                    </button>
                    ` : ''}
                    <button onclick="printAppointment(${a.id})" class="text-gray-600 hover:text-gray-800 mr-2" title="Print">
                        <i class="fa-solid fa-print"></i>
                    </button>
                    <button onclick="deleteAppointment(${a.id})" class="text-red-600 hover:text-red-800" title="Delete">
                        <i class="fa-solid fa-trash"></i>
                    </button>
                </td>
            </tr>`;
        }).join('');
    } catch (error) {
        document.getElementById('allAppointmentsTable').innerHTML =
            `<tr><td colspan="9" class="py-8 text-center text-red-500">${esc(error.message)}</td></tr>`;
    }
}

// === APPROVE APPOINTMENT ===
async function approveAppointment(id) {
    if (!confirm('Approve this appointment? An email notification will be sent to the patient.')) return;
    try {
        await api(`/api/appointments/${id}/approve`, { method: 'POST' });
        alert('Appointment approved! Email notification sent to the patient.');
        updateStats();
        renderAllAppointments();
        renderHistory(false);
    } catch (error) {
        alert(error.message);
    }
}

// === RESCHEDULE APPOINTMENT (REPLACES REJECT) ===
function openRescheduleModal(id) {
    const a = aptCache[id];
    if (!a) return;
    rescheduleId = id;
    document.getElementById('rsInfo').textContent = a.userName + ' — current: ' + a.date + ' ' + a.time;
    document.getElementById('rsReason').value = '';
    document.getElementById('rsDate').value = '';
    document.getElementById('rsDate').min = new Date().toISOString().split('T')[0];
    document.getElementById('rsTime').innerHTML = '<option value="">Select a date first...</option>';
    document.getElementById('rescheduleModal').classList.remove('hidden');
}

function closeRescheduleModal() {
    document.getElementById('rescheduleModal').classList.add('hidden');
    rescheduleId = null;
}

async function loadRescheduleSlots() {
    const selectedDate = document.getElementById('rsDate').value;
    const select = document.getElementById('rsTime');
    if (!selectedDate) {
        select.innerHTML = '<option value="">Select a date first...</option>';
        return;
    }
    const day = new Date(selectedDate + 'T00:00:00').getDay();
    if (day === 0 || day === 6) {
        select.innerHTML = '<option value="">Monday–Friday only</option>';
        return;
    }
    try {
        const data = await api(`/api/appointments/slots?date=${encodeURIComponent(selectedDate)}`);
        const free = ALL_TIME_SLOTS.filter(t => !data.taken.includes(t));
        if (free.length === 0) {
            select.innerHTML = '<option value="">No available slots on this date</option>';
            return;
        }
        select.innerHTML = '<option value="">Select time...</option>' +
            free.map(t => `<option value="${t}">${t}</option>`).join('');
    } catch (error) {
        select.innerHTML = `<option value="">${esc(error.message)}</option>`;
    }
}

async function submitReschedule() {
    const reason = document.getElementById('rsReason').value.trim();
    const newDate = document.getElementById('rsDate').value;
    const newTime = document.getElementById('rsTime').value;

    if (!reason) { alert('Please enter the reason for rescheduling first.'); return; }
    if (!newDate || !newTime) { alert('Please select the new date and time.'); return; }

    const btn = document.getElementById('rsSubmitBtn');
    btn.disabled = true;
    btn.classList.add('opacity-60', 'cursor-not-allowed');
    try {
        await api(`/api/appointments/${rescheduleId}/reschedule`, {
            method: 'POST',
            body: JSON.stringify({ date: newDate, time: newTime, reason })
        });
        alert('Appointment rescheduled. Email notification sent to the patient.');
        closeRescheduleModal();
        updateStats();
        renderAllAppointments();
        renderHistory(false);
    } catch (error) {
        alert(error.message);
        loadRescheduleSlots();
    } finally {
        btn.disabled = false;
        btn.classList.remove('opacity-60', 'cursor-not-allowed');
    }
}

// === DELETE APPOINTMENT ===
async function deleteAppointment(id) {
    if (!confirm('Delete this appointment permanently? This cannot be undone.')) return;
    try {
        await api(`/api/appointments/${id}`, { method: 'DELETE' });
        delete aptCache[id];
        alert('Appointment deleted.');
        updateStats();
        renderAllAppointments();
        renderHistory(false);
    } catch (error) {
        alert(error.message);
    }
}

// === PRINT APPOINTMENT DETAILS ===
function printAppointment(id) {
    const a = aptCache[id];
    if (!a) { alert('Appointment details not found.'); return; }
    const st = statusInfo(a);
    const rows = [
        ['Patient Name', a.userName],
        ['Role', a.userRole],
        ['Date', a.date],
        ['Time', a.time],
        ['Visit Type', a.type],
        ['Purpose / Symptoms', a.reason],
        ['Status', st.text]
    ];
    if (a.rescheduleReason) {
        rows.push(['Reschedule Reason', a.rescheduleReason]);
        if (a.oldDate) rows.push(['Previous Schedule', a.oldDate + ' ' + a.oldTime]);
    }
    if (a.status === 'rejected' && a.rejectionReason) {
        rows.push(['Rejection Reason', a.rejectionReason]);
    }
    const body = rows.map(r => '<tr><th>' + esc(r[0]) + '</th><td>' + esc(r[1]) + '</td></tr>').join('');

    const w = window.open('', '_blank', 'width=800,height=700');
    if (!w) { alert('Please allow pop-ups to print.'); return; }
    w.document.write(
        '<html><head><title>Appointment #' + a.id + '</title>' +
        '<style>' +
        'body{font-family:Arial,sans-serif;padding:40px;color:#111;}' +
        'h1{text-align:center;margin-bottom:4px;}' +
        'p.sub{text-align:center;color:#555;margin-top:0;margin-bottom:30px;}' +
        'table{width:100%;border-collapse:collapse;}' +
        'th,td{border:1px solid #999;padding:10px;text-align:left;vertical-align:top;}' +
        'th{background:#f1f5f9;width:35%;}' +
        '.foot{margin-top:50px;display:flex;justify-content:space-between;}' +
        '.sig{border-top:1px solid #000;width:220px;text-align:center;padding-top:4px;font-size:13px;}' +
        '</style></head><body>' +
        '<h1>School Clinic</h1>' +
        '<p class="sub">Appointment Details &mdash; Ref #' + a.id + '</p>' +
        '<table>' + body + '</table>' +
        '<div class="foot"><div class="sig">Patient Signature</div><div class="sig">School Nurse</div></div>' +
        '<p style="margin-top:30px;font-size:12px;color:#777;">Printed: ' + esc(new Date().toLocaleString()) + '</p>' +
        '</body></html>'
    );
    w.document.close();
    w.focus();
    setTimeout(() => { w.print(); }, 300);
}

// === RENDER APPOINTMENT HISTORY ===
async function renderHistory(oldestFirst = false) {
    try {
        const data = await api('/api/appointments/all');
        let apts = data.appointments;
        apts.forEach(a => { aptCache[a.id] = a; });

        apts.sort((a, b) => {
            const dateA = new Date(`${a.date}T${a.time}`);
            const dateB = new Date(`${b.date}T${b.time}`);
            return oldestFirst ? dateA - dateB : dateB - dateA;
        });

        const tbody = document.getElementById('historyTable');
        if (apts.length === 0) {
            tbody.innerHTML = '<tr><td colspan="9" class="py-8 text-center text-gray-400 italic">No appointment history yet.</td></tr>';
            return;
        }

        tbody.innerHTML = apts.map((a, i) => {
            const st = statusInfo(a);
            return `
            <tr class="border-b hover:bg-blue-50">
                <td class="py-2 px-2 text-center">${i + 1}</td>
                <td class="py-2 px-2">${esc(a.userName)}</td>
                <td class="py-2 px-2">${esc(a.userRole)}</td>
                <td class="py-2 px-2">${esc(a.date)}</td>
                <td class="py-2 px-2">${esc(a.time)}</td>
                <td class="py-2 px-2">${esc(a.type)}</td>
                <td class="py-2 px-2 max-w-xs truncate">${esc(a.reason)}</td>
                <td class="py-2 px-2 text-center">
                    <span class="px-2 py-0.5 rounded-full text-xs font-medium ${st.cls}">${st.text}</span>
                </td>
                <td class="py-2 px-2 text-center whitespace-nowrap">
                    <button onclick="printAppointment(${a.id})" class="text-gray-600 hover:text-gray-800 mr-2" title="Print">
                        <i class="fa-solid fa-print"></i>
                    </button>
                    <button onclick="deleteAppointment(${a.id})" class="text-red-600 hover:text-red-800" title="Delete">
                        <i class="fa-solid fa-trash"></i>
                    </button>
                </td>
            </tr>`;
        }).join('');
    } catch (error) {
        document.getElementById('historyTable').innerHTML =
            `<tr><td colspan="9" class="py-8 text-center text-red-500">${esc(error.message)}</td></tr>`;
    }
}

// === SEARCH PATIENT HISTORY ===
async function searchPatientHistory() {
    const name = document.getElementById('searchPatientName').value.trim().toLowerCase();
    const resultDiv = document.getElementById('patientHistoryResult');
    const tableBody = document.getElementById('patientHistoryTable');

    if (!name) { alert('Please enter a name to search.'); return; }

    try {
        const data = await api('/api/appointments/all');
        const matches = data.appointments.filter(a => a.userName.toLowerCase().includes(name));
        resultDiv.classList.remove('hidden');

        if (matches.length === 0) {
            tableBody.innerHTML = '<tr><td colspan="6" class="py-4 text-center text-gray-400 italic">No records found for that name.</td></tr>';
            return;
        }

        tableBody.innerHTML = matches.map((a, i) => {
            const st = statusInfo(a);
            return `
            <tr class="border-b hover:bg-blue-50">
                <td class="py-2 px-2">${i + 1}</td>
                <td class="py-2 px-2">${esc(a.date)}</td>
                <td class="py-2 px-2">${esc(a.time)}</td>
                <td class="py-2 px-2">${esc(a.type)}</td>
                <td class="py-2 px-2 max-w-xs truncate">${esc(a.reason)}</td>
                <td class="py-2 px-2">
                    <span class="px-2 py-0.5 rounded-full text-xs font-medium ${st.cls}">${st.text}</span>
                </td>
            </tr>`;
        }).join('');
    } catch (error) {
        resultDiv.classList.remove('hidden');
        tableBody.innerHTML = `<tr><td colspan="6" class="py-4 text-center text-red-500">${esc(error.message)}</td></tr>`;
    }
}

// === LOGOUT ===
async function logoutSystem() {
    if (!confirm('Are you sure you want to log out?')) return;
    try {
        await api('/api/logout', { method: 'POST' });
    } catch (error) {
        console.warn('Logout API error:', error);
    }
    currentUser = null;
    document.getElementById('authSection').classList.remove('hidden');
    document.getElementById('userDashboard').classList.add('hidden');
    document.getElementById('nurseDashboard').classList.add('hidden');
    document.getElementById('loginEmail').value = '';
    document.getElementById('loginPass').value = '';
    document.getElementById('authMsg').textContent = '';
    showAuthTab('login');
}

// === INITIALIZE ON PAGE LOAD (+ Enter key support sa forms) ===
document.addEventListener('DOMContentLoaded', () => {
    setDateRestrictions();

    ['loginEmail', 'loginPass'].forEach(id => {
        document.getElementById(id).addEventListener('keydown', e => { if (e.key === 'Enter') loginUser(); });
    });
    ['regName', 'regEmail', 'regPass'].forEach(id => {
        document.getElementById(id).addEventListener('keydown', e => { if (e.key === 'Enter') registerUser(); });
    });
    document.getElementById('searchPatientName').addEventListener('keydown', e => {
        if (e.key === 'Enter') searchPatientHistory();
    });
    document.addEventListener('keydown', e => {
        if (e.key === 'Escape') closeRescheduleModal();
    });
});
</script>
<style>
.nx-hero{background:linear-gradient(135deg,#1e3a8a 0%,#2563eb 55%,#0ea5e9 100%);border-radius:18px;color:#fff;padding:22px 24px;box-shadow:0 10px 30px rgba(37,99,235,.25);}
.nx-hero p{color:#dbeafe}
.nx-chip{display:inline-flex;align-items:center;gap:8px;background:rgba(255,255,255,.16);border:1px solid rgba(255,255,255,.28);padding:6px 12px;border-radius:999px;font-size:13px;font-weight:500}
.nx-kpi{background:#fff;border:1px solid #e5e7eb;border-radius:16px;padding:16px;display:flex;align-items:center;gap:14px;box-shadow:0 2px 12px rgba(0,0,0,.04);transition:all .3s ease}
.nx-kpi:hover{transform:translateY(-3px);box-shadow:0 10px 26px rgba(0,0,0,.08)}
.nx-kpi .ico{width:46px;height:46px;border-radius:12px;display:flex;align-items:center;justify-content:center;font-size:18px;flex-shrink:0}
.nx-kpi .lbl{font-size:12px;color:#6b7280;font-weight:500;text-transform:uppercase;letter-spacing:.04em}
.nx-kpi .val{font-size:26px;font-weight:700;color:#111827;line-height:1.1}
.nx-seg{display:inline-flex;background:#f1f5f9;border-radius:12px;padding:4px;gap:4px}
.nx-seg button{padding:8px 16px;border-radius:9px;font-size:13px;font-weight:600;color:#475569}
.nx-seg button.on{background:#fff;color:#1d4ed8;box-shadow:0 1px 6px rgba(0,0,0,.1)}
.nx-table th{font-size:12px;text-transform:uppercase;letter-spacing:.05em;color:#64748b;font-weight:600;background:#f8fafc;padding:12px;text-align:left;white-space:nowrap}
.nx-table td{padding:12px;border-bottom:1px solid #f1f5f9;vertical-align:middle}
.nx-table tbody tr:hover{background:#eff6ff}
.nx-avatar{width:36px;height:36px;border-radius:50%;background:linear-gradient(135deg,#3b82f6,#06b6d4);color:#fff;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:14px;flex-shrink:0}
.nx-empty{text-align:center;padding:48px 16px;color:#94a3b8}
.nx-empty i{font-size:42px;margin-bottom:10px;color:#cbd5e1}
.nx-new{background:#dcfce7;color:#166534;font-size:10px;font-weight:700;padding:2px 7px;border-radius:999px;margin-left:6px;letter-spacing:.04em}
.nx-badge{background:#ef4444;color:#fff;font-size:11px;font-weight:700;min-width:20px;height:20px;border-radius:999px;display:none;align-items:center;justify-content:center;padding:0 6px;margin-left:auto}
.nx-chart{display:flex;align-items:flex-end;gap:10px;height:200px;padding:8px 4px 0}
.nx-bar-col{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:flex-end;height:100%;cursor:pointer}
.nx-bar{width:100%;max-width:38px;border-radius:8px 8px 0 0;background:linear-gradient(180deg,#60a5fa,#2563eb);min-height:4px;transition:all .3s ease;position:relative}
.nx-bar-col:hover .nx-bar{filter:brightness(1.1);transform:scaleY(1.03);transform-origin:bottom}
.nx-bar.sel{background:linear-gradient(180deg,#fbbf24,#f59e0b)}
.nx-bar.zero{background:#e2e8f0}
.nx-bar-val{font-size:12px;font-weight:700;color:#1e3a8a;margin-bottom:4px}
.nx-bar-lbl{font-size:11px;color:#64748b;margin-top:6px;font-weight:500}
.nx-pill{display:inline-block;padding:2px 10px;border-radius:999px;font-size:12px;font-weight:600}
@media (max-width:640px){.nx-chart{gap:4px}.nx-bar-val{font-size:10px}.nx-bar-lbl{font-size:9px}}

/* ===== MONTHLY RECORD: RESPONSIVE FIX ===== */
#nurseDashboard main { min-width: 0; }
#nurseViewMonthly { min-width: 0; }
#nurseViewMonthly .grid > * { min-width: 0; }          /* pinipigilan ang table na magpalobo ng layout */
#nurseViewMonthly .nx-kpi { min-width: 0; }
#nurseViewMonthly .nx-kpi > div:last-child { min-width: 0; }
#nurseViewMonthly .nx-kpi .val { overflow-wrap: anywhere; }  /* para sa "September" atbp. */

/* Tablet at maliliit na laptop (may sidebar): i-stack ang table at detail panel */
@media (max-width: 1279px) {
  #nurseViewMonthly .grid.lg\:grid-cols-5 { grid-template-columns: minmax(0, 1fr); }
  #nurseViewMonthly .lg\:col-span-3,
  #nurseViewMonthly .lg\:col-span-2 { grid-column: 1 / -1; }
}

/* Phone */
@media (max-width: 640px) {
  #nurseViewMonthly .nx-hero { padding: 16px; }
  #nurseViewMonthly .nx-hero h2 { font-size: 1.25rem; }
  #nurseViewMonthly .nx-hero > div:last-child { width: 100%; }
  #nurseViewMonthly .nx-hero > div:last-child select { flex: 1; }

  #nurseViewMonthly .nx-kpi { padding: 12px; gap: 10px; }
  #nurseViewMonthly .nx-kpi .ico { width: 38px; height: 38px; font-size: 15px; }
  #nurseViewMonthly .nx-kpi .val { font-size: 20px; }
  #nurseViewMonthly .nx-kpi .lbl { font-size: 11px; }

  #nurseViewMonthly .nx-chart { gap: 3px; }
  #nurseViewMonthly .nx-bar-col { min-width: 0; }

  #nurseViewMonthly .nx-table th { padding: 8px; font-size: 11px; }
  #nurseViewMonthly .nx-table td { padding: 8px; font-size: 13px; }
  #nurseViewMonthly .nx-pill { padding: 2px 8px; font-size: 11px; }
}

/* ===== TODAY'S APPOINTMENTS: RESPONSIVE FIX (para gumana sa phone / tablet / laptop) ===== */
#nurseViewToday { min-width: 0; }
#nurseViewToday .grid > * { min-width: 0; }
#nurseViewToday .nx-kpi { min-width: 0; }
#nurseViewToday .nx-kpi > div:last-child { min-width: 0; }
#nurseViewToday .overflow-x-auto { -webkit-overflow-scrolling: touch; }
#nurseViewToday .nx-no { display:inline-flex; align-items:center; justify-content:center; min-width:28px; height:28px; border-radius:999px; background:#dbeafe; color:#1e40af; font-weight:700; font-size:13px; }

@media (max-width: 640px) {
  #nurseViewToday .nx-hero { padding: 16px; }
  #nurseViewToday .nx-hero h2 { font-size: 1.25rem; }

  #nurseViewToday .nx-kpi { padding: 12px; gap: 10px; }
  #nurseViewToday .nx-kpi .ico { width: 38px; height: 38px; font-size: 15px; }
  #nurseViewToday .nx-kpi .val { font-size: 20px; }
  #nurseViewToday .nx-kpi .lbl { font-size: 11px; }

  #nurseViewToday .nx-seg { width: 100%; }
  #nurseViewToday .nx-seg button { flex: 1; padding: 8px 6px; font-size: 12px; }

  #nurseViewToday .nx-table th { padding: 8px; font-size: 11px; }
  #nurseViewToday .nx-table td { padding: 8px; font-size: 13px; }
}
</style>

<script>
(function () {
    const MONTHS = ['January','February','March','April','May','June','July','August','September','October','November','December'];
    const SHORT = MONTHS.map(m => m.slice(0, 3));
    const $ = id => document.getElementById(id);

    let todayData = { today: '', booked: [], scheduled: [] };
    let todayMode = 'booked';
    let monthlyYear = new Date().getFullYear();
    let monthlyData = null;
    let selectedMonth = null;

    function nurseVisible() {
        const el = $('nurseDashboard');
        return el && !el.classList.contains('hidden');
    }

    function fmtLongDate(iso) {
        if (!iso) return '';
        const d = new Date(iso + 'T00:00:00');
        return d.toLocaleDateString('en-US', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' });
    }

    function stInfo(a) { return typeof statusInfo === 'function' ? statusInfo(a) : { cls: '', text: a.status }; }

    // ---------- SORT: pinakamaagang petsa at oras ang #1 ----------
    function timeKey(a) {
        const parts = String(a.time || '').split(':');
        const h = (parts[0] || '0').trim().padStart(2, '0');
        const m = (parts[1] || '00').trim().padStart(2, '0');
        return String(a.date || '') + ' ' + h + ':' + m;
    }

    function sortByDateTime(list) {
        return (list || []).slice().sort((x, y) => {
            const kx = timeKey(x), ky = timeKey(y);
            if (kx < ky) return -1;
            if (kx > ky) return 1;
            return (x.id || 0) - (y.id || 0);
        });
    }

    // ---------- BUILD UI ----------
    function build() {
        const nav = document.querySelector('#nurseSidebar nav');
        const main = document.querySelector('#nurseDashboard main');
        if (!nav || !main || $('navToday')) return;

        const mk = (id, icon, label, tab) => {
            const a = document.createElement('a');
            a.href = '#';
            a.id = id;
            a.className = 'sidebar-link flex items-center gap-3 px-4 py-3 rounded-lg text-blue-100';
            a.innerHTML = '<i class="fa-solid ' + icon + ' w-5 text-center"></i> ' + label +
                (tab === 'today' ? '<span id="nxTodayBadge" class="nx-badge">0</span>' : '');
            a.addEventListener('click', e => { e.preventDefault(); showNurseTab(tab); });
            return a;
        };
        $('navDashboard').insertAdjacentElement('afterend', mk('navToday', 'fa-calendar-day', "Today's Appointments", 'today'));
        $('navAppointments').insertAdjacentElement('afterend', mk('navMonthly', 'fa-chart-column', 'Monthly Record', 'monthly'));

        const today = document.createElement('div');
        today.id = 'nurseViewToday';
        today.className = 'hidden fade-in';
        main.appendChild(today);

        const monthly = document.createElement('div');
        monthly.id = 'nurseViewMonthly';
        monthly.className = 'hidden fade-in';
        main.appendChild(monthly);
    }

    // ---------- TAB ROUTER (wraps original, hindi ginagalaw ang original) ----------
    function hookRouter() {
        const orig = window.showNurseTab;
        window.showNurseTab = function (tab) {
            ['nurseViewToday', 'nurseViewMonthly'].forEach(id => $(id) && $(id).classList.add('hidden'));
            ['navToday', 'navMonthly'].forEach(id => $(id) && $(id).classList.remove('active'));

            if (tab === 'today' || tab === 'monthly') {
                ['nurseViewDashboard', 'nurseViewAppointments', 'nurseViewHistory'].forEach(id => $(id).classList.add('hidden'));
                ['navDashboard', 'navHistory', 'navAppointments'].forEach(id => $(id).classList.remove('active'));
                if (tab === 'today') {
                    $('nurseViewToday').classList.remove('hidden');
                    $('navToday').classList.add('active');
                    loadToday();
                } else {
                    $('nurseViewMonthly').classList.remove('hidden');
                    $('navMonthly').classList.add('active');
                    loadMonthly(monthlyYear);
                }
                const sb = $('nurseSidebar');
                if (window.innerWidth < 768 && sb && !sb.classList.contains('-translate-x-full')) toggleNurseSidebar();
            } else {
                orig(tab);
            }
        };

        // Auto-refresh ng Today kapag may inaprubahan / nire-reschedule
        ['approveAppointment', 'submitReschedule', 'deleteAppointment'].forEach(name => {
            const fn = window[name];
            if (typeof fn !== 'function') return;
            window[name] = async function () {
                const r = await fn.apply(this, arguments);
                loadToday(true);
                return r;
            };
        });
    }

    // ---------- TODAY ----------
    async function loadToday(silent) {
        try {
            const data = await api('/api/appointments/today');
            // Naka-ayos ayon sa petsa at oras: 8:00 = #1, 8:30 = #2, at iba pa
            todayData = {
                today: data.today,
                booked: sortByDateTime(data.booked),
                scheduled: sortByDateTime(data.scheduled)
            };
            [...todayData.booked, ...todayData.scheduled].forEach(a => { aptCache[a.id] = a; });
            updateBadge();
            if (!silent || !$('nurseViewToday').classList.contains('hidden')) renderToday();
        } catch (e) {
            if (!silent) $('nurseViewToday').innerHTML = '<div class="dashboard-card p-6 text-red-500">' + esc(e.message) + '</div>';
        }
    }

    function updateBadge() {
        const pending = todayData.booked.filter(a => a.status === 'pending').length;
        const b = $('nxTodayBadge');
        if (!b) return;
        b.textContent = pending;
        b.style.display = pending > 0 ? 'inline-flex' : 'none';
    }

    function setTodayMode(m) { todayMode = m; renderToday(); }
    window.nxSetTodayMode = setTodayMode;
    window.nxRefreshToday = () => loadToday();

    function renderToday() {
        const d = todayData;
        const booked = d.booked, sched = d.scheduled;
        const pend = booked.filter(a => a.status === 'pending').length;
        const appr = booked.filter(a => a.status === 'approved').length;
        const list = todayMode === 'booked' ? booked : sched;

        const kpi = (icon, bg, color, label, val) =>
            '<div class="nx-kpi"><div class="ico" style="background:' + bg + ';color:' + color + '"><i class="fa-solid ' + icon + '"></i></div>' +
            '<div><div class="lbl">' + label + '</div><div class="val">' + val + '</div></div></div>';

        const rows = list.map((a, i) => {
            const st = stInfo(a);
            const initial = esc((a.userName || '?').trim().charAt(0).toUpperCase());
            const when = todayMode === 'booked'
                ? '<div class="font-semibold text-gray-800">' + esc(a.date) + '</div><div class="text-xs text-gray-500">' + esc(a.time) + '</div>'
                : '<div class="font-semibold text-gray-800">' + esc(a.time) + '</div><div class="text-xs text-gray-500">Today</div>';
            const bookedAt = todayMode === 'booked'
                ? '<div class="text-xs text-gray-500"><i class="fa-regular fa-clock mr-1"></i>Booked ' + esc(a.bookedAt || '') + '</div>' : '';
            const actions = a.status === 'pending'
                ? '<button onclick="approveAppointment(' + a.id + ')" class="px-3 py-1.5 bg-green-600 hover:bg-green-700 text-white rounded-lg text-xs font-semibold mr-1"><i class="fa-solid fa-check mr-1"></i>Approve</button>' +
                  '<button onclick="openRescheduleModal(' + a.id + ')" class="px-3 py-1.5 bg-blue-50 hover:bg-blue-100 text-blue-700 rounded-lg text-xs font-semibold mr-1"><i class="fa-solid fa-calendar-days mr-1"></i>Reschedule</button>'
                : '';
            return '<tr>' +
                '<td class="text-center"><span class="nx-no">' + (i + 1) + '</span></td>' +
                '<td><div class="flex items-center gap-3"><div class="nx-avatar">' + initial + '</div><div>' +
                    '<div class="font-semibold text-gray-800">' + esc(a.userName) +
                    (todayMode === 'booked' && a.status === 'pending' ? '<span class="nx-new">NEW</span>' : '') + '</div>' +
                    '<div class="text-xs text-gray-500">' + esc(a.userRole) + '</div></div></div></td>' +
                '<td>' + when + bookedAt + '</td>' +
                '<td class="text-gray-700">' + esc(a.type) + '</td>' +
                '<td class="max-w-xs text-gray-600" title="' + esc(a.reason) + '"><div class="truncate">' + esc(a.reason) + '</div></td>' +
                '<td class="text-center"><span class="px-2.5 py-1 rounded-full text-xs font-semibold ' + st.cls + '">' + st.text + '</span></td>' +
                '<td class="text-center whitespace-nowrap">' + actions +
                '<button onclick="printAppointment(' + a.id + ')" class="px-2.5 py-1.5 bg-gray-100 hover:bg-gray-200 text-gray-700 rounded-lg text-xs" title="Print"><i class="fa-solid fa-print"></i></button></td>' +
                '</tr>';
        }).join('');

        const emptyMsg = todayMode === 'booked'
            ? ['fa-inbox', 'No new appointment requests yet today', 'Mga bagong mag-a-appointment ngayong araw ay lalabas dito.']
            : ['fa-calendar-xmark', 'No appointments scheduled for today', 'Walang naka-schedule na pasyente para ngayong araw.'];

        $('nurseViewToday').innerHTML =
            '<div class="nx-hero mb-6 flex flex-col md:flex-row md:items-center justify-between gap-4">' +
                '<div><div class="nx-chip mb-3"><i class="fa-solid fa-calendar-day"></i> ' + esc(fmtLongDate(d.today)) + '</div>' +
                '<h2 class="text-2xl font-bold">Today\'s Appointments</h2>' +
                '<p class="text-sm mt-1">Real-time view of new requests and patients scheduled for today.</p></div>' +
                '<button onclick="nxRefreshToday()" class="bg-white/15 hover:bg-white/25 border border-white/30 text-white px-4 py-2 rounded-lg text-sm font-semibold self-start md:self-auto"><i class="fa-solid fa-rotate mr-2"></i>Refresh</button>' +
            '</div>' +
            '<div class="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">' +
                kpi('fa-user-plus', '#dbeafe', '#1d4ed8', 'New Requests Today', booked.length) +
                kpi('fa-hourglass-half', '#fef9c3', '#a16207', 'Awaiting Approval', pend) +
                kpi('fa-circle-check', '#dcfce7', '#15803d', 'Approved (Today\'s)', appr) +
                kpi('fa-stethoscope', '#cffafe', '#0e7490', 'Scheduled Today', sched.length) +
            '</div>' +
            '<div class="dashboard-card p-4 sm:p-6">' +
                '<div class="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3 mb-5">' +
                    '<h3 class="text-lg font-bold text-gray-800"><i class="fa-solid fa-list-ul text-blue-600 mr-2"></i>' +
                        (todayMode === 'booked' ? 'Newly Booked Today' : 'Scheduled For Today') + '</h3>' +
                    '<div class="nx-seg">' +
                        '<button class="' + (todayMode === 'booked' ? 'on' : '') + '" onclick="nxSetTodayMode(\'booked\')">New Bookings (' + booked.length + ')</button>' +
                        '<button class="' + (todayMode === 'scheduled' ? 'on' : '') + '" onclick="nxSetTodayMode(\'scheduled\')">Today\'s Schedule (' + sched.length + ')</button>' +
                    '</div>' +
                '</div>' +
                (list.length === 0
                    ? '<div class="nx-empty"><i class="fa-solid ' + emptyMsg[0] + '"></i><p class="font-semibold text-gray-600">' + emptyMsg[1] + '</p><p class="text-sm mt-1">' + emptyMsg[2] + '</p></div>'
                    : '<div class="overflow-x-auto rounded-xl border border-gray-200"><table class="nx-table w-full text-sm min-w-max"><thead><tr>' +
                        '<th class="text-center">#</th><th>Patient</th><th>Schedule</th><th>Visit Type</th><th>Symptoms</th><th class="text-center">Status</th><th class="text-center">Actions</th>' +
                      '</tr></thead><tbody>' + rows + '</tbody></table></div>') +
            '</div>';
    }

    // ---------- MONTHLY ----------
    async function loadMonthly(year) {
        const box = $('nurseViewMonthly');
        try {
            monthlyData = await api('/api/records/monthly?year=' + encodeURIComponent(year));
            monthlyYear = monthlyData.year;
            const nowY = new Date().getFullYear(), nowM = new Date().getMonth() + 1;
            selectedMonth = (monthlyYear === nowY) ? nowM : (selectedMonth && monthlyData.months.some(m => m.month === selectedMonth) ? selectedMonth : null);
            await renderMonthly();
        } catch (e) {
            box.innerHTML = '<div class="dashboard-card p-6 text-red-500">' + esc(e.message) + '</div>';
        }
    }
    window.nxChangeYear = y => { loadMonthly(parseInt(y, 10)); };
    window.nxPickMonth = m => { selectedMonth = m; renderMonthly(); };

    async function renderMonthly() {
        const d = monthlyData;
        const byMonth = {};
        d.months.forEach(m => { byMonth[m.month] = m; });
        const full = MONTHS.map((_, i) => byMonth[i + 1] || { month: i + 1, requests: 0, clients: 0, approved: 0, pending: 0, rescheduled: 0 });

        const totalVisits = full.reduce((s, m) => s + m.requests, 0);
        const active = full.filter(m => m.requests > 0);
        const busiest = active.length ? active.reduce((a, b) => (b.clients > a.clients ? b : a)) : null;
        const avg = active.length ? (full.reduce((s, m) => s + m.clients, 0) / active.length).toFixed(1) : '0';
        const maxClients = Math.max(1, ...full.map(m => m.clients));

        const years = d.years.slice();
        if (!years.includes(d.year)) years.unshift(d.year);
        const yearOpts = years.sort((a, b) => b - a).map(y => '<option value="' + y + '"' + (y === d.year ? ' selected' : '') + '>' + y + '</option>').join('');

        const kpi = (icon, bg, color, label, val, sub) =>
            '<div class="nx-kpi"><div class="ico" style="background:' + bg + ';color:' + color + '"><i class="fa-solid ' + icon + '"></i></div>' +
            '<div><div class="lbl">' + label + '</div><div class="val">' + val + '</div>' +
            (sub ? '<div class="text-xs text-gray-500">' + sub + '</div>' : '') + '</div></div>';

        const bars = full.map(m => {
            const h = m.clients > 0 ? Math.max(6, Math.round((m.clients / maxClients) * 150)) : 4;
            return '<div class="nx-bar-col" onclick="nxPickMonth(' + m.month + ')" title="' + MONTHS[m.month - 1] + ': ' + m.clients + ' client(s)">' +
                '<div class="nx-bar-val">' + (m.clients || '') + '</div>' +
                '<div class="nx-bar ' + (m.clients ? '' : 'zero') + (selectedMonth === m.month ? ' sel' : '') + '" style="height:' + h + 'px"></div>' +
                '<div class="nx-bar-lbl">' + SHORT[m.month - 1] + '</div></div>';
        }).join('');

        const trs = full.map(m =>
            '<tr class="cursor-pointer ' + (selectedMonth === m.month ? 'bg-amber-50' : '') + '" onclick="nxPickMonth(' + m.month + ')">' +
            '<td class="font-semibold text-gray-800">' + MONTHS[m.month - 1] + '</td>' +
            '<td class="text-center"><span class="nx-pill" style="background:#dbeafe;color:#1e40af">' + m.clients + '</span></td>' +
            '<td class="text-center text-gray-700">' + m.requests + '</td>' +
            '<td class="text-center"><span class="nx-pill status-approved">' + m.approved + '</span></td>' +
            '<td class="text-center"><span class="nx-pill status-pending">' + m.pending + '</span></td>' +
            '<td class="text-center"><span class="nx-pill status-rescheduled">' + m.rescheduled + '</span></td>' +
            '<td class="text-center text-blue-600"><i class="fa-solid fa-chevron-right text-xs"></i></td></tr>'
        ).join('');

        $('nurseViewMonthly').innerHTML =
            '<div class="nx-hero mb-6 flex flex-col md:flex-row md:items-center justify-between gap-4">' +
                '<div><div class="nx-chip mb-3"><i class="fa-solid fa-chart-column"></i> Annual Overview</div>' +
                '<h2 class="text-2xl font-bold">Monthly Clinic Record</h2>' +
                '<p class="text-sm mt-1">Number of clients served by the clinic each month.</p></div>' +
                '<div class="flex items-center gap-2 self-start md:self-auto">' +
                    '<select onchange="nxChangeYear(this.value)" class="px-3 py-2 rounded-lg text-sm font-semibold text-gray-800 bg-white focus:outline-none">' + yearOpts + '</select>' +
                    '<button onclick="nxPrintMonthly()" class="bg-white/15 hover:bg-white/25 border border-white/30 text-white px-4 py-2 rounded-lg text-sm font-semibold"><i class="fa-solid fa-print mr-2"></i>Print</button>' +
                '</div>' +
            '</div>' +
            '<div class="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">' +
                kpi('fa-users', '#dbeafe', '#1d4ed8', 'Clients in ' + d.year, d.yearClients, 'Unique patients') +
                kpi('fa-notes-medical', '#cffafe', '#0e7490', 'Total Requests', totalVisits, 'All statuses') +
                kpi('fa-ranking-star', '#fef3c7', '#b45309', 'Busiest Month', busiest ? MONTHS[busiest.month - 1] : '—', busiest ? busiest.clients + ' clients' : '') +
                kpi('fa-gauge-high', '#dcfce7', '#15803d', 'Avg. Clients / Month', avg, 'Active months only') +
            '</div>' +
            '<div class="dashboard-card p-4 sm:p-6 mb-6">' +
                '<h3 class="text-lg font-bold text-gray-800 mb-1"><i class="fa-solid fa-chart-simple text-blue-600 mr-2"></i>Clients per Month — ' + d.year + '</h3>' +
                '<p class="text-xs text-gray-500 mb-3">Click a bar or a row to see the list of clients for that month.</p>' +
                '<div class="nx-chart">' + bars + '</div></div>' +
            '<div class="grid lg:grid-cols-5 gap-6">' +
                '<div class="dashboard-card p-4 sm:p-6 lg:col-span-3"><h3 class="text-lg font-bold text-gray-800 mb-4"><i class="fa-solid fa-table-list text-blue-600 mr-2"></i>Monthly Summary</h3>' +
                    '<div class="overflow-x-auto rounded-xl border border-gray-200"><table class="nx-table w-full text-sm"><thead><tr>' +
                    '<th>Month</th><th class="text-center">Clients</th><th class="text-center">Requests</th><th class="text-center">Approved</th><th class="text-center">Pending</th><th class="text-center">Rescheduled</th><th></th>' +
                    '</tr></thead><tbody>' + trs + '</tbody></table></div></div>' +
                '<div class="dashboard-card p-4 sm:p-6 lg:col-span-2" id="nxMonthDetail"></div>' +
            '</div>';

        renderMonthDetail();
    }

    async function renderMonthDetail() {
        const box = $('nxMonthDetail');
        if (!selectedMonth) {
            box.innerHTML = '<div class="nx-empty"><i class="fa-solid fa-hand-pointer"></i><p class="font-semibold text-gray-600">Select a month</p><p class="text-sm mt-1">Pumili ng buwan para makita ang mga client.</p></div>';
            return;
        }
        const key = monthlyYear + '-' + String(selectedMonth).padStart(2, '0');
        box.innerHTML = '<p class="text-gray-400 text-sm">Loading…</p>';
        try {
            const data = await api('/api/records/monthly/' + key);
            const items = data.clients.map((c, i) =>
                '<div class="flex items-center gap-3 py-3 border-b border-gray-100 last:border-0">' +
                '<div class="nx-avatar">' + esc(c.name.trim().charAt(0).toUpperCase()) + '</div>' +
                '<div class="flex-1 min-w-0"><div class="font-semibold text-gray-800 truncate">' + esc(c.name) + '</div>' +
                '<div class="text-xs text-gray-500">' + esc(c.role) + ' · Last visit ' + esc(c.lastDate) + '</div></div>' +
                '<span class="nx-pill" style="background:#dbeafe;color:#1e40af">' + c.visits + ' visit' + (c.visits > 1 ? 's' : '') + '</span></div>'
            ).join('');
            box.innerHTML =
                '<div class="flex justify-between items-start mb-3"><div>' +
                '<h3 class="text-lg font-bold text-gray-800">' + MONTHS[selectedMonth - 1] + ' ' + monthlyYear + '</h3>' +
                '<p class="text-sm text-gray-500">' + data.clients.length + ' client' + (data.clients.length === 1 ? '' : 's') + ' served</p></div>' +
                '<i class="fa-solid fa-user-group text-blue-300 text-2xl"></i></div>' +
                (data.clients.length ? '<div style="max-height:380px;overflow-y:auto">' + items + '</div>'
                    : '<div class="nx-empty"><i class="fa-solid fa-folder-open"></i><p class="font-semibold text-gray-600">No clients this month</p></div>');
        } catch (e) {
            box.innerHTML = '<p class="text-red-500 text-sm">' + esc(e.message) + '</p>';
        }
    }

    window.nxPrintMonthly = function () {
        if (!monthlyData) return;
        const byMonth = {};
        monthlyData.months.forEach(m => { byMonth[m.month] = m; });
        const rows = MONTHS.map((name, i) => {
            const m = byMonth[i + 1] || { requests: 0, clients: 0, approved: 0, pending: 0, rescheduled: 0 };
            return '<tr><td>' + name + '</td><td>' + m.clients + '</td><td>' + m.requests + '</td><td>' + m.approved + '</td><td>' + m.pending + '</td><td>' + m.rescheduled + '</td></tr>';
        }).join('');
        const w = window.open('', '_blank', 'width=850,height=750');
        if (!w) { alert('Please allow pop-ups to print.'); return; }
        w.document.write(
            '<html><head><title>Monthly Record ' + monthlyData.year + '</title><style>' +
            'body{font-family:Arial,sans-serif;padding:40px;color:#111}h1{text-align:center;margin:0}p.sub{text-align:center;color:#555;margin:4px 0 28px}' +
            'table{width:100%;border-collapse:collapse}th,td{border:1px solid #999;padding:9px;text-align:center}th{background:#f1f5f9}td:first-child{text-align:left}' +
            '.sum{margin:18px 0;font-size:14px}.sig{margin-top:60px;width:220px;border-top:1px solid #000;text-align:center;padding-top:4px;font-size:13px;margin-left:auto}' +
            '</style></head><body><h1>School Clinic</h1><p class="sub">Monthly Client Record &mdash; ' + monthlyData.year + '</p>' +
            '<div class="sum"><b>Total unique clients in ' + monthlyData.year + ':</b> ' + monthlyData.yearClients + '</div>' +
            '<table><thead><tr><th>Month</th><th>Clients</th><th>Requests</th><th>Approved</th><th>Pending</th><th>Rescheduled</th></tr></thead><tbody>' + rows + '</tbody></table>' +
            '<div class="sig">School Nurse</div><p style="font-size:12px;color:#777;margin-top:24px">Printed: ' + esc(new Date().toLocaleString()) + '</p></body></html>'
        );
        w.document.close(); w.focus();
        setTimeout(() => w.print(), 300);
    };

    // ---------- INIT ----------
    document.addEventListener('DOMContentLoaded', () => {
        build();
        hookRouter();
        // I-refresh ang pulang bilang sa sidebar habang naka-login ang nurse
        setInterval(() => { if (nurseVisible()) loadToday(true); }, 30000);
        const obs = new MutationObserver(() => { if (nurseVisible()) { loadToday(true); obs.disconnect(); } });
        obs.observe($('nurseDashboard'), { attributes: true, attributeFilter: ['class'] });
    });
})();
</script>

</body>
</html>
"""


@app.get("/")
def index():
    return Response(HTML_CONTENT, mimetype="text/html")


# === API ROUTES ===
@app.post("/api/register")
def register():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    role = data.get("role") or ""

    if not all([name, email, password, role]):
        return jsonify(error="All fields are required."), 400
    if not email.endswith("@gmail.com"):
        return jsonify(error="Email must end with @gmail.com."), 400
    if len(password) < 6:
        return jsonify(error="Password must be at least 6 characters."), 400
    if role not in ("Student", "Teacher", "Staff"):
        return jsonify(error="Invalid role selected."), 400

    conn = get_db()
    if not conn:
        return jsonify(error="Database connection failed."), 500

    cur = conn.cursor()
    try:
        cur.execute("SELECT id FROM users WHERE email = %s", (email,))
        if cur.fetchone():
            return jsonify(error="Email already registered."), 409

        password_hash = generate_password_hash(password)
        cur.execute(
            "INSERT INTO users (name, email, password_hash, role) VALUES (%s, %s, %s, %s)",
            (name, email, password_hash, role),
        )
        conn.commit()
        return jsonify(message="Account created successfully!"), 201
    except Exception as e:
        conn.rollback()
        return jsonify(error=f"Registration failed: {str(e)}"), 500
    finally:
        cur.close()


@app.post("/api/login")
def login():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    conn = get_db()
    if not conn:
        return jsonify(error="Database connection failed."), 500

    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT id, name, email, password_hash, role FROM users WHERE email = %s", (email,)
        )
        row = cur.fetchone()
        if not row:
            return jsonify(error="Email not found."), 401
        if not check_password_hash(row[3], password):
            return jsonify(error="Incorrect password."), 401

        session["user_id"] = row[0]
        return jsonify(user={
            "id": row[0], "name": row[1], "email": row[2], "role": row[4]
        }), 200
    except Exception as e:
        return jsonify(error=f"Login failed: {str(e)}"), 500
    finally:
        cur.close()


@app.post("/api/logout")
def logout():
    session.pop("user_id", None)
    return jsonify(message="Logged out successfully."), 200


@app.get("/api/appointments/slots")
@login_required
def get_taken_slots():
    selected_date = request.args.get("date")
    if not selected_date:
        return jsonify(error="Date is required."), 400

    conn = get_db()
    if not conn:
        return jsonify(error="Database connection failed."), 500

    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT time FROM appointments WHERE date = %s AND status != 'rejected'",
            (selected_date,),
        )
        taken = [row[0] for row in cur.fetchall()]
        return jsonify(taken=taken), 200
    except Exception as e:
        return jsonify(error=str(e)), 500
    finally:
        cur.close()


@app.post("/api/appointments")
@login_required
def create_appointment():
    data = request.get_json(silent=True) or {}
    date = data.get("date")
    time = data.get("time")
    apt_type = data.get("type")
    reason = (data.get("reason") or "").strip()

    if not all([date, time, apt_type, reason]):
        return jsonify(error="All fields are required."), 400

    try:
        parsed = datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        return jsonify(error="Invalid date format."), 400
    if parsed.weekday() >= 5:
        return jsonify(error="Appointments are Monday–Friday only."), 400
    if time not in TIME_SLOTS:
        return jsonify(error="Invalid time slot."), 400

    conn = get_db()
    if not conn:
        return jsonify(error="Database connection failed."), 500

    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO appointments (user_id, date, time, type, reason)
            VALUES (%s, %s, %s, %s, %s)
        """, (g.user["id"], date, time, apt_type, reason))
        conn.commit()
        return jsonify(message="Appointment submitted successfully!"), 201
    except Exception as e:
        conn.rollback()
        if "unique constraint" in str(e).lower() or "duplicate key" in str(e).lower():
            return jsonify(error="This time slot has already been booked."), 409
        return jsonify(error=f"Failed to create appointment: {str(e)}"), 500
    finally:
        cur.close()


@app.get("/api/appointments")
@login_required
def get_my_appointments():
    conn = get_db()
    if not conn:
        return jsonify(error="Database connection failed."), 500

    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT a.id, u.name, u.role, a.date, a.time, a.type, a.reason, a.status,
                   a.rejection_reason, a.reschedule_reason, a.old_date, a.old_time
            FROM appointments a
            JOIN users u ON a.user_id = u.id
            WHERE a.user_id = %s
            ORDER BY a.date DESC, a.time DESC
        """, (g.user["id"],))
        return jsonify(appointments=appointment_rows_to_list(cur.fetchall())), 200
    except Exception as e:
        return jsonify(error=str(e)), 500
    finally:
        cur.close()


@app.get("/api/appointments/all")
@nurse_required
def get_all_appointments():
    conn = get_db()
    if not conn:
        return jsonify(error="Database connection failed."), 500

    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT a.id, u.name, u.role, a.date, a.time, a.type, a.reason, a.status,
                   a.rejection_reason, a.reschedule_reason, a.old_date, a.old_time
            FROM appointments a
            JOIN users u ON a.user_id = u.id
            ORDER BY a.created_at DESC
        """)
        return jsonify(appointments=appointment_rows_to_list(cur.fetchall())), 200
    except Exception as e:
        return jsonify(error=str(e)), 500
    finally:
        cur.close()


# === APPROVE (nagpapadala ng email sa Gmail ng user) ===
@app.post("/api/appointments/<int:apt_id>/approve")
@nurse_required
def approve(apt_id):
    conn = get_db()
    if not conn:
        return jsonify(error="Database connection failed."), 500

    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT a.status, a.date, a.time, a.type, u.name, u.email
            FROM appointments a
            JOIN users u ON a.user_id = u.id
            WHERE a.id = %s
        """, (apt_id,))
        row = cur.fetchone()
        if row is None:
            return jsonify(error="Appointment not found."), 404

        cur.execute("UPDATE appointments SET status = 'approved' WHERE id = %s", (apt_id,))
        conn.commit()

        # iwas double-email kapag na-approve na dati
        if row[0] != "approved":
            notify_user("approved", row[5], row[4], row[1], row[2], row[3])
        return jsonify(message="Appointment approved. Email notification sent."), 200
    except Exception as e:
        conn.rollback()
        return jsonify(error=str(e)), 500
    finally:
        cur.close()


@app.post("/api/appointments/<int:apt_id>/reject")
@nurse_required
def reject(apt_id):
    data = request.get_json(silent=True) or {}
    rejection_reason = (data.get("rejectionReason") or "").strip()
    if not rejection_reason:
        return jsonify(error="A rejection reason is required."), 400

    conn = get_db()
    if not conn:
        return jsonify(error="Database connection failed."), 500

    cur = conn.cursor()
    try:
        cur.execute(
            "UPDATE appointments SET status = 'rejected', rejection_reason = %s WHERE id = %s",
            (rejection_reason, apt_id),
        )
        if cur.rowcount == 0:
            return jsonify(error="Appointment not found."), 404
        conn.commit()
        return jsonify(message="Appointment rejected."), 200
    except Exception as e:
        conn.rollback()
        return jsonify(error=str(e)), 500
    finally:
        cur.close()


# === RESCHEDULE (nurse sets new date/time + required reason; may email din) ===
@app.post("/api/appointments/<int:apt_id>/reschedule")
@nurse_required
def reschedule(apt_id):
    data = request.get_json(silent=True) or {}
    new_date = (data.get("date") or "").strip()
    new_time = (data.get("time") or "").strip()
    reason = (data.get("reason") or "").strip()

    if not reason:
        return jsonify(error="A reschedule reason is required."), 400
    if not new_date or not new_time:
        return jsonify(error="New date and time are required."), 400

    try:
        parsed = datetime.strptime(new_date, "%Y-%m-%d")
    except ValueError:
        return jsonify(error="Invalid date format."), 400
    if parsed.weekday() >= 5:
        return jsonify(error="Appointments are Monday–Friday only."), 400
    if new_time not in TIME_SLOTS:
        return jsonify(error="Invalid time slot."), 400

    conn = get_db()
    if not conn:
        return jsonify(error="Database connection failed."), 500

    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT a.date, a.time, a.type, u.name, u.email
            FROM appointments a
            JOIN users u ON a.user_id = u.id
            WHERE a.id = %s
        """, (apt_id,))
        current = cur.fetchone()
        if current is None:
            return jsonify(error="Appointment not found."), 404

        cur.execute("""
            UPDATE appointments
            SET old_date = %s, old_time = %s,
                date = %s, time = %s,
                reschedule_reason = %s,
                rejection_reason = NULL,
                status = 'approved'
            WHERE id = %s
        """, (current[0], current[1], new_date, new_time, reason, apt_id))
        conn.commit()

        notify_user(
            "rescheduled", current[4], current[3], new_date, new_time, current[2],
            reason=reason, old_date=current[0], old_time=current[1],
        )
        return jsonify(message="Appointment rescheduled."), 200
    except Exception as e:
        conn.rollback()
        if "unique constraint" in str(e).lower() or "duplicate key" in str(e).lower():
            return jsonify(error="That time slot has already been booked."), 409
        return jsonify(error=str(e)), 500
    finally:
        cur.close()


# === DELETE APPOINTMENT (nurse only) ===
@app.delete("/api/appointments/<int:apt_id>")
@nurse_required
def delete_appointment(apt_id):
    conn = get_db()
    if not conn:
        return jsonify(error="Database connection failed."), 500

    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM appointments WHERE id = %s", (apt_id,))
        if cur.rowcount == 0:
            return jsonify(error="Appointment not found."), 404
        conn.commit()
        return jsonify(message="Appointment deleted."), 200
    except Exception as e:
        conn.rollback()
        return jsonify(error=str(e)), 500
    finally:
        cur.close()


@app.get("/api/stats")
@nurse_required
def get_stats():
    conn = get_db()
    if not conn:
        return jsonify(error="Database connection failed."), 500

    cur = conn.cursor()
    try:
        cur.execute("SELECT COUNT(*) FROM appointments")
        total = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM appointments WHERE created_at >= NOW() - INTERVAL '1 day'")
        new_today = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM appointments WHERE status = 'pending'")
        pending = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM appointments WHERE status = 'approved'")
        approved = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM appointments WHERE status = 'rejected'")
        rejected = cur.fetchone()[0]
        return jsonify({
            "total": total,
            "newToday": new_today,
            "pending": pending,
            "approved": approved,
            "rejected": rejected,
        }), 200
    except Exception as e:
        return jsonify(error=str(e)), 500
    finally:
        cur.close()


# === NURSE: TODAY'S APPOINTMENTS ===
@app.get("/api/appointments/today")
@nurse_required
def get_today_appointments():
    conn = get_db()
    if not conn:
        return jsonify(error="Database connection failed."), 500

    cur = conn.cursor()
    base = """
        SELECT a.id, u.name, u.role, a.date, a.time, a.type, a.reason, a.status,
               a.rejection_reason, a.reschedule_reason, a.old_date, a.old_time,
               to_char(a.created_at AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Manila', 'HH12:MI AM')
        FROM appointments a
        JOIN users u ON a.user_id = u.id
    """
    try:
        cur.execute("SELECT to_char(NOW() AT TIME ZONE 'Asia/Manila', 'YYYY-MM-DD')")
        today = cur.fetchone()[0]

        # Bagong nag-book ngayong araw (booked today)
        # Naka-ayos ayon sa petsa at oras ng appointment: pinakamaaga ang una (#1)
        cur.execute(
            base + """
            WHERE (a.created_at AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Manila')::date
                  = (NOW() AT TIME ZONE 'Asia/Manila')::date
            ORDER BY a.date ASC, a.time ASC, a.id ASC
            """
        )
        booked_rows = cur.fetchall()

        # May schedule ngayong araw (scheduled today)
        # Pinakamaagang oras ang una (8:00 = #1, 8:30 = #2, at iba pa)
        cur.execute(base + " WHERE a.date = %s ORDER BY a.time ASC, a.id ASC", (today,))
        scheduled_rows = cur.fetchall()

        def pack(rows):
            out = []
            for r in rows:
                item = appointment_rows_to_list([r])[0]
                item["bookedAt"] = r[12]
                out.append(item)
            return out

        return jsonify(today=today, booked=pack(booked_rows), scheduled=pack(scheduled_rows)), 200
    except Exception as e:
        return jsonify(error=str(e)), 500
    finally:
        cur.close()


# === NURSE: MONTHLY RECORD (summary per month for a year) ===
@app.get("/api/records/monthly")
@nurse_required
def get_monthly_record():
    year = request.args.get("year", type=int) or datetime.now().year

    conn = get_db()
    if not conn:
        return jsonify(error="Database connection failed."), 500

    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT substr(date, 6, 2),
                   COUNT(*),
                   COUNT(DISTINCT user_id) FILTER (WHERE status <> 'rejected'),
                   COUNT(*) FILTER (WHERE status = 'approved' AND reschedule_reason IS NULL),
                   COUNT(*) FILTER (WHERE status = 'pending'),
                   COUNT(*) FILTER (WHERE reschedule_reason IS NOT NULL)
            FROM appointments
            WHERE substr(date, 1, 4) = %s
            GROUP BY 1
            ORDER BY 1
        """, (str(year),))
        months = [
            {"month": int(r[0]), "requests": r[1], "clients": r[2],
             "approved": r[3], "pending": r[4], "rescheduled": r[5]}
            for r in cur.fetchall()
        ]

        cur.execute("""
            SELECT COUNT(DISTINCT user_id) FROM appointments
            WHERE substr(date, 1, 4) = %s AND status <> 'rejected'
        """, (str(year),))
        year_clients = cur.fetchone()[0]

        cur.execute("SELECT DISTINCT substr(date, 1, 4) FROM appointments ORDER BY 1 DESC")
        years = [int(r[0]) for r in cur.fetchall()]

        return jsonify(year=year, years=years, yearClients=year_clients, months=months), 200
    except Exception as e:
        return jsonify(error=str(e)), 500
    finally:
        cur.close()


# === NURSE: LIST OF CLIENTS IN ONE MONTH (month = YYYY-MM) ===
@app.get("/api/records/monthly/<string:month>")
@nurse_required
def get_monthly_clients(month):
    try:
        datetime.strptime(month, "%Y-%m")
    except ValueError:
        return jsonify(error="Invalid month format."), 400

    conn = get_db()
    if not conn:
        return jsonify(error="Database connection failed."), 500

    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT u.name, u.role, COUNT(*), MAX(a.date)
            FROM appointments a
            JOIN users u ON a.user_id = u.id
            WHERE substr(a.date, 1, 7) = %s AND a.status <> 'rejected'
            GROUP BY u.id, u.name, u.role
            ORDER BY COUNT(*) DESC, u.name ASC
        """, (month,))
        clients = [
            {"name": r[0], "role": r[1], "visits": r[2], "lastDate": r[3]}
            for r in cur.fetchall()
        ]
        return jsonify(month=month, clients=clients), 200
    except Exception as e:
        return jsonify(error=str(e)), 500
    finally:
        cur.close()
# =====================================================================
# CLINIC UPDATE  -  I-paste ang BUONG code na ito sa app.py,
# mismo sa ITAAS ng linyang:   # === RUN SERVER ===
# (wala nang ibang babaguhin sa app.py)
# =====================================================================
import re

VISIT_TYPES = ("First Aid", "Health Promotion", "Medical")
CIVIL_STATUSES = ("Single", "Married", "Separated", "Widowed")


def calc_age(born):
    today = datetime.now().date()
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))


# ---------- DATABASE: bagong columns sa users ----------
_orig_init_db = init_db


def init_db():
    _orig_init_db()
    conn = get_db()
    if not conn:
        return
    cur = conn.cursor()
    for col, typ in (("birthday", "TEXT"), ("civil_status", "TEXT"), ("address", "TEXT"),
                     ("age", "INTEGER"), ("religion", "TEXT"), ("course", "TEXT"),
                     ("gender", "TEXT"), ("nationality", "TEXT"), ("contact", "TEXT")):
        cur.execute(f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {col} {typ}")
    conn.commit()
    cur.close()


# ---------- BACKEND: visit type (3 lang) ----------
@app.before_request
def _check_visit_type():
    if request.method == "POST" and request.path == "/api/appointments":
        d = request.get_json(silent=True) or {}
        if d.get("type") not in VISIT_TYPES:
            return jsonify(error="Invalid visit type."), 400


# ---------- BACKEND: Create Account na may personal info ----------
def register_v2():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    role = data.get("role") or ""

    if not all([name, email, password, role]):
        return jsonify(error="All fields are required."), 400
    if not email.endswith("@gmail.com"):
        return jsonify(error="Email must end with @gmail.com."), 400
    if len(password) < 6:
        return jsonify(error="Password must be at least 6 characters."), 400
    if role not in ("Student", "Teacher", "Staff"):
        return jsonify(error="Invalid role selected."), 400

    birthday = (data.get("birthday") or "").strip()
    civil_status = (data.get("civilStatus") or "").strip()
    address = (data.get("address") or "").strip()
    religion = (data.get("religion") or "").strip()
    course = (data.get("course") or "").strip()
    gender = (data.get("gender") or "").strip()
    nationality = (data.get("nationality") or "").strip()
    contact = re.sub(r"[\s-]", "", data.get("contact") or "")

    if not all([birthday, civil_status, address, religion, gender, nationality, contact]):
        return jsonify(error="Please fill in all personal information."), 400
    if role == "Student" and not course:
        return jsonify(error="Course is required for students."), 400
    try:
        age = calc_age(datetime.strptime(birthday, "%Y-%m-%d").date())
    except ValueError:
        return jsonify(error="Invalid birthday."), 400
    if age < 5 or age > 100:
        return jsonify(error="Invalid birthday."), 400
    if civil_status not in CIVIL_STATUSES:
        return jsonify(error="Invalid civil status."), 400
    if gender not in ("Male", "Female"):
        return jsonify(error="Invalid gender."), 400
    if not re.fullmatch(r"(09|\+639)\d{9}", contact):
        return jsonify(error="Invalid contact number."), 400

    conn = get_db()
    if not conn:
        return jsonify(error="Database connection failed."), 500

    cur = conn.cursor()
    try:
        cur.execute("SELECT id FROM users WHERE email = %s", (email,))
        if cur.fetchone():
            return jsonify(error="Email already registered."), 409

        cur.execute(
            "INSERT INTO users (name, email, password_hash, role, birthday, civil_status, address, "
            "age, religion, course, gender, nationality, contact) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (name, email, generate_password_hash(password), role, birthday, civil_status, address,
             age, religion, course, gender, nationality, contact),
        )
        conn.commit()
        return jsonify(message="Account created successfully!"), 201
    except Exception as e:
        conn.rollback()
        return jsonify(error=f"Registration failed: {str(e)}"), 500
    finally:
        cur.close()


app.view_functions["register"] = register_v2


# ---------- BACKEND: Monthly record (bilang ng clients per visit type) ----------
def monthly_v2():
    year = request.args.get("year", type=int) or datetime.now().year

    conn = get_db()
    if not conn:
        return jsonify(error="Database connection failed."), 500

    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT substr(date, 6, 2),
                   COUNT(*),
                   COUNT(DISTINCT user_id) FILTER (WHERE status <> 'rejected'),
                   COUNT(*) FILTER (WHERE status = 'approved' AND reschedule_reason IS NULL),
                   COUNT(*) FILTER (WHERE status = 'pending'),
                   COUNT(*) FILTER (WHERE reschedule_reason IS NOT NULL),
                   COUNT(DISTINCT user_id) FILTER (WHERE status <> 'rejected' AND type ILIKE 'First Aid%%'),
                   COUNT(DISTINCT user_id) FILTER (WHERE status <> 'rejected' AND type ILIKE 'Health Promotion%%'),
                   COUNT(DISTINCT user_id) FILTER (WHERE status <> 'rejected'
                        AND type NOT ILIKE 'First Aid%%' AND type NOT ILIKE 'Health Promotion%%')
            FROM appointments
            WHERE substr(date, 1, 4) = %s
            GROUP BY 1
            ORDER BY 1
        """, (str(year),))
        months = [
            {"month": int(r[0]), "requests": r[1], "clients": r[2],
             "approved": r[3], "pending": r[4], "rescheduled": r[5],
             "firstAid": r[6], "health": r[7], "medical": r[8]}
            for r in cur.fetchall()
        ]

        cur.execute("""
            SELECT COUNT(DISTINCT user_id) FROM appointments
            WHERE substr(date, 1, 4) = %s AND status <> 'rejected'
        """, (str(year),))
        year_clients = cur.fetchone()[0]

        cur.execute("SELECT DISTINCT substr(date, 1, 4) FROM appointments ORDER BY 1 DESC")
        years = [int(r[0]) for r in cur.fetchall()]

        return jsonify(year=year, years=years, yearClients=year_clients, months=months), 200
    except Exception as e:
        return jsonify(error=str(e)), 500
    finally:
        cur.close()


app.view_functions["get_monthly_record"] = nurse_required(monthly_v2)


# ---------- BACKEND: listahan ng patients (auto-fill ng Medical Certificate) ----------
def patients_v1():
    conn = get_db()
    if not conn:
        return jsonify(error="Database connection failed."), 500

    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT id, name, role, birthday, civil_status, address, religion,
                   course, gender, nationality, contact
            FROM users WHERE role <> 'nurse' ORDER BY name ASC
        """)
        out = []
        for r in cur.fetchall():
            age = ""
            try:
                if r[3]:
                    age = calc_age(datetime.strptime(r[3], "%Y-%m-%d").date())
            except ValueError:
                pass
            out.append({
                "id": r[0], "name": r[1], "role": r[2], "birthday": r[3],
                "civilStatus": r[4], "address": r[5], "religion": r[6],
                "course": r[7], "gender": r[8], "nationality": r[9],
                "contact": r[10], "age": age,
            })
        return jsonify(patients=out), 200
    except Exception as e:
        return jsonify(error=str(e)), 500
    finally:
        cur.close()


app.add_url_rule("/api/patients", "get_patients", nurse_required(patients_v1), methods=["GET"])


# ---------- FRONTEND: binabago ang HTML_CONTENT ----------
def _hrep(old, new):
    global HTML_CONTENT
    if HTML_CONTENT.count(old) != 1:
        raise RuntimeError("Clinic update: hindi tumugma ang bahaging ito ng HTML:\n" + old[:90])
    HTML_CONTENT = HTML_CONTENT.replace(old, new)


_INP = 'w-full px-4 py-2.5 border border-gray-400 rounded-lg focus:outline-none focus:ring-2 focus:ring-green-500'
_LBL = 'block font-medium mb-1'

_hrep('placeholder="Juan Dela Cruz">', f'''placeholder="Juan Dela Cruz">
          </div>
          <div class="grid grid-cols-1 min-[420px]:grid-cols-2 gap-3">
            <div><label class="{_LBL}">Birthday</label><input type="date" id="regBirthday" class="{_INP}"></div>
            <div><label class="{_LBL}">Age</label><input type="text" id="regAge" readonly class="{_INP}" placeholder="Auto"></div>
            <div><label class="{_LBL}">Civil Status</label>
              <select id="regCivil" class="{_INP}"><option value="">Select...</option><option>Single</option><option>Married</option><option>Separated</option><option>Widowed</option></select></div>
            <div><label class="{_LBL}">Gender</label>
              <select id="regGender" class="{_INP}"><option value="">Select...</option><option>Male</option><option>Female</option></select></div>
            <div class="min-[420px]:col-span-2"><label class="{_LBL}">Address</label><input type="text" id="regAddress" class="{_INP}" placeholder="Barangay, Municipality, Province"></div>
            <div><label class="{_LBL}">Religion</label><input type="text" id="regReligion" class="{_INP}" placeholder="e.g. Roman Catholic"></div>
            <div><label class="{_LBL}">Nationality</label><input type="text" id="regNationality" class="{_INP}" value="Filipino"></div>
            <div><label class="{_LBL}">Course</label><input type="text" id="regCourse" class="{_INP}" placeholder="e.g. BSIT (students)"></div>
            <div><label class="{_LBL}">Contact #</label><input type="tel" id="regContact" class="{_INP}" placeholder="09123456789"></div>
          </div>
          <div class="hidden">''')

_hrep("const role = document.getElementById('regRole').value;", r'''const role = document.getElementById('regRole').value;
    const gv = id => document.getElementById(id).value.trim();
    const profile = {
        birthday: gv('regBirthday'), civilStatus: gv('regCivil'), address: gv('regAddress'),
        age: gv('regAge'), religion: gv('regReligion'), course: gv('regCourse'),
        gender: gv('regGender'), nationality: gv('regNationality'), contact: gv('regContact')
    };
    {
        const m0 = document.getElementById('authMsg');
        const missing = !profile.birthday || !profile.civilStatus || !profile.address || !profile.religion ||
            !profile.gender || !profile.nationality || !profile.contact || (role === 'Student' && !profile.course);
        const badPhone = profile.contact && !/^(09|\+639)\d{9}$/.test(profile.contact.replace(/[\s-]/g, ''));
        if (missing || badPhone) {
            m0.textContent = missing ? 'Please fill in all personal information!' : 'Enter a valid contact number (e.g. 09123456789).';
            m0.className = 'mt-4 text-center font-medium text-orange-600';
            return;
        }
    }''')
_hrep("body: JSON.stringify({ name, email, password: pass, role })",
      "body: JSON.stringify({ name, email, password: pass, role, ...profile })")

HTML_CONTENT, _n = re.subn(
    r"<option>General Consultation</option>.*?<option>Other Medical Concern</option>",
    lambda m: "<option>First Aid</option>\n          <option>Health Promotion</option>\n          <option>Medical</option>",
    HTML_CONTENT, flags=re.S)
if _n != 1:
    raise RuntimeError("Clinic update: visit type options not found")

_hrep("const maxClients = Math.max(1, ...full.map(m => m.clients));",
      "const maxClients = Math.max(1, ...full.map(m => Math.max(m.firstAid || 0, m.health || 0, m.medical || 0)));")

_NEW_BARS = r'''const bars = full.map(m => {
            const hh = v => v > 0 ? Math.max(6, Math.round((v / maxClients) * 150)) : 3;
            const one = (v, c) => '<div class="nx-b3"><div class="nx-b3v">' + (v || '') + '</div>' +
                '<div class="nx-b3b" style="height:' + hh(v) + 'px;background:' + c + (v ? '' : ';opacity:.35') + '"></div></div>';
            return '<div class="nx-grp' + (selectedMonth === m.month ? ' sel' : '') + '" onclick="nxPickMonth(' + m.month + ')" title="' +
                MONTHS[m.month - 1] + ' - First Aid: ' + (m.firstAid || 0) + ', Health Promotion: ' + (m.health || 0) + ', Medical: ' + (m.medical || 0) + '">' +
                '<div class="nx-bars3">' + one(m.firstAid || 0, '#22c55e') + one(m.health || 0, '#facc15') + one(m.medical || 0, '#3b82f6') + '</div>' +
                '<div class="nx-bar-lbl">' + SHORT[m.month - 1] + '</div></div>';
        }).join('');'''
HTML_CONTENT, _n = re.subn(r"const bars = full\.map\(m => \{.*?\}\)\.join\(''\);",
                           lambda m: _NEW_BARS, HTML_CONTENT, count=1, flags=re.S)
if _n != 1:
    raise RuntimeError("Clinic update: monthly bars not found")

_hrep("""'<div class="nx-chart">' + bars + '</div></div>' +""",
      """'<div class="nx-legend"><span><i style="background:#22c55e"></i>First Aid</span><span><i style="background:#facc15"></i>Health Promotion</span><span><i style="background:#3b82f6"></i>Medical</span></div>' +
                '<div class="nx-chart-scroll"><div class="nx-chart nx-chart3">' + bars + '</div></div></div>' +""")

_EXTRA = r'''
<style>
#formRegister select, #formRegister input { min-width: 0; }
.nx-chart-scroll{overflow-x:auto;-webkit-overflow-scrolling:touch;padding-bottom:6px}
.nx-chart3{min-width:640px;height:auto;align-items:flex-end;gap:4px}
.nx-grp{flex:1;min-width:48px;display:flex;flex-direction:column;align-items:center;justify-content:flex-end;cursor:pointer;border-radius:10px;padding:4px 2px}
.nx-grp:hover,.nx-grp.sel{background:#fffbeb}
.nx-bars3{display:flex;align-items:flex-end;gap:2px;height:185px}
.nx-b3{display:flex;flex-direction:column;align-items:center;justify-content:flex-end;width:14px}
.nx-b3v{font-size:10px;font-weight:700;color:#1e293b;margin-bottom:2px;min-height:12px}
.nx-b3b{width:100%;border-radius:4px 4px 0 0;transition:all .3s ease}
.nx-legend{display:flex;flex-wrap:wrap;gap:14px;font-size:12px;color:#475569;margin-bottom:8px}
.nx-legend i{display:inline-block;width:12px;height:12px;border-radius:3px;margin-right:6px;vertical-align:-1px}
#nurseViewCert{min-width:0}
</style>

<script>
function nxCalcAge(iso) {
    if (!iso) return '';
    const b = new Date(iso + 'T00:00:00'), t = new Date();
    let a = t.getFullYear() - b.getFullYear();
    const m = t.getMonth() - b.getMonth();
    if (m < 0 || (m === 0 && t.getDate() < b.getDate())) a--;
    return a >= 0 ? a : '';
}
document.addEventListener('DOMContentLoaded', () => {
    const b = document.getElementById('regBirthday');
    if (!b) return;
    b.max = new Date().toISOString().split('T')[0];
    b.addEventListener('change', () => { document.getElementById('regAge').value = nxCalcAge(b.value); });
});

// ===== MEDICAL CERTIFICATE (Nurse Panel, kasunod ng Monthly Record) =====
(function () {
    const $ = id => document.getElementById(id);
    let patients = [];
    const LOGO_L = 'data:image/jpeg;base64,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', LOGO_M = 'data:image/jpeg;base64,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', LOGO_R = 'data:image/jpeg;base64,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';

    const CERT_CSS =
'.cert-paper{background:#fff;color:#222;font-family:Verdana,Geneva,sans-serif;font-size:15px;line-height:2.05;padding:26px 56px 100px;max-width:820px;min-height:1060px;margin:0 auto;position:relative;box-shadow:0 4px 24px rgba(0,0,0,.12);border:1px solid #e5e7eb;box-sizing:border-box}' +
'.cert-head{display:flex;align-items:center;gap:10px}' +
'.cert-head .lg{display:flex;align-items:center;gap:8px;flex-shrink:0}' +
'.cert-head .lg img,.cert-head .rg img{height:64px;width:auto;display:block}' +
'.cert-head .tx{flex:1;min-width:0;line-height:1.25}' +
'.cert-head .u{font-size:21px;font-weight:800;letter-spacing:.3px}' +
'.cert-head .s{font-size:14px}' +
'.cert-head .em{font-family:Georgia,serif;font-size:11px;margin-left:34px;color:#444}' +
'.cert-title{text-align:center;font-size:32px;font-weight:800;color:#4b4b4b;margin:44px 0 40px;letter-spacing:.5px;line-height:1.2}' +
'.cert-body{padding:0 4px}' +
'.cert-body p{margin:0 0 28px;text-align:justify}' +
'.cf{box-sizing:border-box;display:inline-block;min-width:70px;max-width:100%;border-bottom:1px solid #222;padding:0 6px;outline:none;line-height:1.5;min-height:1.5em;vertical-align:baseline;word-break:break-word;text-align:left}' +
'.cf:focus{background:#eff6ff}' +
'.cf:empty:before{content:attr(data-ph);color:#b0b5bd;font-size:.8em}' +
'.cf.md{min-width:230px}.cf.lg{min-width:min(300px,100%)}.cf.xl{min-width:min(470px,100%)}.cf.sm{min-width:50px}' +
'.cf.line{display:block;margin-top:8px}' +
'.opt{cursor:pointer;border-radius:3px;padding:0 1px;-webkit-user-select:none;user-select:none}' +
'.opt:hover{background:#dbeafe}' +
'.opt.on{text-decoration:underline;text-decoration-thickness:2px;text-underline-offset:3px;background:none}' +
'.cert-sign{margin-top:18px;line-height:1.45;margin-left:-14px}' +
'.cert-foot{position:absolute;left:30px;bottom:18px;font-family:Arial,Helvetica,sans-serif;font-size:15px;font-style:italic;font-weight:700;line-height:1.35}' +
'@media(max-width:700px){.cert-paper{padding:16px 14px 80px;font-size:12.5px;min-height:0}.cert-head .lg img,.cert-head .rg img{height:34px}.cert-head .u{font-size:12px}.cert-head .s{font-size:10px}.cert-head .em{font-size:9px;margin-left:0}.cert-title{font-size:20px;margin:24px 0}.cert-body p{margin-bottom:18px;text-align:left}.cert-foot{font-size:11px;left:14px}}';

    const CERT_HTML = `
<div class="nx-hero mb-6 flex flex-col md:flex-row md:items-center justify-between gap-4">
  <div><div class="nx-chip mb-3"><i class="fa-solid fa-file-medical"></i> Health Services Unit</div>
  <h2 class="text-2xl font-bold">Medical Certificate</h2>
  <p class="text-sm mt-1">I-type sa mga linya. I-click ang Mr/Ms/Mrs, Male/Female at civil status para i-underline (click ulit para alisin).</p></div>
  <div class="flex flex-wrap gap-2 items-center">
    <select id="certPatient" onchange="certFill(this.value)" class="px-3 py-2 rounded-lg text-sm font-semibold text-gray-800 bg-white focus:outline-none max-w-full w-full sm:w-64"><option value="">Auto-fill from patient (optional)</option></select>
    <button onclick="certClear()" class="bg-white/15 hover:bg-white/25 border border-white/30 text-white px-4 py-2 rounded-lg text-sm font-semibold"><i class="fa-solid fa-eraser mr-2"></i>Clear</button>
    <button onclick="certPrint()" class="bg-white text-blue-700 hover:bg-blue-50 px-4 py-2 rounded-lg text-sm font-semibold"><i class="fa-solid fa-print mr-2"></i>Print</button>
  </div>
</div>
<div class="overflow-x-auto"><div class="cert-paper" id="certPaper">
  <div class="cert-head">
    <div class="lg"><img src="${LOGO_L}" alt=""><img src="${LOGO_M}" alt=""></div>
    <div class="tx">
      <div class="u">SOUTHERN LUZON STATE UNIVERSITY</div>
      <div class="s">Judge Guillermo Eleazar Campus, Tagkawayan<br>Health Services Unit</div>
      <div class="em" contenteditable="true" spellcheck="false">nursekrista_slsujge@slsu.edu.ph</div>
    </div>
    <div class="rg"><img src="${LOGO_R}" alt=""></div>
  </div>
  <div class="cert-title">MEDICAL CERTIFICATE</div>
  <div class="cert-body">
    <p>Date <span class="cf md" id="cfDate" contenteditable="true"></span></p>
    <p>To whom it may concern:</p>
    <p>This is to certify that <b class="og" data-g="title"><span class="opt" data-v="Mr">Mr</span>/<span class="opt" data-v="Ms">Ms</span>/<span class="opt" data-v="Mrs">Mrs.</span></b>
      <span class="cf lg" id="cfName" contenteditable="true" data-ph="Full name"></span>,
      <span class="og" data-g="gender"><span class="opt" data-v="Male">Male</span>/<span class="opt" data-v="Female">Female</span></span>,
      <span class="cf sm" id="cfAge" contenteditable="true"></span> years old,
      <span class="og" data-g="civil"><span class="opt" data-v="Single">single</span>/<span class="opt" data-v="Married">married</span>/<span class="opt" data-v="Separated">separated</span></span>,
      from <span class="cf xl" id="cfAddress" contenteditable="true"></span>, was seen and examined on
      <span class="cf md" id="cfExam" contenteditable="true"></span> and was diagnosed to
      <span class="cf xl" id="cfDiag" contenteditable="true"></span>.</p>
    <p>I therefore recommend <span class="cf xl" id="cfRec" contenteditable="true"></span>
      <span class="cf line" contenteditable="true"></span><span class="cf line" contenteditable="true"></span></p>
    <p>This certificate is being issued upon the request of <span class="og" data-g="req"><span class="opt" data-v="Msr">Msr</span>/<span class="opt" data-v="Ms">Ms.</span></span>
      <span class="cf lg" id="cfReq" contenteditable="true"></span>
      for whatever purpose it may serve (excluding legal matters).</p>
    <div class="cert-sign">Respectfully Yours,<br><br><br>
      <b contenteditable="true" spellcheck="false">KRISTA KEITH C. GUERRA, RN, CHRA</b><br>
      <span contenteditable="true" spellcheck="false">Head, Health Services Unit</span></div>
  </div>
  <div class="cert-foot">OP-SLSU-JGE-AFA-HSU-3.0.F1<br>Effective: 11/23/2026</div>
</div></div>`;

    function today() { return new Date().toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' }); }
    function set(id, v) { const e = $(id); if (e) e.textContent = v; }
    function pick(group, value) {
        document.querySelectorAll('#certPaper .og[data-g="' + group + '"] .opt').forEach(o => {
            o.classList.toggle('on', !!value && o.dataset.v.toLowerCase() === String(value).toLowerCase());
        });
    }

    async function loadPatients() {
        try {
            const d = await api('/api/patients');
            patients = d.patients;
            $('certPatient').innerHTML = '<option value="">Auto-fill from patient (optional)</option>' +
                patients.map(p => '<option value="' + p.id + '">' + esc(p.name) + ' (' + esc(p.role) + ')</option>').join('');
        } catch (e) { console.error(e); }
    }

    window.certFill = function (id) {
        const p = patients.find(x => String(x.id) === String(id));
        if (!p) return;
        const female = p.gender === 'Female', male = p.gender === 'Male';
        set('cfDate', today()); set('cfExam', today());
        set('cfName', p.name); set('cfAge', p.age === '' ? '' : p.age);
        set('cfAddress', p.address || ''); set('cfReq', p.name);
        pick('title', female ? 'Ms' : (male ? 'Mr' : ''));
        pick('gender', p.gender || '');
        pick('civil', ['Single', 'Married', 'Separated'].includes(p.civilStatus) ? p.civilStatus : '');
        pick('req', female ? 'Ms' : (male ? 'Msr' : ''));
    };

    window.certClear = function () {
        $('certPaper').querySelectorAll('.cf').forEach(e => { e.textContent = ''; });
        $('certPaper').querySelectorAll('.opt.on').forEach(e => e.classList.remove('on'));
        $('certPatient').value = '';
    };

    window.certPrint = function () {
        const paper = $('certPaper').cloneNode(true);
        paper.querySelectorAll('[contenteditable]').forEach(e => e.removeAttribute('contenteditable'));
        const w = window.open('', '_blank', 'width=900,height=1100');
        if (!w) { alert('Please allow pop-ups to print.'); return; }
        w.document.write('<html><head><title>Medical Certificate</title><style>' + CERT_CSS +
            '@page{size:8.5in 11in;margin:.5in}html,body{margin:0;-webkit-print-color-adjust:exact;print-color-adjust:exact}' +
            '.cert-paper{box-shadow:none;border:0;max-width:none;width:100%;height:9.85in;min-height:0;padding:0 .25in;font-size:14px;line-height:1.95;overflow:hidden}' +
            '.cert-body p{margin-bottom:21px}.cert-title{margin:30px 0 30px;font-size:30px}.cert-foot{left:.25in;bottom:0;font-size:14px}' +
            '.cf:empty:before{content:none}.opt:hover{background:none}' +
            '</style></head><body>' + paper.outerHTML + '</body></html>');
        w.document.close(); w.focus();
        setTimeout(() => w.print(), 600);
    };

    function build() {
        const nav = document.querySelector('#nurseSidebar nav');
        const main = document.querySelector('#nurseDashboard main');
        if (!nav || !main || $('navCert')) return;
        const st = document.createElement('style'); st.textContent = CERT_CSS; document.head.appendChild(st);

        const a = document.createElement('a');
        a.href = '#'; a.id = 'navCert';
        a.className = 'sidebar-link flex items-center gap-3 px-4 py-3 rounded-lg text-blue-100';
        a.innerHTML = '<i class="fa-solid fa-file-medical w-5 text-center"></i> Medical Certificate';
        a.addEventListener('click', e => { e.preventDefault(); showNurseTab('cert'); });
        ($('navMonthly') || $('navAppointments')).insertAdjacentElement('afterend', a);

        const v = document.createElement('div');
        v.id = 'nurseViewCert'; v.className = 'hidden fade-in'; v.innerHTML = CERT_HTML;
        v.addEventListener('click', e => {
            const o = e.target.closest('.opt');
            if (!o) return;
            const was = o.classList.contains('on');
            o.parentElement.querySelectorAll('.opt').forEach(x => x.classList.remove('on'));
            if (!was) o.classList.add('on');
        });
        v.addEventListener('paste', e => {
            e.preventDefault();
            document.execCommand('insertText', false, (e.clipboardData || window.clipboardData).getData('text'));
        });
        main.appendChild(v);
    }

    function hook() {
        const prev = window.showNurseTab;
        window.showNurseTab = function (tab) {
            $('nurseViewCert').classList.add('hidden');
            $('navCert').classList.remove('active');
            if (tab === 'cert') {
                ['nurseViewDashboard', 'nurseViewAppointments', 'nurseViewHistory', 'nurseViewToday', 'nurseViewMonthly']
                    .forEach(id => $(id) && $(id).classList.add('hidden'));
                ['navDashboard', 'navHistory', 'navAppointments', 'navToday', 'navMonthly']
                    .forEach(id => $(id) && $(id).classList.remove('active'));
                $('nurseViewCert').classList.remove('hidden');
                $('navCert').classList.add('active');
                if (!$('cfDate').textContent) set('cfDate', today());
                loadPatients();
                const sb = $('nurseSidebar');
                if (window.innerWidth < 768 && sb && !sb.classList.contains('-translate-x-full')) toggleNurseSidebar();
            } else {
                prev(tab);
            }
        };
    }

    document.addEventListener('DOMContentLoaded', () => { build(); hook(); });
})();
</script>
'''
_hrep("\n</body>\n</html>", _EXTRA + "\n</body>\n</html>")

# ===================== TAPOS NA ANG CLINIC UPDATE =====================
# === RUN SERVER ===
if __name__ == "__main__":
    with app.app_context():
        init_db()
    app.run(host="0.0.0.0", port=5050, debug=True)
