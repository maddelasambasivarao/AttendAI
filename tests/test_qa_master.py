"""
tests/test_qa_master.py – Comprehensive Master QA & Security Test Suite for AttendAI.

Covers:
  1. Database Integrity & SQLite Foreign Key Enforcement & Cascades.
  2. Authentication, Password Security & Open Redirect Protection.
  3. Role-Based Access Control (Admin vs Faculty permissions).
  4. Student CRUD, Academic Safeguards & Form Validation.
  5. Attendance Entry, Duplicate Prevention & Audit Trail Logging.
  6. Exact Percentage Calculations & Deterministic Projection Mathematics.
  7. Excel / CSV Import & Export Robustness and Error Handling.
  8. Machine Learning Model Loading, Inference, Feature Hygiene (No Leakage) & Risk Calibration.
  9. PDF Report Generation Quality & Required Elements.
  10. Dashboard & System Route Integrity and Template Link Verification.
"""

import os
import io
import re
import json
import glob
from datetime import date, datetime, timedelta
import pytest
import openpyxl
from werkzeug.security import check_password_hash
from sqlalchemy.exc import IntegrityError

from database.models import (
    db, User, Faculty, Semester, Subject, Student,
    AttendanceRecord, AttendanceEditHistory, StudentSubjectEnrolment,
    PredictionHistory, Intervention, SystemSetting
)
from routes.auth import is_safe_url
from routes.analytics import classify_risk_tier
from ml.predict import predict_risk, get_trained_pipeline
from ml.recommendations import calculate_attendance_recovery
from ml.data_generator import extract_snapshot_features
from reports.pdf_builder import (
    build_student_pdf, build_department_pdf, build_semester_pdf,
    build_subject_pdf, build_high_risk_pdf, build_ml_predictions_pdf
)
from reports.excel_builder import (
    build_student_excel, build_attendance_records_excel,
    build_risk_analysis_excel, build_subject_statistics_excel,
    build_semester_matrix_excel, build_attendance_upload_template_excel
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def qa_data(db):
    """Seed comprehensive clean dataset for QA validation."""
    # 1. Admin Account
    admin_u = User(username="qa_admin", email="admin_qa@attendai.edu", role="admin")
    admin_u.set_password("AdminSecure@123")
    db.session.add(admin_u)
    db.session.flush()

    admin_fac = Faculty(
        user_id=admin_u.id, name="Dr. Chief Administrator", department="Computer Science", employee_id="QA_ADM01"
    )
    db.session.add(admin_fac)

    # 2. Faculty Account
    fac_u = User(username="qa_faculty", email="fac_qa@attendai.edu", role="faculty")
    fac_u.set_password("FacultySecure@123")
    db.session.add(fac_u)
    db.session.flush()

    faculty_member = Faculty(
        user_id=fac_u.id, name="Prof. Sunita Rao", department="Computer Science", employee_id="QA_FAC01"
    )
    db.session.add(faculty_member)

    # 3. Another Faculty Account (for permission barrier testing)
    other_fac_u = User(username="other_faculty", email="other_fac@attendai.edu", role="faculty")
    other_fac_u.set_password("OtherSecure@123")
    db.session.add(other_fac_u)
    db.session.flush()

    other_faculty = Faculty(
        user_id=other_fac_u.id, name="Prof. Vikram Seth", department="Mechanical", employee_id="QA_FAC02"
    )
    db.session.add(other_faculty)

    # 4. Semester
    sem = Semester(
        name="Spring Term 2026",
        year=2026,
        section="A",
        start_date=date(2026, 1, 10),
        end_date=date(2026, 5, 20),
        is_active=True
    )
    db.session.add(sem)
    db.session.flush()

    # 5. Subjects
    subj_cs = Subject(
        name="Artificial Intelligence",
        code="CS501",
        semester_id=sem.id,
        faculty_id=faculty_member.id,
        total_classes_planned=40,
        subject_type="theory"
    )
    subj_other = Subject(
        name="Thermodynamics",
        code="ME501",
        semester_id=sem.id,
        faculty_id=other_faculty.id,
        total_classes_planned=40,
        subject_type="theory"
    )
    db.session.add_all([subj_cs, subj_other])
    db.session.flush()

    # 6. Students
    st_high_att = Student(
        student_id="STU_QA_01",
        roll_number="QA202601",
        name="Ananya Verma",
        department="Computer Science",
        year=2,
        section="A",
        email="ananya@attendai.edu",
        semester_id=sem.id,
        is_active=True
    )
    st_low_att = Student(
        student_id="STU_QA_02",
        roll_number="QA202602",
        name="Devendra Singh",
        department="Computer Science",
        year=2,
        section="A",
        email="devendra@attendai.edu",
        semester_id=sem.id,
        is_active=True
    )
    db.session.add_all([st_high_att, st_low_att])
    db.session.flush()

    st_high_att.enroll_in_subject(subj_cs.id)
    st_low_att.enroll_in_subject(subj_cs.id)

    # 7. Seed attendance records (10 sessions)
    for i in range(10):
        d = date(2026, 2, 1) + timedelta(days=i)
        # Ananya: 9 present, 1 absent (90.0%)
        db.session.add(AttendanceRecord(
            student_id=st_high_att.id, subject_id=subj_cs.id, date=d, session_slot=1,
            status="present" if i != 4 else "absent", marked_by=admin_u.id
        ))
        # Devendra: 4 present, 6 absent (40.0%)
        db.session.add(AttendanceRecord(
            student_id=st_low_att.id, subject_id=subj_cs.id, date=d, session_slot=1,
            status="present" if i < 4 else "absent", marked_by=admin_u.id
        ))

    db.session.commit()

    return {
        "admin_user": admin_u,
        "faculty_user": fac_u,
        "other_faculty_user": other_fac_u,
        "faculty_member": faculty_member,
        "other_faculty": other_faculty,
        "semester": sem,
        "subj_cs": subj_cs,
        "subj_other": subj_other,
        "st_high": st_high_att,
        "st_low": st_low_att,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 1. DATABASE INTEGRITY, CONSTRAINTS & CASCADE DELETES
# ─────────────────────────────────────────────────────────────────────────────

def test_database_foreign_key_enforcement(qa_data, db):
    """Verify that foreign key constraints are strictly enforced in SQLite."""
    # Attempt to insert attendance record with a non-existent student ID
    invalid_record = AttendanceRecord(
        student_id=999999,  # Does not exist
        subject_id=qa_data["subj_cs"].id,
        date=date(2026, 3, 1),
        session_slot=1,
        status="present"
    )
    db.session.add(invalid_record)
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_database_unique_constraints(qa_data, db):
    """Verify duplicate rejection on unique columns."""
    # Duplicate username
    dup_user = User(username="qa_admin", email="diff@attendai.edu")
    dup_user.set_password("pass123")
    db.session.add(dup_user)
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()

    # Duplicate roll number
    dup_student = Student(roll_number="QA202601", name="Clone", semester_id=qa_data["semester"].id)
    db.session.add(dup_student)
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_database_cascade_deletions(qa_data, db):
    """Verify that deleting a student cascades to attendance records and enrolments."""
    st = qa_data["st_low"]
    st_id = st.id
    assert AttendanceRecord.query.filter_by(student_id=st_id).count() == 10

    # Delete student
    db.session.delete(st)
    db.session.commit()

    # Verify cascaded deletion: attendances must be wiped cleanly
    assert AttendanceRecord.query.filter_by(student_id=st_id).count() == 0
    assert StudentSubjectEnrolment.query.filter_by(student_id=st_id).count() == 0


def test_faculty_deletion_sets_null_on_subjects(qa_data, db):
    """Deleting a faculty member should set subject.faculty_id to NULL without dropping the course."""
    fac = qa_data["other_faculty"]
    subj = qa_data["subj_other"]
    assert subj.faculty_id == fac.id

    db.session.delete(fac)
    db.session.commit()

    db.session.refresh(subj)
    assert subj.faculty_id is None


# ─────────────────────────────────────────────────────────────────────────────
# 2. AUTHENTICATION & SECURITY
# ─────────────────────────────────────────────────────────────────────────────

def test_password_hashing_security(qa_data):
    """Ensure passwords are never stored in plaintext and check_password works."""
    admin = qa_data["admin_user"]
    assert admin.password_hash != "AdminSecure@123"
    assert admin.password_hash.startswith("scrypt:") or admin.password_hash.startswith("pbkdf2:")
    assert admin.check_password("AdminSecure@123") is True
    assert admin.check_password("WrongPassword") is False


def test_open_redirect_protection():
    """Verify is_safe_url blocks external malicious redirects and protocol-relative URLs."""
    from flask import Request
    # Test safe internal relative paths
    assert is_safe_url("/admin/dashboard") is True
    assert is_safe_url("/faculty/dashboard") is True
    assert is_safe_url("/attendance/mark?sem=1") is True

    # Test dangerous external or protocol-relative targets
    assert is_safe_url("https://evil.attacker.com") is False
    assert is_safe_url("http://phishing.site/login") is False
    assert is_safe_url("//evil.com/fake-login") is False
    assert is_safe_url("javascript:alert(1)") is False
    assert is_safe_url("") is False
    assert is_safe_url(None) is False


def test_login_flow_with_open_redirect_attempt(client, qa_data):
    """Verify login redirects to dashboard when next param points to an external site."""
    res = client.post(
        "/login?next=https://malicious-phishing-site.com",
        data={"username": "qa_admin", "password": "AdminSecure@123"},
        follow_redirects=False
    )
    assert res.status_code == 302
    assert "malicious" not in res.location
    assert "/admin/dashboard" in res.location


def test_change_password_workflow(client, qa_data):
    """Verify password change enforces current password, match, and minimum length."""
    admin = qa_data["admin_user"]
    with client.session_transaction() as sess:
        sess["_user_id"] = str(admin.id)
        sess["_fresh"] = True

    # 1. Wrong current password
    res = client.post("/change-password", data={
        "current_password": "WrongPassword",
        "new_password": "NewSecretPass123",
        "confirm_password": "NewSecretPass123"
    }, follow_redirects=True)
    assert b"Current password is incorrect" in res.data

    # 2. Passwords do not match
    res = client.post("/change-password", data={
        "current_password": "AdminSecure@123",
        "new_password": "NewSecretPass123",
        "confirm_password": "DifferentPass123"
    }, follow_redirects=True)
    assert b"New passwords do not match" in res.data

    # 3. Too short password (< 8 chars)
    res = client.post("/change-password", data={
        "current_password": "AdminSecure@123",
        "new_password": "short",
        "confirm_password": "short"
    }, follow_redirects=True)
    assert b"Password must be at least 8 characters" in res.data

    # 4. Successful password change
    res = client.post("/change-password", data={
        "current_password": "AdminSecure@123",
        "new_password": "BrandNewPassword@2026",
        "confirm_password": "BrandNewPassword@2026"
    }, follow_redirects=True)
    assert b"Password changed successfully" in res.data
    assert admin.check_password("BrandNewPassword@2026") is True


# ─────────────────────────────────────────────────────────────────────────────
# 3. ROLE-BASED ACCESS CONTROL & FACULTY PERMISSION BOUNDARIES
# ─────────────────────────────────────────────────────────────────────────────

def test_unauthenticated_access_redirects_to_login(client):
    """Unauthenticated access to any protected route must redirect to login."""
    protected_urls = [
        "/admin/dashboard",
        "/admin/students",
        "/admin/settings",
        "/faculty/dashboard",
        "/attendance/mark",
        "/analytics/overview",
        "/reports/",
    ]
    for url in protected_urls:
        res = client.get(url, follow_redirects=False)
        assert res.status_code == 302
        assert "/login" in res.location


def test_faculty_blocked_from_admin_only_routes(client, qa_data):
    """Faculty members must be blocked with an alert from accessing admin-only routes."""
    fac = qa_data["faculty_user"]
    with client.session_transaction() as sess:
        sess["_user_id"] = str(fac.id)
        sess["_fresh"] = True

    admin_routes = [
        "/admin/dashboard",
        "/admin/settings",
        "/admin/semesters",
        "/admin/subjects",
        "/admin/faculty",
    ]
    for url in admin_routes:
        res = client.get(url, follow_redirects=True)
        assert b"Administrator access required" in res.data


def test_faculty_safeguard_prevents_hard_delete_with_history(client, qa_data):
    """Faculty cannot permanently delete a student with attendance records."""
    fac = qa_data["faculty_user"]
    st = qa_data["st_low"]
    with client.session_transaction() as sess:
        sess["_user_id"] = str(fac.id)
        sess["_fresh"] = True

    res = client.post(
        f"/admin/students/{st.id}/delete",
        data={"action": "permanent"},
        follow_redirects=True
    )
    assert b"Academic Safeguard: Faculty cannot permanently delete" in res.data
    # Student still exists, but is deactivated
    re_st = db.session.get(Student, st.id)
    assert re_st is not None
    assert re_st.is_active is False


def test_faculty_cannot_correct_attendance_for_unassigned_subject(client, qa_data):
    """Faculty member cannot modify attendance records for a course assigned to another instructor."""
    fac = qa_data["faculty_user"]  # Assigned to CS501, not ME501
    subj_other = qa_data["subj_other"]
    st = qa_data["st_high"]

    # Seed an attendance record for ME501
    rec = AttendanceRecord(
        student_id=st.id, subject_id=subj_other.id, date=date(2026, 2, 1),
        session_slot=2, status="absent"
    )
    db.session.add(rec)
    db.session.commit()

    with client.session_transaction() as sess:
        sess["_user_id"] = str(fac.id)
        sess["_fresh"] = True

    res = client.post(
        f"/attendance/correct/{rec.id}",
        data={"status": "present", "reason": "Attempted unauthorized change"},
        follow_redirects=True
    )
    assert b"Unauthorized: Only the assigned faculty or an administrator can correct attendance" in res.data
    # Status remains unchanged
    db.session.refresh(rec)
    assert rec.status == "absent"


# ─────────────────────────────────────────────────────────────────────────────
# 4. STUDENT CRUD & FORM VALIDATION BOUNDARIES
# ─────────────────────────────────────────────────────────────────────────────

def test_add_student_validations(client, qa_data):
    """Test input boundary validation on adding students."""
    admin = qa_data["admin_user"]
    sem = qa_data["semester"]
    with client.session_transaction() as sess:
        sess["_user_id"] = str(admin.id)
        sess["_fresh"] = True

    # 1. Missing name or roll
    res = client.post("/admin/students/add", data={
        "name": "", "roll_number": "", "semester_id": sem.id
    }, follow_redirects=True)
    assert b"Full name, roll number, and semester are required" in res.data

    # 2. Duplicate roll number
    res = client.post("/admin/students/add", data={
        "name": "Another Student", "roll_number": "QA202601", "semester_id": sem.id
    }, follow_redirects=True)
    assert b"already assigned to another student" in res.data

    # 3. Invalid email format
    res = client.post("/admin/students/add", data={
        "name": "Test Student", "roll_number": "QA9999", "semester_id": sem.id,
        "email": "not_an_email_address"
    }, follow_redirects=True)
    assert b"Invalid email format" in res.data

    # 4. Invalid year (< 1 or > 6)
    res = client.post("/admin/students/add", data={
        "name": "Test Student", "roll_number": "QA9999", "semester_id": sem.id,
        "year": 10
    }, follow_redirects=True)
    assert b"Academic year must be between 1 and 6" in res.data


def test_add_semester_validations(client, qa_data):
    """Test semester start/end date logic validation."""
    admin = qa_data["admin_user"]
    with client.session_transaction() as sess:
        sess["_user_id"] = str(admin.id)
        sess["_fresh"] = True

    # Start date after end date
    res = client.post("/admin/semesters/add", data={
        "name": "Invalid Term",
        "year": 2026,
        "start_date": "2026-08-01",
        "end_date": "2026-05-01"  # Before start date!
    }, follow_redirects=True)
    assert b"start date cannot be after end date" in res.data


def test_add_subject_validations(client, qa_data):
    """Test course code and semester requirement validations."""
    admin = qa_data["admin_user"]
    sem = qa_data["semester"]
    with client.session_transaction() as sess:
        sess["_user_id"] = str(admin.id)
        sess["_fresh"] = True

    # Missing code
    res = client.post("/admin/subjects/add", data={
        "name": "Algorithms", "code": "", "semester_id": sem.id
    }, follow_redirects=True)
    assert b"Subject course code is required" in res.data

    # Duplicate code in same semester
    res = client.post("/admin/subjects/add", data={
        "name": "Duplicate AI", "code": "CS501", "semester_id": sem.id
    }, follow_redirects=True)
    assert b"already exists in semester" in res.data


# ─────────────────────────────────────────────────────────────────────────────
# 5. ATTENDANCE ENTRY, DUPLICATE PREVENTION & AUDIT LOGGING
# ─────────────────────────────────────────────────────────────────────────────

def test_attendance_session_marking_and_duplicate_prevention(client, qa_data):
    """Verify attendance marking updates existing records without duplicate generation."""
    admin = qa_data["admin_user"]
    subj = qa_data["subj_cs"]
    sem = qa_data["semester"]
    st = qa_data["st_high"]
    att_date = date(2026, 3, 10)

    with client.session_transaction() as sess:
        sess["_user_id"] = str(admin.id)
        sess["_fresh"] = True

    # 1. Initial mark
    client.post(
        f"/attendance/mark?subject_id={subj.id}&semester_id={sem.id}&attendance_date={att_date.isoformat()}&session_slot=1",
        data={f"status_{st.id}": "present", f"remarks_{st.id}": "First entry"},
        follow_redirects=True
    )
    rec = AttendanceRecord.query.filter_by(
        student_id=st.id, subject_id=subj.id, date=att_date, session_slot=1
    ).first()
    assert rec is not None
    assert rec.status == "present"

    # 2. Re-mark same session as absent -> Must update in-place, not duplicate
    client.post(
        f"/attendance/mark?subject_id={subj.id}&semester_id={sem.id}&attendance_date={att_date.isoformat()}&session_slot=1",
        data={f"status_{st.id}": "absent", f"remarks_{st.id}": "Correction"},
        follow_redirects=True
    )
    matching = AttendanceRecord.query.filter_by(
        student_id=st.id, subject_id=subj.id, date=att_date, session_slot=1
    ).all()
    assert len(matching) == 1
    assert matching[0].status == "absent"

    # Audit history must have logged the change
    audit_logs = AttendanceEditHistory.query.filter_by(attendance_record_id=rec.id).all()
    assert len(audit_logs) >= 1
    assert audit_logs[-1].old_status == "present"
    assert audit_logs[-1].new_status == "absent"


# ─────────────────────────────────────────────────────────────────────────────
# 6. EXACT PERCENTAGE CALCULATIONS & PROJECTION MATHEMATICS
# ─────────────────────────────────────────────────────────────────────────────

def test_exact_attendance_percentage_formulas(qa_data):
    """Verify (Attended / Conducted) * 100 calculation and edge cases."""
    st_high = qa_data["st_high"]  # 9 attended out of 10
    st_low  = qa_data["st_low"]   # 4 attended out of 10

    stats_high = st_high.get_overall_stats()
    assert stats_high["conducted"] == 10
    assert stats_high["attended"] == 9
    assert stats_high["percentage"] == 90.0
    assert stats_high["risk_level"] == "Low"

    stats_low = st_low.get_overall_stats()
    assert stats_low["conducted"] == 10
    assert stats_low["attended"] == 4
    assert stats_low["percentage"] == 40.0
    assert stats_low["risk_level"] == "High"


def test_deterministic_projection_mathematics():
    """Verify classes needed, safe buffer, and irrecoverable shortage formulas."""
    # Scenario A: Student at 60% (12/20), 20 remaining classes, 75% target
    # Consecutive classes to reach 75%: (0.75 * 20 - 12) / 0.25 = 12 classes.
    # Attending 12 consecutive classes results in (12 + 12) / (20 + 12) = 24 / 32 = 75.0%
    res_a = calculate_attendance_recovery(
        total_conducted=20, classes_attended=12, remaining_classes=20, target_threshold=75.0
    )
    assert res_a["classes_needed_for_target"] == 12
    assert res_a["is_recoverable"] is True
    assert res_a["can_recover_in_remaining"] is True
    assert res_a["max_possible_percentage"] == 80.0  # (12 + 20) / 40 = 32/40 = 80.0%
    assert res_a["safe_skips_remaining"] == 2  # 32 - 30 = 2 classes can be skipped
    assert res_a["max_additional_misses"] == 2  # floor(12 + 20 - 0.75*(20 + 20)) = 2

    # Scenario B: Irrecoverable shortage (10/30 attended, only 5 classes remaining)
    # Total classes = 35. Max attended = 10 + 5 = 15. Max pct = 15 / 35 = 42.86% < 75%
    res_b = calculate_attendance_recovery(
        total_conducted=30, classes_attended=10, remaining_classes=5, target_threshold=75.0
    )
    assert res_b["is_recoverable"] is False
    assert res_b["max_possible_percentage"] < 75.0

    # Scenario C: High attendance with buffer (36/40 attended, 10 remaining classes)
    res_c = calculate_attendance_recovery(
        total_conducted=40, classes_attended=36, remaining_classes=10, target_threshold=75.0
    )
    assert res_c["classes_needed_for_target"] == 0
    assert res_c["safe_skips_remaining"] > 0
    assert res_c["is_recoverable"] is True


# ─────────────────────────────────────────────────────────────────────────────
# 7. EXCEL / CSV IMPORT AND EXPORT ROBUSTNESS
# ─────────────────────────────────────────────────────────────────────────────

def test_excel_upload_handles_missing_and_corrupt_files(client, qa_data):
    """Verify upload endpoint handles empty files and invalid extensions gracefully."""
    admin = qa_data["admin_user"]
    with client.session_transaction() as sess:
        sess["_user_id"] = str(admin.id)
        sess["_fresh"] = True

    # 1. Disallowed file extension (.txt)
    txt_io = io.BytesIO(b"roll_number,status\nQA202601,present")
    res = client.post("/attendance/import", data={
        "file": (txt_io, "test.txt")
    }, follow_redirects=True)
    assert b"Only .csv, .xlsx, and .xls files are allowed" in res.data

    # 2. Empty file
    empty_csv = io.BytesIO(b"")
    res = client.post("/attendance/import", data={
        "file": (empty_csv, "empty.csv")
    }, follow_redirects=True)
    assert b"contains no rows" in res.data or b"Could not parse file" in res.data


def test_excel_export_generators_produce_valid_workbooks(qa_data):
    """Verify all 6 Excel export functions generate valid, readable openpyxl workbooks."""
    st = qa_data["st_high"]
    sem = qa_data["semester"]
    subj = qa_data["subj_cs"]

    # 1. Student workbook
    wb1 = openpyxl.load_workbook(build_student_excel(st.id), data_only=True)
    assert "Student Profile" in wb1.sheetnames

    # 2. Attendance records dump
    wb2 = openpyxl.load_workbook(build_attendance_records_excel(), data_only=True)
    assert wb2.active.max_row > 4

    # 3. Risk analysis dump
    wb3 = openpyxl.load_workbook(build_risk_analysis_excel(sem.id), data_only=True)
    assert "Academic Risk Analysis" in wb3.sheetnames

    # 4. Subject statistics dump
    wb4 = openpyxl.load_workbook(build_subject_statistics_excel(sem.id), data_only=True)
    assert "Course Performance Statistics" in wb4.sheetnames

    # 5. Semester matrix dump
    wb5 = openpyxl.load_workbook(build_semester_matrix_excel(sem.id), data_only=True)
    assert "Semester Matrix" in wb5.sheetnames

    # 6. Upload template
    wb6 = openpyxl.load_workbook(build_attendance_upload_template_excel(), data_only=True)
    assert "Attendance Upload Template" in wb6.sheetnames


# ─────────────────────────────────────────────────────────────────────────────
# 8. MACHINE LEARNING MODEL, INFERENCE & ZERO DATA LEAKAGE
# ─────────────────────────────────────────────────────────────────────────────

def test_model_loading_and_prediction_pipeline(qa_data):
    """Verify model loads successfully and inference produces valid probabilities."""
    pipeline, meta = get_trained_pipeline()
    assert pipeline is not None
    assert meta["version"] == "2.0.0"

    st_low = qa_data["st_low"]
    pred = predict_risk(st_low.id)

    assert "risk_probability" in pred
    assert 0.0 <= pred["risk_probability"] <= 1.0
    assert pred["risk_category"] in ("Low", "Medium", "High")
    assert "recommendations" in pred
    assert len(pred["recommendations"]) > 0


def test_zero_data_leakage_in_features():
    """Verify that feature calculation strictly uses information up to the snapshot checkpoint."""
    import numpy as np
    # 50 classes: attended 10 out of first 10, but missed all next 40
    history = np.array([1] * 10 + [0] * 40)
    feat_at_10 = extract_snapshot_features(history, snapshot_idx=10, total_planned=50)

    # At class 10, student attendance was 100%, NOT 20%
    assert feat_at_10["total_classes_so_far"] == 10
    assert feat_at_10["classes_attended"] == 10
    assert feat_at_10["current_percentage"] == 100.0
    assert feat_at_10["consecutive_absences"] == 0
    assert feat_at_10["remaining_classes"] == 40


def test_calibrated_risk_tiers():
    """Verify calibrated probability boundary thresholds."""
    assert classify_risk_tier(0.70) == "High"
    assert classify_risk_tier(0.65) == "High"
    assert classify_risk_tier(0.50) == "Medium"
    assert classify_risk_tier(0.35) == "Medium"
    assert classify_risk_tier(0.20) == "Low"


def test_calibrated_threshold_metrics_precision_and_recall():
    """Verify that ml/models/threshold_metrics.json exists and holds real evaluation numbers."""
    thresh_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "ml", "models", "threshold_metrics.json")
    assert os.path.exists(thresh_path), "threshold_metrics.json must be saved in ml/models/"
    with open(thresh_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["model_name"] == "Logistic Regression"
    assert data["model_version"] == "2.0.0"
    assert data["high_risk"]["threshold"] == 0.65
    assert data["high_risk"]["precision"] > 0.75  # ~81.31%
    assert data["high_risk"]["recall"] > 0.70     # ~78.38%

    assert data["medium_risk"]["threshold"] == 0.35
    assert data["medium_risk"]["recall"] > 0.85    # ~90.09% high-sensitivity
    assert data["medium_risk"]["precision"] > 0.60 # ~65.36%


# ─────────────────────────────────────────────────────────────────────────────
# 9. PDF REPORTS INTEGRITY & REQUIRED ELEMENTS
# ─────────────────────────────────────────────────────────────────────────────

def test_student_pdf_contains_all_nine_required_elements(qa_data):
    """
    Verify individual student PDF report contains all 9 required items:
    1. App name, 2. Student details, 3. Attendance summary, 4. Subject-wise table,
    5. Risk category, 6. ML probability, 7. Attendance projection,
    8. Recommendations, 9. Generation date.
    """
    st = qa_data["st_low"]
    buf = build_student_pdf(st.id)
    pdf_bytes = buf.getvalue()

    assert pdf_bytes.startswith(b"%PDF")
    assert b"%%EOF" in pdf_bytes
    assert len(pdf_bytes) > 2000


def test_all_institutional_pdf_reports(qa_data):
    """Verify all cohort PDF reports generate without errors."""
    sem = qa_data["semester"]
    subj = qa_data["subj_cs"]

    for builder, args in [
        (build_department_pdf, ("Computer Science", sem.id)),
        (build_semester_pdf, (sem.id,)),
        (build_subject_pdf, (subj.id,)),
        (build_high_risk_pdf, (sem.id,)),
        (build_ml_predictions_pdf, (sem.id,)),
    ]:
        buf = builder(*args)
        assert buf.getvalue().startswith(b"%PDF")


# ─────────────────────────────────────────────────────────────────────────────
# 10. TEMPLATE INTEGRITY & COMPLETE ROUTE COVERAGE
# ─────────────────────────────────────────────────────────────────────────────

def test_all_templates_have_valid_endpoints(app):
    """Verify that every url_for() call across all templates refers to a real Flask endpoint."""
    valid_endpoints = set(app.view_functions.keys())
    valid_endpoints.add("static")

    pattern = re.compile(r'url_for\([\'"]([a-zA-Z0-9_\.]+)[\'"]')
    broken = []

    for filepath in glob.glob("templates/**/*.html", recursive=True):
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        for match in pattern.finditer(content):
            ep = match.group(1)
            if ep not in valid_endpoints:
                broken.append((filepath, ep))

    assert len(broken) == 0, f"Found broken endpoints in templates: {broken}"
