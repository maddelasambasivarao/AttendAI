"""
tests/test_attendance.py – Comprehensive unit & integration tests
for the complete Attendance Management Module.

Covers:
  1. Multi-level filter selection & marking interface (dept, year, section, sem, sub, date, session).
  2. Displaying enrolled students and marking Present / Absent.
  3. Saving attendance records to SQLite.
  4. Preventing duplicate entries for the same student, subject, date, and session slot.
  5. Audit history logging on record modifications.
  6. Authorised faculty and admin correction (/attendance/correct/<id>).
  7. Unauthorized faculty correction rejection.
  8. Record edit history JSON endpoint (/attendance/history/<id>).
  9. Bulk upload via CSV with column alias mapping and auto-enrolment.
  10. Handling missing values (default to absent), invalid dates, and non-existent roll numbers.
  11. Bulk upload via Excel (.xlsx).
  12. Bulk upload updating existing sessions with audit trail.
  13. Downloadable attendance CSV template (/attendance/template).
  14. Automatic attendance percentage calculation: (Attended / Conducted) × 100 with risk tiers.
  15. Individual student attendance history route (/attendance/student/<id>).
  16. Subject-wise attendance report route (/attendance/report/subject/<id>).
  17. Semester-wide attendance matrix report route (/attendance/report/semester/<id>).
"""

import io
from datetime import date, datetime, timedelta
import pytest
import pandas as pd

from database.models import (
    User, Faculty, Semester, Student, Subject,
    StudentSubjectEnrolment, AttendanceRecord, AttendanceEditHistory
)


@pytest.fixture
def att_data(db):
    """Seed comprehensive test data for attendance testing."""
    # 1. Admin
    admin_user = User(username="admin", email="admin@attendai.edu", role="admin")
    admin_user.set_password("Admin@123")
    db.session.add(admin_user)
    db.session.flush()

    admin_fac = Faculty(user_id=admin_user.id, name="Admin Head", department="Admin", employee_id="A001")
    db.session.add(admin_fac)

    # 2. Faculty 1 (Assigned to CS101)
    fac1_user = User(username="faculty1", email="fac1@attendai.edu", role="faculty")
    fac1_user.set_password("Faculty@123")
    db.session.add(fac1_user)
    db.session.flush()

    fac1 = Faculty(user_id=fac1_user.id, name="Dr. Sharma", department="Computer Science", employee_id="F001")
    db.session.add(fac1)

    # 3. Faculty 2 (Assigned to CS102)
    fac2_user = User(username="faculty2", email="fac2@attendai.edu", role="faculty")
    fac2_user.set_password("Faculty@123")
    db.session.add(fac2_user)
    db.session.flush()

    fac2 = Faculty(user_id=fac2_user.id, name="Prof. Verma", department="Information Technology", employee_id="F002")
    db.session.add(fac2)

    # 4. Semester
    sem = Semester(
        name="Semester 3 - 2025",
        year=2025,
        section="A",
        start_date=date(2025, 7, 1),
        end_date=date(2025, 12, 15),
        is_active=True
    )
    db.session.add(sem)
    db.session.flush()

    # 5. Subjects
    sub1 = Subject(
        name="Machine Learning",
        code="CS601",
        semester_id=sem.id,
        faculty_id=fac1.id,
        total_classes_planned=45,
        subject_type="theory"
    )
    sub2 = Subject(
        name="Database Systems",
        code="CS602",
        semester_id=sem.id,
        faculty_id=fac2.id,
        total_classes_planned=40,
        subject_type="theory"
    )
    db.session.add_all([sub1, sub2])
    db.session.flush()

    # 6. Students
    st1 = Student(
        student_id="STU2025001",
        roll_number="CS202501",
        name="Aarav Sharma",
        department="Computer Science",
        year=2,
        section="A",
        email="aarav@attendai.edu",
        semester_id=sem.id
    )
    st2 = Student(
        student_id="STU2025002",
        roll_number="CS202502",
        name="Deepika Rao",
        department="Computer Science",
        year=2,
        section="A",
        email="deepika@attendai.edu",
        semester_id=sem.id
    )
    st3 = Student(
        student_id="STU2025003",
        roll_number="IT202501",
        name="Rohit Verma",
        department="Information Technology",
        year=2,
        section="B",
        email="rohit@attendai.edu",
        semester_id=sem.id
    )
    db.session.add_all([st1, st2, st3])
    db.session.flush()

    # Auto enroll in subjects
    st1.enroll_in_semester_subjects()
    st2.enroll_in_semester_subjects()
    st3.enroll_in_semester_subjects()
    db.session.commit()

    return {
        "admin": admin_user,
        "faculty1": fac1_user,
        "faculty1_prof": fac1,
        "faculty2": fac2_user,
        "faculty2_prof": fac2,
        "semester": sem,
        "sub1": sub1,
        "sub2": sub2,
        "st1": st1,
        "st2": st2,
        "st3": st3
    }


# ─────────────────────────────────────────────────────────────────────────────
# 1. Marking Interface (GET & POST)
# ─────────────────────────────────────────────────────────────────────────────
def test_mark_attendance_page_loads(client, att_data):
    """Faculty can view marking page with pre-populated semester, subjects and filters."""
    client.post("/login", data={"username": "faculty1", "password": "Faculty@123"})

    sem = att_data["semester"]
    sub1 = att_data["sub1"]

    r = client.get(f"/attendance/mark?semester_id={sem.id}&subject_id={sub1.id}&attendance_date=2025-09-01&session_slot=1")
    assert r.status_code == 200
    assert b"Mark Attendance" in r.data
    assert b"CS601" in r.data
    assert b"Aarav Sharma" in r.data
    assert b"Deepika Rao" in r.data


def test_mark_attendance_post_saves_records(client, db, att_data):
    """Marking attendance saves individual Present / Absent records in SQLite."""
    client.post("/login", data={"username": "faculty1", "password": "Faculty@123"})

    sem = att_data["semester"]
    sub1 = att_data["sub1"]
    st1 = att_data["st1"]
    st2 = att_data["st2"]

    r = client.post(
        f"/attendance/mark?semester_id={sem.id}&subject_id={sub1.id}&attendance_date=2025-09-01&session_slot=1",
        data={
            f"status_{st1.id}": "present",
            f"remarks_{st1.id}": "",
            f"status_{st2.id}": "absent",
            f"remarks_{st2.id}": "Unexcused absence",
        },
        follow_redirects=True
    )
    assert r.status_code == 200

    # Verify records in database
    rec1 = AttendanceRecord.query.filter_by(student_id=st1.id, subject_id=sub1.id, date=date(2025, 9, 1), session_slot=1).first()
    assert rec1 is not None
    assert rec1.status == "present"

    rec2 = AttendanceRecord.query.filter_by(student_id=st2.id, subject_id=sub1.id, date=date(2025, 9, 1), session_slot=1).first()
    assert rec2 is not None
    assert rec2.status == "absent"
    assert rec2.remarks == "Unexcused absence"


def test_prevent_duplicate_entries_and_record_updates(client, db, att_data):
    """Submitting attendance for same student, subject, date & session updates rather than duplicating."""
    client.post("/login", data={"username": "faculty1", "password": "Faculty@123"})

    sem = att_data["semester"]
    sub1 = att_data["sub1"]
    st1 = att_data["st1"]

    # Initial marking: Absent
    client.post(
        f"/attendance/mark?semester_id={sem.id}&subject_id={sub1.id}&attendance_date=2025-09-02&session_slot=1",
        data={f"status_{st1.id}": "absent", f"remarks_{st1.id}": "Sick"},
        follow_redirects=True
    )

    count_before = AttendanceRecord.query.filter_by(
        student_id=st1.id, subject_id=sub1.id, date=date(2025, 9, 2), session_slot=1
    ).count()
    assert count_before == 1

    # Re-submission on the same session: Changed to Present
    client.post(
        f"/attendance/mark?semester_id={sem.id}&subject_id={sub1.id}&attendance_date=2025-09-02&session_slot=1",
        data={f"status_{st1.id}": "present", f"remarks_{st1.id}": "Arrived late with permission"},
        follow_redirects=True
    )

    # Zero duplicate rows created
    count_after = AttendanceRecord.query.filter_by(
        student_id=st1.id, subject_id=sub1.id, date=date(2025, 9, 2), session_slot=1
    ).count()
    assert count_after == 1

    # Status updated
    updated_rec = AttendanceRecord.query.filter_by(
        student_id=st1.id, subject_id=sub1.id, date=date(2025, 9, 2), session_slot=1
    ).first()
    assert updated_rec.status == "present"

    # Audit history created
    audit = AttendanceEditHistory.query.filter_by(attendance_record_id=updated_rec.id).first()
    assert audit is not None
    assert audit.old_status == "absent"
    assert audit.new_status == "present"


# ─────────────────────────────────────────────────────────────────────────────
# 2. View Attendance & Filtering
# ─────────────────────────────────────────────────────────────────────────────
def test_view_attendance_with_filters(client, db, att_data):
    """Attendance log view filters by subject, student, status, and date range."""
    client.post("/login", data={"username": "faculty1", "password": "Faculty@123"})

    sem = att_data["semester"]
    sub1 = att_data["sub1"]
    st1 = att_data["st1"]

    # Add a record
    rec = AttendanceRecord(
        student_id=st1.id,
        subject_id=sub1.id,
        date=date(2025, 9, 10),
        session_slot=1,
        status="present",
        marked_by=att_data["faculty1"].id
    )
    db.session.add(rec)
    db.session.commit()

    # Filter by subject
    r = client.get(f"/attendance/view?semester_id={sem.id}&subject_id={sub1.id}")
    assert r.status_code == 200
    assert b"Aarav Sharma" in r.data
    assert b"CS601" in r.data

    # Filter by search query
    r_search = client.get(f"/attendance/view?semester_id={sem.id}&search=CS202501")
    assert r_search.status_code == 200
    assert b"Aarav Sharma" in r_search.data


# ─────────────────────────────────────────────────────────────────────────────
# 3. Authorised Faculty Correction & Audit History
# ─────────────────────────────────────────────────────────────────────────────
def test_authorized_faculty_correction_logs_audit_trail(client, db, att_data):
    """Faculty assigned to the subject can correct attendance and a detailed audit log is saved."""
    sem = att_data["semester"]
    sub1 = att_data["sub1"]
    st1 = att_data["st1"]

    # Create record: marked absent
    rec = AttendanceRecord(
        student_id=st1.id,
        subject_id=sub1.id,
        date=date(2025, 9, 15),
        session_slot=1,
        status="absent",
        marked_by=att_data["faculty1"].id
    )
    db.session.add(rec)
    db.session.commit()

    # Login as faculty1 (assigned to CS601)
    client.post("/login", data={"username": "faculty1", "password": "Faculty@123"})

    r = client.post(
        f"/attendance/correct/{rec.id}",
        data={
            "status": "present",
            "reason": "Submitted valid medical slip certified by health center"
        },
        follow_redirects=True
    )
    assert r.status_code == 200

    # Verify status changed
    db.session.refresh(rec)
    assert rec.status == "present"

    # Verify audit history entry
    audit = AttendanceEditHistory.query.filter_by(attendance_record_id=rec.id).first()
    assert audit is not None
    assert audit.old_status == "absent"
    assert audit.new_status == "present"
    assert "medical slip" in audit.reason.lower()
    assert audit.edited_by == att_data["faculty1"].id


def test_unauthorized_faculty_correction_rejected(client, db, att_data):
    """Faculty NOT assigned to the subject cannot modify its attendance records."""
    sub1 = att_data["sub1"]  # assigned to faculty1
    st1 = att_data["st1"]

    rec = AttendanceRecord(
        student_id=st1.id,
        subject_id=sub1.id,
        date=date(2025, 9, 15),
        session_slot=1,
        status="absent",
        marked_by=att_data["faculty1"].id
    )
    db.session.add(rec)
    db.session.commit()

    # Login as faculty2 (assigned to CS602, NOT CS601)
    client.post("/login", data={"username": "faculty2", "password": "Faculty@123"})

    r = client.post(
        f"/attendance/correct/{rec.id}",
        data={"status": "present", "reason": "Attempting unauthorized correction"},
        follow_redirects=True
    )
    assert r.status_code == 200
    assert b"Unauthorized" in r.data

    # Record must remain unchanged
    db.session.refresh(rec)
    assert rec.status == "absent"
    assert AttendanceEditHistory.query.filter_by(attendance_record_id=rec.id).count() == 0


def test_admin_can_correct_any_attendance(client, db, att_data):
    """Administrator can correct attendance for any subject."""
    sub1 = att_data["sub1"]
    st1 = att_data["st1"]

    rec = AttendanceRecord(
        student_id=st1.id,
        subject_id=sub1.id,
        date=date(2025, 9, 16),
        session_slot=1,
        status="absent",
        marked_by=att_data["faculty1"].id
    )
    db.session.add(rec)
    db.session.commit()

    # Login as admin
    client.post("/login", data={"username": "admin", "password": "Admin@123"})

    r = client.post(
        f"/attendance/correct/{rec.id}",
        data={"status": "present", "reason": "Administrative override"},
        follow_redirects=True
    )
    assert r.status_code == 200

    db.session.refresh(rec)
    assert rec.status == "present"
    assert AttendanceEditHistory.query.filter_by(attendance_record_id=rec.id).count() == 1


def test_record_history_json_endpoint(client, db, att_data):
    """JSON endpoint /attendance/history/<id> returns audit logs."""
    sub1 = att_data["sub1"]
    st1 = att_data["st1"]

    rec = AttendanceRecord(
        student_id=st1.id,
        subject_id=sub1.id,
        date=date(2025, 9, 17),
        session_slot=1,
        status="present",
        marked_by=att_data["faculty1"].id
    )
    db.session.add(rec)
    db.session.flush()

    audit = AttendanceEditHistory(
        attendance_record_id=rec.id,
        old_status="absent",
        new_status="present",
        reason="Verified attendance by HOD",
        edited_by=att_data["faculty1"].id,
        edited_at=datetime.utcnow()
    )
    db.session.add(audit)
    db.session.commit()

    client.post("/login", data={"username": "faculty1", "password": "Faculty@123"})
    r = client.get(f"/attendance/history/{rec.id}")
    assert r.status_code == 200

    data = r.get_json()
    assert data["record_id"] == rec.id
    assert data["student"] == st1.name
    assert len(data["history"]) == 1
    assert data["history"][0]["old_status"] == "Absent"
    assert data["history"][0]["new_status"] == "Present"


# ─────────────────────────────────────────────────────────────────────────────
# 4. Bulk Upload via CSV & Excel
# ─────────────────────────────────────────────────────────────────────────────
def test_bulk_import_csv_success(client, db, att_data):
    """Bulk import CSV creates records, maps columns and auto-enrolls."""
    client.post("/login", data={"username": "faculty1", "password": "Faculty@123"})

    csv_content = (
        "roll_number,code,date,session_slot,status,remarks\n"
        "CS202501,CS601,2025-09-20,1,present,On time\n"
        "CS202502,CS601,2025-09-20,1,absent,Unwell\n"
    )
    file_bytes = io.BytesIO(csv_content.encode("utf-8"))

    r = client.post(
        "/attendance/import",
        data={
            "file": (file_bytes, "test_attendance.csv"),
            "subject_id": att_data["sub1"].id,
            "default_date": "2025-09-20",
            "default_session": "1"
        },
        content_type="multipart/form-data",
        follow_redirects=True
    )
    assert r.status_code == 200
    assert b"Bulk Upload Complete" in r.data

    # Verify rows created
    rec1 = AttendanceRecord.query.filter_by(
        student_id=att_data["st1"].id, subject_id=att_data["sub1"].id, date=date(2025, 9, 20)
    ).first()
    assert rec1 is not None
    assert rec1.status == "present"

    rec2 = AttendanceRecord.query.filter_by(
        student_id=att_data["st2"].id, subject_id=att_data["sub1"].id, date=date(2025, 9, 20)
    ).first()
    assert rec2 is not None
    assert rec2.status == "absent"


def test_bulk_import_missing_values_and_invalid_date(client, db, att_data):
    """Missing status defaults to absent; invalid date is gracefully skipped with warning."""
    client.post("/login", data={"username": "faculty1", "password": "Faculty@123"})

    csv_content = (
        "roll_number,code,date,session_slot,status\n"
        "CS202501,CS601,2025-09-21,1,\n"             # Missing status -> defaults to absent
        "CS202502,CS601,invalid-date-format,1,present\n" # Invalid date -> skipped
        "UNKNOWN_ROLL,CS601,2025-09-21,1,present\n"       # Unknown student -> skipped
    )
    file_bytes = io.BytesIO(csv_content.encode("utf-8"))

    r = client.post(
        "/attendance/import",
        data={
            "file": (file_bytes, "edge_cases.csv"),
            "subject_id": att_data["sub1"].id,
            "default_date": "2025-09-21",
            "default_session": "1"
        },
        content_type="multipart/form-data",
        follow_redirects=True
    )
    assert r.status_code == 200

    # Missing status row must be saved with status 'absent'
    rec1 = AttendanceRecord.query.filter_by(
        student_id=att_data["st1"].id, subject_id=att_data["sub1"].id, date=date(2025, 9, 21)
    ).first()
    assert rec1 is not None
    assert rec1.status == "absent"

    # Invalid date row must NOT crash and not be inserted with invalid date
    rec2 = AttendanceRecord.query.filter_by(
        student_id=att_data["st2"].id, subject_id=att_data["sub1"].id, date=date(2025, 9, 21)
    ).first()
    assert rec2 is None


def test_bulk_import_duplicate_updates_with_audit(client, db, att_data):
    """Re-importing an existing session updates the record and logs into edit history."""
    client.post("/login", data={"username": "faculty1", "password": "Faculty@123"})

    # First import
    csv_1 = (
        "roll_number,code,date,session_slot,status\n"
        "CS202501,CS601,2025-09-22,1,absent\n"
    )
    client.post(
        "/attendance/import",
        data={"file": (io.BytesIO(csv_1.encode("utf-8")), "batch1.csv")},
        content_type="multipart/form-data",
        follow_redirects=True
    )

    rec = AttendanceRecord.query.filter_by(
        student_id=att_data["st1"].id, subject_id=att_data["sub1"].id, date=date(2025, 9, 22), session_slot=1
    ).first()
    assert rec.status == "absent"

    # Second import with updated status
    csv_2 = (
        "roll_number,code,date,session_slot,status\n"
        "CS202501,CS601,2025-09-22,1,present\n"
    )
    client.post(
        "/attendance/import",
        data={"file": (io.BytesIO(csv_2.encode("utf-8")), "batch2.csv")},
        content_type="multipart/form-data",
        follow_redirects=True
    )

    db.session.refresh(rec)
    assert rec.status == "present"

    # Audit history recorded
    audit = AttendanceEditHistory.query.filter_by(attendance_record_id=rec.id).first()
    assert audit is not None
    assert audit.old_status == "absent"
    assert audit.new_status == "present"
    assert audit.reason == "Bulk upload update"


def test_bulk_import_excel(client, db, att_data):
    """Bulk import works with .xlsx Excel spreadsheets."""
    client.post("/login", data={"username": "faculty1", "password": "Faculty@123"})

    df = pd.DataFrame([
        {"roll_number": "CS202501", "code": "CS601", "date": "2025-09-25", "session_slot": 1, "status": "present"},
        {"roll_number": "CS202502", "code": "CS601", "date": "2025-09-25", "session_slot": 1, "status": "late"},
    ])
    excel_buffer = io.BytesIO()
    df.to_excel(excel_buffer, index=False, engine="openpyxl")
    excel_buffer.seek(0)

    r = client.post(
        "/attendance/import",
        data={"file": (excel_buffer, "attendance_upload.xlsx")},
        content_type="multipart/form-data",
        follow_redirects=True
    )
    assert r.status_code == 200
    assert b"Bulk Upload Complete" in r.data

    rec_late = AttendanceRecord.query.filter_by(
        student_id=att_data["st2"].id, subject_id=att_data["sub1"].id, date=date(2025, 9, 25)
    ).first()
    assert rec_late is not None
    assert rec_late.status == "late"


def test_download_attendance_template(client, att_data):
    """Route /attendance/template returns downloadable CSV template."""
    client.post("/login", data={"username": "faculty1", "password": "Faculty@123"})

    r = client.get("/attendance/template")
    assert r.status_code == 200
    assert r.content_type.startswith("text/csv")
    assert b"roll_number,date,session_slot,status,remarks,code" in r.data


# ─────────────────────────────────────────────────────────────────────────────
# 5. Percentage Calculation & Risk Classification
# ─────────────────────────────────────────────────────────────────────────────
def test_attendance_percentage_and_risk_classification(db, att_data):
    """Automatic percentage calculation: (Attended / Conducted) × 100 with accurate risk tiers."""
    st = att_data["st1"]
    sub = att_data["sub1"]
    admin = att_data["admin"]

    # 0 conducted classes
    stats_0 = st.get_subject_stats(sub.id)
    assert stats_0["conducted"] == 0
    assert stats_0["attended"] == 0
    assert stats_0["percentage"] == 100.0

    # 4 sessions conducted: 3 present, 1 absent -> (3 / 4) * 100 = 75.0% (Regular)
    dates = [date(2025, 10, i) for i in range(1, 5)]
    statuses = ["present", "present", "present", "absent"]
    for d, s in zip(dates, statuses):
        rec = AttendanceRecord(
            student_id=st.id, subject_id=sub.id, date=d, session_slot=1,
            status=s, marked_by=admin.id
        )
        db.session.add(rec)
    db.session.commit()

    stats_75 = st.get_subject_stats(sub.id)
    assert stats_75["conducted"] == 4
    assert stats_75["attended"] == 3
    assert stats_75["absent"] == 1
    assert stats_75["percentage"] == 75.0
    assert stats_75["risk_level"] == "Low"
    assert not stats_75["is_shortage"]

    # Add 1 more absent: 3 / 5 = 60.0% (Medium Risk / Shortage)
    rec5 = AttendanceRecord(
        student_id=st.id, subject_id=sub.id, date=date(2025, 10, 5), session_slot=1,
        status="absent", marked_by=admin.id
    )
    db.session.add(rec5)
    db.session.commit()

    stats_60 = st.get_subject_stats(sub.id)
    assert stats_60["conducted"] == 5
    assert stats_60["attended"] == 3
    assert stats_60["percentage"] == 60.0
    assert stats_60["risk_level"] == "Medium"
    assert stats_60["is_shortage"]

    # Add 1 more absent: 3 / 6 = 50.0% (High Risk / Critical)
    rec6 = AttendanceRecord(
        student_id=st.id, subject_id=sub.id, date=date(2025, 10, 6), session_slot=1,
        status="absent", marked_by=admin.id
    )
    db.session.add(rec6)
    db.session.commit()

    stats_50 = st.get_subject_stats(sub.id)
    assert stats_50["conducted"] == 6
    assert stats_50["attended"] == 3
    assert stats_50["percentage"] == 50.0
    assert stats_50["risk_level"] == "High"
    assert stats_50["is_shortage"]


# ─────────────────────────────────────────────────────────────────────────────
# 6. Reports and Student History Routes
# ─────────────────────────────────────────────────────────────────────────────
def test_individual_student_attendance_history_route(client, db, att_data):
    """Route /attendance/student/<id> renders summary KPIs, subject breakdown, and timeline."""
    st = att_data["st1"]
    sub = att_data["sub1"]

    rec = AttendanceRecord(
        student_id=st.id, subject_id=sub.id, date=date(2025, 10, 1), session_slot=1,
        status="present", marked_by=att_data["faculty1"].id
    )
    db.session.add(rec)
    db.session.commit()

    client.post("/login", data={"username": "faculty1", "password": "Faculty@123"})
    r = client.get(f"/attendance/student/{st.id}")
    assert r.status_code == 200
    assert b"Aarav Sharma" in r.data
    assert b"CS202501" in r.data
    assert b"Machine Learning" in r.data


def test_subject_wise_report_route(client, db, att_data):
    """Route /attendance/report/subject/<id> displays conducted classes, roster, and shortage."""
    sub = att_data["sub1"]
    st1 = att_data["st1"]
    st2 = att_data["st2"]

    db.session.add_all([
        AttendanceRecord(student_id=st1.id, subject_id=sub.id, date=date(2025, 10, 2), session_slot=1, status="present", marked_by=att_data["faculty1"].id),
        AttendanceRecord(student_id=st2.id, subject_id=sub.id, date=date(2025, 10, 2), session_slot=1, status="absent", marked_by=att_data["faculty1"].id),
    ])
    db.session.commit()

    client.post("/login", data={"username": "faculty1", "password": "Faculty@123"})
    r = client.get(f"/attendance/report/subject/{sub.id}")
    assert r.status_code == 200
    assert b"Machine Learning" in r.data
    assert b"Classes Conducted" in r.data
    assert b"Aarav Sharma" in r.data
    assert b"Deepika Rao" in r.data


def test_semester_wise_report_route(client, db, att_data):
    """Route /attendance/report/semester/<id> renders master matrix with student rows and subject columns."""
    sem = att_data["semester"]
    sub1 = att_data["sub1"]
    st1 = att_data["st1"]

    rec = AttendanceRecord(
        student_id=st1.id, subject_id=sub1.id, date=date(2025, 10, 3), session_slot=1,
        status="present", marked_by=att_data["faculty1"].id
    )
    db.session.add(rec)
    db.session.commit()

    client.post("/login", data={"username": "admin", "password": "Admin@123"})
    r = client.get(f"/attendance/report/semester/{sem.id}")
    assert r.status_code == 200
    assert b"Semester 3 - 2025" in r.data
    assert b"Master Attendance Matrix" in r.data
    assert b"CS601" in r.data
    assert b"Aarav Sharma" in r.data
