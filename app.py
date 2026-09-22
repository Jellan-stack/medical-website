from datetime import date, datetime
from functools import wraps
import os
from pathlib import Path
import psycopg2  # ✅ Ginamit ang tamang package
from flask import Flask, g, jsonify, request, send_from_directory, session
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

# ✅ IISA LANG NG GET_DB FUNCTION — PARA SA POSTGRESQL
def get_db():
    if "db" not in g:
        try:
            g.db = psycopg2.connect(DATABASE_URL)
            g.db.autocommit = False
        except Exception as e:
            print(f"❌ DB Connection Error: {e}")
            return None
    return g.db

@app.teardown_appcontext
def close_db(_error):
    db = g.pop("db", None)
    if db is not None:
        db.close()

TIME_SLOTS = [
    "08:00", "08:30", "09:00", "09:30", "10:00", "10:30",
    "11:00", "11:30", "13:00", "13:30", "14:00", "14:30", "15:00", "15:30",
]

# === DATABASE INITIALIZATION — POSTGRESQL SYNTAX ===
def init_db():
    conn = get_db()
    if not conn:
        print("❌ Hindi makakonekta sa database!")
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
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK(status IN ('pending', 'approved', 'rejected')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(date, time)
        );
    """)
    
    cur.execute("SELECT id FROM users WHERE email = %s", ("nurse@school.ph",))
    nurse = cur.fetchone()
    if nurse is None:
        cur.execute(
            "INSERT INTO users (name, email, password_hash, role) VALUES (%s, %s, %s, %s)",
            ("School Nurse", "nurse@school.ph", generate_password_hash("nurse123"), "nurse"),
        )
    
    conn.commit()
    cur.close()
    conn.close()
    print("✅ Database ready!")

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

# === HTML CONTENT (HINDI BINAGO) ===
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
<div id="userDashboard" class="hidden min-h-screen flex flex-col md:flex-row">
    <!-- Mobile Menu Button -->
    <div class="md:hidden bg-blue-900 text-white p-3 flex justify-between items-center">
        <span class="font-bold">Clinic</span>
        <button id="userMenuBtn" class="text-xl">☰</button>
    </div>
    <!-- Sidebar -->
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
    <!-- Overlay -->
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
<div id="nurseDashboard" class="hidden min-h-screen flex flex-col md:flex-row">
    <!-- Mobile Menu Button -->
    <div class="md:hidden bg-blue-900 text-white p-3 flex justify-between items-center">
        <div>
            <span class="font-bold">NURSE PANEL</span>
            <p class="text-xs text-blue-200">Clinic Management</p>
        </div>
        <button id="nurseMenuBtn" class="text-xl">☰</button>
    </div>
    <!-- Sidebar -->
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
    <!-- Overlay -->
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
    
    <!-- Search Bar - Responsive -->
    <div class="flex flex-col sm:flex-row gap-3 mb-4">
        <input type="text" id="searchPatientName" placeholder="Type patient name..." 
            class="flex-1 px-4 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 w-full">
        <button onclick="searchPatientHistory()" 
            class="bg-blue-600 hover:bg-blue-700 text-white px-5 py-2.5 rounded-lg font-semibold whitespace-nowrap w-full sm:w-auto">
            <i class="fa-solid fa-magnifying-glass mr-2"></i> Search
        </button>
    </div>

    <!-- RESULT CONTAINER — ITO ANG PINAKAIMPORTANTENG INAYOS -->
    <div id="searchResult" class="mt-2 w-full overflow-x-auto">
        <!-- Lalabas dito ang detalye ng pasyente -->
        <div class="min-w-max">
            <!-- Siguraduhin na ang laman dito ay gumagamit ng:
                 - wrap text, hindi pilit na mahahaba
                 - responsive table o card-based layout sa phone
            -->
        </div>
    </div>
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
<!-- ⚡ JAVASCRIPT: Sidebar Toggle -->
<script>
// ===== USER SIDEBAR =====
function toggleUserSidebar() {
  const sidebar = document.getElementById('userSidebar');
  const overlay = document.getElementById('userOverlay');
  sidebar.classList.toggle('-translate-x-full');
  overlay.classList.toggle('hidden');
}
document.addEventListener('DOMContentLoaded', () => {
  const btn = document.getElementById('userMenuBtn');
  if (btn) btn.onclick = toggleUserSidebar;
});
// ===== NURSE SIDEBAR =====
function toggleNurseSidebar() {
  const sidebar = document.getElementById('nurseSidebar');
  const overlay = document.getElementById('nurseOverlay');
  sidebar.classList.toggle('-translate-x-full');
  overlay.classList.toggle('hidden');
}
document.addEventListener('DOMContentLoaded', () => {
  const btn = document.getElementById('nurseMenuBtn');
  if (btn) btn.onclick = toggleNurseSidebar;
});
</script>
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
    selectedTimeSlot = null;
    document.getElementById('aptTime').value = '';
    
    if (!selectedDate) {
        container.innerHTML = '<span class="text-gray-400 text-sm col-span-3">Select a date first...</span>';
        return;
    }
    const dateObj = new Date(selectedDate + 'T00:00:00');
    const dayOfWeek = dateObj.getDay();
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
    try {
        const data = await api('/api/stats');
        document.getElementById('statNew').textContent = data.newRequests;
        document.getElementById('statPending').textContent = data.pending;
        document.getElementById('statApproved').textContent = data.approved;
        document.getElementById('statRejected').textContent = data.rejected;
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

        // Apply role filter
        if (filterRole !== 'all') {
            apts = apts.filter(a => a.userRole === filterRole);
        }
        // Apply status filter
        if (filterStatus !== 'all') {
            apts = apts.filter(a => a.status === filterStatus);
        }

        const tbody = document.getElementById('allAppointmentsTable');
        if (apts.length === 0) {
            tbody.innerHTML = '<tr><td colspan="9" class="py-8 text-center text-gray-400 italic">No appointment requests found.</td></tr>';
            return;
        }

        const cls = { pending: 'status-pending', approved: 'status-approved', rejected: 'status-rejected' };
        const txt = { pending: '⏳ Pending', approved: '✅ Approved', rejected: '❌ Rejected' };

        tbody.innerHTML = apts.map((a, i) => `
            <tr class="border-b hover:bg-blue-50">
                <td class="py-2 px-2 text-center">${i + 1}</td>
                <td class="py-2 px-2">${a.userName}</td>
                <td class="py-2 px-2">${a.userRole}</td>
                <td class="py-2 px-2">${a.date}</td>
                <td class="py-2 px-2">${a.time}</td>
                <td class="py-2 px-2">${a.type}</td>
                <td class="py-2 px-2 max-w-xs truncate">${a.reason}</td>
                <td class="py-2 px-2 text-center">
                    <span class="px-2 py-0.5 rounded-full text-xs font-medium ${cls[a.status]}">${txt[a.status]}</span>
                </td>
                <td class="py-2 px-2 text-center">
                    ${a.status === 'pending' ? `
                        <button onclick="approveAppointment(${a.id})" class="text-green-600 hover:text-green-800 mr-2" title="Approve">
                            <i class="fa-solid fa-check"></i>
                        </button>
                        <button onclick="rejectAppointment(${a.id})" class="text-red-600 hover:text-red-800" title="Reject">
                            <i class="fa-solid fa-xmark"></i>
                        </button>
                    ` : ''}
                </td>
            </tr>`).join('');
    } catch (error) {
        document.getElementById('allAppointmentsTable').innerHTML = 
            `<tr><td colspan="9" class="py-8 text-center text-red-500">❌ ${error.message}</td></tr>`;
    }
}

// === APPROVE APPOINTMENT ===
async function approveAppointment(id) {
    if (!confirm('✅ Approve this appointment?')) return;
    try {
        await api(`/api/appointments/${id}/approve`, { method: 'POST' });
        alert('✅ Appointment approved!');
        updateStats();
        renderAllAppointments();
        renderHistory(false);
    } catch (error) {
        alert(`❌ ${error.message}`);
    }
}

// === REJECT APPOINTMENT ===
async function rejectAppointment(id) {
    if (!confirm('❌ Reject this appointment?')) return;
    try {
        await api(`/api/appointments/${id}/reject`, { method: 'POST' });
        alert('❌ Appointment rejected.');
        updateStats();
        renderAllAppointments();
        renderHistory(false);
    } catch (error) {
        alert(`❌ ${error.message}`);
    }
}

// === RENDER APPOINTMENT HISTORY ===
async function renderHistory(oldestFirst = false) {
    try {
        const data = await api('/api/appointments/all');
        let apts = data.appointments;

        // Sort by date/time
        apts.sort((a, b) => {
            const dateA = new Date(`${a.date}T${a.time}`);
            const dateB = new Date(`${b.date}T${b.time}`);
            return oldestFirst ? dateA - dateB : dateB - dateA;
        });

        const tbody = document.getElementById('historyTable');
        if (apts.length === 0) {
            tbody.innerHTML = '<tr><td colspan="8" class="py-8 text-center text-gray-400 italic">No appointment history yet.</td></tr>';
            return;
        }

        const cls = { pending: 'status-pending', approved: 'status-approved', rejected: 'status-rejected' };
        const txt = { pending: '⏳ Pending', approved: '✅ Approved', rejected: '❌ Rejected' };

        tbody.innerHTML = apts.map((a, i) => `
            <tr class="border-b hover:bg-blue-50">
                <td class="py-2 px-2 text-center">${i + 1}</td>
                <td class="py-2 px-2">${a.userName}</td>
                <td class="py-2 px-2">${a.userRole}</td>
                <td class="py-2 px-2">${a.date}</td>
                <td class="py-2 px-2">${a.time}</td>
                <td class="py-2 px-2">${a.type}</td>
                <td class="py-2 px-2 max-w-xs truncate">${a.reason}</td>
                <td class="py-2 px-2 text-center">
                    <span class="px-2 py-0.5 rounded-full text-xs font-medium ${cls[a.status]}">${txt[a.status]}</span>
                </td>
            </tr>`).join('');
    } catch (error) {
        document.getElementById('historyTable').innerHTML = 
            `<tr><td colspan="8" class="py-8 text-center text-red-500">❌ ${error.message}</td></tr>`;
    }
}

// === SEARCH PATIENT HISTORY ===
async function searchPatientHistory() {
    const name = document.getElementById('searchPatientName').value.trim().toLowerCase();
    const resultDiv = document.getElementById('patientHistoryResult');
    const tableBody = document.getElementById('patientHistoryTable');

    if (!name) {
        alert('⚠️ Please enter a name to search.');
        return;
    }

    try {
        const data = await api('/api/appointments/all');
        const matches = data.appointments.filter(a => 
            a.userName.toLowerCase().includes(name)
        );

        resultDiv.classList.remove('hidden');

        if (matches.length === 0) {
            tableBody.innerHTML = '<tr><td colspan="6" class="py-4 text-center text-gray-400 italic">No records found for that name.</td></tr>';
            return;
        }

        const cls = { pending: 'status-pending', approved: 'status-approved', rejected: 'status-rejected' };
        const txt = { pending: '⏳ Pending', approved: '✅ Approved', rejected: '❌ Rejected' };

        tableBody.innerHTML = matches.map((a, i) => `
            <tr class="border-b hover:bg-blue-50">
                <td class="py-2 px-2">${i + 1}</td>
                <td class="py-2 px-2">${a.date}</td>
                <td class="py-2 px-2">${a.time}</td>
                <td class="py-2 px-2">${a.type}</td>
                <td class="py-2 px-2 max-w-xs truncate">${a.reason}</td>
                <td class="py-2 px-2">
                    <span class="px-2 py-0.5 rounded-full text-xs font-medium ${cls[a.status]}">${txt[a.status]}</span>
                </td>
            </tr>`).join('');
    } catch (error) {
        resultDiv.classList.remove('hidden');
        tableBody.innerHTML = `<tr><td colspan="6" class="py-4 text-center text-red-500">❌ ${error.message}</td></tr>`;
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
    // Reset all views
    document.getElementById('authSection').classList.remove('hidden');
    document.getElementById('userDashboard').classList.add('hidden');
    document.getElementById('nurseDashboard').classList.add('hidden');
    // Reset forms
    document.getElementById('loginEmail').value = '';
    document.getElementById('loginPass').value = '';
    document.getElementById('authMsg').textContent = '';
    showAuthTab('login');
}

// === INITIALIZE ON PAGE LOAD ===
document.addEventListener('DOMContentLoaded', () => {
    setDateRestrictions();
});
</script>
"""
    return HTML_CONTENT

# === API ROUTES ===
@app.post("/api/register")
def register():
    data = request.get_json()
    name = data.get("name", "").strip()
    email = data.get("email", "").strip().lower()
    password = data.get("password", "")
    role = data.get("role", "")

    if not all([name, email, password, role]):
        return jsonify(error="All fields are required."), 400
    if role not in ("Student", "Teacher", "Staff"):
        return jsonify(error="Invalid role selected."), 400

    conn = get_db()
    if not conn:
        return jsonify(error="Database connection failed."), 500

    try:
        cur = conn.cursor()
        cur.execute("SELECT id FROM users WHERE email = %s", (email,))
        if cur.fetchone():
            return jsonify(error="Email already registered."), 409

        password_hash = generate_password_hash(password)
        cur.execute(
            "INSERT INTO users (name, email, password_hash, role) VALUES (%s, %s, %s, %s)",
            (name, email, password_hash, role)
        )
        conn.commit()
        return jsonify(message="Account created successfully!"), 201
    except Exception as e:
        conn.rollback()
        return jsonify(error=f"Registration failed: {str(e)}"), 500
    finally:
        cur.close()
        conn.close()

@app.post("/api/login")
def login():
    data = request.get_json()
    email = data.get("email", "").strip().lower()
    password = data.get("password", "")

    conn = get_db()
    if not conn:
        return jsonify(error="Database connection failed."), 500

    try:
        cur = conn.cursor()
        cur.execute("SELECT id, name, email, password_hash, role FROM users WHERE email = %s", (email,))
        row = cur.fetchone()
        if not row:
            return jsonify(error="Email not found."), 401
        if not check_password_hash(row[3], password):
            return jsonify(error="Incorrect password."), 401

        session["user_id"] = row[0]
        return jsonify(user={
            "id": row[0],
            "name": row[1],
            "email": row[2],
            "role": row[4]
        }), 200
    except Exception as e:
        return jsonify(error=f"Login failed: {str(e)}"), 500
    finally:
        cur.close()
        conn.close()

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

    try:
        cur = conn.cursor()
        cur.execute("SELECT time FROM appointments WHERE date = %s AND status != 'rejected'", (selected_date,))
        taken = [row[0] for row in cur.fetchall()]
        return jsonify(taken=taken), 200
    except Exception as e:
        return jsonify(error=str(e)), 500
    finally:
        cur.close()
        conn.close()

@app.post("/api/appointments")
@login_required
def create_appointment():
    data = request.get_json()
    date = data.get("date")
    time = data.get("time")
    apt_type = data.get("type")
    reason = data.get("reason")

    if not all([date, time, apt_type, reason]):
        return jsonify(error="All fields are required."), 400

    conn = get_db()
    if not conn:
        return jsonify(error="Database connection failed."), 500

    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO appointments (user_id, date, time, type, reason)
            VALUES (%s, %s, %s, %s, %s)
        """, (g.user["id"], date, time, apt_type, reason))
        conn.commit()
        return jsonify(message="Appointment submitted successfully!"), 201
    except Exception as e:
        conn.rollback()
        if "unique constraint" in str(e).lower():
            return jsonify(error="This time slot has already been booked."), 409
        return jsonify(error=f"Failed to create appointment: {str(e)}"), 500
    finally:
        cur.close()
        conn.close()

@app.get("/api/appointments")
@login_required
def get_my_appointments():
    conn = get_db()
    if not conn:
        return jsonify(error="Database connection failed."), 500

    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT a.id, u.name, u.role, a.date, a.time, a.type, a.reason, a.status
            FROM appointments a
            JOIN users u ON a.user_id = u.id
            WHERE a.user_id = %s
            ORDER BY a.date DESC, a.time DESC
        """, (g.user["id"],))
        appointments = [
            {
                "id": row[0],
                "userName": row[1],
                "userRole": row[2],
                "date": row[3],
                "time": row[4],
                "type": row[5],
                "reason": row[6],
                "status": row[7]
            }
            for row in cur.fetchall()
        ]
        return jsonify(appointments=appointments), 200
    except Exception as e:
        return jsonify(error=str(e)), 500
    finally:
        cur.close()
        conn.close()

@app.get("/api/appointments/all")
@nurse_required
def get_all_appointments():
    conn = get_db()
    if not conn:
        return jsonify(error="Database connection failed."), 500

    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT a.id, u.name, u.role, a.date, a.time, a.type, a.reason, a.status
            FROM appointments a
            JOIN users u ON a.user_id = u.id
            ORDER BY a.created_at DESC
        """)
        appointments = [
            {
                "id": row[0],
                "userName": row[1],
                "userRole": row[2],
                "date": row[3],
                "time": row[4],
                "type": row[5],
                "reason": row[6],
                "status": row[7]
            }
            for row in cur.fetchall()
        ]
        return jsonify(appointments=appointments), 200
    except Exception as e:
        return jsonify(error=str(e)), 500
    finally:
        cur.close()
        conn.close()

@app.post("/api/appointments/<int:apt_id>/approve")
@nurse_required
def approve(apt_id):
    conn = get_db()
    if not conn:
        return jsonify(error="Database connection failed."), 500

    try:
        cur = conn.cursor()
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
        conn.close()

@app.post("/api/appointments/<int:apt_id>/reject")
@nurse_required
def reject(apt_id):
    conn = get_db()
    if not conn:
        return jsonify(error="Database connection failed."), 500

    try:
        cur = conn.cursor()
        cur.execute("UPDATE appointments SET status = 'rejected' WHERE id = %s", (apt_id,))
        if cur.rowcount == 0:
            return jsonify(error="Appointment not found."), 404
        conn.commit()
        return jsonify(message="Appointment rejected."), 200
    except Exception as e:
        conn.rollback()
        return jsonify(error=str(e)), 500
    finally:
        cur.close()
        conn.close()

@app.get("/api/stats")
@nurse_required
def get_stats():
    conn = get_db()
    if not conn:
        return jsonify(error="Database connection failed."), 500

    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM appointments")
        total = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM appointments WHERE status = 'pending'")
        pending = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM appointments WHERE status = 'approved'")
        approved = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM appointments WHERE status = 'rejected'")
        rejected = cur.fetchone()[0]

        return jsonify({
            "newRequests": total,
            "pending": pending,
            "approved": approved,
            "rejected": rejected
        }), 200
    except Exception as e:
        return jsonify(error=str(e)), 500
    finally:
        cur.close()
        conn.close()

# === RUN SERVER ===
if __name__ == "__main__":
    with app.app_context():
        init_db()
    app.run(host="0.0.0.0", port=5050, debug=True)
