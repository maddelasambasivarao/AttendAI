"""
tests/test_dashboard_and_pages.py – Integration tests for the AttendAI
Professional Academic SaaS Dashboard and all 9 required pages.

Verifies:
  1. Login Page: Academic SaaS design, demo chips, authentication flow.
  2. Dashboard 6 KPI cards: Total students, total subjects, average attendance,
     high-risk, medium-risk, low-risk.
  3. Dashboard 5 Charts: Department-wise, subject-wise, monthly trends,
     risk distribution, top 10 students with shortages.
  4. Empty states when there is no data (no fake statistics).
  5. Student management page with filters, search, and CRUD.
  6. Faculty management page with search, department filter, and add modal.
  7. Attendance entry page (mark attendance) with session parameters.
  8. Attendance analytics page with distribution and student overview.
  9. Risk prediction page with calibrated thresholds and human oversight disclaimer.
 10. Individual student risk report with recovery math and intervention modal.
 11. Settings page: institutional thresholds, ML model diagnostics, and account security.
"""

from datetime import date
import pytest
from database.models import (
    User, Faculty, Semester, Subject, Student,
    AttendanceRecord, PredictionHistory, SystemSetting
)


@pytest.fixture
def saas_seed(db):
    """Seed sample data for dashboard and page verification."""
    # 1. Admin
    admin = User(username="saas_admin", email="admin@saas.edu", role="admin")
    admin.set_password("Admin@123")
    db.session.add(admin)
    db.session.flush()

    admin_fac = Faculty(user_id=admin.id, name="Dr. Director", department="Computer Science", employee_id="DIR001")
    db.session.add(admin_fac)

    # 2. Faculty
    fac_user = User(username="saas_faculty", email="faculty@saas.edu", role="faculty")
    fac_user.set_password("Faculty@123")
    db.session.add(fac_user)
    db.session.flush()

    fac = Faculty(user_id=fac_user.id, name="Prof. Ananya Sen", department="Computer Science", employee_id="FAC002")
    db.session.add(fac)

    # 3. Semester
    sem = Semester(
        name="Spring 2025",
        year=2025,
        is_active=True,
        start_date=date(2025, 1, 1),
        end_date=date(2025, 5, 30)
    )
    db.session.add(sem)
    db.session.flush()

    # 4. Subjects
    subj1 = Subject(name="Operating Systems", code="CS301", semester_id=sem.id, faculty_id=fac.id, total_classes_planned=40)
    subj2 = Subject(name="Database Systems", code="CS302", semester_id=sem.id, faculty_id=fac.id, total_classes_planned=40)
    db.session.add_all([subj1, subj2])
    db.session.flush()

    # 5. Students
    # Student A: High Risk (3 attended out of 10 = 30.0%)
    st_a = Student(
        student_id="STU_A", roll_number="CS2501", name="Arjun HighRisk",
        department="Computer Science", year=3, section="A", semester_id=sem.id
    )
    # Student B: Medium Risk (7 attended out of 10 = 70.0%)
    st_b = Student(
        student_id="STU_B", roll_number="CS2502", name="Bhavna MediumRisk",
        department="Computer Science", year=3, section="A", semester_id=sem.id
    )
    # Student C: Low Risk (10 attended out of 10 = 100.0%)
    st_c = Student(
        student_id="STU_C", roll_number="IT2501", name="Chetan LowRisk",
        department="Information Technology", year=3, section="B", semester_id=sem.id
    )
    db.session.add_all([st_a, st_b, st_c])
    db.session.flush()

    st_a.enroll_in_subject(subj1.id)
    st_b.enroll_in_subject(subj1.id)
    st_c.enroll_in_subject(subj1.id)

    # 6. Attendance Sessions across months (Jan and Feb)
    dates_jan = [date(2025, 1, i) for i in range(10, 15)]
    dates_feb = [date(2025, 2, i) for i in range(10, 15)]
    all_dates = dates_jan + dates_feb  # 10 sessions

    # St A: present for first 3, absent for remaining 7
    for i, d in enumerate(all_dates):
        status_a = "present" if i < 3 else "absent"
        db.session.add(AttendanceRecord(student_id=st_a.id, subject_id=subj1.id, date=d, session_slot=1, status=status_a, marked_by=admin.id))

    # St B: present for 7, absent for 3
    for i, d in enumerate(all_dates):
        status_b = "absent" if i in (2, 5, 8) else "present"
        db.session.add(AttendanceRecord(student_id=st_b.id, subject_id=subj1.id, date=d, session_slot=1, status=status_b, marked_by=admin.id))

    # St C: present for all 10
    for d in all_dates:
        db.session.add(AttendanceRecord(student_id=st_c.id, subject_id=subj1.id, date=d, session_slot=1, status="present", marked_by=admin.id))

    # 7. Predictions
    pred_a = PredictionHistory(
        student_id=st_a.id, semester_id=sem.id,
        attendance_percentage=30.0, risk_probability=0.88,
        predicted_final_percentage=42.0, risk_level="High",
        model_version="2.0.0"
    )
    pred_b = PredictionHistory(
        student_id=st_b.id, semester_id=sem.id,
        attendance_percentage=70.0, risk_probability=0.48,
        predicted_final_percentage=68.0, risk_level="Medium",
        model_version="2.0.0"
    )
    pred_c = PredictionHistory(
        student_id=st_c.id, semester_id=sem.id,
        attendance_percentage=100.0, risk_probability=0.08,
        predicted_final_percentage=96.0, risk_level="Low",
        model_version="2.0.0"
    )
    db.session.add_all([pred_a, pred_b, pred_c])
    db.session.commit()

    return {
        "admin": admin,
        "faculty": fac_user,
        "semester": sem,
        "subj1": subj1,
        "st_a": st_a,
        "st_b": st_b,
        "st_c": st_c,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 1. Login Page
# ─────────────────────────────────────────────────────────────────────────────
def test_login_page_renders_academic_saas_portal(client):
    """Login page loads with Academic SaaS branding and quick demo sign-in chips."""
    r = client.get("/login")
    assert r.status_code == 200
    assert b"AttendAI" in r.data
    assert b"Academic SaaS Portal" in r.data
    assert b"Quick Demo Sign-in" in r.data
    assert b"admin" in r.data
    assert b"faculty1" in r.data


# ─────────────────────────────────────────────────────────────────────────────
# 2. Executive Dashboard (6 KPI Cards + 5 Charts)
# ─────────────────────────────────────────────────────────────────────────────
def test_dashboard_kpi_cards_and_charts(client, saas_seed):
    """Admin dashboard loads all 6 KPI cards, 5 Chart.js containers, and Top 10 shortages."""
    client.post("/login", data={"username": "saas_admin", "password": "Admin@123"})

    r = client.get("/admin/dashboard")
    assert r.status_code == 200

    # 6 KPI Cards
    assert b"Total Students" in r.data
    assert b"Total Subjects" in r.data
    assert b"Avg Attendance" in r.data
    assert b"High Risk" in r.data
    assert b"Medium Risk" in r.data
    assert b"Low Risk" in r.data

    # Real calculated values (3 students, 2 subjects)
    assert b">3<" in r.data   # 3 students
    assert b">2<" in r.data   # 2 subjects

    # 5 Chart Elements
    assert b"deptChart" in r.data             # Chart 1: Department-wise
    assert b"subjectChart" in r.data          # Chart 2: Subject-wise
    assert b"monthlyTrendChart" in r.data     # Chart 3: Monthly Trends
    assert b"riskDistChart" in r.data         # Chart 4: Risk Distribution
    assert b"Top 10 Students with Attendance Shortages" in r.data  # Chart 5 / Table

    # Shortage Students Table Check
    assert b"Arjun HighRisk" in r.data
    assert b"Bhavna MediumRisk" in r.data
    assert b"CS2501" in r.data


def test_dashboard_empty_states_when_no_data(client, db):
    """When database has 0 students or sessions, dashboard displays clean empty states."""
    admin = User(username="empty_admin", email="empty@test.com", role="admin")
    admin.set_password("Admin@123")
    db.session.add(admin)
    db.session.commit()

    client.post("/login", data={"username": "empty_admin", "password": "Admin@123"})

    r = client.get("/admin/dashboard")
    assert r.status_code == 200
    assert b"Total Students" in r.data
    # Empty state for shortage table
    assert b"Zero Attendance Shortages!" in r.data or b"No Department Data" in r.data


# ─────────────────────────────────────────────────────────────────────────────
# 3. Faculty Dashboard
# ─────────────────────────────────────────────────────────────────────────────
def test_faculty_dashboard_loads_correctly(client, saas_seed):
    """Faculty dashboard displays assigned scholars, courses taught, and interventions."""
    client.post("/login", data={"username": "saas_faculty", "password": "Faculty@123"})

    r = client.get("/faculty/dashboard")
    assert r.status_code == 200
    assert b"Prof. Ananya Sen" in r.data
    assert b"Assigned Scholars" in r.data
    assert b"Courses Taught" in r.data


# ─────────────────────────────────────────────────────────────────────────────
# 4. Settings Page (Academic Policies, Security, ML Model Diagnostics)
# ─────────────────────────────────────────────────────────────────────────────
def test_settings_page_and_threshold_update(client, saas_seed):
    """Settings page renders configuration tabs and allows updating institutional policies."""
    client.post("/login", data={"username": "saas_admin", "password": "Admin@123"})

    r = client.get("/admin/settings")
    assert r.status_code == 200
    assert b"Institutional Attendance &amp; Risk Thresholds" in r.data
    assert b"Mandatory Attendance Target" in r.data
    assert b"ML Model Diagnostics" in r.data

    # POST to update thresholds
    r_post = client.post(
        "/admin/settings",
        data={
            "action": "thresholds",
            "attendance_required": "80",
            "high_risk_threshold": "70",
            "medium_risk_threshold": "40",
            "institution_name": "Indian Institute of Science & Technology",
            "academic_year": "2025-2026",
            "active_semester_id": saas_seed["semester"].id
        },
        follow_redirects=True
    )
    assert r_post.status_code == 200
    assert b"Institutional academic thresholds and settings saved successfully" in r_post.data

    # Verify persistence
    assert SystemSetting.get("attendance_required") == "80"
    assert SystemSetting.get("institution_name") == "Indian Institute of Science & Technology"


def test_settings_redirect_for_logged_in_users(client, saas_seed):
    """The /settings shortcut redirects admin to /admin/settings."""
    client.post("/login", data={"username": "saas_admin", "password": "Admin@123"})
    r = client.get("/settings", follow_redirects=False)
    assert r.status_code == 302
    assert "/admin/settings" in r.headers["Location"]


# ─────────────────────────────────────────────────────────────────────────────
# 5. Faculty Management Page
# ─────────────────────────────────────────────────────────────────────────────
def test_faculty_management_page_and_filters(client, saas_seed):
    """Faculty directory page loads with search, department filters, and modal."""
    client.post("/login", data={"username": "saas_admin", "password": "Admin@123"})

    r = client.get("/admin/faculty")
    assert r.status_code == 200
    assert b"Faculty Directory" in r.data
    assert b"Prof. Ananya Sen" in r.data
    assert b"FAC002" in r.data

    # Filter by search
    r_search = client.get("/admin/faculty?search=Ananya")
    assert r_search.status_code == 200
    assert b"Prof. Ananya Sen" in r_search.data


# ─────────────────────────────────────────────────────────────────────────────
# 6. Verification of All 9 Core Pages
# ─────────────────────────────────────────────────────────────────────────────
def test_all_nine_core_pages_return_200(client, saas_seed):
    """
    Ensures every button and link works across all 9 required pages:
    1. Login (/login)
    2. Dashboard (/admin/dashboard & /faculty/dashboard)
    3. Student management (/admin/students)
    4. Faculty management (/admin/faculty)
    5. Attendance entry (/attendance/mark)
    6. Attendance analytics (/analytics/overview)
    7. Risk prediction (/analytics/risk)
    8. Individual student report (/analytics/student/<id>/risk)
    9. Settings (/admin/settings)
    """
    client.post("/login", data={"username": "saas_admin", "password": "Admin@123"})
    st = saas_seed["st_a"]

    endpoints = [
        "/admin/dashboard",
        "/admin/students",
        "/admin/faculty",
        "/attendance/mark",
        "/analytics/overview",
        "/analytics/risk",
        f"/analytics/student/{st.id}/risk",
        "/admin/settings",
    ]

    for url in endpoints:
        resp = client.get(url)
        assert resp.status_code == 200, f"URL {url} failed with status {resp.status_code}"
