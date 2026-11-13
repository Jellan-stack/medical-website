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
    const LOGO_L = 'data:image/jpeg;base64,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', LOGO_M = 'data:image/jpeg;base64,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', LOGO_R = 'data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAMCAgMCAgMDAwMEAwMEBQgFBQQEBQoHBwYIDAoMDAsKCwsNDhIQDQ4RDgsLEBYQERMUFRUVDA8XGBYUGBIUFRT/2wBDAQMEBAUEBQkFBQkUDQsNFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBT/wAARCACUAJQDASIAAhEBAxEB/8QAHQAAAgICAwEAAAAAAAAAAAAAAAgGBwMFAgQJAf/EAE8QAAEDAgQDBAQICAwEBwAAAAIDBAUGEgABByITFDIIEUJSISNighUWJDFykqKyMzRBQ1FTgYMJNURUYWNxkZOhwtIXJUXwZHOjsbPB0//EABwBAAEFAQEBAAAAAAAAAAAAAAACAwQFBgEHCP/EADIRAAICAQQBAwEGBAcAAAAAAAACAwQSAQUiMhMRFEIGISMxUmJyFSQzskGCkZKiwvD/2gAMAwEAAhEDEQA/APVPBgwYADBgxwwAc8GOGA88AHHvzzy9OXdivtT9cKP0jjklqjlxarLD6hikHFcrfQAfvdP9OIn2h+0ZE6JweaKZJSNUOAzyZsbuj+tV8gfex5zulai1LqN2+NF9Uc06K5ckG5uCIvoBhiWTDqUN7cfb/dQ8mG3qT+ESSTXNOBos3SXhXkn/AAfsAB/fxgp3+ESMXWSc7RXDbl1Lxz+8w9wg/wBeF0YdnrU2SADSoeWAD/nKQNvv2Y2ivZY1XRC4qNee4sj/AL8MZSlF7zce/wD1PQvTHWqkdXo816dlcl1ke7JdirlY5b/TD8n3cWB33Bl6O/Hk+0o3UzSaZbTSdOVBBvWRXpPAZHYPsGYbLPYw8WhHaxp3VOOSYyrhrAVQO1VgsraK+fmRLPr+h1YkK35i+p7h5uE2mLDB4+4wApkYXCeRjjJxMPF566HPBjh35fpwYDpzwYMGAAwYMGAAx8zx9xwUwAddy5RZoGqsQgkGVxGfSOFW1P7eNP024VjqOY51W4HL8fNXgs8vR4T6j/Z6PaxXvbX19dS84408hnWaMW0/jRdAt7hX9T9ANt3tZ+xhWoqKezco2j49qq9knCoIt2zYbzVM8Rnl/wAEMre3N1fw1/xGDW7e2pl5ELGnEUcvALJb/wDbEhV7QWss9RrmpJqThtPqTRG9WbXYHmZBfZ6lHO81d5AHRZv68QyiqApugZpo0nG3xoqFy0drZOWjcX0bGcIzRW4QdEg7bK71m4dAAfWdl+CkH5ys2xkqkp+L1Fyqlx8UqkkXSvGcsnHLGB8i58LR83NJwij0X3h1mGHoo3+ZKq1rTrlYc3bGIop3UDCMhnLaq9QphR7ku71YB20AXbXgnyJtCsPirAteN9+wL9/RjfajQVWNIfUxqdVS0K10/USnUYOEII4HUWqDNYUTzaAjeAA2k2/v3+TEdaZNqSrfUSltbKaYahxAtYqEbqoNwBwqbVJwcc5W4xgPGdgsaIOAMA4zfhbMSfTymH0BPP3ooVAppZKxEhT6a1cKci5SYkiis3BUnZgsYA4WfIheHQfkC85OKqXCxxQ9VN/UuhTCn9cNI41iRytFSsiM8RSKxOHQvo9s5Ntv8YWOA9v5MHXhhHGo02xrlzFOqFl2lNtxM1apUdN+TyAAvusv43sdGFwjdTYVtSei7ac1LpZWp6GXRKWOFUXlU5AAaKNDADAA3nff7Bh48XE87V+mL1g5RWnHkemqBhxlotwAh7fRhDMon3EH4ZEF151ljpuc02mqPql0+hkWs3PKnTj/ANTIC0bWA3Ow7D+UGGw/GGKb1Xq5zCJTTWpqfhdTzjXmcWSr1uLB8ojHxYO5d3zaQj+dMAALLLzAcbSnY5SYhYh02qika8Wo+Pj4WHgackskX8kxRfNlXKqoOLBBUwbJDZ0de/fitK6TnY6la5aTkBJfCkfDODlzXYKgikDhyrKTSuSp7DSOxoxSs6/ob8PaYt9gv7mVfzFnzunCDWX+CtJtWZRtJGpmn8Xn0i4bdyvL8wTdJwPquKCO/hHvAOvFP1HXeqtHS6sZN1RV8W+R6kXkk7D3+veHt4m0rPVBBQsxprTrbOplzQbom/bt0ue+E3X8ePEXHRv55JoF/QssQWWImGGZqTSTT6hdJZJpqVKtkKYB2Bx5v3Rn8C3AAC2aOD9ae++wPbsss2YjSwlTa23V+cL4ioUP2sdS6IcBkU+rUDMOpvNfKMy9/r+3h4tCO0PT+tsUZNr46aaj8qi3J7w9sfOHt48/9SdI86SajOQMqjU1GrLm3TlmuXebdb8qLsfzSuItQ9byunVUxtRRKpA/YneG6wFQ8aJ+wfRivV3R+ZRQXLFKXCY9hrssZMRqiKqaVxSkTOsc882kg1TcgJ9Q3D32l/fiR55+jLFgbZHz09TlgwYMA4cc/myx1XiuTVqqqXzABFjtZ/NliNaiyAQ9A1LIl0NI1yt9VI88A0/TU8jpiVVqaefyal67mQdKuT8ZmZnf/rww8VpdUmjcWwa5wD4akqBre9eIu+UW4St4HFxju+xKQ6FrzsvssA/GFM6dKfFFmFVk3XdOQcBFQvBbmtZImjxuZsADv5ZEDcWWbzswylB6iuqCpmEjaij6Wq3RKQRWRlNQIpws7bLGduXGeB64klT/ADpn6nx8ULrMMQRfMzW1Uvt9w5Qy05XsG5NukD3Ualed4wTEakDSoW7tLoM259Es2Dr2fKEQ38YOixKUpWmqra1TWj2TawVHz0blH1gZt1m7B09ADWYykT5XALdbcN6S1/jDfOK8p+j05SVq1OrUXtLw/wDyuZBtxTkZVI2nFaMQdgdrgwNZFZJx+MJWlv3niV05DjJ1VF1Lqok7kKgyQzeQdEtW6z4YdqGzjKgN96vTvPx+30S2kxL2WfDgnY0um+m9W1pMKVBTbY6fN0BA41Aq9oDmekQP+bohYk3HaHgxbcF2TqIYuRfVAk9rmX6if1M6J2d30M9n+WLZhJljPxraQjlwcsHSQrILJdBgWIDXHaEpSjZzKCTcuKgqXu2wkE3N259+zaHv55Yb/Uwjxx95eRoteKtS0C0jdTFM09GprA4SbJppthBFvf8AnTEMsv0fdxDOz92hKorSo4qma2hI7NaWaqv2EizzsyNELCsNHf3Fv8+MGtkpqlq3pvNRTLT46ViDDjOHsxKN+ZWbhvIOXC+y+zxnisKUWmI9rpfV8C1Sk3MS0AlWirjl+Kkq2AOvGT3fdl2uzAr9G7CqteS28rQ5cVX4/q5Db1jobQVeZKZTdJRbxcv5SLYUlfrhvxVtQ9nOqKSh5BlRNS5ztOu0jQdUdWJc4wcJH1pAfWF/fjcxPathm+aaVYQknR5Fs51wAumf+Kl32e+AYtt9WkGzpo51eYZoQoJcbOQNceDkHnv+bF7Xt17aeWu+QuWvHo3Pi3+0Vbs8toekdY12TEctP5R2zSZyFDzjXjGiilksaIRjgDABRvWWVO8DM8aHVSsnFQagV3Wsnmm5XoiS+LNAUkoAOc384SKJm7JveNx77AIs9iV57cWo9rDTXtTuVqZeN37SRRT5yFkHCXKOlR/K4Zn1bfReOfs7cUzXGnkhJ1gVLVS3iU9UuXFODq96ity9RR4rAbho54X500UeDf12GYePfOhnSTTPRshtZtUfB+pspDUgslFZ9lT4y7uuzRH4rRp818cnfLot1lkTV/F49EA2ODsvLf0WX0Nq1p6ypF4jL064CRpOQVVBqsCoLck4SOxZisYGYcVE/r+Dx4mlLzKlZzK5h8L1XUVSJcNWLixFjKzzQCs4J7/+SQ4GBBYfrlbT+gbHNez2+W02m2moNRxMSykkEUmcDDM0mkTTyon8n5cj3GredpmX4XZsDu7sdnizGr9NLEXr8iQdiGXN92focVjvFq5cNgz9njZ5j97DB59OFr7D6C8HpxUFOSCWSEnCTrho4Ry8O0M/92GU/JhC9R+l/QUMvmwYMvmwYWTTj3fNhfu2VXw0ppI9hW5Xy9SGMa1bhnvMS/C/Y7x98cWVq1qnDaRUg5nphT1Y7EW6WXrXCvhAMv04Q6lNSy1l7QjCr67fs4mBhQN+RuFcgbRrdHeG8/bMLzwyzfAqL1rRP5dOzGSQzaxLc6WUq6e0kVot3lHtajBk4dxD18NjhZZ2jwjbpetv4RrHfYAHvHHcLOunNVtZWNewis5NAMcw1Ep7vWCRdkewHCrEDbrAAXrfLmgCHTf48WjQ+mOqbynm9KwtZwNK0uJ8aQrKmpEpabnvR1fKAsaEYb/QalnfsxBJOgv+HKla1QxhplOQfINafpqWqpqk3lVZB3xUXOfqrOKkCVhpGtvAzceDEzTgWGS14v2li6C6axdZ1SMq1bt86Eotyq1hhRbgiMlK9/yyRMAABzzMvmy6Bz6LLMTTX/Q2Vq+bZ6gUfNrQVYwjU00AFK8HQDeYB9LeeXpuErvmxbWmlEtNNqGhaZZd3BjGoI9+Q9ZeM/eK7PFbdoqoZKaewGmNOOTaTFVKkLt4j3Xso9L0uFfe78g/biOykNo11h+97N/cVDo/IVv2gWppQb19QtEKmakubdUVeYcGd6oR5W3pAZGZnvOy+zDM0bQVI6RU2bSGYM4GOSC9dxd1e2qsXX7+MpZ03ozp5nbwoqnYFr6dvdaA/eMvtkWKzj9PZLWZZKqtTMia0538zHUaspa2bh4Fn361b2OgMc6iIo/Fw7MbGou0PSU8zkomnW8zWrk0ySP4vRqrlEbht/GPwP28UDRwz9GUPCR89RdUNlI9kk2VWCLNYNgWeC8/sY2erfaUzc6hxNKUCg2d09Sj9B5IqRaoZouOFfkTUO7yn6fphibaQ9pKcqyraYp6bjQZ5PhcXu1S7jWV7iVbpCI9PqQO/wBoMYvequ2b060bT81PQquxbxRrfxWLRfRl/wCP+pF4Wo4qo0TOOeoPkQ2LAHgPyGH+/GlDS6nAfouxZK8FFU3IRvFPkwcfruD0X4vzW7Tei6iapzMk+QpSoA2M6gbEAOMi8hfrQ9gsUvCSrvN28h5cUPhuPs4vLFei7SPoco+wf38eS779MX/ptGsU5W8Q/S3alu06Vbqr5VOhKQLjU+uIGjYglkZVFwEk6l0Nhw6QH13+c+gMMnrjpMlq7QRxyamTWaZmLyLf9+9u6DoO7FDU3U2Wkup7OoxEE4WoDRipw/KXQ0ce4R2H9PDh5enL+zPHqX0V4NdqTWB/XX5fuMzvCNJblSf/AMvxEOoCvqkpqYCcpsKep97WD9aJq06hV5ZsxqBujla42BcfGSA/VXgHFDrvM8Tetqf0toWWYPdc67LVmub72MGshxQFY+jkoZvf3F5TO8/bxr9b6BcMtY6optios1aakQCqrXNJU0bZZr3GjvHp6f8A1cVg61C0fpp5QEdEaIqxFRkHwqmjNvzi2DRUwt5uRW3uD8nFco778ehLzKWszOuD/EtQde2dI1611KOFlKfgJ9wdP1JDySPDdsHbfe2cGPnNuYHZ5PaDDeR0o0lmSLtosDls4AVUlUiuAxz8Q/34Qd++e6p0NrVklH0++YNORqYpumEHZs3EhetzKXNrfjZg3RR6AAA2BZ4MdTsn9pNbTWUbUpOrcWlnytiK5l/F6xn/APEf2erz4jO/ibAhPZWpZ8T9WPRbLBjDkp6MGHi5PO3tyahFVWreUAkrewp5vwbL/wCUKgBn9iwPr4rbTB4EFReo86bpzH8vGtGfPNGbdwaXMPkhvsceqANm9VbYHXg7QoFnrnXN3zfCauNlpFUStM0ZUyydVFRqLiViWbp+jy/GJuZub0Q5gDSv6OvyYix87BhYG8u5cyNuezY9XkvjbJpSlZNjDYs2mokDs9g2j5H7+GG0qbRFVttBWUKZrU88mJGpkQWdOnJ/J0bEb+ZVM7wPPwlZ5MQ2o6YiSeLLQtNadauitnbxpLR19zJ/TfMUTD3+DicdnyQWeVLoau5kEHtrKoWaWbY1iBta5Oxp8oAVfUgHC37tmLGZslNfZ6js5vkTUNIVQNUeoBLcOKS04yRrTtFak1PmoLltCINKeYKBncIbOM5+2YfUxS8nQ+sOUlJxf/DakJLlViVGo3iRis/39fFBwBkZ7c7dnlxqaY1QqrSbRXUSSbxDKn6rCpkkl2yLO1uw4oB+a8m2wPp5Yh5Fe1vlzUvjWmURmtTqKpp5mnnARyS1UzWZ9JA39DQP8Yr/AN3js1RqNSur2l1UQsYklOrycM9AImQvaC4GwgtMyy2DiC1E1PWCr01hzXYlUdEsZJs2A7DuSeAsaN/vgHv4j9EaWJaXxVX1K+euJR3Sy5m9bOT4yP8AFYLGCIAH61az6GHkZSA1i57v+XXgIv2NKlRi5R7BSJtGjB215xKRckKIGsBpImiB9B3gd/uHh1tOHUFlqLAZPZqLhnSS/NpcR4kmZhZ4b/P0e/iE6G6mTdJ9m6kRpCnqddM0qeVdOu5kHMpA0lAbu3BmSwArY0VvsO3eHX+TGZrXNaRND5jHxlEQCEoMW0Ugfi7k3X+GH7ZVxwRSMzDoBoZ8b8Eist/Nxvyd76Zit7mm4aNieq1/qGWCh7ElevjyVrPV54gIOsotsly7NyikJo3iHG89hmZ4reHmZCKcwMguGxiaKJrX7DaOz8ll/WaPv34lGjWmfK6y6lVI6j27WEVlUkVUWzc20aL1LjND5Sz20jM/3Pt4s/tC6fxUXpNLzCSQfCr1wximS1x3mHwiBh9PZ/rxf7qy2KktSXrieR/wN6t5NzifkrZGirOD+MdKzEUQCfNtzRD6fgxZNI9qmLYwbBOtIScp5+DcAdPM2JuWZHZuLipX/awtclUc7K66s49BwuEIxsc+pMwRWS4N5mfn37MThpXqNQp5jT8LUFSZEG1SOilVQ+vZZjwbYptz+n2WCtF5dJeTfpPWLs1PddWmeXxuvH9xYfaeqSPk4LSCvYJ4L1shVLI0nSPzG3O8z+vwrPfwtFZak1Vo/MVlTGmcvT7J0E4+SfvG/JA8VM1j3uAsWVVMAs3nZ0YvHVyn31N9lXSGnJJtmylspOHZKti/NrWFeP8AlnjPqZoHXz3UGoJNOEbV5CyD8nLBnlWbuDTZAYBsNoijwVTvyM+MZkZX+zj6Frv66aZmHhb0ldv2lRdmmuZOr63eR9UyOr9RzEjDyEak8nWCLOnG9yV52AGy71Oz7mF5BM1EbC6zCw8PRpPopqLRGoRVM9RYURSKMY5Se00xquRm/hBW3YZi4AEkrO7PcHz3YRoN+Itxij33uh6mdmqtV690QpWXcKEq6JuTZZQsvSaiKhJFn+3MMGIr2ModeI7PsAo4TUyN8q5eCmWX4MCWKzL9o5ZF72DD6+npoWkbthp6i29uLTRaltVMqmTTPOLqMAM1h6AcJAAEHvgAF9fEX7MsrEISdXNJ+oHNJxARgyqsqxs4zcWjkFj6wOzYZ+Dox6KV7QkPqNTD2AnGnOR7sMwIPmMfaEvCX9OPPhzQEj2Y9doJKdEZCnHTg2ou1kr0njJX1S14ewB7wwzhhLmV1mq1W0thOpcKFT6WVOJ5UlRNfa6rFncKzpw9eMDu8jiQWBvZ9DZ5MYDiqs06bUFUFSU81pWPgK1Foxi2rwHQMod62BG0jAQ6FTV22eTFQa0a4a21TNOaZiKrGmIKEeFG1LU8c2Sg4dkqHW3Rduz4pGHnA/oAfXjoaWP6NCo5XTiKrFnMxVXILRUhUOcgUib6eLhG0MXJnxXZAfWYAi3DjWbzO/E9o8lNDMucXqp6e4STtRNaqpfVOoY2nGiUjHV3FCq4YGlxuYNuBorWB5wA0T2b9mGM7POoS1f6eMyk8s06hiSOKl0S603aWw/rd1/7caPtU6cMtQdLH6yimTeSiRzeMHNuZ5ifiDb4Ty2YhtyUi2k9xBkgo1BaszVNVlDz80Dh1NsXqqhxqI2G3jwaAk5R4Pg2ACwB/wCDv8eGO1JZRmWndWAvPpy7fUUwzb8ulYCN6KSN4HfsSsSDr8eFQqOOhKWT+E6eZVKyqxuqqzfxr4eMEaqYGB+uDff5DPrxO9Ie0A7oHnGDIQkKaCNSfvYfN1wibqnYC3KK/mvWq/gj2e2GG4JcO5n6drwthKWpH6SUjTDl83prVdnCw6sg4cM4VpHRjgGnFMFjbgaqJnwuMAHZ5wDHRjKRW1TbP1Kur1JqqD/dG/FuMcg7WBEA5gwWbGZnZeH0MSVzqbp84VbXVO5pB0e9VtVziSRM/GFh5uQA/cM8dTOrqKp8HhlqfTBg9WVckgycOnBqXnediKTnf9QsOz6es8Uqvw5ZGur3YtYJVbtxxIrFdnSUjtU6ZqCk9YpjkWjo3K8E7jXQs5A1Xbl274vCMEd5uD8GywMdrtVamxUrVUPS4uCQhIRx8vctrLAeqgYIh+5C9Y/cx0a/7QSLFm4a0SxVpZs4bqgU68AuccCAXmLdud9mftq4WxY5auDRZREU6dNgADNsid58XfeZmfjO/rxRbpfgmVoom4/Jionsvr93p3/KZqSg52VZ8pGTZprSZpRrVm2d+ucGZmABZ1gkG88eqNPQCNOwEdFtreXZIA2D0eEAt/8ArCP6AUdEaXay0w5qBEwCQbmjHqmYGCEgfgOz2LwDD4ZKCmj3kYhaO7HNkkhni9xC+WRNrVnr6YTdlF17Sj1vL6maSU2usKaKUodRvMz6ARZBf3l9v+4sVbpC2mK/0yXn9NtdHi1WyDh2/wDi+tLx7tgDhVY1rBHlllUQ39B7/Bsxo6ynJDWeqqunIaMWn/jMCtEU20QeA0NVkIGrIuUVVdl3CA7L/Etb58Wg3rvQ2u3cXRuqdPx0DXgNxRyZ1zCpMXLizZe3cb0T/crHjRx/mO1tM9Wl/MaKXqnWCh06jQr2rGc3GNqMdvl2zSBFny8iqoCLZE3AmYLX3Ld2YWdG4MKtpZpvJas1qwpqLFXI1d7hzZ+LpeNY/wDvrwzGvGnUPR9ORtEaavJGUc13IpE3YuZlw+aN0W92fqTMz4IXmB+TYeGN0N0QhtE6XBgxHJ1JOBE30kY73B/Nn/YHlHDMqeViqs1WvWsfipP6eg29PQjGKjRFswYog2QSyy6QAchyy/ywY2lmDDxo9NPQ+54rnXHTJnq3p5LwDsAyWNMlmip/mFxy2Hl/34sWN8+MSvQf0cA3KqumLHnJnPy2oTnS+qXVRR0LkgkNHOpKSZC7OCkcjJXm26SxgiCrhvl+MK38Ll8wC8zsOOvZak29G1ZBUnRbSHpKbleRQ1BWJWUmKld9RqxyIWG7cGZ7LPk6Vl959AR2jqmiIurKhh6uYJS1E1CsqzmmCyV4AHGvRVAPOie/E5k6FRcV8DjUWqnlPKRLRWVd6iIrE35yKAAAGcGi32NGVjkAMz3mZ2Bee8FwPmpW7fZ0mjw+Sk5011Yf0zMvK6NuZyMZwYrUiIbuAdmlnZ8mkb0fVcazYsAdBgsHt4svW6saoMQf0lSrqtRlRbnASTbPmGDQLevhdHFu3gZhZ0b9mK5YSzuMlaJzjqcdUywSSVToTSlmtyJOGlvc4lJsrT4KFvgMDtv8ap7O5pFXL2iY1GYotmhIU+4b/CM5pqzkhdyUHef4w08Zon1hlmAbDDo8CZFOzxuv2L1JdG9jl+whHMs2riZYV9IIDk7fEpekZl3cZI7d5AR9+67vH8mFx1E0gkqFk2kdJRKlEJK5Ek9nZGQVdxzjK8OhYEtgegTsW349DNPNS6b1RgxlaclEpNp8x8PYaR+Ux6gLEsXSTcpEmoImBbSEsMNEgw23QTLwPNjRd9WuntYLO4GNcVRFO0uCkwNIzbSfQAdF4Ins6z6PHjY1TWNWwdR1ybylUKUWdvb3TlFXmwjTNsjs9SG/z3+3htdQ+z1pdJREpJvabjohVNqqqpKMUeXWb9wZ963eFvR1fswsHxdaQyslSApcitNnCAbM3BmfFdgiCwbzv8+MzvkevtkTRcuSiqdSSrJh5ce39pRsJQ8nUcxyQ8xIvz3pNooQkTVP3D2fTPDJ0z2WNQoJohVTCOgGEuklZnT5fhlw8WZuOkVfYy2e3hzafpmHpdlysPFM4tt5GaIIh9nHecuG7Rsa65poogNxqmVojifrtMM0eFjkP1qntn8ityEoRgn+tKj2jo+KexD8LAl1ZRqQDC+MC9tbyWH7fRib9oPU66PPTCEm+Ao3YX1XVDs9kVHiG81j85j9/wBvHPVbtN5TbSTYUFItWUc1zFGUrqSz4cbG5F6O9Ii/DLeQB8Xd1YoiOqWjoydpqBVRnSio998L1VTkvEmjNXtVuKlLuwVv4zLo9UHRffvMMJ2fZYNpiaCr1JFm3PuUmTN+nI7yGoLulE6KqqCoKYpen2+djWdeh8ZYFzEpAsbZb5Deq0cLGreatgcK87+L0YsCk5rSDtZNquUobKl4nURdibSb5xrz4KN8z/GLBMEnA37wcHcQFnuADIwxKJqoGXZYqtxOpurNHq2VJzmu0RNyENMqjfkskAXfJ3fk/Xf+disNZdbX0NphEspOBjInVioI22edtGoA5bMTO6xbyqrAA3o37N/sY0LNgp2eRacWRMuy23g6t1snn0OgKVO0ZDNKcp5HytBvDi/k6uERfvcOPlllnllhEP4O/JQKyrIUhLJsTFtmff5rzt/14e/u9OeeGkI23vrNDmxzwYMGFloGOCmOeOGADyi7ROnq2m+sNRxRASbNyub9kfmSVO/794e5jt0BW0NMsIamK0U4SUMvzlNz95cSFd/1vfuJuZ2XgHRZeFhgBg6Xao7PmWs9OIvorhI1RGCXKmXeIOBz6kTL7v6Cx52TsJJU1LuIuWYLxj5uXrWzhKw8V7ZwtmYW0ku3WvMhd9YxNa05Sz2LdGKlcVi8aRUlVL9U+QkjNE1mzRmsf/TGjZJZVYz3rGFh/hjx1qAhnDbW3SdhSMq6o+iJ9vLQ8XVDdsllKzQNwB27f8VUDDvduLbNp+qRIg7rwshdD6st42LZ07WlNx2olCN3YORgppuDnlVt+9vfsA957OjeeGZoOIZ67VVRTmMriLeQFMVK4qlNm4TNGaRuFUEWPB77Em6XFtvDrAADzGdnHOrmmrX4ren29jf0hoiVV06UxUkp8AatMCWCQlKOcCk7UATPl+ZRDYapo5gZ5WdZ7MYtNdbK9nI+PVgJim9Smb1qbxu0kQVgJs24EAGtyxhYYXmG/YG/rxZUN2dKRpeotQqjgBcwtTVygSMlJA4MzA7T3pAfRn3nfilNQeyzM0/U0xVjOpIlCnUaYVgUWKp5xxMI5JaPsZgt0WGi3d3mdm9x5OgxUl+BfhxLSk+0LKsmCgT+j1ak3VGzMYlmjKJKD3f1R9OKxp2oKJhKvCpEdE9UHswgCaTNaTgjWFqA9HCvPZZ9nEAj6KrmL1Poqo4x4k9pBjBmt8DUxKt0WztwqtKLM/UgrYdhi2SOwLDVMLNgHZTaNCa+yNNUqyla1dIWNVo17zlTgbaTWAzsBEzW3mbeUMPps/YDB4PUYaCVm7DuzWv+oL9sWcTQTOlAIrBfVxKAzTH9yO8uk8UxVdbU3L1TRTLVnUJ5VMfU+TR4wbQWXKQKyKpmiJgfW4sV4V/RYC1+IFTVFRlIarvqiqevKTUjMq7m3zMUpknDnJvxXAvGKwJAYXgkTZ2AF0Hf0YYnTnsFUZSen8bSVTvntcQTHJXNNhJAHLpcYA5kA23gkSoAsIX7DC+/BrGugv22X9VsjR9pKhqFrSNqOkqQrBJhW9KQDhzlQjVUHLBy3sv4LmOLZvvDeFioXgd+ItQvxZqinqF091bnkJznWbd3p3qe1dZtHLrIsgHlwd33g9Azssv9aGQdR3jhrHVF0DQdSytfuI2FhZxy1BtIVG6EEVlERyAchNUvyWph9UcI7qvqjp5T9TOD0nptBg946qoTZ5nwWiqv4VWObmfCbmV5XrAAH1/TxzyKg3PaiqJyJmtWrjsg6eS2mmdVttR5NN9x4JF2yEMoNptIAcWZ2XAe8AG230dAWDhW5SRdS8o4kpBwq9fO1TWXcrFeapn1njCair55eRKunjhXrPeapn9/DQdm3seyVTyDSoq3ZlHwaWfFSiHA2LPfJxQ8CX2i/LitZnmcyTyz7pLgv4F4diTS5eg9L8pmRCySqEweWmO8G9nqQ/zM/fwyGefox1kUMkUxARyAB+YRx2M/y4mqmJtoIlhiVFOWDHzBhZIPuDBgwAYyTuxEK40spXUlgDWpIVnLAGXqzXS9al/SB9Q/szxMvnx89GAbdFfsLQ77BOnDl0Sya86zTP526L0cwH+zMwI/tYwLdgmikcwcRNQVNDvkt6Thu9G8C/tsv+1hnu7B3YRihF9jW0+Isj6B110caZqwk0y1RiE/nYyiJIv7fZO/uPFZVx2v4PUilvi/MxMhSk6yk2Ml64OYbZKtHaLngrWGCoieaNnR/sw8hBnb6M8Lr2leyw01gTymYHgRlVJDuM9iL0PIrb4vKf5MIfJOhGniniXOu3+UWyKqqlFKkp5w5qOLBE1Yx/Kvz5gOUcN3j58siiHB3gaz4LOjZff7fUg6lgI3RzSSm3isJI5QUoD6eaOX4AsvwbTRFEwbfguMIHZ12IgBmd+KzrXSisNOnJpVBTr+LAP5Twr23+MGzEMB23M9rhJQ/YPDfuZSibdbSd0LO1KbUBVlPu4WUmHMo2bC3Zxq0C1MDNJJF8jzBktwbFTB2iBgF4fJvbwxWmPaL1S1WjY2lqGg2PMR7NFs/qaYIjATEO7imAdBnZ0b8Ljp3oFXWp75FvEQrpqzWP1sq/SNFskHn39fuY9KtK9MYjSmjmUBEp9ySW5RYh3rq+Mz/pzw5pJLL3JtOW5bbnxUpiU7Griv1Be19qLUFRP+uxrY2QSz/qkSvEMfG38H/p039OcjUKw/oN4l/pSyw0Hp/TgwvFS49lBr+KlX6fdnagdNFk3EJTyAPw6X7q5dx9c+/PFmin3Z45W4Ms+7CyUkaR9NDlgwYMA6GDBgwAGDBgwAGDBgwAGDBgwAGDBgwAYxTHu+bHVGLaI+sBukJ+bIMu//ANsGDAN+mhntyxkwYMA4c8GDBgAMGDBgAMGDBgAMGDBgA//Z';

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
