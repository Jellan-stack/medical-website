from datetime import datetime
from functools import wraps
from html import escape
from email.message import EmailMessage
import os
import re
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


# =====================================================================
# TATLONG LOGO NG MEDICAL CERTIFICATE / MEDICAL RECORD (NA-EMBED SA CODE)
# Order: SLSU seal (left), Bagong Pilipinas (middle), JGE Campus seal (right)
# =====================================================================
LOGO_L = 'data:image/jpeg;base64,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'
LOGO_M = 'data:image/jpeg;base64,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'
LOGO_R = 'data:image/jpeg;base64,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'
_LOGOS = {"L": LOGO_L, "M": LOGO_M, "R": LOGO_R}

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
        color, title = "#16a34a", "Appointment Approved"
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

// === PRINT (papalitan ng Medical Certificate auto-fill sa dulo ng file) ===
function printAppointment(id) {
    alert('Loading... pakisubukan ulit.');
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
#nurseViewMonthly .grid > * { min-width: 0; }
#nurseViewMonthly .nx-kpi { min-width: 0; }
#nurseViewMonthly .nx-kpi > div:last-child { min-width: 0; }
#nurseViewMonthly .nx-kpi .val { overflow-wrap: anywhere; }

@media (max-width: 1279px) {
  #nurseViewMonthly .grid.lg\:grid-cols-5 { grid-template-columns: minmax(0, 1fr); }
  #nurseViewMonthly .lg\:col-span-3,
  #nurseViewMonthly .lg\:col-span-2 { grid-column: 1 / -1; }
}

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

/* ===== TODAY'S APPOINTMENTS: RESPONSIVE FIX ===== */
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
        cur.execute(
            base + """
            WHERE (a.created_at AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Manila')::date
                  = (NOW() AT TIME ZONE 'Asia/Manila')::date
            ORDER BY a.date ASC, a.time ASC, a.id ASC
            """
        )
        booked_rows = cur.fetchall()

        # May schedule ngayong araw (scheduled today)
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
# CLINIC UPDATE
# =====================================================================
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


def _patient_dict(r):
    """r = (id, name, role, birthday, civil_status, address, religion, course, gender, nationality, contact)"""
    age = ""
    try:
        if r[3]:
            age = calc_age(datetime.strptime(r[3], "%Y-%m-%d").date())
    except ValueError:
        pass
    return {
        "id": r[0], "name": r[1], "role": r[2], "birthday": r[3],
        "civilStatus": r[4], "address": r[5], "religion": r[6],
        "course": r[7], "gender": r[8], "nationality": r[9],
        "contact": r[10], "age": age,
    }


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
        return jsonify(patients=[_patient_dict(r) for r in cur.fetchall()]), 200
    except Exception as e:
        return jsonify(error=str(e)), 500
    finally:
        cur.close()


app.add_url_rule("/api/patients", "get_patients", nurse_required(patients_v1), methods=["GET"])


# ---------- BACKEND: buong info ng nag-appointment (para sa Patient Info at Certificate) ----------
def apt_certificate_v1(apt_id):
    conn = get_db()
    if not conn:
        return jsonify(error="Database connection failed."), 500

    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT u.id, u.name, u.role, u.birthday, u.civil_status, u.address, u.religion,
                   u.course, u.gender, u.nationality, u.contact,
                   a.date, a.time, a.type, a.reason
            FROM appointments a
            JOIN users u ON a.user_id = u.id
            WHERE a.id = %s
        """, (apt_id,))
        r = cur.fetchone()
        if r is None:
            return jsonify(error="Appointment not found."), 404
        return jsonify(
            patient=_patient_dict(r[:11]),
            appointment={"date": r[11], "time": r[12], "type": r[13], "reason": r[14]},
        ), 200
    except Exception as e:
        return jsonify(error=str(e)), 500
    finally:
        cur.close()


app.add_url_rule("/api/appointments/<int:apt_id>/certificate", "apt_certificate",
                 nurse_required(apt_certificate_v1), methods=["GET"])


# ---------- FRONTEND: binabago ang HTML_CONTENT ----------
def _hrep(old, new):
    global HTML_CONTENT
    if HTML_CONTENT.count(old) != 1:
        raise RuntimeError("Clinic update: hindi tumugma ang bahaging ito ng HTML:\n" + old[:90])
    HTML_CONTENT = HTML_CONTENT.replace(old, new)


def _hrep_all(old, new):
    """Papalitan ang LAHAT ng tugma (kahit higit sa isa)."""
    global HTML_CONTENT
    if HTML_CONTENT.count(old) < 1:
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

# ---------- PATIENT INFO BUTTON (ⓘ) sa lahat ng talahanayan ng nurse ----------
_hrep_all(
    r'''<button onclick="printAppointment(${a.id})" class="text-gray-600 hover:text-gray-800 mr-2" title="Print">''',
    r'''<button onclick="nxShowInfo(${a.id})" class="text-blue-600 hover:text-blue-800 mr-2" title="Patient Info">
                        <i class="fa-solid fa-circle-info"></i>
                    </button>
                    <button onclick="printAppointment(${a.id})" class="text-gray-600 hover:text-gray-800 mr-2" title="Print">''')

_hrep(
    r"""'<button onclick="printAppointment(' + a.id + ')" class="px-2.5 py-1.5 bg-gray-100""",
    r"""'<button onclick="nxShowInfo(' + a.id + ')" class="px-2.5 py-1.5 bg-blue-50 hover:bg-blue-100 text-blue-700 rounded-lg text-xs mr-1" title="Patient Info"><i class="fa-solid fa-circle-info"></i></button>' +
                '<button onclick="printAppointment(' + a.id + ')" class="px-2.5 py-1.5 bg-gray-100""")

# ---------- MEDICAL CERTIFICATE + PATIENT INFO (CSS + JS) ----------
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
.pi-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px 18px}
.pi-grid .pi-full{grid-column:1/-1}
.pi-item .pi-l{font-size:11px;color:#6b7280;font-weight:600;text-transform:uppercase;letter-spacing:.04em}
.pi-item .pi-v{font-size:14px;color:#111827;font-weight:600;word-break:break-word}
@media(min-width:900px){.pi-grid.pi-wide{grid-template-columns:repeat(4,minmax(0,1fr))}}
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

// ===== MEDICAL CERTIFICATE + PATIENT INFO (Nurse Panel) =====
(function () {
    const $ = id => document.getElementById(id);
    let patients = [];
    const LOGO_L = '__LOGO_L__', LOGO_M = '__LOGO_M__', LOGO_R = '__LOGO_R__';

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

    // --- Patient Information (laman ng Create Account) ---
    const PI_FIELDS = [
        ['Full Name', 'name'], ['Role', 'role'], ['Birthday', 'birthday'], ['Age', 'age'],
        ['Civil Status', 'civilStatus'], ['Gender', 'gender'], ['Religion', 'religion'], ['Nationality', 'nationality'],
        ['Course', 'course'], ['Contact #', 'contact'], ['Address', 'address']
    ];
    function piValue(p, key) {
        let v = p ? p[key] : '';
        if (key === 'birthday' && v) {
            try { v = new Date(v + 'T00:00:00').toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' }); } catch (e) {}
        }
        return (v === undefined || v === null || v === '') ? '—' : v;
    }
    function piGridHTML(p, wide) {
        return '<div class="pi-grid' + (wide ? ' pi-wide' : '') + '">' + PI_FIELDS.map(f =>
            '<div class="pi-item' + (f[1] === 'address' ? ' pi-full' : '') + '"><div class="pi-l">' + f[0] + '</div><div class="pi-v">' + esc(piValue(p, f[1])) + '</div></div>'
        ).join('') + '</div>';
    }
    function renderInfoCard(p) {
        const box = $('certInfoBody');
        if (!box) return;
        box.innerHTML = p ? piGridHTML(p, true)
            : '<p class="text-sm text-gray-400 italic">Pumili ng pasyente sa itaas, o pindutin ang 🖨 sa isang appointment para lumabas dito ang personal info.</p>';
    }

    const CERT_HTML = `
<div class="nx-hero mb-6 flex flex-col md:flex-row md:items-center justify-between gap-4">
  <div><div class="nx-chip mb-3"><i class="fa-solid fa-file-medical"></i> Health Services Unit</div>
  <h2 class="text-2xl font-bold">Medical Certificate</h2>
  <p class="text-sm mt-1">"Type on the provided lines. Click Mr./Ms./Mrs., Male/Female, and Civil Status to underline your selection (click again to remove the underline).".</p></div>
  <div class="flex flex-wrap gap-2 items-center">
    <select id="certPatient" onchange="certFill(this.value)" class="px-3 py-2 rounded-lg text-sm font-semibold text-gray-800 bg-white focus:outline-none max-w-full w-full sm:w-64"><option value="">Auto-fill from patient (optional)</option></select>
    <button onclick="certClear()" class="bg-white/15 hover:bg-white/25 border border-white/30 text-white px-4 py-2 rounded-lg text-sm font-semibold"><i class="fa-solid fa-eraser mr-2"></i>Clear</button>
    <button onclick="certPrint()" class="bg-white text-blue-700 hover:bg-blue-50 px-4 py-2 rounded-lg text-sm font-semibold"><i class="fa-solid fa-print mr-2"></i>Print</button>
  </div>
</div>
<div class="dashboard-card p-4 sm:p-5 mb-6">
  <h3 class="text-base font-bold text-gray-800 mb-3"><i class="fa-solid fa-id-card text-blue-600 mr-2"></i>Patient Information <span class="text-xs font-normal text-gray-500"></span></h3>
  <div id="certInfoBody"></div>
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

    function fmtDate(iso) {
        const o = { year: 'numeric', month: 'long', day: 'numeric' };
        if (!iso) return new Date().toLocaleDateString('en-US', o);
        return new Date(iso + 'T00:00:00').toLocaleDateString('en-US', o);
    }
    function set(id, v) { const e = $(id); if (e) e.textContent = v; }
    function pick(group, value) {
        document.querySelectorAll('#certPaper .og[data-g="' + group + '"] .opt').forEach(o => {
            o.classList.toggle('on', !!value && o.dataset.v.toLowerCase() === String(value).toLowerCase());
        });
    }

    // Pinupunan ang certificate gamit ang info ng pasyente
    function fillCertificate(p, examIso) {
        const female = p.gender === 'Female', male = p.gender === 'Male';
        set('cfDate', fmtDate());
        set('cfExam', fmtDate(examIso));
        set('cfName', p.name || '');
        set('cfAge', (p.age === '' || p.age === null || p.age === undefined) ? '' : p.age);
        set('cfAddress', p.address || '');
        set('cfReq', p.name || '');
        set('cfDiag', '');
        set('cfRec', '');
        pick('title', female ? 'Ms' : (male ? 'Mr' : ''));
        pick('gender', p.gender || '');
        pick('civil', ['Single', 'Married', 'Separated'].includes(p.civilStatus) ? p.civilStatus : '');
        pick('req', female ? 'Ms' : (male ? 'Msr' : ''));
        renderInfoCard(p);
    }

    async function loadPatients() {
        try {
            const d = await api('/api/patients');
            patients = d.patients;
            const cur = $('certPatient').value;
            $('certPatient').innerHTML = '<option value="">Auto-fill from patient (optional)</option>' +
                patients.map(p => '<option value="' + p.id + '">' + esc(p.name) + ' (' + esc(p.role) + ')</option>').join('');
            $('certPatient').value = cur;
        } catch (e) { console.error(e); }
    }

    window.certFill = function (id) {
        const p = patients.find(x => String(x.id) === String(id));
        if (!p) { renderInfoCard(null); return; }
        fillCertificate(p, null);
    };

    window.certClear = function () {
        $('certPaper').querySelectorAll('.cf').forEach(e => { e.textContent = ''; });
        $('certPaper').querySelectorAll('.opt.on').forEach(e => e.classList.remove('on'));
        $('certPatient').value = '';
        renderInfoCard(null);
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

    // ===== 🖨 PRINT NG APPOINTMENT -> MEDICAL CERTIFICATE NA NAKA-FILL =====
    window.printAppointment = async function (id) {
        try {
            const d = await api('/api/appointments/' + id + '/certificate');
            showNurseTab('cert');
            await loadPatients();
            fillCertificate(d.patient, d.appointment.date);
            $('certPatient').value = String(d.patient.id);
        } catch (e) {
            alert(e.message);
        }
    };

    // ===== ⓘ PATIENT INFO MODAL =====
    window.nxShowInfo = async function (id) {
        try {
            const d = await api('/api/appointments/' + id + '/certificate');
            const p = d.patient, a = d.appointment;
            let m = $('nxInfoModal');
            if (!m) {
                m = document.createElement('div');
                m.id = 'nxInfoModal';
                m.className = 'hidden fixed inset-0 flex items-center justify-center p-4 bg-black/50';
                m.style.zIndex = '60';
                m.addEventListener('click', e => { if (e.target === m) m.classList.add('hidden'); });
                document.body.appendChild(m);
                document.addEventListener('keydown', e => { if (e.key === 'Escape') m.classList.add('hidden'); });
            }
            m.innerHTML =
                '<div class="bg-white rounded-2xl shadow-2xl w-full max-w-2xl p-6 max-h-[90vh] overflow-y-auto">' +
                '<div class="flex justify-between items-start mb-4"><div>' +
                '<h3 class="text-lg font-bold text-gray-800"><i class="fa-solid fa-id-card text-blue-600 mr-2"></i>Patient Information</h3>' +
                '<p class="text-sm text-gray-500">Appointment: ' + esc(a.date) + ' ' + esc(a.time) + ' · ' + esc(a.type) + '</p></div>' +
                '<button onclick="document.getElementById(\'nxInfoModal\').classList.add(\'hidden\')" class="text-gray-400 hover:text-gray-700 text-xl"><i class="fa-solid fa-xmark"></i></button></div>' +
                piGridHTML(p, false) +
                '<div class="mt-4 pt-4 border-t border-gray-100"><div class="pi-l text-xs text-gray-500 font-semibold uppercase">Purpose / Symptoms</div>' +
                '<div class="text-sm text-gray-800">' + esc(a.reason || '—') + '</div></div>' +
                '<div class="flex justify-end gap-2 mt-5">' +
                '<button onclick="document.getElementById(\'nxInfoModal\').classList.add(\'hidden\')" class="px-4 py-2 bg-gray-100 hover:bg-gray-200 text-gray-700 rounded-lg text-sm font-medium">Close</button>' +
                '<button onclick="document.getElementById(\'nxInfoModal\').classList.add(\'hidden\');printAppointment(' + id + ')" class="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-semibold"><i class="fa-solid fa-print mr-1"></i> Medical Certificate</button>' +
                '</div></div>';
            m.classList.remove('hidden');
        } catch (e) {
            alert(e.message);
        }
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
        renderInfoCard(null);
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
                if (!$('cfDate').textContent) set('cfDate', fmtDate());
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

# Isingit ang mga logo sa script
_EXTRA = (_EXTRA.replace("__LOGO_L__", _LOGOS["L"])
                .replace("__LOGO_M__", _LOGOS["M"])
                .replace("__LOGO_R__", _LOGOS["R"]))

_hrep("\n</body>\n</html>", _EXTRA + "\n</body>\n</html>")

# =====================================================================
# MEDICAL RECORD (1st YEAR) + YEAR LEVEL
# =====================================================================
import json

YEAR_LEVELS = ("1st Year", "2nd Year", "3rd Year", "4th Year", "5th Year")
MR_STUDENT_KEYS = ("name", "birthday", "gender", "civilStatus", "religion",
                   "nationality", "department", "course", "address", "contact",
                   "emName", "emAddress", "emContact")


# ---------- DATABASE: year_level + medical_records ----------
_init_db_v3 = init_db


def init_db():
    _init_db_v3()
    conn = get_db()
    if not conn:
        return
    cur = conn.cursor()
    cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS year_level TEXT")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS medical_records (
            user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            name TEXT, birthday TEXT, gender TEXT, civil_status TEXT, religion TEXT,
            nationality TEXT, department TEXT, course TEXT, address TEXT, contact TEXT,
            nurse_data TEXT DEFAULT '{}',
            submitted_at TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    for col in ("em_name", "em_address", "em_contact"):
        cur.execute(f"ALTER TABLE medical_records ADD COLUMN IF NOT EXISTS {col} TEXT")
    conn.commit()
    cur.close()


# ---------- BACKEND: Create Account na may Year Level ----------
_register_v2 = app.view_functions["register"]


def register_v3():
    data = request.get_json(silent=True) or {}
    role = data.get("role") or ""
    year = (data.get("yearLevel") or "").strip()
    if role == "Student" and year not in YEAR_LEVELS:
        return jsonify(error="Please select your year level."), 400

    result = _register_v2()
    resp, status = result if isinstance(result, tuple) else (result, 200)

    if status == 201 and role == "Student":
        conn = get_db()
        if conn:
            cur = conn.cursor()
            try:
                cur.execute(
                    "UPDATE users SET year_level = %s WHERE email = %s",
                    (year, (data.get("email") or "").strip().lower()),
                )
                conn.commit()
            except Exception:
                conn.rollback()
            finally:
                cur.close()
    return resp, status


app.view_functions["register"] = register_v3


# ---------- BACKEND: helpers ----------
def _mr_clean_student(d, strict):
    out = {k: str(d.get(k) or "").strip()[:200] for k in MR_STUDENT_KEYS}
    if not strict:
        return out, None
    if not all(out.values()):
        return out, "Please fill in all fields."
    try:
        age = calc_age(datetime.strptime(out["birthday"], "%Y-%m-%d").date())
    except ValueError:
        return out, "Invalid birthday."
    if age < 5 or age > 100:
        return out, "Invalid birthday."
    if out["civilStatus"] not in CIVIL_STATUSES:
        return out, "Invalid civil status."
    if out["gender"] not in ("Male", "Female"):
        return out, "Invalid gender."
    out["contact"] = re.sub(r"[\s-]", "", out["contact"])
    if not re.fullmatch(r"(09|\+639)\d{9}", out["contact"]):
        return out, "Invalid contact number."
    out["emContact"] = re.sub(r"[\s-]", "", out["emContact"])
    if not re.fullmatch(r"(09|\+639)\d{9}", out["emContact"]):
        return out, "Invalid emergency contact number."
    return out, None


def _mr_clean_nurse(d):
    if not isinstance(d, dict):
        return {}
    out = {}
    for k, v in list(d.items())[:600]:
        k = str(k)[:40]
        if re.fullmatch(r"[A-Za-z0-9_]+", k):
            out[k] = str(v)[:500]
    return out


def _mr_load(cur, uid):
    cur.execute("""
        SELECT id, name, role, birthday, civil_status, address, religion, course,
               gender, nationality, contact, year_level
        FROM users WHERE id = %s
    """, (uid,))
    u = cur.fetchone()
    if u is None:
        return None
    cur.execute("""
        SELECT name, birthday, gender, civil_status, religion, nationality, department,
               course, address, contact, nurse_data, submitted_at,
               em_name, em_address, em_contact
        FROM medical_records WHERE user_id = %s
    """, (uid,))
    r = cur.fetchone()
    if r:
        stu = {"name": r[0], "birthday": r[1], "gender": r[2], "civilStatus": r[3],
               "religion": r[4], "nationality": r[5], "department": r[6],
               "course": r[7], "address": r[8], "contact": r[9],
               "emName": r[12], "emAddress": r[13], "emContact": r[14]}
        try:
            nurse = json.loads(r[10] or "{}")
        except ValueError:
            nurse = {}
        submitted = r[11] is not None
    else:
        # wala pang record: i-prefill mula sa Create Account
        stu = {"name": u[1], "birthday": u[3], "gender": u[8], "civilStatus": u[4],
               "religion": u[6], "nationality": u[9], "department": "",
               "course": u[7], "address": u[5], "contact": u[10],
               "emName": "", "emAddress": "", "emContact": ""}
        nurse, submitted = {}, False
    stu = {k: (v or "") for k, v in stu.items()}
    age = ""
    try:
        age = calc_age(datetime.strptime(stu["birthday"], "%Y-%m-%d").date())
    except ValueError:
        pass
    stu["age"] = age
    return {"userId": u[0], "role": u[2], "yearLevel": u[11] or "",
            "submitted": submitted, "student": stu, "nurse": nurse}


_MR_COLS = ("name, birthday, gender, civil_status, religion, nationality, "
            "department, course, address, contact, em_name, em_address, em_contact")


def _ph(n):
    return ", ".join(["%s"] * n)


def _mr_student_params(s):
    return (s["name"], s["birthday"], s["gender"], s["civilStatus"], s["religion"],
            s["nationality"], s["department"], s["course"], s["address"], s["contact"],
            s["emName"], s["emAddress"], s["emContact"])


# ---------- BACKEND: STUDENT (sariling record) ----------
def mr_me_get():
    conn = get_db()
    if not conn:
        return jsonify(error="Database connection failed."), 500
    cur = conn.cursor()
    try:
        rec = _mr_load(cur, g.user["id"])
        rec["required"] = g.user["role"] == "Student" and rec["yearLevel"] == "1st Year"
        return jsonify(rec), 200
    except Exception as e:
        return jsonify(error=str(e)), 500
    finally:
        cur.close()


def mr_me_save():
    if g.user["role"] != "Student":
        return jsonify(error="Students only."), 403
    data = request.get_json(silent=True) or {}
    stu, err = _mr_clean_student(data, strict=True)
    if err:
        return jsonify(error=err), 400

    conn = get_db()
    if not conn:
        return jsonify(error="Database connection failed."), 500
    cur = conn.cursor()
    try:
        cur.execute("SELECT year_level FROM users WHERE id = %s", (g.user["id"],))
        row = cur.fetchone()
        if not row or row[0] != "1st Year":
            return jsonify(error="Medical record is for 1st year students only."), 403
        cur.execute(f"""
            INSERT INTO medical_records (user_id, {_MR_COLS}, submitted_at, updated_at)
            VALUES (%s, {_ph(13)}, NOW(), NOW())
            ON CONFLICT (user_id) DO UPDATE SET
                name = EXCLUDED.name, birthday = EXCLUDED.birthday, gender = EXCLUDED.gender,
                civil_status = EXCLUDED.civil_status, religion = EXCLUDED.religion,
                nationality = EXCLUDED.nationality, department = EXCLUDED.department,
                course = EXCLUDED.course, address = EXCLUDED.address, contact = EXCLUDED.contact,
                em_name = EXCLUDED.em_name, em_address = EXCLUDED.em_address,
                em_contact = EXCLUDED.em_contact,
                submitted_at = COALESCE(medical_records.submitted_at, NOW()),
                updated_at = NOW()
        """, (g.user["id"],) + _mr_student_params(stu))
        conn.commit()
        return jsonify(message="Medical record submitted."), 200
    except Exception as e:
        conn.rollback()
        return jsonify(error=str(e)), 500
    finally:
        cur.close()


# ---------- BACKEND: NURSE ----------
def mr_list():
    conn = get_db()
    if not conn:
        return jsonify(error="Database connection failed."), 500
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT u.id, u.name, COALESCE(m.course, u.course),
                   (m.submitted_at IS NOT NULL),
                   to_char(m.submitted_at AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Manila', 'Mon DD, YYYY')
            FROM users u
            LEFT JOIN medical_records m ON m.user_id = u.id
            WHERE u.role = 'Student' AND u.year_level = '1st Year'
            ORDER BY (m.submitted_at IS NULL) ASC, u.name ASC
        """)
        students = [{"id": r[0], "name": r[1], "course": r[2] or "",
                     "submitted": r[3], "submittedAt": r[4]} for r in cur.fetchall()]
        return jsonify(students=students), 200
    except Exception as e:
        return jsonify(error=str(e)), 500
    finally:
        cur.close()


def mr_nurse_get(uid):
    conn = get_db()
    if not conn:
        return jsonify(error="Database connection failed."), 500
    cur = conn.cursor()
    try:
        rec = _mr_load(cur, uid)
        if rec is None or rec["role"] != "Student":
            return jsonify(error="Student not found."), 404
        return jsonify(rec), 200
    except Exception as e:
        return jsonify(error=str(e)), 500
    finally:
        cur.close()


def mr_nurse_save(uid):
    data = request.get_json(silent=True) or {}
    stu, _err = _mr_clean_student(data.get("student") or {}, strict=False)
    nurse = _mr_clean_nurse(data.get("nurse") or {})

    conn = get_db()
    if not conn:
        return jsonify(error="Database connection failed."), 500
    cur = conn.cursor()
    try:
        cur.execute("SELECT role FROM users WHERE id = %s", (uid,))
        row = cur.fetchone()
        if not row or row[0] != "Student":
            return jsonify(error="Student not found."), 404
        cur.execute(f"""
            INSERT INTO medical_records (user_id, {_MR_COLS}, nurse_data, updated_at)
            VALUES (%s, {_ph(13)}, %s, NOW())
            ON CONFLICT (user_id) DO UPDATE SET
                name = EXCLUDED.name, birthday = EXCLUDED.birthday, gender = EXCLUDED.gender,
                civil_status = EXCLUDED.civil_status, religion = EXCLUDED.religion,
                nationality = EXCLUDED.nationality, department = EXCLUDED.department,
                course = EXCLUDED.course, address = EXCLUDED.address, contact = EXCLUDED.contact,
                em_name = EXCLUDED.em_name, em_address = EXCLUDED.em_address,
                em_contact = EXCLUDED.em_contact,
                nurse_data = EXCLUDED.nurse_data, updated_at = NOW()
        """, (uid,) + _mr_student_params(stu) + (json.dumps(nurse),))
        conn.commit()
        return jsonify(message="Medical record saved."), 200
    except Exception as e:
        conn.rollback()
        return jsonify(error=str(e)), 500
    finally:
        cur.close()


app.add_url_rule("/api/medrec/me", "mr_me_get", login_required(mr_me_get), methods=["GET"])
app.add_url_rule("/api/medrec/me", "mr_me_save", login_required(mr_me_save), methods=["POST"])
app.add_url_rule("/api/medrec", "mr_list", nurse_required(mr_list), methods=["GET"])
app.add_url_rule("/api/medrec/<int:uid>", "mr_nurse_get", nurse_required(mr_nurse_get), methods=["GET"])
app.add_url_rule("/api/medrec/<int:uid>", "mr_nurse_save", nurse_required(mr_nurse_save), methods=["POST"])


# ---------- FRONTEND: Year Level sa Create Account ----------
_YEAR_OPTS = "".join(f"<option>{y}</option>" for y in YEAR_LEVELS)
_hrep(
    f'<div><label class="{_LBL}">Contact #</label>',
    f'<div id="regYearWrap"><label class="{_LBL}">Year Level</label>'
    f'<select id="regYear" class="{_INP}"><option value="">Select...</option>{_YEAR_OPTS}</select></div>\n'
    f'            <div><label class="{_LBL}">Contact #</label>',
)
_hrep("if (missing || badPhone) {",
      "const noYear = role === 'Student' && !document.getElementById('regYear').value;\n"
      "        if (missing || badPhone || noYear) {")
_hrep("m0.textContent = missing ? 'Please fill in all personal information!' : 'Enter a valid contact number (e.g. 09123456789).';",
      "m0.textContent = (noYear && !missing && !badPhone) ? 'Please select your year level!' : "
      "(missing ? 'Please fill in all personal information!' : 'Enter a valid contact number (e.g. 09123456789).');")
_hrep("body: JSON.stringify({ name, email, password: pass, role, ...profile })",
      "body: JSON.stringify({ name, email, password: pass, role, ...profile, "
      "yearLevel: (role === 'Student' ? document.getElementById('regYear').value : '') })")


# ---------- FRONTEND: Medical Record (student form + nurse panel + print) ----------
_MR_EXTRA = r'''
<style id="mrStyle">
.mr-paper{background:#fff;color:#111;font-family:Verdana,Geneva,sans-serif;font-size:14px;line-height:1.9;padding:24px 50px 40px;max-width:820px;margin:0 auto 24px;position:relative;box-shadow:0 4px 24px rgba(0,0,0,.12);border:1px solid #e5e7eb;box-sizing:border-box}
.mr-head{display:flex;align-items:center;gap:10px}
.mr-head .lg{display:flex;align-items:center;gap:8px;flex-shrink:0}
.mr-head img{height:64px;width:auto;display:block}
.mr-head .tx{flex:1;min-width:0;line-height:1.25}
.mr-head .u{font-size:21px;font-weight:800;letter-spacing:.3px}
.mr-head .s{font-size:14px}
.mr-head .em{font-family:Georgia,serif;font-size:11px;margin-left:34px;color:#444}
.mr-title{text-align:center;font-weight:700;font-size:16px;margin:18px 0 10px}
.mr-sec{text-align:center;margin:14px 0 4px}
.mr-sub{margin-top:6px}
.mr-indent{padding-left:44px}
.mr-row{display:flex;flex-wrap:wrap;gap:2px 22px;align-items:baseline;margin-bottom:4px}
.mr-it{display:flex;align-items:baseline;gap:4px;flex:1 1 190px;min-width:0}
.mr-it.w2{flex:2 1 330px}.mr-it.full{flex:1 1 100%}
.mr-it>label{white-space:nowrap}
.mr-f{flex:1;min-width:40px;border-bottom:1px solid #222;padding:0 4px;outline:none;min-height:1.5em;word-break:break-word;line-height:1.5;display:inline-block}
.mr-f[contenteditable="true"]:focus,.mr-cell:focus{background:#eff6ff}
.mr-ro{background:#f8fafc}
.mr-grid3{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:0 18px}
.mr-ck{display:flex;justify-content:space-between;gap:6px;cursor:pointer;-webkit-user-select:none;user-select:none}
.mr-ck b{font-weight:400}
.mr-ck .bx{white-space:pre}
.mr-ck .bx:before{content:'(    )'}
.mr-ck.on .bx:before{content:'( ✓ )';font-weight:700}
.mr-ck.in{display:inline-flex;justify-content:flex-start;margin-right:34px}
.mr-foot2{display:flex;justify-content:space-between;align-items:flex-end;gap:20px;margin-top:26px}
.mr-sigline{width:240px;border-top:1px solid #222;text-align:center;margin-top:30px}
.mr-priv{font-family:Arial,Helvetica,sans-serif;font-size:8px;line-height:1.3;margin-top:16px;font-weight:600}
.mr-code{font-family:Georgia,serif;font-style:italic;font-size:12px;line-height:1.3;margin-top:10px}
.mr-pg{position:absolute;right:30px;bottom:14px;font-family:Georgia,serif;font-size:14px}
.mr-center{text-align:center;line-height:1.3;font-family:Georgia,serif}
.mr-dent{display:flex;gap:14px;align-items:flex-start;margin-top:8px}
.mr-legend{width:30%;font-family:Georgia,serif;font-size:10.5px;line-height:1.25;flex-shrink:0}
.mr-legend div{display:flex;gap:8px;margin-bottom:2px}.mr-legend b{width:26px;flex-shrink:0}
.dcx{position:relative;width:100%;min-width:560px;aspect-ratio:960/375;container-type:inline-size;--bw:max(1.5px,0.27cqw);background:#fff;font-family:Arial,Helvetica,sans-serif;color:#000}
.dcx .l{position:absolute;background:#000;pointer-events:none}
.dcx .l.h{height:var(--bw);transform:translateY(-50%)}
.dcx .l.v{width:var(--bw);transform:translateX(-50%)}
.dcx .c{position:absolute;box-sizing:border-box;overflow:hidden;outline:none;display:flex;align-items:center;justify-content:center;text-align:center;font-size:1.5cqw;font-weight:700;line-height:1;word-break:break-all;background-size:100% 100%;background-repeat:no-repeat}
.dcx .to{position:absolute;background-size:100% 100%;background-repeat:no-repeat;pointer-events:none}
.dcx .c:focus{background-color:rgba(219,234,254,.55)}
.dcx .t{position:absolute;box-sizing:border-box;display:flex;align-items:center;justify-content:center;text-align:center;font-weight:800;line-height:1.15;pointer-events:none;white-space:nowrap;-webkit-text-stroke:.25px #000}
.dcx .t.n{font-size:1.85cqw}
.dcx .t.lab{font-size:1.7cqw}
.dcx .t.bx{font-size:1.75cqw}
.dcx .t.lt{font-size:1.6cqw}
.mr-tp{border-collapse:collapse;font-family:Georgia,serif;font-size:11px;margin:6px 0 10px}
.mr-tp td{border:1px solid #444;height:19px;min-width:90px;padding:0 3px}
.mr-tp td.nm{border:0;text-align:right;padding-right:8px;min-width:150px}
.mr-sv{border-collapse:collapse;width:100%;table-layout:fixed;font-size:11px;font-family:Georgia,serif}
.mr-sv th,.mr-sv td{border:1px solid #444;height:22px;padding:0 3px}
.mr-sv th{background:#f3f4f6}
.mr-cell{outline:none}
@media(max-width:700px){
 .mr-paper{padding:14px 12px 34px;font-size:12px}
 .mr-head img{height:34px}.mr-head .u{font-size:12px}.mr-head .s{font-size:10px}.mr-head .em{font-size:9px;margin-left:0}
 .mr-indent{padding-left:10px}.mr-grid3{grid-template-columns:1fr}.mr-dent{flex-direction:column}.mr-legend{width:100%}
 .mr-foot2{flex-direction:column;align-items:stretch}.mr-sigline{width:100%}
}
</style>

<script>
(function () {
    const $ = id => document.getElementById(id);
    const LOGO_L = '__MR_LOGO_L__', LOGO_M = '__MR_LOGO_M__', LOGO_R = '__MR_LOGO_R__';
    const STU_KEYS = ['name', 'birthday', 'gender', 'civilStatus', 'religion', 'nationality', 'department', 'course', 'address', 'contact', 'emName', 'emAddress', 'emContact'];
    let mrMe = null, cur = null, list = [], gate = false;

    const PRIV = 'DATA PRIVACY NOTICE: This form is owned and managed by SLSU-JGE&#39;s Health Services Unit (HSU) and may collect your personal information which includes your full name and email address. The Info Unit shall process your personal information solely for the purpose mentioned herein, in compliance with the Data Privacy Act of 2012 (&quot;Act&quot;), its Implementing Rules and Regulations, its issuances and releases, and this Privacy Notice. The Info Unit shall retain your personal information as long as necessary and shall be stored in secured storage locations with only authorized personnel having access to it. As a respondent, we understand and uphold your rights under the Act. For any concerns or inquiries, please send an email to nursekrista_slsujge@slsu.edu.ph';

    // Same na header/logo ng Medical Certificate
    const HEAD = '<div class="mr-head"><div class="lg"><img src="' + LOGO_L + '" alt=""><img src="' + LOGO_M + '" alt=""></div>' +
        '<div class="tx"><div class="u">SOUTHERN LUZON STATE UNIVERSITY</div>' +
        '<div class="s">Judge Guillermo Eleazar Campus, Tagkawayan<br>Health Services Unit</div>' +
        '<div class="em">nursekrista_slsujge@slsu.edu.ph</div></div>' +
        '<div class="rg"><img src="' + LOGO_R + '" alt=""></div></div>';

    function pretty(iso) {
        if (!iso) return '';
        try { return new Date(iso + 'T00:00:00').toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' }); }
        catch (e) { return iso; }
    }
    function todayPretty() { return new Date().toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' }); }
    function ageOf(iso) {
        if (!iso) return '';
        const b = new Date(iso + 'T00:00:00'), t = new Date();
        if (isNaN(b)) return '';
        let a = t.getFullYear() - b.getFullYear();
        const m = t.getMonth() - b.getMonth();
        if (m < 0 || (m === 0 && t.getDate() < b.getDate())) a--;
        return a >= 0 ? a : '';
    }

    // ================= CREATE ACCOUNT: Year Level ay para sa Student lang =================
    document.addEventListener('DOMContentLoaded', () => {
        const r = $('regRole'), w = $('regYearWrap');
        if (r && w) r.addEventListener('change', () => { w.style.display = r.value === 'Student' ? '' : 'none'; });
    });

    // ================= STUDENT: MEDICAL RECORD FORM (Name -> Contact#) =================
    function buildStudent() {
        if ($('mrStuScreen')) return;
        const inp = 'w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500';
        const lb = 'block text-gray-600 text-sm font-medium mb-1';
        const req = ' <span class="text-red-500">*</span>';
        const fld = (label, id, type, extra, ro) => '<div class="' + (extra || '') + '"><label class="' + lb + '">' + label + req +
            '</label><input type="' + type + '" id="' + id + '" class="' + inp + (ro ? ' bg-gray-100' : '') + '"' + (ro ? ' readonly' : '') + '></div>';
        const sel = (label, id, opts) => '<div><label class="' + lb + '">' + label + req + '</label><select id="' + id + '" class="' + inp + '"><option value="">Select...</option>' +
            opts.map(o => '<option>' + o + '</option>').join('') + '</select></div>';

        const d = document.createElement('div');
        d.id = 'mrStuScreen';
        d.className = 'hidden fixed inset-0 overflow-auto bg-gray-50 p-3 sm:p-6';
        d.style.zIndex = '55';
        d.innerHTML =
            '<div class="max-w-3xl mx-auto"><div class="dashboard-card p-4 sm:p-6">' + HEAD +
            '<div class="mr-title">Medical Record</div>' +
            '<p class="text-sm text-gray-500 text-center mb-5" id="mrStuNote"></p>' +
            '<div class="grid grid-cols-1 sm:grid-cols-2 gap-3">' +
                fld('Name', 'mrs_name', 'text', 'sm:col-span-2') +
                fld('Birthday', 'mrs_birthday', 'date') +
                fld('Age', 'mrs_age', 'text', '', true) +
                sel('Gender', 'mrs_gender', ['Male', 'Female']) +
                sel('Civil Status', 'mrs_civil', ['Single', 'Married', 'Separated', 'Widowed']) +
                fld('Religion', 'mrs_religion', 'text') +
                fld('Nationality', 'mrs_nationality', 'text') +
                fld('Department', 'mrs_department', 'text') +
                fld('Course to apply for', 'mrs_course', 'text') +
                fld('Address', 'mrs_address', 'text', 'sm:col-span-2') +
                fld('Contact#', 'mrs_contact', 'tel') +
                '<div class="sm:col-span-2 font-semibold text-gray-700 mt-2 pt-3 border-t border-gray-200">In Case of Emergency please notify:</div>' +
                fld('Parents/Guardian', 'mrs_emName', 'text', 'sm:col-span-2') +
                fld('Address', 'mrs_emAddress', 'text', 'sm:col-span-2') +
                fld('Contact#', 'mrs_emContact', 'tel') +
            '</div>' +
            '<p id="mrStuMsg" class="mt-3 text-sm font-medium"></p>' +
            '<div class="flex flex-wrap justify-end gap-2 mt-5">' +
                '<button id="mrStuClose" class="px-4 py-2 bg-gray-100 hover:bg-gray-200 text-gray-700 rounded-lg text-sm font-medium">Close</button>' +
                '<button id="mrStuLogout" class="px-4 py-2 bg-red-50 hover:bg-red-100 text-red-600 rounded-lg text-sm font-medium"><i class="fa-solid fa-right-from-bracket mr-1"></i>Log Out</button>' +
                '<button id="mrStuSubmit" class="px-5 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-semibold"><i class="fa-solid fa-paper-plane mr-1"></i>Submit Medical Record</button>' +
            '</div>' +
            '<div class="mr-priv">' + PRIV + '</div></div></div>';
        document.body.appendChild(d);

        $('mrs_birthday').max = new Date().toISOString().split('T')[0];
        $('mrs_birthday').addEventListener('change', () => { $('mrs_age').value = ageOf($('mrs_birthday').value); });
        $('mrStuClose').addEventListener('click', () => { if (!gate) $('mrStuScreen').classList.add('hidden'); });
        $('mrStuLogout').addEventListener('click', () => logoutSystem());
        $('mrStuSubmit').addEventListener('click', submitStu);
    }

    function openStu(isGate) {
        buildStudent();
        gate = !!isGate;
        const s = mrMe.student;
        const set = (id, v) => { $(id).value = v || ''; };
        set('mrs_name', s.name); set('mrs_birthday', s.birthday); set('mrs_age', ageOf(s.birthday));
        set('mrs_gender', s.gender); set('mrs_civil', s.civilStatus); set('mrs_religion', s.religion);
        set('mrs_nationality', s.nationality); set('mrs_department', s.department);
        set('mrs_course', s.course); set('mrs_address', s.address); set('mrs_contact', s.contact);
        set('mrs_emName', s.emName); set('mrs_emAddress', s.emAddress); set('mrs_emContact', s.emContact);
        $('mrStuMsg').textContent = '';
        $('mrStuNote').textContent = gate
            ? 'As a 1st Year student, please complete your Medical Record before using the clinic system.'
            : 'You may update your information below, then submit again.';
        $('mrStuClose').style.display = gate ? 'none' : '';
        $('mrStuLogout').style.display = gate ? '' : 'none';
        $('mrStuScreen').classList.remove('hidden');
    }
    window.mrOpenStu = () => openStu(false);

    async function submitStu() {
        const v = id => $(id).value.trim();
        const data = {
            name: v('mrs_name'), birthday: v('mrs_birthday'), gender: v('mrs_gender'), civilStatus: v('mrs_civil'),
            religion: v('mrs_religion'), nationality: v('mrs_nationality'), department: v('mrs_department'),
            course: v('mrs_course'), address: v('mrs_address'), contact: v('mrs_contact'),
            emName: v('mrs_emName'), emAddress: v('mrs_emAddress'), emContact: v('mrs_emContact')
        };
        const msg = $('mrStuMsg');
        msg.className = 'mt-3 text-sm font-medium text-orange-600';
        if (STU_KEYS.some(k => !data[k])) { msg.textContent = 'Please fill in all fields.'; return; }
        if (!/^(09|\+639)\d{9}$/.test(data.contact.replace(/[\s-]/g, ''))) { msg.textContent = 'Enter a valid contact number (e.g. 09123456789).'; return; }
        if (!/^(09|\+639)\d{9}$/.test(data.emContact.replace(/[\s-]/g, ''))) { msg.textContent = 'Enter a valid emergency contact number (e.g. 09123456789).'; return; }

        const btn = $('mrStuSubmit');
        btn.disabled = true; btn.classList.add('opacity-60', 'cursor-not-allowed');
        try {
            await api('/api/medrec/me', { method: 'POST', body: JSON.stringify(data) });
            mrMe.submitted = true;
            mrMe.student = Object.assign({}, data, { age: ageOf(data.birthday) });
            $('mrStuScreen').classList.add('hidden');
            gate = false;
            renderCard();
            alert('Medical record submitted!');
        } catch (e) {
            msg.className = 'mt-3 text-sm font-medium text-red-600';
            msg.textContent = e.message;
        } finally {
            btn.disabled = false; btn.classList.remove('opacity-60', 'cursor-not-allowed');
        }
    }

    function renderCard() {
        const main = document.querySelector('#userDashboard main');
        if (!main || !mrMe) return;
        let c = $('mrCard');
        if (!c) {
            c = document.createElement('div');
            c.id = 'mrCard';
            c.className = 'dashboard-card p-4 mb-6 fade-in flex flex-col sm:flex-row sm:items-center justify-between gap-3';
            main.children[0].insertAdjacentElement('afterend', c);
        }
        c.innerHTML =
            '<div class="flex items-center gap-3"><div class="w-11 h-11 rounded-xl bg-blue-100 text-blue-700 flex items-center justify-center"><i class="fa-solid fa-notes-medical"></i></div>' +
            '<div><div class="font-bold text-gray-800">Medical Record</div>' +
            '<div class="text-sm ' + (mrMe.submitted ? 'text-green-600' : 'text-orange-600') + '">' +
            (mrMe.submitted ? '<i class="fa-solid fa-circle-check mr-1"></i>Submitted' : 'Not yet submitted') + '</div></div></div>' +
            '<button onclick="mrOpenStu()" class="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg text-sm font-semibold">' +
            (mrMe.submitted ? 'View / Update' : 'Fill Up Now') + '</button>';
    }

    async function initStudent() {
        const old = $('mrCard'); if (old) old.remove();
        let d;
        try { d = await api('/api/medrec/me'); } catch (e) { return; }
        if (!d.required) return;
        mrMe = d;
        renderCard();
        if (!d.submitted) openStu(true);
    }

    // ================= NURSE: FULL MEDICAL RECORD (Page 1 + Page 2) =================
    const F = (k, ro, cls) => '<span class="mr-f' + (ro ? ' mr-ro' : '') + (cls ? ' ' + cls : '') + '" data-k="' + k + '"' + (ro ? '' : ' contenteditable="true"') + '></span>';
    const IT = (label, k, cls, ro) => '<div class="mr-it ' + (cls || '') + '"><label>' + label + '</label>' + F(k, ro) + '</div>';
    const IM = (label, k, cls) => '<div class="mr-it ' + (cls || '') + '"><label>' + label + '</label><span class="mr-f mr-ro" data-m="' + k + '"></span></div>';
    const ROW = h => '<div class="mr-row">' + h + '</div>';
    const CK = (label, k, inl) => '<div class="mr-ck' + (inl ? ' in' : '') + '" data-k="' + k + '"><b>' + label + '</b><span class="bx"></span></div>';

    function page1() {
        return '<div class="mr-paper" id="mrP1">' + HEAD +
            '<div class="mr-title">Medical Record</div>' +
            ROW(IT('Name:', 'name', 'full')) +
            ROW(IT('Birthday:', 'birthday', '', true) + IT('Age:', 'age', '', true) + IT('Gender:', 'gender')) +
            ROW(IT('Civil Status:', 'civilStatus') + IT('Religion:', 'religion') + IT('Nationality:', 'nationality')) +
            ROW(IT('Department:', 'department') + IT('Course to apply for:', 'course')) +
            ROW(IT('Address:', 'address', 'w2') + IT('Contact#:', 'contact')) +
            '<div class="mr-sub">In Case of Emergency please notify:</div>' +
            '<div class="mr-indent">' +
                ROW(IT('Parents/Guardian:', 'emName', 'full')) +
                ROW(IT('Address:', 'emAddress', 'full')) +
                ROW(IT('Contact#:', 'emContact', 'full')) +
            '</div>' +
            '<div class="mr-sec">Vital Signs</div>' +
            ROW(IT('Blood Pressure:', 'bp') + IT('Temperature:', 'temp') + IT('Pulse Rate:', 'pulse')) +
            ROW(IT('Height:', 'height') + IT('Weight:', 'weight') + IT('Respiratory Rate:', 'resp')) +
            ROW(IT('Other Physical and/or Medical Observations:', 'obs', 'full')) +
            '<div class="mr-sec">Past Medical History</div>' +
            '<div class="mr-grid3">' +
                '<div>' + CK('Hypertension', 'hx_hypertension') + CK('Asthma', 'hx_asthma') + CK('Hernia', 'hx_hernia') + CK('Goiter', 'hx_goiter') + '</div>' +
                '<div>' + CK('Heart Disease', 'hx_heart') + CK('Diabetes', 'hx_diabetes') + CK('Ulcer', 'hx_ulcer') + CK('COPD', 'hx_copd') + '</div>' +
                '<div>' + CK('Allergies', 'hx_allergies') + CK('Cancer', 'hx_cancer') + CK('Kidney Disease', 'hx_kidney') + CK('Liver Disease', 'hx_liver') + '</div>' +
            '</div>' +
            '<div class="mr-sub">Others:</div>' +
            ROW(IT('Previous Hospitalization:', 'prevHosp', 'full')) +
            ROW(IT('Previous Operations:', 'prevOps', 'full')) +
            ROW(IT('Previous Trauma:', 'prevTrauma', 'full')) +
            ROW(IT('Medicine Intakes/Vitamins:', 'meds', 'full')) +
            '<div class="mr-sub">History of:</div>' +
            '<div class="mr-indent mr-row" style="align-items:baseline">' + CK('Smoking', 'smoking', true) + CK('Alcoholism', 'alcohol', true) + IT('Sports:', 'sports') + '</div>' +
            '<div class="mr-foot2"><div class="mr-it" style="max-width:300px"><label>DATE:</label>' + F('recDate') + '</div><div class="mr-sigline">Signature</div></div>' +
            '<div class="mr-priv">' + PRIV + '</div>' +
            '<div class="mr-code">SLSU-JGE-AFA-HSU-1.0.F2<br>Effective: 102025</div><div class="mr-pg">1</div></div>';
    }

    function page2() {
        const TEETH = {"tu": [{"d": "data:image/png;base64,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", "x": 12, "y": 54, "w": 61, "h": 45}, {"d": "data:image/png;base64,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", "x": 59, "y": 54, "w": 70, "h": 45}, {"d": "data:image/png;base64,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", "x": 115, "y": 54, "w": 70, "h": 45}, {"d": "data:image/png;base64,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", "x": 171, "y": 54, "w": 72, "h": 45}, {"d": "data:image/png;base64,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", "x": 229, "y": 54, "w": 74, "h": 45}, {"d": "data:image/png;base64,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", "x": 289, "y": 54, "w": 74, "h": 45}, {"d": "data:image/png;base64,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", "x": 349, "y": 54, "w": 74, "h": 45}, {"d": "data:image/png;base64,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", "x": 409, "y": 54, "w": 74, "h": 45}, {"d": "data:image/png;base64,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", "x": 469, "y": 54, "w": 76, "h": 45}, {"d": "data:image/png;base64,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", "x": 531, "y": 54, "w": 74, "h": 45}, {"d": "data:image/png;base64,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", "x": 591, "y": 54, "w": 74, "h": 45}, {"d": "data:image/png;base64,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", "x": 651, "y": 54, "w": 74, "h": 45}, {"d": "data:image/png;base64,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", "x": 711, "y": 54, "w": 74, "h": 45}, {"d": "data:image/png;base64,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", "x": 771, "y": 54, "w": 74, "h": 45}, {"d": "data:image/png;base64,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", "x": 831, "y": 54, "w": 70, "h": 45}, {"d": "data:image/png;base64,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", "x": 887, "y": 54, "w": 60, "h": 45}], "tl": [{"d": "data:image/png;base64,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", "x": 12, "y": 272, "w": 59, "h": 40}, {"d": "data:image/png;base64,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", "x": 57, "y": 272, "w": 70, "h": 40}, {"d": "data:image/png;base64,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", "x": 113, "y": 272, "w": 71, "h": 40}, {"d": "data:image/png;base64,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", "x": 170, "y": 272, "w": 72, "h": 40}, {"d": "data:image/png;base64,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", "x": 228, "y": 272, "w": 74, "h": 40}, {"d": "data:image/png;base64,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", "x": 288, "y": 272, "w": 75, "h": 40}, {"d": "data:image/png;base64,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", "x": 349, "y": 272, "w": 74, "h": 40}, {"d": "data:image/png;base64,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", "x": 409, "y": 272, "w": 75, "h": 40}, {"d": "data:image/png;base64,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", "x": 470, "y": 272, "w": 76, "h": 40}, {"d": "data:image/png;base64,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", "x": 532, "y": 272, "w": 75, "h": 40}, {"d": "data:image/png;base64,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", "x": 593, "y": 272, "w": 74, "h": 40}, {"d": "data:image/png;base64,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", "x": 653, "y": 272, "w": 74, "h": 40}, {"d": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAN4AAAB4CAQAAAA3K4TPAAAMsElEQVR42u2dfUxdZx3HP9wLg8I61lI6bEcxbPRmxEY2pkyyZlOrnbJsSTOZOFFJpqIhsTEkRGvkD5aQNGYz1fBHYxPrgmvqYpgskjUZWsXQjqWODddZ2OgL6+xaSjtebnm59/oHUF76POc8z3m7l3vP9/zTnsN9znnO9zzP83t/wIcPHz58+PDhw4cPHz58JBPS/Fdg8G7SSCNAgDRiRIEoEZ88r5BHKSG2cheZZJEJTHOdDznPGT5glOiqv89mOw/xACE2L/x9BulkECBCGhDhGu/yGr1cYJRpnzw3EKSYh3mYSu4lXfgXM1zgLU5wkkGuESOb7eziccrIUmh/lo95n5N00EvMJ88pbODzfJkKSriLgMLfT3KZK8AdbOF27buF6eEor/I/f42xh3waGSBCLA7HMC2U+BRYQxYNDMeFtqVjjL0EfSr0kEM9p+JM3OLRw26fEHXiWphwlY5x+jhFWOMXQ+zxiTFHKX0uj6QudpFPEQ1c0vpds0+OEbJpYsxV4vqpIePm/SroZEbj1weVVI6URANTrhLXTaVQnq3mEEOKbVx3f/pci3peC79Q/tsZznKaD5gmh23cy1buMNX/XuVppqRXC/gu3+cehXvH+CZHffKWkMHv+ZbC333CGd6mjz7Ocm3BIhnkdjZTRD655PE5vr5sWlz+yp/hJVOd8kl+yAOmn0GUJn7lT5TzyOW06XR1kWZCStaVWuHvpylXNgvsVdAuD/u0AWTSY/qqjlCsYQEdFbQwQ4WWXeew6TM1+dRl0m0qH+7RXAZECkCUXZpPVstFnz5jdBm+nnM8qt1iUKJ812i3FKDJxKrakcqe01oT6gostFlIVNhag6UnrPHXPjFChnpdjyXqICRpr9HiU9aZjL6XhdJtkiOPEVdMUVskI6/exkd20WRVTjm7S4fB63jeluIxJ2yzzkabRSa2n87UWvvKDV5Fi62WcyTWylpbrVYybiK6BFKFuiz6pa+h1mbbOUw7PvLmdb/TJr6KFEG79BW02m47W6Iq1NtuOc/E4/FsKlDXKO3+AUdG9ZSj0uZylHLZgLw5odciqVAg9aC1OtK+jDxn7CE5hq7iCQ0znqF4m7nGpMxTDrUvmzadMmblGCoOjvTiMp2UJiB1LVKvQb5Dd8hl1kELi3jyNFr7HLhPjBgDkrji+KFa0uERi9YUHSW91sF+FAs9F4sm8FonyEu0kJk0acBPuaMvVnSHiLZXwRiPGow92/dabGbnGhh3hxy9S6nwHmHKHO7Nywb0nXaCvBhhZ+QfRxb6IU8sg+WSSE2nJYBsA0ODFQeUgLwYAwlC3iGJoFLk8H1KJFFfIReUnnMGYRtFTpAXY28CK+bVLozwOaEGFnKhV08YjL1e666ilQvoE3GmrlQivvdrqN4bFC336ULbZsSlfAMjlb3VCfJiTLAjrqvdKYlU9qjS74M8y3EGaFcKIiqSqAru+LwrDCKuw2Q7QV6M7rhRl84xWw7XIjpu0nGOKtMPpV2qfx10RXhrMBh7jc6QF4vb2Dso6dgxxVczvkqdLxdSVkE9z9NloDwv5QcdppGdFJjk3VXRxWmOKSw5Rwyy+4qcIe9YXLy9RdKOqehdVYIpcKXnIUQ1rfRKfHjyY5ZzdNJAqcSJuu/mnaOmzuEtBlEuXVZSM91yiuiizZYa2yl8HYtSXB4dXJYEPagdUUY5zj4qVq1Opas+hhaLs4tFs1xMGDXs9dS5Q5okqea4HBZGlYUWDFROJoPN0rtMfGrT9ElsMAiQH3CGvBgdHtsyO6RhfWpWlRGhEbuVWg5oT5TmR2QhVKKQ64Ixaqwt75Tm2Ub1je6y7yvHQ/J2Sqa0GWWL65DEYz3jOHGLL/owzRLFJmxiYNvvnJNI1lCdh+TJVoJ2R1Rg748DJlPnrDSuM8cZ8o57WJhClm2qnq/TkVDkmXnJ5X4GTQPlsOQ7CFtI3bBqto1IMhDsj934HEOm1paI9JcacQIBjvCmsH5WllIGqhP4ikSD+o2WYU13vpkhzCSTTHCVDznLe7zH+3zIVSaYtVlR7AOT6yelnsl7eFLHJPVHrnEvmwTXHmEDYx6Q95jw7Bkt1+t9GrQNcpw3+IhJIsAM40wyzTSQTjY5rGcTn+IeyvgsBZYMFuaZ6L9kN9uEVx7nd3qW/G6JxFnpyaQ5bFtlLZGKACuPSxymijzlD7uQJ2hjQFNm7VWaBxql/j1NLUsWqVXvAXnVwvm/T0tcaleoZHTAhoc8kzJaFPLh53Pa1VxKeZJ1T1vbq3UhB8eeWUzns6kxrfXXq5VnLsN6mgVKuXVxf0DSQpXeY+2WpgO6jRx6hV9foXIL2SZl4y6y16q3TICQqVLSoxxGKVPW9+s9UqW0EpDbKBbG9OsoCVUSl+piGSnnPSR7DG2lp5Q/lUrJjNGrSv+8kC6r93ObB+JKruDs2xotPGlAzwl+4EIZ4T/zGJPSq3copw/0S0zRxWzVIe+TW0ple4W7hcE3OtGMj0ivTPCMS099kh9Jr00yodjKJK9L6Ncib0xSqXzKdfI2C8+qi8uZ0tUxylOmyrJ1vMgrkiv/Yla5ldeFpf4z2KBDXpiw8OoF18nLFZ69ofz7LOkktZ/XXH3yOt4TntcJXzrDdTuPME9eRDJtvuM6eXYTXOYk52/wnMtPPsZjvH/L2T9wUqONj7kitAHN6ZCXIRRNZnnDdfLEY0y9SP4kV4Xnf20gUjiFc3yNj1dM1C/wPa0WJrgsJC+iQ14O6wTXzjPo+gsYlVgf1PEnwbk3XR938xjk6Zv0nefb/FRTto3Ysx2nLwjs6UKZ76rr3b9ATCDqb9Zo4Wfcz0MrzvybPR6Mu3n8nQd5mi28a3FrDNEbTtPzpIrNY/s86HxIqPDqGQeyV5RN7FKV1RICbUKHgKKBLABsEDplwvzDg4e/smLVWMQ2rTamqOM5rhLjGi/wlCduLKeQKRx5yiihUWii6vOkzFmWsADqlIUiByXsWoNbwnQKR55yvuwxSQqxN4G3aRJ3ThmpgDxh9M64etSszMDq1Vfc6EJVsbWCPULT9JD6qu2IP9cGyoQ+sksaTqG1ClmocYd6E474lGyhK06+xHijTBJeUW+PPG+/+zrJB5TsGyodkIRBFNsjr8bTThRI3KkjSV0XNiDJEBzRaUS0N4HX6E+IdBdvUedE3NCtGTCFCdORGAeTlLoiSVE5zUIiiSCkpxnsmpCMSkOuNHJM0ySZGNX/txgUF21IOvK6pSGKQevkdcdxy9p6g1TGmqSiTt5T7Qowy80yBXHsUppBwm/Ek9htb1AtzY23kdYcjXvdv0rDjIO2JNiRoNAgMy9iJaUukSqO1xoG0B5Z0/uQp1NjUD7OovfUe3OYEZpN9nLdsiaJK6GRXsOMinZrDceY9iShRBXHTOowtMV1ZdbHTnoM55N5q4rFbIr9DpfltYt80/2QzzlarNhNBGlWKCQy41kCuSc6X79ptl3TGrB7VnJcIZ9vLJmoA8hW6PYELaxP2B5UKaZijjhevzchDEi9Cl3vdyRp0nnsNV3l5o/RhNzRwgFkKeyDPD/+EkuAKVRIsl5UyktIYtRK63StlEC7E2TdKOCgaYr1khU5SJJjl8lWgksEHor76rFLcZ1LZlfXKpQpv5KL7I9bld4A1Qa22dUf2j5SCM+aFhVeTmGr59t75NJoaPoSVQFNIZQa7th8qxTX4mHGQpDddBrU0R1jeCFOLMqB5F/pxKp7u7IwECPGf2n2yBKaQUg68kbYR4h8Kmliv26FleRCPm1apaSi9FBHsQfOpAzqb3FojVOfOjszq9ouhjToixHjMu1UuZQ2szQJrl9lVhhx3z+69mbgQV5imm3cqWFs28E3+BLpjDJusS5LGtkUUs6DfJocIrCQxb/U2ixf4P6Ff0c4QjX/cftVrF3vdIif8B3tOpsTDHKaPt7iI6aIEIRlGeDBhWkuCGRxJ5u4j/vZzmbWcfvNvP0wp+jkrwyuyKjP4Of8mI1c4ii/dbGISFKQB1BBK1+09MsoE0wyS5DAskoYgYWZKECA28gyqFUR5i+8SM+yUhxBKqngBq95kMmfJMikhuNaUqhzx3UOUe6LJHaRR7PhttbuHR3J6hfwFkW0STatd/MYSJEcXg+wg1YtS4z9rTH2JUFAYkKhnOfpV6w6becYcXRHdR/LdLsq2h3dAGp1EFRT/Ou9JPegD/EUX+UzyrvImmOGs5zgFf6WCNVeUmHGTuNO7qaEEorYyEY2sZmNZCn1PcYNJrnCRwzzDv/kDOOJ1LFUQ4B13EUJJWwld0ENny+RuKiSzy38f45JLjHIBS5xTbUSnw8fPnz48OHDhw8fPnzEGf8HCo2KAMMsbQIAAAAASUVORK5CYII=", "x": 713, "y": 272, "w": 74, "h": 40}, {"d": "data:image/png;base64,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", "x": 773, "y": 272, "w": 72, "h": 40}, {"d": "data:image/png;base64,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", "x": 831, "y": 272, "w": 70, "h": 40}, {"d": "data:image/png;base64,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", "x": 887, "y": 272, "w": 59, "h": 40}], "du": [{"d": "data:image/png;base64,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", "x": 161, "y": 122, "w": 68, "h": 43}, {"d": "data:image/png;base64,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", "x": 215, "y": 122, "w": 78, "h": 43}, {"d": "data:image/png;base64,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", "x": 279, "y": 122, "w": 77, "h": 43}, {"d": "data:image/png;base64,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", "x": 342, "y": 122, "w": 77, "h": 43}, {"d": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAOoAAACBCAQAAABkru5cAAAJkUlEQVR42u2dT0wc5xXAf3ih60KxS/AmFGvjhHaDRbs2LXJXQkHegyUqkaxaDkhI5YDEgQMHDpE4cKASByQOeyASqixRiQMNhz0goWqVlYKEhMIBiRZnC8JxQ0kINiGYYjAYzLI92ESxd2Z2vtk/zC7vN7fV7uw38+Z733vve+8NCIIgCIIgCIIgCIIgCIIgCIIgCIIgCIIgCIIgCIIgCIJgdwpsP0IHxZRQiosK3qaKt7lCKRf5CRAjxjP+x0NW2GCLx3zPIx5xKEK1I4Vc5TpeqnBzlTIucYnCpL+Kc8w2/+ZffME9vmJbhHrWOCnjDdy4qaGWX/ImTsvjO2GPdRaYYYYveSpCzSZFvMNveZ/f8C5v4eRCBv7jiP9ynyhzfMEKx7LmZpJrdBJhi3jWji3CdHBNZmomKOc2LbxP5Rn8f5x1/skMn3OPHRFqOvDQwp95LyNqVn3dXWGaT/mMLVGbVqlhOKvK1uyxzAC1Ih5VigkQYtOGAj09dgjTlS+rbWbVbyE3+SN/4CZFKZ/rGU/Y5Dse8/QHF8XJRUq4xM8px8VP07DeLvIJIZZFqHqz8wPa8XMxpVVvj02+ZoX7RFnhIU+IacScLnIFDz5uc5MrKa/XTxjlY74Uob7qe97iQxq5gcPSbDnkOxZZYpEHPOQxT0yH/Yqo5F2uc4Mb/JrLKVzd93zCX1kUocI1/kSA31Oi/MvHRPmcRf7DV2ynJXZbwC/w0kgD1/mZxXN8y9/5mG/OrzHkZoB1CyZKjHl6qU3DqquNEx9BljmxaEKt05ED2x4ZwEuQNQvifMAgfkqzEu4IMMaaJdGeEMZ3vgTqZ0H5Nu0ySSsVZzDaCpq5yxIx5TGvMUDleRBoAb08V7w5e4yc+XN/mTYm2VEW7Cpt+S7SaiKKaixKH16bjN5BNR2MKS4bx4TyWRV3s6ewes7SZVvlVUU3EXYVRPuAznw0njw8MH0LorRnzLZN30LiU4xMj1OWb0J1MW3KIArTlkMX76FfwYhapjn/3Bgjq/eAceotRZTs8MB2MMOxScE25ZdYr7Gsc6nT3Mnxa3PQzLxJ828gv8TazGGCwxKmJaUgvn0ooZVZU4INU51rF1dLAK+mtedg5EdPbIRGE2mcuYabXuZNKONg7lxSGWPscsAcAR0VPM4uRyzndYS0mBaGmWCaFQOxDufKU7rwwzwc1/EzndTio/wcxM8u4MRFp8G2xagtcq8MaXolvLBGt4UttXyknDGD1dXWNCb4awv5H/k0bRvri7XLvsMuZFVjwJP5F0WxSBETugGXKrsOukdzwPO4RJ4vKSCo66Xb0gfw6ERBx89nDoAuIR2xdthxsCM6ob8GkeMreHWEOmO/oVbrbEMNihQTWNNZV20X9e7UHOh+VnKJco2gTjz4TG0PLWf5Pc1vRtgVGSYwxnNNI8p2QtUOx8+KBDVYYkHz81K7CVWbHZGgBoc8smOQIRGn5jffStt/FlPECQd5UahfzK80P9+320yNaX7zdhr+rZIJ9thjmx2eEqWb4hwXqo/rGp/G7VfG3Kdp0T1PeSemTGPjajrHy30ndFwa2yXaNeoUJ4ykdNZSnVS1bYaptYFfV4KHOmp0Fh89zRPTCafacJ2Y04mU9Fg+pzNJ4vcOkwTO5PmuoIURlth9+Sjv0G/afNQL6vfZUak06zyBJ5ajmk0mSpNOmMKfxZnppZ0RzVyGUVOao1+3sY9N92kiuje+21JQv9lkLu0BIfwZ3jZw0cQw82waZPgOJT3LgO5ve7ApfsOKzV7lEopypZqVtQzsc5Ryhz7CrJtK1n5uWDFTors/E2fOztnOy0lue5eiO9KsWB83pmSyGFNDL/NK5Ysxg4XAo2tzxInbO+PZx1GSC1/gIzwKZ2xLesbX3Z3US6rcdDFpoXvThM75iuhgw+B3Ibv7YH5TpQfrDOEzudffwKzJcoYXx2FKGT9NFsqhT9N2EuPfDvyMJan0m7J9IRjQZvImHBEmYCrX0EGACdY4MF2o32tx7D2Wuzwk2r4OmggnVd8LuZJtOWT6VjwnyhB3TMSdHLipp5lepk3c+CNLDkKHhQYAcTYYSSiKdtHJlImFYyOXmge0Kq5IMVYYIWByR9FNMGnxsnokq1PJKNtlnmECCZmSDlqZMznfo2fSwSIFvJZa6awwQI2p89drpqP+uNOC2g3zmOzmcMwy43Th1bSz60xV4J6adDmY5u5mwtIKtUWIZhMK2W3g98XZVBRqu4kQR5gOanTNu2sMKzQ/COVulV8lQwoX+nq/pIGkFvIdXX0QSaN5t8OEYW27hx6iCtc2RR05jo8py81XD5ikyTCgUKXjgviV9cq6zowPGtSRFtFqGFTQCpkG8yMP2kkLEQ4sCvaYKP14dXdBLnP3NT82xkcWRtmYINZV+g26+bpoZ1ZxgVmgkbzCSYDxFJoyrxLUdVQ8BF/GbHYJmTS1tM4y/Up3wULdWd2v3IBvg2HL47I91QwmsVuNBdutm3NXQTvd1Kc0ujIGiLLEEG5ddT+qGLiMs8dd+xZApYsKOpiyaEDFWaKXmgyuS+W6JlED40rtsF7M0CHb9GvLijquZ5Cocp/C07Y1nVmsEyuj27DIX1ucQWrPZ3FYCU2MsmopQDeZpZcStCgvGPvcVdqLylOF7KePKeUenRt0Z7ik2U9EycI9YYWh3PdD00khDQwrdDA8TWbJxKplvtXVqTkUoTPXornZw0WvosLbpz/NkdRapRa2R4Sol+Lq5Aq5k9mE3mjGplN7mkqMGhhnX+GVQ3fxiUDNU4yfMYUbvMtoSqrYQ7+ClbtBkDoRp9WZoxJf3SFoKXbjoc8wkyixl0WViCY1x6dHKTC3SYguvKayf0pepoFuKO37tsoMTQ9NinZxnD0WGKIFLxWUUoyTQhw4cFKCCy9tTCgo99NNPX8+3tyze0Zd/I0PLPzuKZtss88RhxwDJZRSRoWyxfyMvzBIXOZXur3HTguvKErPEZY3pmaSesYs789aOTYZFrMoG/hNJYumfhwxKnHc7PFi230jgwLdZfS8vbHNLnjoI2ppn0c/LL/MIL4cffNGHnmyrUQsb7y/nknUdf7a2drV7S7iOj4aqKXK0itt46zzGf/g0/PY/8n+sRQH1dRxi9/xDm8axJXi7PMtq3zDfaLcO8/vJ86dAFkhV7nJLap4AyfHxAAHhcAx+3zNfRZY5LGEE8jBqGcBDhycEAcKuACccKLT0EsQBEEQBEEQBEEQBEEQBEEQBEEQBEEQBEEQBEEQBEEQBMGm/B+QszgnWfAc+AAAAABJRU5ErkJggg==", "x": 405, "y": 122, "w": 78, "h": 43}, {"d": "data:image/png;base64,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", "x": 469, "y": 122, "w": 79, "h": 43}, {"d": "data:image/png;base64,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", "x": 534, "y": 122, "w": 79, "h": 43}, {"d": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAPAAAACBCAQAAABUIv99AAAMyklEQVR42u2dXUwc1xXHf8tiLzG1McHULim2TEpskZKSOBEqiRWqkPKAxAOqrJKKB0s8WJUfiILKAw9ORSUqKqHIqqiEZCk8uEIVVaioQkUtJySkNKUlcULj4NCkJA6J7WCKzTfMTh8IMR/zcWZ2dnYW7n/eFnb2zj1z7znnfz4uKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCj4iJCagnXIopBcIiwyyyJh0skglWmu8T5zSsDJ/Jof5WnKeIxc0gihoxElhRTCgM4cH9PPJd5iUk1Wsq3Zarq5hS66NK7SRJ6atuTAXuoZFYp2/XWDBtLV9AUbx2hkxIVw164RTpOhpjF4OEItnUzEINp71zL9VJKiJjUoyOc8NzwR7b0rSjcFamoTjRRO0Oq5cNeuSVqUkBOFVEq5yF3H63KZZaKOvnOLNgqVH+wvinmRHzvUkv/lDd7hBnCYZyhll4PvzvIbfs2iWld+oJROhyv3Bp1UcWjdPXZRQptDk2yIU4o+ii+yaXKkb5cZpN6SvsjlLEMO7jhOpRJDvFDBJw5EodFPFRHBfSOcZdKBFm9UovAehXSy4sAsauekSLhryKPFwYbdEQy+K5PwthBuET1iu/cTmjnhWlOW0sOy6HemqE38xFylhzoyk1y8pxgTCneaZnJi/r1KMYt9IdEm1+owRjmTtAR6Pg3C6b5Bu2eURBb1Qm1/ObHxp/XWZA9lSWXiH6KRK8ygCTblJo7FYQQn6RMoBo3mxM3rZuuvK2nindWMi1bQDM0bvFuvqaIzTAtG0enInIubgFc3shZyk8Be1kSbcosPBOIx2pmzHcswxcEQ8OpK7kvMcAQoZ1jkiQ5Q7uPGuJfzgleuLy6KwoWAdXSWaCI1YMIN0SRaudepTYD7Vy0gR6epCIqAdXQGqQyQ2VXIZVG2RZ0HjpA7FNAnoEYb/Fw4Ej1WnygDYd3KrRak2ETp5kQA3LZeAQVS79cOI3PX+/3XHRvYtk7BGJeoD8xu0yYYb48/9JKcua1PEN8lYY2i9HMyUNbCaUFEa9QPfdxKj9CfXI29+GsilAk2Zo2OQPruqTQwL3CefHgxc2hmSbyWLzjKcogF9QKL+RZVAfbXTwoWj0aDH0MppkvgrK95c9k+0JAXBRtzF0cCT6d2CF5Tn54jlTK6RRHVu9TEcRwRzgsY3o44EpDeIpsOwcva5tfOWCUMvZ2Jm83cL5iOBpILDYJX9rJfZmwW5wXreImiOPx2ieD1uko5yYcyQXhxlFK/hpMj0IETHnvHYVoFPFUZyYoUwfPp9PnnE9TZbiujZHloAfQIjJFkr+uTbNWTlPi3rdhtmE2+ifcuDdsi4/gUU4IYto98wxlLfXzdI4UwbPPA9b553/HHHtoE67iTNL8GVGVJg+R6IN5PbBLJi9luqBGYsQP+RZ1KLdJSYnWXdtms3q6k8Xed+gtXBEEe38rMC1g0tfpiE+/l4KW5+IYK2/4g03FxRk1sajNnyT3NFraMnbYnPA4df+Rz1TZ27NMqTmHAcADzMXim5yzSDGrYGciwJTJ7/RpKsWE4QqPa9aOZGW9t26SgRq4AByxF3O7XQLoNeWG3FTj1pgHJnYewTdaKT1VOxiKpd/lIxtbzeXYmUrhgyRkm0NByF9kpNazRO8dOxilTX0V35yw67fJkXCUw6/Jhtrrxd/jVjhbwHyzsmWfj//OZhsz0squGBdmGqXRDKHSaUpdxx1kTNtqNH1xsuBkNKPmSaWKbjMc7USrXpH1Bt0sOJ6pWsOnLP2MwN3Nu8i9TqOGEkNK+wHcMP/+zq4eIGIb+divpAm/zmsGnu9ytYB2dK4IAc5u31h2lhrmGY0q6ADQZpkhVuhWwzpRla4OQRaqJW//smGF8ai5w9YyJQZ1XlPCam7Sf35r+Tx6v8rzpX190+Qhf8pnBp/fxlJKuKVbcr2CdRcOSy1KbHhSxkIrtJhFQtYbhvGFWS0ksAh7ZEprLtK1ZH4opnFdmUrnTtOPFe8gww8VlWHat0Dt7k3DrbNPtFmNM7wyZFEtrjnKDQ1TSykVat1FqQIfJ3hZyJ+CJTcGCHJoFeX+aBw03K03ufUV8h7wNaS9DVLEn6cVbbTIrLms5Tm9a+FWiFifuY8AbfWGz8kpZ5UK+wVY2KGwuGlyY1SN60MItXdhsc9qzdrldpmkq9jUTaSav4gpD1JOX8BzqDHJcJL7Wms5IjM+TyXlRA22NdvZ6NglFpjkdM7Zv7Fmb8rQJLlKRkC37EI2MEkVnnjZHXkGJ6XzEmARRLqhFX127XpdbN1pUPlmnuvcIxhtl0OcO7Huo3RQn6xarjHzTjtTTsVSBRTgrao+r0RWXVix9FslmVqLpFjee6OOUDzVNGZTQyLABb3BZtFVnWPgtMSTsjIuEu0xH3Nob5ltQKYMWW2yto7MUluilOi71tylUcJHrMRJChVw3/XZ3LMMzr3AbY4IZlpimL86lUB2WrdjMjawBx2ccXeW0xzZ2Pl2COqM5GzVRbhggXFMzed4L+BbnKCafIoopiHvZV5qla9ZtaqZIWiNsna5haj0yvfbSKDz+Q7Ocw1rL2q8YzSvdJLPRX0Y43TK/f9xC95fQwZiDkxrWIjPNMZ46WESHuGmNzogFrWFdeHcl1pfReFv0v9djnqWQpiwtgCwq6bDY5MyauLh3KZuFXsea/i83MW/bbZuqxtx9JxjiXSUuNct2EUW2Zkq7g4NvdHRXLl+O+AABu05exbZnMa14wa9v1XiJKxopsKm1a7X1aMOU0y8+fWXYIWUjo3E3990uMDTNegTf9YIO3pKamdjzcAtstGmXwAZO3UI1mPcNkK+QEE0Oj6tcpJ8aw+VSIzgEIOpVscr6DaExAD0wKmyaKg6L6mUzOU2vrRF0S+yApItpFZ0ok/TSQKmheZRDu8itOuXVhN5jW4JSR59rq5s6hVZCGqct13KbmOsbFtrmPVRzxFTJZYvaGup0eymLta0vSP1rIgzaWpfSHOFM0xUzLm4B1SLsqV1m41hdFXnMHvfw07lFS+A62KTZUhhzDvrQl9O3hZDtE1OvObYaU2OAGku+eQ+NosN3hrzvdJcb2PZEZbZ5JXdpEbPLe6mmk1EmGKaZfEfum7WP22ajMNJpFvnoIwFrae4DigRE4IijJiUZ5Djmok9aiGfClqXPF/TSWbUr9rIDkWurjXWmqYsrsZpiUtURpdtmJ4hQJ8hu0xmjZiefGt4sSkRojWNL7ciW1KIVOmxj47ITSvv860sZXDQIzxatjtsI9myo2h22FUqa6LzwpUAwD4FArTDnpDdu/ZZDVNDGRVpsfyFMIU22vaGj9G7zJm8OkW9Lf9w7SrYxgSc5lNDKEFOWbNVdWhN2NluAERG0KL93ilJlQrKjC7nAhA1bNezn6WzJ1G5M4xV0nhAUiYfIIocDwB0WfRxhOscp5DB7TUM2N3mRnzOuBGyGfl7iPxw26TUAEGWOO9xhD9/nacop4UFSSWM/+9jNAroHo8gkl3RmN9wrRDoZhJhngQyyDIynT6nnZ/yNZT8nLDltuDRe4BfsM1gfVxhhkjRyOMphsogQZZ6vmGc3aczyLr9nwGXbJ4Aj/JTneJAIM/TzEv3oQIiD3E8YDcjiB1RSuokf1OigkS/9n6rkNdILeIGfbBLy57zKJa6jcYB8HqWAw6SzmxRSvnnSBa7xT97nIz7lU+4IVnSIfRzlIR6lmCf41rq/fMg5/so8BznKPjRWiJDDD3mGB9b91xf08jJvJmaaktsLC/Mjaqn4ZtJnucQf+Rc3WGI3BznOU5wgn4MmOlFnmn/zGu/wOXMb7hsmQia5FPAE3yPTVJW9x+94jzD7CAMZPMTjPEb21/N6kz/xMn8nmrgpSu5qeo1LXKKY5ylnH1EmmWSa29xGByb5mNukcdjU5Amxnyd5Elhmad3nKYRIJSx4/R/hLK/wPreZI0wGWRwgDR2d//EmL/F6oqdoO7RLeJvneIRCspjkA8aY/uYvi6TzMIcF99jlOqb2MBozfMEtIEwGM3wAXOMN/uGrBb+NBQxR3uVdQ8/5cU7EPcvsu6Rykwk0bvIh8ywEQbDbS8BmWGEBLe6/8jFvMYYGLKzbPQJjpmxnRLnGCjncHzdjcoG/8Ete98S7VnCJDKroFMVlnVzLXOZMAPoIKHy9U5VzWZTRKLvGOLXDTpVICv6rjHbGYxBzlGlGuMhpH05AV0SHaxziBE9TRD4HSbOdAZ27TDDGRwzxNp/5yyQrAcfy5Ac5znHyyOMBcsn6usHx6kpdQWOerxjldQa5xlTyPqZCiPvYz7c5QIQwGrMsMYfGLFNMJ5JmVFBQUFBQUFBQUFBQUFBQUFBQUFBQUEgG/B8xx06T4mjlCQAAAABJRU5ErkJggg==", "x": 599, "y": 122, "w": 80, "h": 43}, {"d": "data:image/png;base64,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", "x": 665, "y": 122, "w": 80, "h": 43}, {"d": "data:image/png;base64,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", "x": 731, "y": 122, "w": 70, "h": 43}], "dl": [{"d": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAMYAAAB+CAQAAADVC6bOAAANOklEQVR42u2df0xV5xnHP/cHXgQB4SrgpQilAyurmR21rtZuNmNlGRnLzGaKmUlNusVmpiOZjUvM1qb+0cy1Lms6t3X95TJS26px7aytbTpddZjSqrRaVrQgFqmCIMgP773cc+7+4MIu8J4f995z7r3A+Z5A4Jz3nPd53+c97/s87/Pj2ChHYoQRvMiAnVHIyMihvwMEkcd/IBj6CYcNEYKCc7ZJ/9mxheodvWJHDbJCmYlPdWLHjh0HIIXaEgijSZ5Am20KxfIU6sNpC/9bnlCvHRvOsP/swtaMUjPa287wMjZSCSIhEyQYRliQ6Y9kaItNxxC1YcGCBQsWLFiwYMGCBQsWLFiwYMGCBQsWLFiwYMFCpLDN2HZlkksmTiAAOJmDAycB+rjMleS0ZMaHGanksIhbKMVNKgG8SCH7dIAATrxc4Txn6ZlkU9bbBgdzmEseN1OImyzceCgkh7nYIWRtdmDHRhAffZzjNBfxkkoqXjpp5Qt6E88gs5iRQTHLKWMppeSTQaqOmgJcZ5Bh/PTQRjOnOcdV/BDq0iAyNpzMo5ASPBTgoZh8ckjFSQqOGOiV6aWTNk5xnEb6ZwozsrmTalZTRnqMTwrSzUWuQWiy8eHDSSYFFDLXtB4J8inPsYfL05sZ+aziB9xJCXOm/Zpzgff4B8fpmX6kl7Cd8yF3n5l0yDSzhYXThxFZbKdnxrEh/GijLuYpNw5YyFaaZzQjxo4zbCMreRnhoR5pVjBi7LjBluRkxT10zipGjB3Pm6mZ2aK655c8HqVwGcRLL33cABzMIYUccjScnSPRFgYZYIgh+uilFy+E1MpUcriJhSwgDQdBJMBJShR1/I0HzFIPI2dGOQcpjqDzB+jmEhdopZUW2ulhZBIFedzJXSHlMJ000pmLU5OyAL1000M3/fTTyUU+5wJ9SKp32UnBgYQEuMijgJtYTBFfoRyPzt74Jz/GmwzMWEgL83WWvcpxjtBAO1fHHfLV4MRFGvPJIY8SyriVW8glVcDgVg5zhCa6GND1ZD39cDP38RNW6eqRd/ieQfXGwIwijuh6K/po5E0O0qoxTtXhws0iivCQhTM02TjooZkGuk3aQ/s267mPBZol/8rPErtor2VEY3nroZ4NlEz7veBydtKt0dZNiSRwjYaGLbOHZTNoE34J76m2d4TqRJG2Dp8qaY1UzzjbSAobaVNps597EkHW06qM2MMSZi7W0a7Y8n6y403OVtXRUcdMRz4Niu0/kDysaGYlswHp7FHsg0fjR8azKqzYMaviNNcpypK18SFggwor6phtWKfQE90xGXx1ogK/Iiu2MhtRr9AbG82uuIR+RY1iE7MTLo4Je6TdbGvgUYsVQsmqXWFr3USUKk5QTzC7sVHYKwEzFcDdCqxoYrbDqTB915tVYaXC0j1IORZ2KmyS2s2ozEWjwmqx1uIEkM8VYf+YogBvTLyumeTYINzBNmURF78XnfFQbaYJbBwW9NAVioyuaKGCA85GiwdhqImPKrwlvrLCNEWaUMRpIsPIStI5I3RwzI/gGbNjOmsS9JNEZSyPnCyOrRMKry/pdpCv4QBH2csm3DOcGW8Le/M+I1++k8JJSp8lr2SCEeYGe6gkO5SbM8Xw98WO29hJITQz5OPWpTHcQ8BopXiiRWItewU2ij5ydPjQlXKM3EnnZFpoYoh0sgjQzJs00R9VqNjkQfNd1rOMId7mDwaFtbj5BtWsYAF+PuHPvKtRPovjfHXK2RvkRO/gNrHrD/MdQZl9/EjHcz7gDs1SQ1ygk156aecM5+lkIGKKl7GOapaN54+9wFO8wHDE7c7ETT7ZpOPBQxm3sTjM3fMGv+FJjWfs4iHB2ds5bcTYyBZKCDJVUW8RaB1+OmhgN3Ws0eVcuUYoXgTp5wlKdUxsHtZQx7M0cAWfhuuRpGnBqxU+oc6Y+bJKwQknTfPOTTFHLUm0U0+titTmZKuKsStID7upZTn5pOEaP1JwkY6HlWxiL+0RBTE0aYTIrGTQWBeF8NFYx+8FJR7RfF1X8m+DovgCtHKCU7RyFR9+YIgBAmRSwWbu1bxfop+r9IY5lUo4cJGNm6yILfZ+budTletFfDBllYSL3EVn7F2xTcDnazq8BBtNjaqTxpODx/sY1Jj60oVRWyPUGKVnTOVzq+Z7cQfmwYY9lLo+/mjmour1Yb4QTqdl5jFjSKNEgr2xTUQ9PtXrQc4oCL0GMCMgFEbVkcHqGcqKC7yoWeaEwsoXJZwaHZ+FTVXhSxcEs0xW/M7wIV2MRgotZanmHcmA6/xCR9KKZuFZrxHMEMkAxWSqEtXF5yxWvNrH67zIR+OqnY15lHEvq1lKAWlJ5pE4Ouh8XOYdnuIzHXd0EzSyDeHMaBXuN61Q3RiQeVFB5Gzh1+yf9MoGGeAjPuJJwMkiVlDJ7XjIYa6he1faXSRznfM08DFdDBPAzwBeJIbpi2BkjxjLDNuE3ZkuwYL+CrWqE5WDTwXywz4e0hnq5SKfxRRTTgWlLGBuDNKTn1aaaMbLfDwU4yYFkPHjx8cwEgF89NNFC6f4b8xhkvlcEvTYr/ht7Myw0SsInpT4Jv9RfcYS9k3YMvuSx3k2iu3AFNzk4CabrJDu62QIL1msYL3GSuPlXQ7SSCt940MnFRdOxr5xFBx3XJYNG8qltAjeyod5xoiHi+MQ9uq4cw07OMAb7KRywtRnFCqEWw9jDmQ74h+0Emq1SOkzyIdmh7CxvqSQfzYoJpGoTRhNDwroGTDKZadSYSOtlmSAeGd4e5JR1IHHmIe7FNydz+jYuTUfKYJpVEqgedch7K1jxk3T1Qrb1Mnh7rxF4KuUOBQJk9nE4Mo2WTA7KDS0wxZWJQEzpoqiAwmkpoI8wdlTZksIQYIcTQJm7BWEqSQOzwv7abmRVdgU3HoNriYKLBek3zPJ91vXJCXqp+FYJE+7QGn5nULZvyd4Ga8mR7CdkyiXufsFVj44a3TyI4diCNnRBG7tpXBI6GycGIpsdAh7aEu8XsHESlWFQtnlswRRs1bBU99jRmW1ijbpRK0cVUJL+OGE0OJWCLM0LaGkUorUawlK25JM+rc4+VGDKbtyIRFXUvRQSkReKfHgSERgm1I2FVNp2aTiMBbvyWqZwiZh/CfNZQqD9IrZct1OFX+m7ea9lALZ5ZCQis/inoW5QjFvhOkJPOwqia+CHIoqL2w0qEsS2W6lolWlIR462BLFkTBKQgXxoGFYWPv5OOfvL+eaolBTGh8SCjXyWDaavoW4V6Hm+GYm36SSu3RDPOfJoEYey20mrh8lip628ZTpdqm0/2RyCHPhJpUaXCbUXKqo78iUxKn1+byh0vIOCuMt0D2oI7JhmANUGibgOanisKr/eU1cWr5RYcUaiwNOiKWxVqcL/2FqYpay0qjhkGYgwNGIAqKjnSS7VSfoEhKEzTrjfiQaqYtyyyyVNTzNSdUYpXA9o85khlSquAgZnvPZFuE4eU5H/NAoLvIC+2lRdatPYSGLWEAuWbgpYym3RvxdjiCX+Rev8D7XTBFeHlPIZf0xNUbbGW0Rl/8LP9VZ9hKvc4QWhvAjk0EuheSRjpMAAebhppgl5OIyxCbRwn720sowAeQIPzdiI40cMpiDnyGG8eNlBEghmwrW88MpQ+RDvhVxhK3hzBhdPR7TEZ0j8wFvcYqrQAY5lFBOGQXMD3W+GUah63TSh59humihkyEcpOIi3MF79EuvY8ZRF/PIxUMeblKRuMwnnOI0bfQRwI6dTFbzc+6e0LKXeFgzciUqmSVyvMzLrOQRvq8SVnmW13iLVgawk0kBuRRQREkoY4JZyCQzxics4jaK6ecSASRAYpAO2lnBHCDIaXbxilk+KdEKopd4lROUcZPg2lX+yDb20cEwAUYYZJAUsnCTS0bSZ4l2UMBlPqEbPxISI8ikMQ+ZZrbzMI34zas6erTyMidJp2DCG3KRv/DCJO9sP4P4kElnYZTeExLHOIpN6Klk/PZoHmf5HG9IWO/nHO/zKn+iIaYv5ZgyTf0fw+xnPw7KuZuvswgnvTTwHm1TSl7jBJe4go+qCNkh08xrPBP6ymo1z0Tw+a3o9+PKJgywa6ZIaqbCRhpZqpsi6VSyR6cOMarTv0HtpNw5+dSbHhfuZ3PczAMJhJ1V1DOg0Rk+2jjENpYLp1EbVRxQ3aSI9dg947NljaOcRznJjUl5EIbpoIFdrKNE10Tmoordhn9H008zm+Now4xZz4gdLspYTglZgA8v/fTwJa1c0giDn4oiHuB+lhjQDpk2jrKfI2ZoEMnMDGORzSqq+BqLWUAqDt1tkhhiiAG66eAcxzhp0tf/ZhUzwlekueTgoYBc3KSG9O3AuO7txAl46eECX9BlSFY4CxYsWLBgwYIFCxYsWLBgwYIFCxYsWLBgwYIFCxYszHLYcEHID0lfeVsoCXAQCSlCb28LqnBSDKFPhuiBAwd2HIDECAP48REIWZKDCWaNbfy3PfR77NzYX8ouODIyo9nQZcU0xPbxp4/VZ8eOD59R7f4fK1Y00fN1qvoAAAAASUVORK5CYII=", "x": 161, "y": 210, "w": 66, "h": 42}, {"d": "data:image/png;base64,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", "x": 213, "y": 210, "w": 79, "h": 42}, {"d": "data:image/png;base64,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", "x": 278, "y": 210, "w": 77, "h": 42}, {"d": "data:image/png;base64,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", "x": 341, "y": 210, "w": 78, "h": 42}, {"d": "data:image/png;base64,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", "x": 405, "y": 210, "w": 78, "h": 42}, {"d": "data:image/png;base64,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", "x": 469, "y": 210, "w": 79, "h": 42}, {"d": "data:image/png;base64,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", "x": 534, "y": 210, "w": 79, "h": 42}, {"d": "data:image/png;base64,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", "x": 599, "y": 210, "w": 80, "h": 42}, {"d": "data:image/png;base64,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", "x": 665, "y": 210, "w": 80, "h": 42}, {"d": "data:image/png;base64,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", "x": 731, "y": 210, "w": 70, "h": 42}]};
        const dcChart = function () {
            const W = 960, H = 375;
            const T = [8.5, 65.5, 122, 178.5, 236.5, 296, 356, 416, 476.5, 537.5, 598, 658, 718.5, 778.5, 837.5, 894.5, 951];
            const B = [8, 64, 120.5, 177, 235, 295, 355.5, 416, 477, 539, 599.5, 660, 720, 780, 838, 894, 950];
            const DU = [158, 222, 286, 349, 412.5, 476.5, 541, 606, 671.5, 737.5, 803.5];
            const DN = [158, 220.5, 285, 348.5, 412, 476.5, 541, 606, 671.5, 737.5, 803.5];
            const NUM = [8, 7, 6, 5, 4, 3, 2, 1, 1, 2, 3, 4, 5, 6, 7, 8];
            const px = (v, t) => (v / t * 100).toFixed(3) + '%';
            const bx = (x1, y1, x2, y2) => 'left:' + px(x1, W) + ';top:' + px(y1, H) + ';width:' + px(x2 - x1, W) + ';height:' + px(y2 - y1, H);
            let h = '';
            const HL = (y, x1, x2) => { h += '<i class="l h" style="left:' + px(x1, W) + ';top:' + px(y, H) + ';width:' + px(x2 - x1, W) + '"></i>'; };
            const VL = (x, y1, y2) => { h += '<i class="v l" style="left:' + px(x, W) + ';top:' + px(y1, H) + ';height:' + px(y2 - y1, H) + '"></i>'; };
            const C = (k, x1, y1, x2, y2, img) => { h += '<div class="c" contenteditable="true" data-k="' + k + '" style="' + bx(x1, y1, x2, y2) + (img ? ';background-image:url(' + img + ')' : '') + '"></div>'; };
            const X = (t, x1, y1, x2, y2, c) => { h += '<div class="t ' + c + '" style="' + bx(x1, y1, x2, y2) + '">' + t + '</div>'; };

            // ---- lines ----
            [7, 30, 52, 100.5].forEach(y => HL(y, T[0], T[16]));
            VL(T[0], 7, 100.5); VL(T[16], 7, 100.5);
            for (let i = 1; i < 16; i++) VL(T[i], 7, 52);

            VL(66.5, 100.5, 166); HL(166, 66.5, 158);
            VL(894.5, 100.5, 166); HL(166, 803.5, 894.5);
            VL(158, 100.5, 269); VL(803.5, 100.5, 269);
            HL(120, 158, 803.5);
            for (let i = 1; i < 10; i++) VL(DU[i], 100.5, 120);

            [166, 187.5, 208].forEach(y => { HL(y, 158, 385); HL(y, 569, 803.5); });
            VL(385, 166, 208); VL(569, 166, 208);
            [215, 271.5, 328, 627, 686.5, 745.5].forEach(x => VL(x, 166, 208));
            HL(176.5, 385, 569); HL(198, 385, 569); VL(476.5, 176.5, 198);

            VL(66.5, 207.5, 269); HL(207.5, 66.5, 158);
            VL(894.5, 207.5, 269); HL(207.5, 803.5, 894.5);
            HL(253, 158, 803.5);
            for (let i = 1; i < 10; i++) VL(DN[i], 253, 269);

            [269, 313, 336.5, 360].forEach(y => HL(y, B[0], B[16]));
            VL(B[0], 269, 360); VL(B[16], 269, 360);
            for (let i = 1; i < 16; i++) VL(B[i], 313, 360);

            // ---- tooth drawings (traced from the reference chart) ----
            ['tu', 'tl', 'du', 'dl'].forEach(g => TEETH[g].forEach(t => { h += '<i class="to" style="' + bx(t.x, t.y, t.x + t.w, t.y + t.h) + ';background-image:url(' + t.d + ')"></i>'; }));

            // ---- editable cells ----
            for (let i = 0; i < 16; i++) {
                C('pa' + i, T[i], 7, T[i + 1], 30);
                C('tu' + i, T[i], 52, T[i + 1], 100.5);
                C('tl' + i, B[i], 269, B[i + 1], 313);
                C('pb' + i, B[i], 336.5, B[i + 1], 360);
            }
            for (let i = 0; i < 10; i++) {
                C('du' + i, DU[i], 100.5, DU[i + 1], 120);
                C('dt' + i, DU[i], 120, DU[i + 1], 166);
                C('dl' + i, DN[i], 208, DN[i + 1], 253);
                C('dn' + i, DN[i], 253, DN[i + 1], 269);
            }

            // ---- printed text ----
            for (let i = 0; i < 16; i++) {
                X(NUM[i], T[i], 30, T[i + 1], 52, 'n');
                X(NUM[i], B[i], 313, B[i + 1], 336.5, 'n');
            }
            X('LABIAL', 420, 53, 533, 69, 'lab');
            X('LABIAL', 420, 297, 533, 312, 'lab');
            X('LINGUAL', 400, 159, 553, 175, 'lab');
            X('LINGUAL', 400, 201, 553, 217, 'lab');
            X('RIGHT<br>UPPER', 66.5, 100.5, 158, 166, 'bx');
            X('LEFT<br>UPPER', 803.5, 100.5, 894.5, 166, 'bx');
            X('RIGHT<br>LOWER', 66.5, 207.5, 158, 269, 'bx');
            X('LEFT<br>LOWER', 803.5, 207.5, 894.5, 269, 'bx');
            ['E', 'D', 'C', 'B'].forEach((c, i) => {
                const xa = [158, 215, 271.5, 328, 385];
                X(c, xa[i], 166, xa[i + 1], 187.5, 'lt'); X(c, xa[i], 187.5, xa[i + 1], 208, 'lt');
            });
            ['B', 'C', 'D', 'E'].forEach((c, i) => {
                const xa = [569, 627, 686.5, 745.5, 803.5];
                X(c, xa[i], 166, xa[i + 1], 187.5, 'lt'); X(c, xa[i], 187.5, xa[i + 1], 208, 'lt');
            });
            X('A', 385, 176.5, 476.5, 198, 'lt'); X('A', 476.5, 176.5, 569, 198, 'lt');

            return '<div class="dcx">' + h + '</div>';
        };
        const chart = dcChart();
        const LEG = [['C', 'Dental Caries'], ['C1', 'Dental Caries with Vital Pulp Exposed'], ['C2', 'Dental Caries with Non Vital Pulp Exposed'],
            ['X', 'Indicated for Extraction'], ['RF', 'Retained Root Fragment'], ['AM', 'Amalgam Filling'], ['S', 'Silicate Filling'],
            ['GC', 'Gold Crown'], ['AB', 'Bridge Abutment'], ['P', 'Pontic'], ['U', 'Gold Clasp'], ['GI', 'Gold Inlay'],
            ['M', 'Missing due to Extraction'], ['Un', 'Unerupted']];
        const legend = '<div class="mr-legend"><b>Legend:</b>' + LEG.map(l => '<div><b>' + l[0] + '</b><span>' + l[1] + '</span></div>').join('') + '</div>';

        const CLINICS = ['Oral Surgery Clinic', 'Operative Clinic', 'Prosthodontia Clinic', 'Crown &amp; Bridge Clinic', 'Oral Medicine Clinic',
            'X-Ray Clinic', 'Children&#39;s Clinic', 'Orthodontia Clinic', 'Clinical Laboratory'];
        const tp = '<table class="mr-tp">' + CLINICS.map((c, i) => '<tr><td class="nm">' + c + '</td><td class="mr-cell" contenteditable="true" data-k="tpA' + i + '"></td><td class="mr-cell" contenteditable="true" data-k="tpB' + i + '"></td></tr>').join('') + '</table>';

        let sv = '<table class="mr-sv"><colgroup><col style="width:15%"><col style="width:45%"><col style="width:20%"><col style="width:20%"></colgroup><thead><tr><th>DATE</th><th>SERVICES RENDERED</th><th>Patient&#39;s Signature</th><th>Dentist&#39;s Signature</th></tr></thead><tbody>';
        for (let r = 0; r < 14; r++) {
            sv += '<tr>' + [0, 1, 2, 3].map(c => '<td class="mr-cell" contenteditable="true" data-k="sv' + r + '_' + c + '"></td>').join('') + '</tr>';
        }
        sv += '</tbody></table>';

        return '<div class="mr-paper hidden" id="mrP2">' + HEAD +
            '<div style="margin-top:10px">' +
            ROW(IM('Name:', 'name', 'full')) +
            ROW(IM('Birthday:', 'birthday') + IM('Age:', 'age') + IM('Gender:', 'gender')) +
            ROW(IM('Civil Status:', 'civilStatus') + IM('Religion:', 'religion') + IM('Nationality:', 'nationality')) +
            ROW(IM('Department:', 'department') + IM('Course:', 'course')) +
            ROW(IM('Address:', 'address', 'w2') + IM('Contact#:', 'contact')) + '</div>' +
            '<div class="mr-center" style="margin-top:14px"><div style="font-size:12px">Republic of the Philippines</div><div style="font-size:13px;font-weight:700">SOUTHERN LUZON STATE UNIVERSITY</div><div style="font-size:12px">Lucban, Quezon</div>' +
            '<div style="font-size:13px;font-weight:700;margin-top:8px">DENTAL RECORD</div></div>' +
            '<div class="mr-dent">' + legend + '<div style="flex:1;min-width:0;overflow-x:auto">' + chart + '</div></div>' +
            '<div class="mr-center" style="font-weight:700;font-size:12px;margin-top:8px">TREATMENT PLAN</div>' +
            '<div style="display:flex;justify-content:center;overflow-x:auto">' + tp + '</div>' +
            '<div style="overflow-x:auto">' + sv + '</div>' +
            '<div class="mr-foot2"><div class="mr-it" style="max-width:300px"><label>DATE:</label>' + F('dentDate') + '</div><div class="mr-sigline">Signature of Dentist</div></div>' +
            '<div class="mr-priv">' + PRIV + '</div>' +
            '<div class="mr-code">SLSU-JGE-AFA-HSU-1.0.F2<br>Effective: 102025</div><div class="mr-pg">2</div></div>';
    }

    function buildNurse() {
        const nav = document.querySelector('#nurseSidebar nav');
        const main = document.querySelector('#nurseDashboard main');
        if (!nav || !main || $('navMedrec')) return;

        const a = document.createElement('a');
        a.href = '#'; a.id = 'navMedrec';
        a.className = 'sidebar-link flex items-center gap-3 px-4 py-3 rounded-lg text-blue-100';
        a.innerHTML = '<i class="fa-solid fa-notes-medical w-5 text-center"></i> Medical Records';
        a.addEventListener('click', e => { e.preventDefault(); showNurseTab('medrec'); });
        ($('navCert') || $('navMonthly') || $('navAppointments')).insertAdjacentElement('afterend', a);

        const v = document.createElement('div');
        v.id = 'nurseViewMedrec'; v.className = 'hidden fade-in';
        v.innerHTML =
            '<div class="nx-hero mb-6 flex flex-col md:flex-row md:items-center justify-between gap-4">' +
                '<div><div class="nx-chip mb-3"><i class="fa-solid fa-notes-medical"></i> Health Services Unit</div>' +
                '<h2 class="text-2xl font-bold">Medical Records</h2>' +
                '<p class="text-sm mt-1">1st Year students&#39; medical records. Open a student to view the full record (page 1) and the dental record (page 2), then fill in the rest and print.</p></div>' +
            '</div>' +
            '<div id="mrListBox" class="dashboard-card p-4 sm:p-6">' +
                '<div class="flex flex-col sm:flex-row gap-3 mb-4">' +
                    '<input type="text" id="mrSearch" placeholder="Search student name..." class="flex-1 px-4 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500">' +
                    '<button onclick="mrLoadList()" class="bg-blue-600 hover:bg-blue-700 text-white px-5 py-2.5 rounded-lg font-semibold"><i class="fa-solid fa-rotate mr-2"></i>Refresh</button>' +
                '</div>' +
                '<div class="overflow-x-auto rounded-xl border border-gray-200"><table class="nx-table w-full text-sm min-w-max"><thead><tr>' +
                    '<th class="text-center">#</th><th>Student</th><th>Course</th><th class="text-center">Student Form</th><th class="text-center">Action</th>' +
                '</tr></thead><tbody id="mrListBody"></tbody></table></div>' +
            '</div>' +
            '<div id="mrDetailBox" class="hidden"></div>';
        v.addEventListener('click', e => {
            const c = e.target.closest('.mr-ck');
            if (c && $('mrPaperWrap') && $('mrPaperWrap').contains(c)) c.classList.toggle('on');
        });
        v.addEventListener('input', e => { if (e.target.closest && e.target.closest('#mrP1')) sync(); });
        v.addEventListener('paste', e => {
            if (!(e.target.closest && e.target.closest('[contenteditable]'))) return;
            e.preventDefault();
            document.execCommand('insertText', false, (e.clipboardData || window.clipboardData).getData('text'));
        });
        v.addEventListener('keydown', e => {
            if (e.key === 'Enter' && e.target.closest && e.target.closest('[contenteditable]')) e.preventDefault();
        });
        main.appendChild(v);
        $('mrSearch').addEventListener('input', renderList);
    }

    async function loadList() {
        try {
            list = (await api('/api/medrec')).students;
            renderList();
        } catch (e) {
            $('mrListBody').innerHTML = '<tr><td colspan="5" class="py-6 text-center text-red-500">' + esc(e.message) + '</td></tr>';
        }
    }
    window.mrLoadList = loadList;

    function renderList() {
        const q = ($('mrSearch').value || '').trim().toLowerCase();
        const rows = list.filter(s => !q || s.name.toLowerCase().includes(q));
        if (!rows.length) {
            $('mrListBody').innerHTML = '<tr><td colspan="5"><div class="nx-empty"><i class="fa-solid fa-folder-open"></i><p class="font-semibold text-gray-600">No 1st Year students found</p></div></td></tr>';
            return;
        }
        $('mrListBody').innerHTML = rows.map((s, i) =>
            '<tr><td class="text-center">' + (i + 1) + '</td>' +
            '<td><div class="flex items-center gap-3"><div class="nx-avatar">' + esc(s.name.trim().charAt(0).toUpperCase()) + '</div><div class="font-semibold text-gray-800">' + esc(s.name) + '</div></div></td>' +
            '<td>' + esc(s.course || '—') + '</td>' +
            '<td class="text-center">' + (s.submitted
                ? '<span class="px-2.5 py-1 rounded-full text-xs font-semibold status-approved">Submitted' + (s.submittedAt ? ' · ' + esc(s.submittedAt) : '') + '</span>'
                : '<span class="px-2.5 py-1 rounded-full text-xs font-semibold status-pending">Not yet filled up</span>') + '</td>' +
            '<td class="text-center"><button onclick="mrOpen(' + s.id + ')" class="px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-xs font-semibold"><i class="fa-solid fa-folder-open mr-1"></i>Open</button></td></tr>'
        ).join('');
    }

    window.mrOpen = async function (uid) {
        try {
            cur = await api('/api/medrec/' + uid);
        } catch (e) { alert(e.message); return; }
        const box = $('mrDetailBox');
        box.innerHTML =
            '<div class="dashboard-card p-4 mb-4 flex flex-col lg:flex-row lg:items-center justify-between gap-3">' +
                '<div><div class="font-bold text-gray-800 text-lg">' + esc(cur.student.name) + '</div>' +
                '<div class="text-sm ' + (cur.submitted ? 'text-green-600' : 'text-orange-600') + '">' +
                (cur.submitted ? 'Student has submitted the form' : 'Student has not submitted yet (you can fill it in)') + '</div></div>' +
                '<div class="flex flex-wrap gap-2">' +
                    '<button onclick="mrBack()" class="px-4 py-2 bg-gray-100 hover:bg-gray-200 text-gray-700 rounded-lg text-sm font-medium"><i class="fa-solid fa-arrow-left mr-1"></i>Back</button>' +
                    '<div class="nx-seg"><button id="mrTab1" class="on" onclick="mrShowPage(1)">Page 1 · Medical</button><button id="mrTab2" onclick="mrShowPage(2)">Page 2 · Dental</button></div>' +
                    '<button onclick="mrSave()" class="px-4 py-2 bg-green-600 hover:bg-green-700 text-white rounded-lg text-sm font-semibold"><i class="fa-solid fa-floppy-disk mr-1"></i>Save</button>' +
                    '<button onclick="mrPrint()" class="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-semibold"><i class="fa-solid fa-print mr-1"></i>Print (2 pages)</button>' +
                '</div></div>' +
            '<div class="overflow-x-auto"><div id="mrPaperWrap">' + page1() + page2() + '</div></div>';
        fillPaper();
        $('mrListBox').classList.add('hidden');
        box.classList.remove('hidden');
        window.scrollTo(0, 0);
    };

    window.mrBack = function () {
        $('mrDetailBox').classList.add('hidden');
        $('mrListBox').classList.remove('hidden');
        loadList();
    };

    window.mrShowPage = function (n) {
        sync();
        $('mrP1').classList.toggle('hidden', n !== 1);
        $('mrP2').classList.toggle('hidden', n !== 2);
        $('mrTab1').classList.toggle('on', n === 1);
        $('mrTab2').classList.toggle('on', n === 2);
    };

    function fillPaper() {
        const s = cur.student, n = cur.nurse || {};
        $('mrPaperWrap').querySelectorAll('[data-k]').forEach(el => {
            const k = el.dataset.k;
            if (el.classList.contains('mr-ck')) { el.classList.toggle('on', n[k] === '1'); return; }
            let v;
            if (k === 'age') v = s.age;
            else if (k === 'birthday') v = pretty(s.birthday);
            else if (STU_KEYS.indexOf(k) >= 0) v = s[k];
            else v = n[k];
            el.textContent = (v === undefined || v === null) ? '' : v;
        });
        const d1 = $('mrPaperWrap').querySelector('[data-k="recDate"]');
        const d2 = $('mrPaperWrap').querySelector('[data-k="dentDate"]');
        if (d1 && !d1.textContent) d1.textContent = todayPretty();
        if (d2 && !d2.textContent) d2.textContent = todayPretty();
        sync();
    }

    // Page 2 header = kopya ng laman ng Page 1
    function sync() {
        const w = $('mrPaperWrap'); if (!w) return;
        w.querySelectorAll('[data-m]').forEach(m => {
            const src = w.querySelector('[data-k="' + m.dataset.m + '"]');
            m.textContent = src ? src.textContent : '';
        });
    }

    function collect() {
        const student = {}, nurse = {};
        $('mrPaperWrap').querySelectorAll('[data-k]').forEach(el => {
            const k = el.dataset.k;
            if (k === 'age') return;
            if (k === 'birthday') { student.birthday = cur.student.birthday; return; }
            if (el.classList.contains('mr-ck')) { if (el.classList.contains('on')) nurse[k] = '1'; return; }
            const v = el.textContent.trim();
            if (STU_KEYS.indexOf(k) >= 0) student[k] = v;
            else if (v) nurse[k] = v;
        });
        return { student, nurse };
    }

    window.mrSave = async function () {
        try {
            const body = collect();
            await api('/api/medrec/' + cur.userId, { method: 'POST', body: JSON.stringify(body) });
            cur.nurse = body.nurse;
            Object.assign(cur.student, body.student);
            alert('Medical record saved.');
        } catch (e) { alert(e.message); }
    };

    window.mrPrint = function () {
        sync();
        const wrap = $('mrPaperWrap').cloneNode(true);
        wrap.querySelectorAll('[contenteditable]').forEach(e => e.removeAttribute('contenteditable'));
        wrap.querySelectorAll('.hidden').forEach(e => e.classList.remove('hidden'));
        const w = window.open('', '_blank', 'width=900,height=1100');
        if (!w) { alert('Please allow pop-ups to print.'); return; }
        w.document.write('<html><head><title>Medical Record</title><style>' + $('mrStyle').textContent +
            '@page{size:8.5in 11in;margin:.4in}html,body{margin:0;-webkit-print-color-adjust:exact;print-color-adjust:exact}' +
            '.mr-paper{box-shadow:none;border:0;max-width:none;width:100%;margin:0;padding:0 .15in .3in;font-size:12px;line-height:1.7;page-break-after:always;min-height:0}' +
            '.mr-paper:last-child{page-break-after:auto}.mr-ro{background:none}.mr-pg{bottom:0}' +
            '.mr-head img{height:60px}.mr-title{margin:12px 0 6px}.dcx{min-width:0}.mr-sv td{height:20px}' +
            '</style></head><body>' + wrap.innerHTML + '</body></html>');
        w.document.close(); w.focus();
        setTimeout(() => w.print(), 600);
    };

    // ================= HOOKS =================
    function hook() {
        const prev = window.showNurseTab;
        window.showNurseTab = function (tab) {
            const v = $('nurseViewMedrec'), nv = $('navMedrec');
            if (v) v.classList.add('hidden');
            if (nv) nv.classList.remove('active');
            if (tab === 'medrec') {
                ['nurseViewDashboard', 'nurseViewAppointments', 'nurseViewHistory', 'nurseViewToday', 'nurseViewMonthly', 'nurseViewCert']
                    .forEach(id => $(id) && $(id).classList.add('hidden'));
                ['navDashboard', 'navHistory', 'navAppointments', 'navToday', 'navMonthly', 'navCert']
                    .forEach(id => $(id) && $(id).classList.remove('active'));
                v.classList.remove('hidden');
                nv.classList.add('active');
                if (!$('mrDetailBox').classList.contains('hidden')) { /* nasa detail pa rin */ } else { loadList(); }
                const sb = $('nurseSidebar');
                if (window.innerWidth < 768 && sb && !sb.classList.contains('-translate-x-full')) toggleNurseSidebar();
            } else {
                prev(tab);
            }
        };

        const od = window.openDashboard;
        window.openDashboard = function () {
            od.apply(this, arguments);
            if (typeof currentUser !== 'undefined' && currentUser && currentUser.role === 'Student') initStudent();
        };

        const lo = window.logoutSystem;
        window.logoutSystem = async function () {
            const r = await lo.apply(this, arguments);
            if (typeof currentUser !== 'undefined' && !currentUser) {
                const s = $('mrStuScreen'); if (s) s.classList.add('hidden');
                const c = $('mrCard'); if (c) c.remove();
                mrMe = null; gate = false;
                if ($('mrDetailBox')) { $('mrDetailBox').classList.add('hidden'); $('mrListBox').classList.remove('hidden'); }
            }
            return r;
        };
    }

    document.addEventListener('DOMContentLoaded', () => { buildNurse(); hook(); });
})();
</script>
'''

_MR_EXTRA = (_MR_EXTRA.replace("__MR_LOGO_L__", _LOGOS["L"])
                      .replace("__MR_LOGO_M__", _LOGOS["M"])
                      .replace("__MR_LOGO_R__", _LOGOS["R"]))

_hrep("\n</body>\n</html>", _MR_EXTRA + "\n</body>\n</html>")

# =====================================================================
# BAGONG UPDATE: COURSE DROPDOWN + LASTNAME/FIRSTNAME/MIDDLENAME
#                + 1ST YEAR -> DIRETSO SA MEDICAL RECORD FORM
# =====================================================================
COURSES = ("BSIT", "BSFAS", "BSBA", "BPA", "BSED", "BEED")


# ---------- BACKEND: validation ng Create Account at ng Medical Record ----------
@app.before_request
def _check_register_v4():
    if request.method != "POST":
        return None

    if request.path == "/api/register":
        d = request.get_json(silent=True) or {}
        parts = [p.strip() for p in str(d.get("name") or "").split(",")]
        if len(parts) != 3 or not all(parts):
            return jsonify(error="Full name must be: Lastname, Firstname, Middlename."), 400
        if d.get("role") == "Student" and (d.get("course") or "").strip() not in COURSES:
            return jsonify(error="Please select your course."), 400

    elif request.path == "/api/medrec/me":
        d = request.get_json(silent=True) or {}
        if (d.get("course") or "").strip() not in COURSES:
            return jsonify(error="Please select your course."), 400

    return None


# ---------- FRONTEND: Full Name = Lastname, Firstname, Middlename ----------
_hrep(
    f'<input type="text" id="regName" class="{_INP}" placeholder="Juan Dela Cruz">',
    f'''<input type="hidden" id="regName">
            <div class="grid grid-cols-1 min-[420px]:grid-cols-3 gap-2">
              <input type="text" id="regLast" class="{_INP}" placeholder="Lastname" autocomplete="family-name">
              <input type="text" id="regFirst" class="{_INP}" placeholder="Firstname" autocomplete="given-name">
              <input type="text" id="regMiddle" class="{_INP}" placeholder="Middlename" autocomplete="additional-name">
            </div>
            <p class="text-xs mt-1" style="color:#374151">Format: Lastname, Firstname, Middlename (all required)</p>''',
)

# ---------- FRONTEND: Course dropdown ----------
_hrep(
    f'<input type="text" id="regCourse" class="{_INP}" placeholder="e.g. BSIT (students)">',
    f'''<select id="regCourse" class="{_INP}"><option value="">Select...</option>'''
    + "".join(f"<option>{c}</option>" for c in COURSES)
    + "</select>",
)

# ---------- FRONTEND: Course din sa Medical Record form ng student ----------
_hrep(
    "fld('Course to apply for', 'mrs_course', 'text') +",
    "sel('Course to apply for', 'mrs_course', ['BSIT', 'BSFAS', 'BSBA', 'BPA', 'BSED', 'BEED']) +",
)

# ---------- FRONTEND: script ----------
_V4_EXTRA = r'''
<script>
(function () {
    const $ = id => document.getElementById(id);

    // Pagsamahin ang 3 name fields -> "Lastname, Firstname, Middlename"
    function syncName() {
        const l = $('regLast').value.trim(), f = $('regFirst').value.trim(), m = $('regMiddle').value.trim();
        $('regName').value = (l && f && m) ? (l + ', ' + f + ', ' + m) : '';
    }

    document.addEventListener('DOMContentLoaded', () => {
        ['regLast', 'regFirst', 'regMiddle'].forEach(id => {
            const el = $(id);
            if (!el) return;
            el.addEventListener('input', syncName);
            el.addEventListener('keydown', e => { if (e.key === 'Enter') registerUser(); });
        });
        // Course ay para sa Student lang
        const role = $('regRole'), course = $('regCourse');
        if (role && course) {
            const wrap = course.parentElement;
            const upd = () => { wrap.style.display = role.value === 'Student' ? '' : 'none'; if (role.value !== 'Student') course.value = ''; };
            role.addEventListener('change', upd);
            upd();
        }
    });

    // Kapag 1st Year student ang nag-Create Account -> auto sign in -> diretso sa Medical Record form
    const origApi = window.api;
    window.api = async function (url, options) {
        const res = await origApi(url, options);
        if (url === '/api/register' && options && options.body) {
            try {
                const b = JSON.parse(options.body);
                if (b.role === 'Student' && b.yearLevel === '1st Year') {
                    const data = await origApi('/api/login', {
                        method: 'POST',
                        body: JSON.stringify({ email: b.email, password: b.password })
                    });
                    currentUser = data.user;
                    $('authMsg').textContent = '';
                    openDashboard();   // lalabas agad ang Medical Record form (personal info -> emergency)
                }
            } catch (e) { console.warn('Auto sign-in skipped:', e); }
        }
        return res;
    };
})();
</script>
'''

_hrep("\n</body>\n</html>", _V4_EXTRA + "\n</body>\n</html>")

# ===================== TAPOS NA ANG CLINIC UPDATE =====================
# === RUN SERVER ===
if __name__ == "__main__":
    with app.app_context():
        init_db()
    app.run(host="0.0.0.0", port=5050, debug=True)
