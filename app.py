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
    HTML_CONTENT = """
    
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🏫 School Clinic - Appointment System</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.7.2/css/all.min.css">
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
        * { font-family: 'Inter', sans-serif; }
        
        .school-bg {
            background: linear-gradient(rgba(255, 255, 255, 0.15), rgba(255, 255, 255, 0.15)), 
                        url('clinic.jpg');
            background-size: 100% auto;
            background-position: center;
            background-attachment: fixed;
            background-repeat: no-repeat;
        }
        .glass {
            background: rgba(255, 255, 255, 0.35);
            backdrop-filter: blur(12px);
            border: 1px solid rgba(255, 255, 255, 0.4);
            color: #000000 !important;
            box-shadow: 0 8px 40px rgba(0,0,0,0.1);
            transition: all 0.4s ease;
        }
        .glass:hover {
            box-shadow: 0 12px 50px rgba(0,0,0,0.15);
            border-color: rgba(255,255,255,0.6);
        }
        .dashboard-card {
            background: #ffffff;
            border: 1px solid #e5e7eb;
            border-radius: 16px;
            box-shadow: 0 2px 12px rgba(0,0,0,0.04);
            transition: all 0.35s ease;
        }
        .dashboard-card:hover {
            box-shadow: 0 8px 30px rgba(0,0,0,0.08);
            transform: translateY(-2px);
        }
        .sidebar-link {
            transition: all 0.3s ease;
        }
        .sidebar-link:hover, .sidebar-link.active {
            background: rgba(255, 255, 255, 0.18);
            border-left: 4px solid #fbbf24;
        }
        .stat-card {
            border-radius: 16px;
            transition: all 0.35s ease;
        }
        .stat-card:hover {
            transform: translateY(-6px);
            box-shadow: 0 15px 35px rgba(0,0,0,0.15);
        }
        .fade-in { animation: fadeIn 0.5s ease-out; }
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(20px); }
            to { opacity: 1; transform: translateY(0); }
        }
        .tab-active {
            border-bottom: 3px solid #3b82f6;
            color: #2563eb;
            font-weight: 600;
        }
        .status-pending { background: #fef08a; color: #854d0e; }
        .status-approved { background: #bbf7d0; color: #166534; }
        .status-rejected { background: #fecaca; color: #991b1b; }
        .history-panel {
            max-height: 550px;
            overflow-y: auto;
        }
        .password-wrapper { position: relative; }
        .eye-icon {
            position: absolute;
            right: 12px;
            top: 50%;
            transform: translateY(-50%);
            cursor: pointer;
            color: #6b7280;
        }
        .password-wrapper input { padding-right: 40px !important; }
        @keyframes pulse-glow {
            0%, 100% { box-shadow: 0 0 4px rgba(251, 191, 36, 0.4); }
            50% { box-shadow: 0 0 15px rgba(251, 191, 36, 0.7); }
        }
        .animate-pulse { animation: pulse-glow 1.5s ease-in-out infinite; }
        .time-slot {
            transition: all 0.25s ease;
            cursor: pointer;
        }
        .time-slot:hover:not(.taken) {
            background-color: #dbeafe;
            border-color: #3b82f6;
            transform: scale(1.03);
        }
        .time-slot.taken {
            background-color: #f3f4f6;
            color: #9ca3af;
            border-color: #e5e7eb;
            cursor: not-allowed;
            text-decoration: line-through;
        }
        .time-slot.selected {
            background-color: #dbeafe;
            border-color: #2563eb;
            border-width: 2px;
            font-weight: 600;
            color: #1e40af;
        }
    </style>
</head>
<body class="bg-gray-50 min-h-screen">

<!-- 🔐 LOGIN PAGE -->
<div id="authSection" class="school-bg flex items-center justify-center min-h-screen p-4">
    <div class="glass rounded-2xl shadow-2xl p-8 w-full max-w-md fade-in">
        <div class="text-center mb-8">
            <i class="fa-solid fa-heart-pulse text-4xl text-red-500 mb-2"></i>
            <h1 class="text-2xl font-bold text-gray-800">Clinic Appointment System</h1>
            <p class="text-gray-500">School Clinic Appointment System</p>
        </div>
        <div class="flex mb-6 border-b border-gray-200">
            <button id="tabLogin" class="flex-1 py-3 text-center tab-active" onclick="showAuthTab('login')">
                <i class="fa-solid fa-right-to-bracket mr-2"></i> Sign In
            </button>
            <button id="tabRegister" class="flex-1 py-3 text-center text-gray-500" onclick="showAuthTab('register')">
                <i class="fa-solid fa-user-plus mr-2"></i> Create Account
            </button>
        </div>
        <!-- LOGIN FORM -->
        <div id="formLogin">
            <div class="space-y-4">
                <div>
                    <label class="block text-gray-700 font-medium mb-1">Email</label>
                    <input type="email" id="loginEmail" class="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500" placeholder="your@email.com">
                </div>
                <div>
                    <label class="block text-gray-700 font-medium mb-1">Password</label>
                    <div class="password-wrapper">
                        <input type="password" id="loginPass" class="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500" placeholder="At least 6 characters">
                        <i class="fa-solid fa-eye eye-icon" id="eyeLogin" onclick="togglePassword('loginPass', 'eyeLogin')"></i>
                    </div>
                </div>
                <button id="loginButton" onclick="loginUser()" class="w-full bg-blue-600 hover:bg-blue-700 text-white py-3 rounded-lg font-semibold">
                    Sign In
                </button>
            </div>
        </div>
        <!-- REGISTER FORM -->
        <div id="formRegister" class="hidden">
            <div class="space-y-4">
                <div>
                    <label class="block text-gray-700 font-medium mb-1">Full Name</label>
                    <input type="text" id="regName" class="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-green-500" placeholder="Juan Dela Cruz">
                </div>
                <div>
                    <label class="block text-gray-700 font-medium mb-1">Email</label>
                    <input type="email" id="regEmail" class="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-green-500" placeholder="your@email.com">
                </div>
                <div>
                    <label class="block text-gray-700 font-medium mb-1">Password</label>
                    <div class="password-wrapper">
                        <input type="password" id="regPass" class="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-green-500" placeholder="At least 6 characters">
                        <i class="fa-solid fa-eye eye-icon" id="eyeReg" onclick="togglePassword('regPass', 'eyeReg')"></i>
                    </div>
                </div>
                <div>
                    <label class="block text-gray-700 font-medium mb-1">You are a...</label>
                    <select id="regRole" class="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-green-500">
                        <option value="Student"> 🎓 Student</option>
                        <option value="Teacher"> 📖 Teacher</option>
                        <option value="Staff"> 🏛️ Staff</option>
                    </select>
                </div>
                <button onclick="registerUser()" class="w-full bg-green-600 hover:bg-green-700 text-white py-3 rounded-lg font-semibold">
                    Create Account
                </button>
            </div>
        </div>
        <p id="authMsg" class="mt-4 text-center font-medium"></p>
    </div>
</div>

<!-- 🏠 USER DASHBOARD -->
<div id="userDashboard" class="hidden min-h-screen flex">
    <aside class="w-64 bg-blue-900 text-white hidden md:block">
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
            <h3 class="text-lg font-bold text-gray-800 mb-4">📅 Book an Appointment</h3>
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
            <h3 class="text-lg font-bold text-gray-800 mb-4">📋 My Appointments</h3>
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
                        </tr>
                    </thead>
                    <tbody id="myAppointmentsTable">
                        <tr><td colspan="6" class="py-4 text-center text-gray-400 italic">No appointments yet.</td></tr>
                    </tbody>
                </table>
            </div>
        </div>
    </main>
</div>

<!-- 👩‍⚕️ NURSE DASHBOARD -->
<div id="nurseDashboard" class="hidden min-h-screen flex">
    <aside class="w-64 bg-blue-900 text-white hidden md:block">
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
                        <div><p class="text-blue-100 text-sm">New Requests</p><p class="text-3xl font-bold" id="statNew">0</p></div>
                        <i class="fa-solid fa-calendar-plus text-3xl text-blue-200"></i>
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
                <div class="stat-card bg-red-500 text-white p-4">
                    <div class="flex items-center justify-between">
                        <div><p class="text-red-100 text-sm">Rejected</p><p class="text-3xl font-bold" id="statRejected">0</p></div>
                        <i class="fa-solid fa-times-circle text-3xl text-red-200"></i>
                    </div>
                </div>
            </div>
            <div class="dashboard-card p-4 mb-6">
                <h3 class="text-lg font-bold text-gray-800 mb-3">🔍 Search Patient History</h3>
                <div class="flex flex-col md:flex-row gap-3">
                    <input type="text" id="searchPatientName" placeholder="Type patient name..." 
                        class="flex-1 px-4 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500">
                    <button onclick="searchPatientHistory()" class="bg-blue-600 hover:bg-blue-700 text-white px-5 py-2.5 rounded-lg font-semibold">
                        <i class="fa-solid fa-magnifying-glass mr-2"></i> Search
                    </button>
                </div>
                <div id="patientHistoryResult" class="mt-4 hidden">
                    <h4 class="font-bold text-gray-700 mb-2">📋 Appointment History:</h4>
                    <div class="history-panel border rounded-lg overflow-hidden">
                        <table class="w-full text-sm">
                            <thead class="bg-gray-100">
                                <tr>
                                    <th class="py-2 px-3 text-left">#</th>
                                    <th class="py-2 px-3 text-left">Date</th>
                                    <th class="py-2 px-3 text-left">Time</th>
                                    <th class="py-2 px-3 text-left">Type</th>
                                    <th class="py-2 px-3 text-left">Symptoms</th>
                                    <th class="py-2 px-3 text-left">Status</th>
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
            <div class="dashboard-card p-6">
                <div class="flex flex-col md:flex-row justify-between items-start md:items-center mb-6 gap-3">
                    <h3 class="text-lg font-bold text-gray-800">
                        <i class="fa-solid fa-clock-rotate-left mr-2 text-blue-600"></i> Appointment History
                        <span class="text-sm font-normal text-gray-500 ml-2">(Chronological Order)</span>
                    </h3>
                    <div class="flex gap-2">
                        <button onclick="renderHistory(true)" class="px-3 py-1.5 bg-gray-100 text-gray-700 rounded-lg text-sm font-medium hover:bg-gray-200">
                            <i class="fa-solid fa-arrow-up-short-wide mr-1"></i> Oldest First
                        </button>
                        <button onclick="renderHistory(false)" class="px-3 py-1.5 bg-gray-100 text-gray-700 rounded-lg text-sm font-medium hover:bg-gray-200">
                            <i class="fa-solid fa-arrow-down-wide-short mr-1"></i> Newest First
                        </button>
                    </div>
                </div>
                <div class="overflow-x-auto history-panel">
                    <table class="w-full text-sm">
                        <thead class="bg-gray-50">
                            <tr class="text-left text-gray-600 border-b-2 border-gray-200">
                                <th class="py-3 px-3 font-semibold text-center">#</th>
                                <th class="py-3 px-3 font-semibold">Name</th>
                                <th class="py-3 px-3 font-semibold">Role</th>
                                <th class="py-3 px-3 font-semibold">Date</th>
                                <th class="py-3 px-3 font-semibold">Time</th>
                                <th class="py-3 px-3 font-semibold">Visit Type</th>
                                <th class="py-3 px-3 font-semibold">Purpose</th>
                                <th class="py-3 px-3 font-semibold text-center">Status</th>
                            </tr>
                        </thead>
                        <tbody id="historyTable">
                            <tr><td colspan="8" class="py-8 text-center text-gray-400 italic">No appointment history yet.</td></tr>
                        </tbody>
                    </table>
                </div>
            </div>
        </div>

        <!-- ALL APPOINTMENTS VIEW -->
        <div id="nurseViewAppointments" class="hidden fade-in">
            <div class="dashboard-card p-6">
                <div class="flex flex-col md:flex-row justify-between items-start md:items-center mb-6 gap-3">
                    <h3 class="text-lg font-bold text-gray-800">📋 ALL Clinic Appointments</h3>
                    <div class="flex gap-2">
                        <select id="filterRole" onchange="renderAllAppointments()" class="px-3 py-1.5 border rounded-lg text-sm">
                            <option value="all">All Roles</option>
                            <option value="Student">Student</option>
                            <option value="Teacher">Teacher</option>
                            <option value="Staff">Staff</option>
                        </select>
                        <select id="filterStatus" onchange="renderAllAppointments()" class="px-3 py-1.5 border rounded-lg text-sm">
                            <option value="all">All Status</option>
                            <option value="pending">⏳ Pending</option>
                            <option value="approved">✅ Approved</option>
                            <option value="rejected">❌ Rejected</option>
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

<script>
// === PASSWORD TOGGLE ===
function togglePassword(inputId, eyeId) {
    const input = document.getElementById(inputId);
    const eye = document.getElementById(eyeId);
    if (input.type === "password") {
        input.type = "text";
        eye.classList.remove("fa-eye"); eye.classList.add("fa-eye-slash");
    } else {
        input.type = "password";
        eye.classList.remove("fa-eye-slash"); eye.classList.add("fa-eye");
    }
}

let currentUser = null;
let selectedTimeSlot = null;
let isSubmittingAppointment = false;

// ✅ AVAILABLE TIME SLOTS (Fixed schedule)
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

// === PREVENT WEEKEND DATES ===
function setDateRestrictions() {
    const today = new Date().toISOString().split('T')[0];
    document.getElementById('aptDate').min = today;
}

// === ✅ LOAD AVAILABLE TIME SLOTS BASED ON SELECTED DATE ===
async function loadAvailableTimeSlots() {
    const dateInput = document.getElementById('aptDate');
    const selectedDate = dateInput.value;
    const container = document.getElementById('timeSlotsContainer');

    // A time slot belongs to the selected date, so never carry it to another date.
    selectedTimeSlot = null;
    document.getElementById('aptTime').value = '';
    
    if (!selectedDate) {
        container.innerHTML = '<span class="text-gray-400 text-sm col-span-3">Select a date first...</span>';
        return;
    }

    // Check if Saturday or Sunday
    const dateObj = new Date(selectedDate + 'T00:00:00');
    const dayOfWeek = dateObj.getDay(); // 0=Sunday, 6=Saturday
    if (dayOfWeek === 0 || dayOfWeek === 6) {
        container.innerHTML = '<span class="text-red-500 text-sm col-span-3">⚠️ Appointments are Monday–Friday only.</span>';
        document.getElementById('aptTime').value = '';
        selectedTimeSlot = null;
        return;
    }

    let takenTimes;
    try {
        const data = await api(`/api/appointments/slots?date=${encodeURIComponent(selectedDate)}`);
        takenTimes = data.taken;
    } catch (error) {
        container.innerHTML = `<span class="text-red-500 text-sm col-span-3">${error.message}</span>`;
        return;
    }

    // Show available slots
    container.innerHTML = ALL_TIME_SLOTS.map(time => {
        const isTaken = takenTimes.includes(time);
        if (isTaken) {
            return `<div class="time-slot taken border rounded px-2 py-1 text-center text-sm">${time}</div>`;
        } else {
            return `<div class="time-slot border border-blue-300 rounded px-2 py-1 text-center text-sm bg-white" onclick="selectTimeSlot('${time}', event)">${time}</div>`;
        }
    }).join('');
}

// === ✅ SELECT TIME SLOT ===
function selectTimeSlot(time, clickEvent) {
    selectedTimeSlot = time;
    document.getElementById('aptTime').value = time;
    
    // Update visual highlight
    document.querySelectorAll('.time-slot').forEach(el => {
        el.classList.remove('selected');
        if (!el.classList.contains('taken')) {
            el.classList.remove('border-blue-600');
        }
    });
    clickEvent.currentTarget.classList.add('selected');
}

// === SWITCH LOGIN/REGISTER TABS ===
function showAuthTab(tab) {
    const tabLogin = document.getElementById('tabLogin');
    const tabReg = document.getElementById('tabRegister');
    if (tab === 'login') {
        tabLogin.classList.add('tab-active'); tabReg.classList.remove('tab-active');
        tabLogin.classList.remove('text-gray-500'); tabReg.classList.add('text-gray-500');
        document.getElementById('formLogin').classList.remove('hidden');
        document.getElementById('formRegister').classList.add('hidden');
    } else {
        tabReg.classList.add('tab-active'); tabLogin.classList.remove('tab-active');
        tabReg.classList.remove('text-gray-500'); tabLogin.classList.add('text-gray-500');
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
    if (!name || !email || !pass) {
        msg.textContent = '⚠️ Please fill in all fields!'; msg.className = 'text-orange-500'; return;
    }
    if (pass.length < 6) {
        msg.textContent = '⚠️ Password must be at least 6 characters!'; msg.className = 'text-orange-500'; return;
    }
    try {
        await api('/api/register', { method: 'POST', body: JSON.stringify({ name, email, password: pass, role }) });
        msg.textContent = '✅ Account created! Please sign in.'; msg.className = 'text-green-500';
        setTimeout(() => showAuthTab('login'), 1500);
    } catch (error) {
        msg.textContent = `❌ ${error.message}`; msg.className = 'text-red-500';
    }
}

// === LOGIN USER ===
async function loginUser() {
    const email = document.getElementById('loginEmail').value.trim().toLowerCase();
    const pass = document.getElementById('loginPass').value;
    const msg = document.getElementById('authMsg');
    const loginButton = document.getElementById('loginButton');

    if (!email || !pass) {
        msg.textContent = '⚠️ Enter your email and password.';
        msg.className = 'text-orange-500';
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
            ? '❌ Cannot connect to the clinic server. Run "py app.py" and open http://127.0.0.1:5050.'
            : `❌ ${error.message}`;
        msg.textContent = message;
        msg.className = 'text-red-500';
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
        const labels = { Student: '🎓 Student', Teacher: '📖 Teacher', Staff: '🏛️ Staff' };
        document.getElementById('displayRole').textContent = labels[currentUser.role];
        renderMyAppointments();
        setDateRestrictions();
    }
}

// === ✅ SUBMIT APPOINTMENT WITH TIME SLOT VALIDATION ===
async function submitAppointment() {
    if (isSubmittingAppointment) return;

    const date = document.getElementById('aptDate').value;
    const time = selectedTimeSlot;
    const type = document.getElementById('aptType').value;
    const reason = document.getElementById('aptReason').value.trim();

    if (!date || !time || !reason) { 
        alert('⚠️ Please select a date, available time slot, and fill in purpose!'); 
        return; 
    }

    const submitButton = document.getElementById('submitAppointmentButton');
    isSubmittingAppointment = true;
    submitButton.disabled = true;
    submitButton.classList.add('opacity-60', 'cursor-not-allowed');

    try {
        await api('/api/appointments', {
            method: 'POST', body: JSON.stringify({ date, time, type, reason })
        });
        alert('✅ Appointment submitted!');
    } catch (error) {
        alert(`❌ ${error.message}`);
        loadAvailableTimeSlots();
        return;
    } finally {
        isSubmittingAppointment = false;
        submitButton.disabled = false;
        submitButton.classList.remove('opacity-60', 'cursor-not-allowed');
    }
    
    // Reset form
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
    try { apts = (await api('/api/appointments')).appointments; }
    catch (error) {
        document.getElementById('myAppointmentsTable').innerHTML = `<tr><td colspan="6" class="py-4 text-center text-red-500">${error.message}</td></tr>`;
        return;
    }
    const tbody = document.getElementById('myAppointmentsTable');
    if (apts.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" class="py-4 text-center text-gray-400 italic">No appointments yet.</td></tr>';
        return;
    }
    const cls = { pending: 'status-pending', approved: 'status-approved', rejected: 'status-rejected' };
    const txt = { pending: '⏳ Pending', approved: '✅ Approved', rejected: '❌ Rejected' };
    tbody.innerHTML = apts.map((a, i) => `
        <tr class="border-b hover:bg-blue-50">
            <td class="py-2 px-2">${i+1}</td>
            <td class="py-2 px-2">${a.date}</td>
            <td class="py-2 px-2">${a.time}</td>
            <td class="py-2 px-2">${a.type}</td>
            <td class="py-2 px-2 max-w-xs truncate">${a.reason}</td>
            <td class="py-2 px-2"><span class="px-2 py-0.5 rounded-full text-xs font-medium ${cls[a.status]}">${txt[a.status]}</span></td>
        </tr>`).join('');
}

// === UPDATE STATISTICS ===
async function updateStats() {
    let apts;
    try { apts = (await api('/api/appointments')).appointments; } catch (error) { return; }
    document.getElementById('statNew').textContent = apts.length;
    document.getElementById('statPending').textContent = apts.filter(a => a.status === 'pending').length;
    document.getElementById('statApproved').textContent = apts.filter(a => a.status === 'approved').length;
    document.getElementById('statRejected').textContent = apts.filter(a => a.status === 'rejected').length;
    document.getElementById('pendingBadge').textContent = apts.filter(a => a.status === 'pending').length;
}

// === SEARCH PATIENT HISTORY ===
async function searchPatientHistory() {
    const name = document.getElementById('searchPatientName').value.trim().toLowerCase();
    const resultDiv = document.getElementById('patientHistoryResult');
    const tableBody = document.getElementById('patientHistoryTable');
    if (!name) { alert('⚠️ Enter patient name!'); return; }
    let history;
    try {
        history = (await api('/api/appointments')).appointments
            .filter(a => a.userName.toLowerCase().includes(name)).sort((a,b) => b.id - a.id);
    } catch (error) { alert(`❌ ${error.message}`); return; }
    resultDiv.classList.remove('hidden');
    if (history.length === 0) {
        tableBody.innerHTML = '<tr><td colspan="6" class="py-4 text-center text-gray-400 italic">❌ No history found.</td></tr>';
        return;
    }
    const cls = { pending: 'status-pending', approved: 'status-approved', rejected: 'status-rejected' };
    const txt = { pending: '⏳ Pending', approved: '✅ Approved', rejected: '❌ Rejected' };
    tableBody.innerHTML = history.map((a, i) => `
        <tr class="border-b hover:bg-blue-50">
            <td class="py-2 px-3">${i+1}</td>
            <td class="py-2 px-3">${a.date}</td>
            <td class="py-2 px-3">${a.time}</td>
            <td class="py-2 px-3">${a.type}</td>
            <td class="py-2 px-3 max-w-xs truncate">${a.reason}</td>
            <td class="py-2 px-3"><span class="px-2 py-0.5 rounded-full text-xs font-medium ${cls[a.status]}">${txt[a.status]}</span></td>
        </tr>`).join('');
}

// === RENDER HISTORY ===
async function renderHistory(oldestFirst = true) {
    let apts;
    try { apts = (await api('/api/appointments')).appointments; } catch (error) { return; }
    apts.sort((a, b) => oldestFirst ? a.id - b.id : b.id - a.id);
    const tbody = document.getElementById('historyTable');
    if (apts.length === 0) {
        tbody.innerHTML = '<tr><td colspan="8" class="py-8 text-center text-gray-400 italic">No appointment history yet.</td></tr>';
        return;
    }
    const roleText = { Student: '🎓 Student', Teacher: '📖 Teacher', Staff: '🏛️ Staff' };
    const cls = { pending: 'status-pending', approved: 'status-approved', rejected: 'status-rejected' };
    const txt = { pending: '⏳ Pending', approved: '✅ Approved', rejected: '❌ Rejected' };
    tbody.innerHTML = apts.map((a, i) => `
        <tr class="border-b border-gray-100 hover:bg-blue-50">
            <td class="py-3 px-3 font-medium text-center">${i+1}</td>
            <td class="py-3 px-3 font-semibold text-blue-800">${a.userName}</td>
            <td class="py-3 px-3 text-sm">${roleText[a.userRole] || a.userRole}</td>
            <td class="py-3 px-3">${a.date}</td>
            <td class="py-3 px-3">${a.time}</td>
            <td class="py-3 px-3 text-sm">${a.type}</td>
            <td class="py-3 px-3 text-sm max-w-xs truncate">${a.reason}</td>
            <td class="py-3 px-3 text-center"><span class="px-2 py-1 rounded text-xs font-semibold ${cls[a.status]}">${txt[a.status]}</span></td>
        </tr>`).join('');
}

// === RENDER ALL APPOINTMENTS ===
async function renderAllAppointments() {
    let apts;
    try { apts = (await api('/api/appointments')).appointments; } catch (error) { return; }
    const roleFilter = document.getElementById('filterRole').value;
    const statusFilter = document.getElementById('filterStatus').value;
    if (roleFilter !== 'all') apts = apts.filter(a => a.userRole === roleFilter);
    if (statusFilter !== 'all') apts = apts.filter(a => a.status === statusFilter);
    apts.sort((a,b) => b.id - a.id);
    updateStats();
    const tbody = document.getElementById('allAppointmentsTable');
    if (apts.length === 0) {
        tbody.innerHTML = '<tr><td colspan="9" class="py-8 text-center text-gray-400 italic">No appointment requests found.</td></tr>';
        return;
    }
    const roleText = { Student: '🎓 Student', Teacher: '📖 Teacher', Staff: '🏛️ Staff' };
    const cls = { pending: 'status-pending', approved: 'status-approved', rejected: 'status-rejected' };
    const txt = { pending: 'Pending', approved: 'Approved', rejected: 'Rejected' };
    tbody.innerHTML = apts.map((a, i) => `
        <tr class="border-b border-gray-100">
            <td class="py-3 px-3 font-medium">${i+1}</td>
            <td class="py-3 px-3 font-semibold text-blue-800">${a.userName}</td>
            <td class="py-3 px-3 text-sm">${roleText[a.userRole] || a.userRole}</td>
            <td class="py-3 px-3">${a.date}</td>
            <td class="py-3 px-3">${a.time}</td>
            <td class="py-3 px-3 text-sm">${a.type}</td>
            <td class="py-3 px-3 text-sm max-w-xs">${a.reason}</td>
            <td class="py-3 px-3 text-center"><span class="px-2 py-1 rounded text-xs font-semibold ${cls[a.status]}">${txt[a.status]}</span></td>
            <td class="py-3 px-3 text-center">
                ${a.status === 'pending' ? `
                    <button onclick="updateStatus(${a.id}, 'approved')" class="bg-green-500 text-white px-2 py-1 rounded text-xs mr-1">✅ Approve</button>
                    <button onclick="updateStatus(${a.id}, 'rejected')" class="bg-red-500 text-white px-2 py-1 rounded text-xs">❌ Reject</button>
                ` : '<span class="text-gray-400 text-xs">—</span>'}
            </td>
        </tr>`).join('');
}

// === UPDATE STATUS ===
async function updateStatus(id, status) {
    try {
        await api(`/api/appointments/${id}/status`, {
            method: 'PATCH', body: JSON.stringify({ status })
        });
        await renderAllAppointments();
        await updateStats();
    } catch (error) { alert(`❌ ${error.message}`); }
}

// === LOGOUT ===
async function logoutSystem() {
    try { await api('/api/logout', { method: 'POST' }); } catch (error) { /* Clear local UI even if server is unavailable. */ }
    currentUser = null;
    selectedTimeSlot = null;
    document.getElementById('userDashboard').classList.add('hidden');
    document.getElementById('nurseDashboard').classList.add('hidden');
    document.getElementById('authSection').classList.remove('hidden');
    document.getElementById('loginEmail').value = '';
    document.getElementById('loginPass').value = '';
    document.getElementById('authMsg').textContent = '';
    showAuthTab('login');
}

// === INITIALIZE ===
api('/api/me').then(data => {
    if (data.user) { currentUser = data.user; openDashboard(); }
});
</script>
</body>
</html>
"""

    return HTML_CONTENT


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
    app.run(
        host=os.environ.get("CLINIC_HOST", "0.0.0.0"),
        port=int(os.environ.get("CLINIC_PORT", "5050")),
        debug=os.environ.get("FLASK_DEBUG", "0") == "1",
        threaded=False,
    )

