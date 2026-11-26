"""
tests/test_reporting_and_export.py – Comprehensive automated test suite
for AttendAI Reporting & Export Engine.

Tests:
  1. PDF Report Generation for multiple students with varying attendance & risk profiles.
  2. Institutional PDF Reports: Department-wise, Semester-wise, Subject-wise,
     High-Risk Shortage Audit, and ML Predictions Audit.
  3. PDF Content & Quality Verification (%PDF header, non-empty stream).
  4. Excel Report Generation:
     - Student 3-tab workbook (Summary, Course Breakdown, Session Logs).
     - Attendance Records raw data dump (with filters).
     - Risk Analysis & Recovery Metrics summary.
     - Subject Statistics aggregate table.
     - Semester Cross-Tabulation Matrix.
     - Attendance Upload Template (.xlsx).
  5. Exact Data Parity: Exported values must match the SQLite database records.
  6. Excel Attendance Upload Round-Trip Test:
     - Uploads an .xlsx workbook created with openpyxl.
     - Verifies database ingestion and percentage updates.
  7. HTTP Blueprint Route Testing for all PDF and Excel endpoints.
"""

import io
from datetime import date, timedelta
import pytest
import openpyxl
from werkzeug.datastructures import FileStorage

from database.models import (
    User, Faculty, Semester, Subject, Student,
    AttendanceRecord, PredictionHistory, Intervention, SystemSetting
)
from reports.pdf_builder import (
    build_student_pdf, build_department_pdf, build_semester_pdf,
    build_subject_pdf, build_high_risk_pdf, build_ml_predictions_pdf
)
from reports.excel_builder import (
    build_student_excel, build_attendance_records_excel,
    build_risk_analysis_excel, build_subject_statistics_excel,
    build_semester_matrix_excel, build_attendance_upload_template_excel
)
from ml.recommendations import calculate_attendance_recovery


@pytest.fixture
def report_data(db):
    """Seed comprehensive test data for reporting and export testing."""
    # 1. Admin User
    admin_user = User(username="report_admin", email="admin_report@attendai.edu", role="admin")
    admin_user.set_password("Admin@123")
    db.session.add(admin_user)
    db.session.flush()

    admin_faculty = Faculty(
        user_id=admin_user.id, name="Dr. A. K. Verma", department="Computer Science", employee_id="REP_FAC01"
    )
    db.session.add(admin_faculty)

    # 2. Semester
    sem = Semester(
        name="Autumn 2025",
        year=2025,
        is_active=True,
        start_date=date(2025, 7, 15),
        end_date=date(2025, 12, 10)
    )
    db.session.add(sem)
    db.session.flush()

    # 3. Subjects
    subj1 = Subject(
        name="Machine Learning Systems",
        code="CS601",
        semester_id=sem.id,
        faculty_id=admin_faculty.id,
        total_classes_planned=40
    )
    subj2 = Subject(
        name="Database Engineering",
        code="CS602",
        semester_id=sem.id,
        faculty_id=admin_faculty.id,
        total_classes_planned=40
    )
    db.session.add_all([subj1, subj2])
    db.session.flush()

    # 4. Multiple Students with distinct attendance behaviors
    # Student A: High Attendance (90%) - Low Risk
    st_low = Student(
        student_id="STU_REP_01",
        roll_number="CS202501",
        name="Aditi Sharma",
        department="Computer Science",
        year=3,
        section="A",
        semester_id=sem.id,
        email="aditi@attendai.edu"
    )
    # Student B: Medium Attendance (68%) - Medium Risk
    st_med = Student(
        student_id="STU_REP_02",
        roll_number="CS202502",
        name="Bhavesh Patel",
        department="Computer Science",
        year=3,
        section="A",
        semester_id=sem.id,
        email="bhavesh@attendai.edu"
    )
    # Student C: Critical Attendance (30%) - High Risk
    st_high = Student(
        student_id="STU_REP_03",
        roll_number="CS202503",
        name="Chetan Kumar",
        department="Information Technology",
        year=3,
        section="B",
        semester_id=sem.id,
        email="chetan@attendai.edu"
    )

    db.session.add_all([st_low, st_med, st_high])
    db.session.flush()

    # Enrol students into semester subjects
    st_low.enroll_in_semester_subjects()
    st_med.enroll_in_semester_subjects()
    st_high.enroll_in_semester_subjects()

    # 5. Populate session records (10 sessions conducted for subj1, 10 for subj2)
    base_date = date(2025, 8, 1)
    for i in range(10):
        d = base_date + timedelta(days=i)
        
        # Subj 1
        # Aditi: 9 present, 1 absent (90%)
        db.session.add(AttendanceRecord(
            student_id=st_low.id, subject_id=subj1.id, date=d, session_slot=1,
            status="present" if i != 5 else "absent", marked_by=admin_user.id
        ))
        # Bhavesh: 7 present, 3 absent (70%)
        db.session.add(AttendanceRecord(
            student_id=st_med.id, subject_id=subj1.id, date=d, session_slot=1,
            status="present" if i < 7 else "absent", marked_by=admin_user.id
        ))
        # Chetan: 3 present, 7 absent (30%)
        db.session.add(AttendanceRecord(
            student_id=st_high.id, subject_id=subj1.id, date=d, session_slot=1,
            status="present" if i < 3 else "absent", marked_by=admin_user.id
        ))

        # Subj 2
        # Aditi: 10 present (100%)
        db.session.add(AttendanceRecord(
            student_id=st_low.id, subject_id=subj2.id, date=d, session_slot=2,
            status="present", marked_by=admin_user.id
        ))
        # Bhavesh: 6 present, 4 absent (60%)
        db.session.add(AttendanceRecord(
            student_id=st_med.id, subject_id=subj2.id, date=d, session_slot=2,
            status="present" if i < 6 else "absent", marked_by=admin_user.id
        ))
        # Chetan: 2 present, 8 absent (20%)
        db.session.add(AttendanceRecord(
            student_id=st_high.id, subject_id=subj2.id, date=d, session_slot=2,
            status="present" if i < 2 else "absent", marked_by=admin_user.id
        ))

    # 6. Prediction Histories
    db.session.add(PredictionHistory(
        student_id=st_low.id, semester_id=sem.id, risk_probability=0.08,
        risk_level="Low", model_version="v2.0.0", attendance_percentage=95.0
    ))
    db.session.add(PredictionHistory(
        student_id=st_med.id, semester_id=sem.id, risk_probability=0.48,
        risk_level="Medium", model_version="v2.0.0", attendance_percentage=65.0
    ))
    db.session.add(PredictionHistory(
        student_id=st_high.id, semester_id=sem.id, risk_probability=0.88,
        risk_level="High", model_version="v2.0.0", attendance_percentage=25.0
    ))

    # 7. Intervention for High-Risk Student
    db.session.add(Intervention(
        student_id=st_high.id, faculty_id=admin_faculty.id,
        notes="Repeated absences across CS601 and CS602",
        student_contacted=True, contact_date=date(2025, 8, 15),
        contact_method="Phone Call", explanation_received=True,
        student_explanation="Viral fever and hospitalisation",
        attendance_improved="pending", status="in_progress"
    ))

    db.session.commit()

    return {
        "admin": admin_user,
        "sem": sem,
        "subj1": subj1,
        "subj2": subj2,
        "st_low": st_low,
        "st_med": st_med,
        "st_high": st_high,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 1. PDF Reports Verification (Multiple Students & Categories)
# ─────────────────────────────────────────────────────────────────────────────

def test_student_pdf_generation_multiple_students(report_data):
    """Verify PDF generation for multiple students with different risk levels."""
    st_low = report_data["st_low"]
    st_med = report_data["st_med"]
    st_high = report_data["st_high"]

    for student in [st_low, st_med, st_high]:
        pdf_buf = build_student_pdf(student.id)
        assert isinstance(pdf_buf, io.BytesIO)
        content = pdf_buf.getvalue()
        assert len(content) > 1000
        # Valid PDF header
        assert content.startswith(b"%PDF")
        # Ensure EOF marker exists
        assert b"%%EOF" in content


def test_student_pdf_contains_required_elements(report_data):
    """Verify that student PDF data structures and inputs match requirements."""
    student = report_data["st_high"]
    stats = student.get_overall_stats()
    assert stats["conducted"] == 20
    assert stats["attended"] == 5
    assert stats["absent"] == 15
    assert stats["percentage"] == 25.0

    pdf_buf = build_student_pdf(student.id)
    assert pdf_buf is not None
    assert pdf_buf.tell() == 0  # stream is reset to beginning


def test_institutional_pdf_builders(report_data):
    """Verify all institutional PDF report generators create valid PDFs."""
    sem = report_data["sem"]
    subj1 = report_data["subj1"]

    # 1. Department PDF
    dept_buf = build_department_pdf("Computer Science", sem.id)
    assert dept_buf.getvalue().startswith(b"%PDF")

    # 2. Semester Master PDF
    sem_buf = build_semester_pdf(sem.id)
    assert sem_buf.getvalue().startswith(b"%PDF")

    # 3. Subject PDF
    subj_buf = build_subject_pdf(subj1.id)
    assert subj_buf.getvalue().startswith(b"%PDF")

    # 4. High-Risk Audit PDF
    risk_buf = build_high_risk_pdf(sem.id)
    assert risk_buf.getvalue().startswith(b"%PDF")

    # 5. ML Predictions Audit PDF
    pred_buf = build_ml_predictions_pdf(sem.id)
    assert pred_buf.getvalue().startswith(b"%PDF")


# ─────────────────────────────────────────────────────────────────────────────
# 2. Excel Workbooks Verification
# ─────────────────────────────────────────────────────────────────────────────

def test_student_excel_workbook(report_data):
    """Verify individual student 3-sheet Excel workbook structure and data."""
    st_low = report_data["st_low"]
    excel_buf = build_student_excel(st_low.id)
    assert isinstance(excel_buf, io.BytesIO)

    wb = openpyxl.load_workbook(excel_buf, data_only=True)
    expected_sheets = ["Student Profile", "Subject Breakdown", "Attendance Session Log"]
    for sname in expected_sheets:
        assert sname in wb.sheetnames

    # Check Student Profile sheet
    ws_profile = wb["Student Profile"]
    assert ws_profile["B3"].value == st_low.name
    assert ws_profile["B4"].value == st_low.roll_number
    assert ws_profile["B6"].value == st_low.department

    # Check overall percentage cell
    overall_pct = ws_profile["D5"].value
    assert overall_pct == 95.0  # 19 / 20 = 95.0%

    # Check Subject Breakdown sheet
    ws_subj = wb["Subject Breakdown"]
    assert ws_subj.max_row >= 3  # Header + 2 subjects

    # Check Session Log sheet
    ws_log = wb["Attendance Session Log"]
    assert ws_log.max_row >= 21  # Header + 20 session records


def test_attendance_records_excel_dump(report_data):
    """Verify attendance records raw dump with filtering."""
    # Full dump (4 header rows + 60 records = 64)
    buf_all = build_attendance_records_excel()
    wb_all = openpyxl.load_workbook(buf_all, data_only=True)
    ws_all = wb_all.active
    assert ws_all.max_row == 64

    # Filtered by department (4 header rows + 20 records = 24)
    buf_dept = build_attendance_records_excel(department="Information Technology")
    wb_dept = openpyxl.load_workbook(buf_dept, data_only=True)
    ws_dept = wb_dept.active
    assert ws_dept.max_row == 24

    # Filtered by status (4 header rows + 23 absent records = 27)
    buf_absent = build_attendance_records_excel(status="absent")
    wb_absent = openpyxl.load_workbook(buf_absent, data_only=True)
    ws_absent = wb_absent.active
    assert ws_absent.max_row == 27


def test_risk_analysis_excel_dump(report_data):
    """Verify risk analysis summary Excel workbook matches database predictions."""
    sem = report_data["sem"]
    buf = build_risk_analysis_excel(semester_id=sem.id)
    wb = openpyxl.load_workbook(buf, data_only=True)
    ws = wb.active

    assert ws.title == "Academic Risk Analysis"
    # 4 header rows + 3 students = 7
    assert ws.max_row == 7

    # Headers in row 4
    headers = [cell.value for cell in ws[4]]
    assert "Roll Number" in headers
    assert "Full Name" in headers
    assert "Attendance %" in headers
    assert "Risk Tier" in headers
    assert "ML Shortage Prob" in headers
    assert "Classes Needed for 75%" in headers
    assert "Max Possible %" in headers
    assert "Feasibility" in headers

    # Verify Chetan is High Risk
    found_high = False
    for row in range(5, 8):
        if ws.cell(row=row, column=2).value == "CS202503":
            found_high = True
            assert ws.cell(row=row, column=10).value == "High"
            assert "88" in str(ws.cell(row=row, column=9).value)
            assert "25" in str(ws.cell(row=row, column=8).value)
    assert found_high


def test_subject_statistics_excel_dump(report_data):
    """Verify subject-level aggregate performance Excel workbook."""
    sem = report_data["sem"]
    buf = build_subject_statistics_excel(semester_id=sem.id)
    wb = openpyxl.load_workbook(buf, data_only=True)
    ws = wb.active

    assert ws.title == "Course Performance Statistics"
    # 3 header rows + 2 subjects = 5
    assert ws.max_row == 5

    # Check CS601 and CS602 codes exist in rows 4 and 5
    codes = [ws.cell(row=r, column=1).value for r in range(4, 6)]
    assert "CS601" in codes
    assert "CS602" in codes


def test_semester_matrix_excel_dump(report_data):
    """Verify semester cross-tabulation matrix."""
    sem = report_data["sem"]
    buf = build_semester_matrix_excel(semester_id=sem.id)
    wb = openpyxl.load_workbook(buf, data_only=True)
    ws = wb.active

    assert ws.title == "Semester Matrix"
    headers = [ws.cell(row=3, column=c).value for c in range(1, ws.max_column + 1)]
    assert "Roll No" in headers
    assert "Student Name" in headers
    assert "Overall %" in headers
    assert "Risk Tier" in headers
    # Subject codes should be column headers
    assert any("CS601" in str(h) for h in headers)
    assert any("CS602" in str(h) for h in headers)


def test_upload_template_excel():
    """Verify attendance upload Excel template structure and guidelines."""
    buf = build_attendance_upload_template_excel()
    wb = openpyxl.load_workbook(buf, data_only=True)
    assert "Attendance Upload Template" in wb.sheetnames
    assert "Upload Instructions" in wb.sheetnames

    ws_tmpl = wb["Attendance Upload Template"]
    expected_headers = ["roll_number", "date", "session_slot", "status", "remarks", "code"]
    actual_headers = [ws_tmpl.cell(row=1, column=i).value for i in range(1, 7)]
    assert actual_headers == expected_headers
    assert ws_tmpl.max_row >= 5  # Header + 4 sample rows


# ─────────────────────────────────────────────────────────────────────────────
# 3. Data Parity: Database vs Export Parity
# ─────────────────────────────────────────────────────────────────────────────

def test_database_to_export_exact_parity(report_data):
    """Verify exact numerical alignment between database models and exported files."""
    st_med = report_data["st_med"]
    db_stats = st_med.get_overall_stats()

    # Recovery math
    rec_math = calculate_attendance_recovery(
        total_conducted=db_stats["conducted"],
        classes_attended=db_stats["attended"],
        remaining_classes=20,
        target_threshold=75.0
    )

    # Student Excel workbook
    buf = build_student_excel(st_med.id)
    wb = openpyxl.load_workbook(buf, data_only=True)
    ws_profile = wb["Student Profile"]

    # Profile Sheet Parity
    assert ws_profile["D3"].value == db_stats["conducted"]
    assert ws_profile["D4"].value == db_stats["attended"]
    assert ws_profile["D5"].value == db_stats["percentage"]

    # Subject Breakdown Parity
    ws_subj = wb["Subject Breakdown"]
    subj1_db = st_med.get_subject_stats(report_data["subj1"].id)
    # Row 2 is CS601
    assert ws_subj.cell(row=2, column=1).value == "CS601"
    assert ws_subj.cell(row=2, column=3).value == subj1_db["conducted"]
    assert ws_subj.cell(row=2, column=4).value == subj1_db["attended"]
    assert ws_subj.cell(row=2, column=6).value == subj1_db["percentage"]


# ─────────────────────────────────────────────────────────────────────────────
# 4. Excel Attendance Upload Round-Trip Test
# ─────────────────────────────────────────────────────────────────────────────

def test_excel_bulk_upload_roundtrip(client, report_data):
    """
    Test uploading attendance records via an .xlsx file using the bulk upload endpoint.
    Verifies that the Excel file is processed and records are saved in the database.
    """
    admin = report_data["admin"]
    subj1 = report_data["subj1"]
    upload_date = date(2025, 9, 1)

    # Log in as admin
    with client.session_transaction() as sess:
        sess["_user_id"] = str(admin.id)
        sess["_fresh"] = True

    # Create an in-memory .xlsx file with attendance records
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["roll_number", "date", "session_slot", "status", "remarks", "code"])
    ws.append(["CS202501", upload_date.isoformat(), 3, "present", "Lab session", subj1.code])
    ws.append(["CS202502", upload_date.isoformat(), 3, "present", "Lab session", subj1.code])
    ws.append(["CS202503", upload_date.isoformat(), 3, "absent", "Unexcused", subj1.code])

    xlsx_io = io.BytesIO()
    wb.save(xlsx_io)
    xlsx_io.seek(0)

    # Post to attendance.bulk_import
    data = {
        "file": (xlsx_io, "test_upload.xlsx"),
        "subject_id": subj1.id,
        "default_date": upload_date.isoformat(),
        "default_session": 3,
    }

    res = client.post(
        "/attendance/import",
        data=data,
        content_type="multipart/form-data",
        follow_redirects=True
    )
    assert res.status_code == 200

    # Verify that the attendance records were created in the database
    new_records = AttendanceRecord.query.filter_by(
        date=upload_date, session_slot=3, subject_id=subj1.id
    ).all()
    assert len(new_records) == 3

    statuses = {r.student.roll_number: r.status for r in new_records}
    assert statuses["CS202501"] == "present"
    assert statuses["CS202502"] == "present"
    assert statuses["CS202503"] == "absent"


# ─────────────────────────────────────────────────────────────────────────────
# 5. HTTP Blueprint Route Testing (PDF & Excel Endpoints)
# ─────────────────────────────────────────────────────────────────────────────

def test_reports_index_route(client, report_data):
    """Test the Reports & Export Hub index page renders successfully."""
    admin = report_data["admin"]
    with client.session_transaction() as sess:
        sess["_user_id"] = str(admin.id)
        sess["_fresh"] = True

    res = client.get("/reports/")
    assert res.status_code == 200
    assert b"Institutional Reporting &amp; Data Export Hub" in res.data
    assert b"Individual Student Dossier" in res.data
    assert b"High-Risk Shortage Audit" in res.data


def test_pdf_routes(client, report_data):
    """Verify HTTP GET responses for all PDF endpoints."""
    admin = report_data["admin"]
    with client.session_transaction() as sess:
        sess["_user_id"] = str(admin.id)
        sess["_fresh"] = True

    st_id = report_data["st_low"].id
    sem_id = report_data["sem"].id
    subj_id = report_data["subj1"].id

    endpoints = [
        f"/reports/pdf/student/{st_id}",
        "/reports/pdf/department/Computer%20Science",
        f"/reports/pdf/semester/{sem_id}",
        f"/reports/pdf/subject/{subj_id}",
        "/reports/pdf/high-risk",
        "/reports/pdf/predictions",
    ]

    for ep in endpoints:
        res = client.get(ep)
        assert res.status_code == 200, f"Endpoint {ep} failed with status {res.status_code}"
        assert res.mimetype == "application/pdf"
        assert res.data.startswith(b"%PDF")


def test_excel_routes(client, report_data):
    """Verify HTTP GET responses for all Excel endpoints."""
    admin = report_data["admin"]
    with client.session_transaction() as sess:
        sess["_user_id"] = str(admin.id)
        sess["_fresh"] = True

    st_id = report_data["st_low"].id
    sem_id = report_data["sem"].id
    subj_id = report_data["subj1"].id

    endpoints = [
        f"/reports/excel/student/{st_id}",
        "/reports/excel/department/Computer%20Science",
        f"/reports/excel/semester/{sem_id}",
        f"/reports/excel/subject/{subj_id}",
        "/reports/excel/high-risk",
        "/reports/excel/predictions",
        "/reports/excel/attendance-records",
        "/reports/excel/risk-analysis",
        "/reports/excel/subject-statistics",
        "/reports/template/excel",
    ]

    excel_mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    for ep in endpoints:
        res = client.get(ep)
        assert res.status_code == 200, f"Endpoint {ep} failed with status {res.status_code}"
        assert res.mimetype == excel_mime
        assert len(res.data) > 1000
