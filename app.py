from datetime import datetime
from functools import wraps
import os
from pathlib import Path

import psycopg2
from flask import Flask, Response, g, jsonify, request, session
from werkzeug.security import check_password_hash, generate_password_hash

# === DATABASE CONFIGURATION ===
DATABASE_URL = os.environ.get("DATABASE_URL")

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
              <option value="rejected">Rejected</option>
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
        if (filterStatus !== 'all') apts = apts.filter(a => a.status === filterStatus);

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
    if (!confirm('Approve this appointment?')) return;
    try {
        await api(`/api/appointments/${id}/approve`, { method: 'POST' });
        alert('Appointment approved!');
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
        alert('Appointment rescheduled.');
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
            todayData = data;
            [...data.booked, ...data.scheduled].forEach(a => { aptCache[a.id] = a; });
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
                '<td class="text-center text-gray-500">' + (i + 1) + '</td>' +
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
        const full = MONTHS.map((_, i) => byMonth[i + 1] || { month: i + 1, requests: 0, clients: 0, approved: 0, pending: 0, rejected: 0 });

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
            '<td class="text-center"><span class="nx-pill status-rejected">' + m.rejected + '</span></td>' +
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
                    '<th>Month</th><th class="text-center">Clients</th><th class="text-center">Requests</th><th class="text-center">Approved</th><th class="text-center">Pending</th><th class="text-center">Rejected</th><th></th>' +
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
            const m = byMonth[i + 1] || { requests: 0, clients: 0, approved: 0, pending: 0, rejected: 0 };
            return '<tr><td>' + name + '</td><td>' + m.clients + '</td><td>' + m.requests + '</td><td>' + m.approved + '</td><td>' + m.pending + '</td><td>' + m.rejected + '</td></tr>';
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
            '<table><thead><tr><th>Month</th><th>Clients</th><th>Requests</th><th>Approved</th><th>Pending</th><th>Rejected</th></tr></thead><tbody>' + rows + '</tbody></table>' +
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


@app.post("/api/appointments/<int:apt_id>/approve")
@nurse_required
def approve(apt_id):
    conn = get_db()
    if not conn:
        return jsonify(error="Database connection failed."), 500

    cur = conn.cursor()
    try:
        cur.execute("UPDATE appointments SET status = 'approved' WHERE id = %s", (apt_id,))
        if cur.rowcount == 0:
            return jsonify(error="Appointment not found."), 404
        conn.commit()
        return jsonify(message="Appointment approved."), 200
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


# === RESCHEDULE (nurse sets new date/time + required reason) ===
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
        cur.execute("SELECT date, time FROM appointments WHERE id = %s", (apt_id,))
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
            ORDER BY a.created_at DESC
            """
        )
        booked_rows = cur.fetchall()

        # May schedule ngayong araw (scheduled today)
        cur.execute(base + " WHERE a.date = %s ORDER BY a.time ASC", (today,))
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
                   COUNT(*) FILTER (WHERE status = 'approved'),
                   COUNT(*) FILTER (WHERE status = 'pending'),
                   COUNT(*) FILTER (WHERE status = 'rejected')
            FROM appointments
            WHERE substr(date, 1, 4) = %s
            GROUP BY 1
            ORDER BY 1
        """, (str(year),))
        months = [
            {"month": int(r[0]), "requests": r[1], "clients": r[2],
             "approved": r[3], "pending": r[4], "rejected": r[5]}
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



# === RUN SERVER ===
if __name__ == "__main__":
    with app.app_context():
        init_db()
    app.run(host="0.0.0.0", port=5050, debug=True)
