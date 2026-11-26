"""
tests/test_risk_monitoring.py – Comprehensive unit and integration tests
for the Risk Monitoring & Faculty Intervention Module.

Covers:
  1. Student current attendance % and ML-predicted shortage probability.
  2. Calibrated Low, Medium, High risk tiers with configurable thresholds.
  3. Actionable recommendations based on attendance, trend, absences, remaining classes.
  4. Deterministic projections: classes needed, max possible %, safe misses, feasibility.
  5. Risk monitoring dashboard and table with multi-parameter filters.
  6. Individual student risk reports with complete diagnostics.
  7. Prediction history persistence with timestamp, probability, and model version.
  8. Clear disclaimer note that predictions are probabilistic estimates requiring faculty review.
  9. Faculty intervention tracker: student contacted, explanation received, and attendance improved outcome.
"""

from datetime import date, datetime, timedelta
import pytest
from database.models import (
    User, Faculty, Semester, Subject, Student,
    AttendanceRecord, PredictionHistory, Intervention
)
from routes.analytics import classify_risk_tier, DEFAULT_HIGH_THRESHOLD, DEFAULT_MEDIUM_THRESHOLD


@pytest.fixture
def risk_data(db):
    """Seed comprehensive test data for risk monitoring and intervention testing."""
    # 1. Admin
    admin_user = User(username="risk_admin", email="admin@test.com", role="admin")
    admin_user.set_password("Admin@123")
    db.session.add(admin_user)
    db.session.flush()

    admin_fac = Faculty(user_id=admin_user.id, name="Dr. Administrator", department="CS", employee_id="RADM001")
    db.session.add(admin_fac)

    # 2. Faculty
    fac_user = User(username="risk_faculty", email="fac@test.com", role="faculty")
    fac_user.set_password("Faculty@123")
    db.session.add(fac_user)
    db.session.flush()

    fac = Faculty(user_id=fac_user.id, name="Prof. Sharma", department="CS", employee_id="RFAC001")
    db.session.add(fac)

    # 3. Semester
    sem = Semester(name="Semester 4 - 2025", year=2025, is_active=True, start_date=date(2025, 1, 1), end_date=date(2025, 6, 30))
    db.session.add(sem)
    db.session.flush()

    # 4. Subject
    subj = Subject(name="Deep Learning", code="CS701", semester_id=sem.id, faculty_id=fac.id, total_classes_planned=40)
    db.session.add(subj)
    db.session.flush()

    # 5. Students
    # High Risk Student: 4 attended out of 10 conducted (40.0%), 3 consecutive absences
    st_high = Student(
        student_id="STU_HIGH", roll_number="CS2025_H1", name="Rohan HighRisk",
        department="Computer Science", year=2, section="A", semester_id=sem.id
    )
    # Medium Risk Student: 7 attended out of 10 conducted (70.0%)
    st_med = Student(
        student_id="STU_MED", roll_number="CS2025_M1", name="Priya MediumRisk",
        department="Computer Science", year=2, section="A", semester_id=sem.id
    )
    # Low Risk Student: 10 attended out of 10 conducted (100.0%)
    st_low = Student(
        student_id="STU_LOW", roll_number="CS2025_L1", name="Aarav LowRisk",
        department="Information Technology", year=2, section="B", semester_id=sem.id
    )
    db.session.add_all([st_high, st_med, st_low])
    db.session.flush()

    st_high.enroll_in_subject(subj.id)
    st_med.enroll_in_subject(subj.id)
    st_low.enroll_in_subject(subj.id)

    # Seed 10 attendance sessions
    dates = [date(2025, 2, i) for i in range(1, 11)]

    # High risk student: 4 present, 6 absent (ends with 3 consecutive absents)
    statuses_high = ["present", "present", "present", "present", "absent", "absent", "absent", "absent", "absent", "absent"]
    for d, s in zip(dates, statuses_high):
        db.session.add(AttendanceRecord(student_id=st_high.id, subject_id=subj.id, date=d, session_slot=1, status=s, marked_by=admin_user.id))

    # Medium risk student: 7 present, 3 absent
    statuses_med = ["present", "present", "absent", "present", "present", "absent", "present", "present", "absent", "present"]
    for d, s in zip(dates, statuses_med):
        db.session.add(AttendanceRecord(student_id=st_med.id, subject_id=subj.id, date=d, session_slot=1, status=s, marked_by=admin_user.id))

    # Low risk student: 10 present
    for d in dates:
        db.session.add(AttendanceRecord(student_id=st_low.id, subject_id=subj.id, date=d, session_slot=1, status="present", marked_by=admin_user.id))

    db.session.commit()

    return {
        "admin": admin_user,
        "faculty": fac_user,
        "faculty_prof": fac,
        "semester": sem,
        "subject": subj,
        "st_high": st_high,
        "st_med": st_med,
        "st_low": st_low,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 1. Configurable Risk Threshold Calibration
# ─────────────────────────────────────────────────────────────────────────────
def test_risk_tier_classification_and_calibration():
    """Verify calibrated default boundaries and custom threshold configuration."""
    # Default: High >= 0.65, Medium >= 0.35, Low < 0.35
    assert classify_risk_tier(0.95) == "High"
    assert classify_risk_tier(0.65) == "High"
    assert classify_risk_tier(0.64) == "Medium"
    assert classify_risk_tier(0.35) == "Medium"
    assert classify_risk_tier(0.34) == "Low"
    assert classify_risk_tier(0.05) == "Low"

    # Custom Configurable Thresholds: High >= 0.80, Medium >= 0.50
    assert classify_risk_tier(0.70, high_threshold=0.80, medium_threshold=0.50) == "Medium"
    assert classify_risk_tier(0.85, high_threshold=0.80, medium_threshold=0.50) == "High"
    assert classify_risk_tier(0.40, high_threshold=0.80, medium_threshold=0.50) == "Low"


# ─────────────────────────────────────────────────────────────────────────────
# 2. Risk Monitoring Dashboard (Requirements 1, 2, 4, 5, 8)
# ─────────────────────────────────────────────────────────────────────────────
def test_risk_monitoring_dashboard_loads(client, risk_data):
    """Dashboard loads with disclaimer note, calibration methodology, and student metrics."""
    client.post("/login", data={"username": "risk_faculty", "password": "Faculty@123"})

    r = client.get("/analytics/risk")
    assert r.status_code == 200

    # Requirement 8: Faculty Review Disclaimer Note
    assert b"Faculty Advisory" in r.data
    assert b"Human Oversight Policy" in r.data
    assert b"probabilistic estimates" in r.data

    # Requirement 2: Calibration & Methodology Documentation
    assert b"Methodology" in r.data
    assert b"Calibration" in r.data
    assert b"Risk Tier Calibration" in r.data

    # Requirement 1: Attendance % and ML Risk Probability %
    assert b"Rohan HighRisk" in r.data
    assert b"CS2025_H1" in r.data

    # Requirement 4: Deterministic Projection
    assert b"Deterministic Projection" in r.data


def test_risk_monitoring_dashboard_filters(client, risk_data):
    """Filters by risk tier, department, and student search."""
    client.post("/login", data={"username": "risk_faculty", "password": "Faculty@123"})

    # Filter High Risk only
    r_high = client.get("/analytics/risk?risk_level=High")
    assert r_high.status_code == 200
    assert b"Rohan HighRisk" in r_high.data
    assert b"Aarav LowRisk" not in r_high.data

    # Filter by department "Information Technology"
    r_dept = client.get("/analytics/risk?department=Information+Technology")
    assert r_dept.status_code == 200
    assert b"Aarav LowRisk" in r_dept.data
    assert b"Rohan HighRisk" not in r_dept.data

    # Filter by search roll number
    r_search = client.get("/analytics/risk?search=CS2025_M1")
    assert r_search.status_code == 200
    assert b"Priya MediumRisk" in r_search.data
    assert b"Rohan HighRisk" not in r_search.data


# ─────────────────────────────────────────────────────────────────────────────
# 3. Individual Student Risk Report (Requirements 1, 3, 4, 6, 7, 8)
# ─────────────────────────────────────────────────────────────────────────────
def test_individual_student_risk_report(client, db, risk_data):
    """Student risk report displays probability, deterministic recovery, explanations, recommendations, and audit history."""
    client.post("/login", data={"username": "risk_faculty", "password": "Faculty@123"})
    st = risk_data["st_high"]

    r = client.get(f"/analytics/student/{st.id}/risk")
    assert r.status_code == 200

    # Student Details
    assert b"Rohan HighRisk" in r.data
    assert b"CS2025_H1" in r.data

    # Requirement 8: Advisory disclaimer note
    assert b"Faculty Advisory" in r.data
    assert b"Human Oversight Policy" in r.data

    # Requirement 1 & 2: ML Probability and Calibrated Risk Tier
    assert b"Risk" in r.data
    assert b"ML Shortage Probability" in r.data

    # Requirement 4: Deterministic Projections
    assert b"Deterministic Attendance Projection" in r.data
    assert b"Consecutive Classes Required" in r.data
    assert b"Max Possible Final Attendance" in r.data

    # Requirement 3: Actionable recommendations
    assert b"Actionable Improvement Guidance" in r.data

    # Requirement 7: Prediction history snapshot saved to DB
    history_count = PredictionHistory.query.filter_by(student_id=st.id).count()
    assert history_count >= 1
    latest_hist = PredictionHistory.query.filter_by(student_id=st.id).first()
    assert latest_hist.model_version is not None
    assert latest_hist.risk_probability is not None


# ─────────────────────────────────────────────────────────────────────────────
# 4. Faculty Intervention Tracker (Requirement 9)
# ─────────────────────────────────────────────────────────────────────────────
def test_faculty_log_intervention_with_contact_and_explanation(client, db, risk_data):
    """Faculty logs an intervention recording contact status, method, and student explanation."""
    client.post("/login", data={"username": "risk_faculty", "password": "Faculty@123"})
    st = risk_data["st_high"]

    r = client.post(
        f"/analytics/intervention/log/{st.id}",
        data={
            "intervention_type": "counselling",
            "student_contacted": "1",
            "contact_method": "In-Person Meeting",
            "contact_date": "2025-02-15",
            "explanation_received": "1",
            "student_explanation": "Severe jaundice and hospitalization during early semester.",
            "notes": "Agreed to submit hospital discharge summary to HOD office.",
            "follow_up_date": "2025-02-25"
        },
        follow_redirects=True
    )
    assert r.status_code == 200
    assert b"Intervention logged successfully" in r.data

    # Verify database record
    intv = Intervention.query.filter_by(student_id=st.id).first()
    assert intv is not None
    assert intv.student_contacted is True
    assert intv.contact_method == "In-Person Meeting"
    assert intv.explanation_received is True
    assert "jaundice" in intv.student_explanation.lower()
    assert intv.attendance_improved == "pending"
    assert intv.attendance_at_intervention == 40.0


def test_faculty_update_intervention_outcome(client, db, risk_data):
    """Faculty updates intervention outcome tracking whether attendance improved afterwards."""
    client.post("/login", data={"username": "risk_faculty", "password": "Faculty@123"})
    st = risk_data["st_high"]
    fac = risk_data["faculty_prof"]

    # Pre-create intervention
    intv = Intervention(
        student_id=st.id,
        faculty_id=fac.id,
        intervention_type="counselling",
        notes="Initial meeting conducted",
        student_contacted=True,
        contact_method="Phone Call",
        explanation_received=True,
        student_explanation="Fever",
        attendance_improved="pending",
        attendance_at_intervention=40.0
    )
    db.session.add(intv)
    db.session.commit()

    # Update intervention outcome
    r = client.post(
        f"/analytics/intervention/update/{intv.id}",
        data={
            "status": "resolved",
            "attendance_improved": "improved",
            "student_explanation": "Medical certificate verified by HOD",
            "notes": "Student attended all 4 follow-up classes"
        },
        follow_redirects=True
    )
    assert r.status_code == 200
    assert b"Intervention #" in r.data

    # Verify updated record in DB
    db.session.refresh(intv)
    assert intv.status == "resolved"
    assert intv.attendance_improved == "improved"
    assert "verified" in intv.student_explanation
    assert intv.post_intervention_attendance_pct is not None


def test_interventions_dashboard_view(client, db, risk_data):
    """Central interventions list loads with filters and outcome success rate."""
    client.post("/login", data={"username": "risk_faculty", "password": "Faculty@123"})
    st = risk_data["st_high"]
    fac = risk_data["faculty_prof"]

    intv = Intervention(
        student_id=st.id,
        faculty_id=fac.id,
        intervention_type="parent_contact",
        notes="Parent notified via phone",
        student_contacted=True,
        contact_method="Phone Call",
        explanation_received=True,
        student_explanation="Parent confirmed illness",
        attendance_improved="improved",
        attendance_at_intervention=40.0,
        status="resolved"
    )
    db.session.add(intv)
    db.session.commit()

    r = client.get("/analytics/interventions")
    assert r.status_code == 200
    assert b"Faculty Intervention Tracker" in r.data
    assert b"Rohan HighRisk" in r.data
    assert b"Phone Call" in r.data
    assert b"Improved" in r.data


# ─────────────────────────────────────────────────────────────────────────────
# 5. Batch Prediction & API
# ─────────────────────────────────────────────────────────────────────────────
def test_batch_prediction_trigger(client, db, risk_data):
    """Batch prediction triggers predictions for all active students in semester."""
    client.post("/login", data={"username": "risk_admin", "password": "Admin@123"})

    r = client.post("/analytics/predict-all", follow_redirects=True)
    assert r.status_code == 200
    assert b"Batch ML predictions complete" in r.data

    # Verify predictions logged
    assert PredictionHistory.query.count() >= 3
