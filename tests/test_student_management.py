"""
tests/test_student_management.py – Comprehensive unit & integration tests
for Student Management and Database operations.
Covers:
  - Student model fields & defaults
  - Duplicate student ID & roll number constraints
  - Password hashing & verification
  - Student subject enrolments & relationships
  - Student search by roll number and name
  - Multi-field filters: department, year, section
  - Student editing with duplicate protection
  - Safe deletion safeguards (soft delete vs hard delete)
  - Bulk import from CSV with duplicate & error handling
"""

import io
from datetime import date
import pytest
from database.models import (
    User, Faculty, Semester, Student, Subject,
    StudentSubjectEnrolment, AttendanceRecord
)


@pytest.fixture
def base_data(db):
    """Seed base admin, faculty, semester and subjects for testing."""
    # Admin
    admin = User(username="test_admin", email="admin@test.com", role="admin")
    admin.set_password("AdminPass@123")
    db.session.add(admin)

    # Faculty
    fac_user = User(username="test_fac", email="fac@test.com", role="faculty")
    fac_user.set_password("FacPass@123")
    db.session.add(fac_user)
    db.session.flush()

    fac = Faculty(user_id=fac_user.id, name="Dr. Test", department="Computer Science", employee_id="T001")
    db.session.add(fac)

    # Semester
    sem = Semester(
        name="Semester 1 - 2025",
        year=2025,
        section="A",
        start_date=date(2025, 1, 1),
        end_date=date(2025, 6, 30),
        is_active=True
    )
    db.session.add(sem)
    db.session.flush()

    # Subjects
    sub1 = Subject(name="Programming in Python", code="CS101", semester_id=sem.id, faculty_id=fac.id, total_classes_planned=40)
    sub2 = Subject(name="Discrete Mathematics", code="MA101", semester_id=sem.id, faculty_id=fac.id, total_classes_planned=35)
    db.session.add_all([sub1, sub2])
    db.session.commit()

    return {
        "admin": admin,
        "faculty_user": fac_user,
        "faculty": fac,
        "semester": sem,
        "subjects": [sub1, sub2]
    }


# ─────────────────────────────────────────────────────────────────────────────
# 1. Model Fields & Validations
# ─────────────────────────────────────────────────────────────────────────────
def test_student_fields_and_defaults(db, base_data):
    """Student is created with all required fields and correct defaults."""
    sem = base_data["semester"]
    st = Student(
        student_id="STU2025001",
        roll_number="CS2501",
        name="Aarav Sharma",
        department="Computer Science",
        year=1,
        section="A",
        email="aarav@test.com",
        semester_id=sem.id
    )
    db.session.add(st)
    db.session.commit()

    saved = Student.query.filter_by(roll_number="CS2501").first()
    assert saved is not None
    assert saved.student_id == "STU2025001"
    assert saved.roll_number == "CS2501"
    assert saved.name == "Aarav Sharma"
    assert saved.full_name == "Aarav Sharma"
    assert saved.department == "Computer Science"
    assert saved.year == 1
    assert saved.section == "A"
    assert saved.email == "aarav@test.com"
    assert saved.semester_id == sem.id
    assert saved.is_active is True


def test_student_auto_generates_student_id(db, base_data):
    """If student_id is omitted, it auto-generates from roll_number."""
    sem = base_data["semester"]
    st = Student(
        roll_number="CS2599",
        name="Rohit Verma",
        semester_id=sem.id
    )
    assert st.student_id == "STU-CS2599"


def test_duplicate_roll_number_rejected(db, base_data):
    """Database rejects duplicate roll numbers."""
    sem = base_data["semester"]
    st1 = Student(student_id="S001", roll_number="DUP01", name="Student One", semester_id=sem.id)
    db.session.add(st1)
    db.session.commit()

    st2 = Student(student_id="S002", roll_number="DUP01", name="Student Two", semester_id=sem.id)
    db.session.add(st2)
    with pytest.raises(Exception):
        db.session.commit()
    db.session.rollback()


def test_duplicate_student_id_rejected(db, base_data):
    """Database rejects duplicate student IDs."""
    sem = base_data["semester"]
    st1 = Student(student_id="UNIQ_ID", roll_number="ROLL01", name="Student A", semester_id=sem.id)
    db.session.add(st1)
    db.session.commit()

    st2 = Student(student_id="UNIQ_ID", roll_number="ROLL02", name="Student B", semester_id=sem.id)
    db.session.add(st2)
    with pytest.raises(Exception):
        db.session.commit()
    db.session.rollback()


# ─────────────────────────────────────────────────────────────────────────────
# 2. Student Subject Enrolments
# ─────────────────────────────────────────────────────────────────────────────
def test_student_subject_enrolment_and_relationship(db, base_data):
    """Student can enroll in subjects and access them via relationship."""
    sem = base_data["semester"]
    sub1, sub2 = base_data["subjects"]

    st = Student(student_id="ENR01", roll_number="ENR_ROLL", name="Enrolled Student", semester_id=sem.id)
    db.session.add(st)
    db.session.flush()

    # Auto enroll in all semester subjects
    enrolled = st.enroll_in_semester_subjects()
    db.session.commit()

    assert len(enrolled) == 2
    assert st.enrolments.count() == 2

    # Check enrolment details
    enr_record = StudentSubjectEnrolment.query.filter_by(student_id=st.id, subject_id=sub1.id).first()
    assert enr_record is not None
    assert enr_record.status == "active"
    assert enr_record.student.id == st.id
    assert enr_record.subject.id == sub1.id


def test_duplicate_enrolment_prevented(db, base_data):
    """Enrolling same student in same subject twice is prevented."""
    sem = base_data["semester"]
    sub1 = base_data["subjects"][0]

    st = Student(student_id="ENR_DUP", roll_number="ENR_DUP_ROLL", name="Dup Enrol", semester_id=sem.id)
    db.session.add(st)
    db.session.flush()

    enr1 = st.enroll_in_subject(sub1.id)
    enr2 = st.enroll_in_subject(sub1.id)  # duplicate call returns existing

    assert enr1.id == enr2.id
    db.session.commit()
    assert st.enrolments.count() == 1


# ─────────────────────────────────────────────────────────────────────────────
# 3. Secure Password Hashing
# ─────────────────────────────────────────────────────────────────────────────
def test_password_hashing_security(db):
    """Password hash is salted, non-plaintext, and verifiable."""
    u = User(username="sec_user", email="sec@test.com")
    raw_pass = "VerySecurePassword#2026"
    u.set_password(raw_pass)

    assert u.password_hash != raw_pass
    assert not u.password_hash.startswith("plaintext")
    assert u.check_password(raw_pass) is True
    assert u.check_password("wrong_guess") is False
    assert u.check_password(raw_pass.lower()) is False


# ─────────────────────────────────────────────────────────────────────────────
# 4. Search & Multi-field Filtering
# ─────────────────────────────────────────────────────────────────────────────
def test_student_search_and_filters_via_routes(client, db, base_data):
    """Search by roll/name and filter by department/year/section via client."""
    sem = base_data["semester"]

    # Login as admin
    client.post("/login", data={"username": "test_admin", "password": "AdminPass@123"})

    # Create several students across departments and years
    students_to_create = [
        Student(student_id="S_CS_1", roll_number="CSE101", name="Priya Patel", department="Computer Science", year=1, section="A", semester_id=sem.id),
        Student(student_id="S_CS_2", roll_number="CSE201", name="Priya Singh", department="Computer Science", year=2, section="B", semester_id=sem.id),
        Student(student_id="S_EC_1", roll_number="ECE101", name="Rahul Nair", department="Electronics", year=1, section="A", semester_id=sem.id),
    ]
    db.session.add_all(students_to_create)
    db.session.commit()

    # Search by name "Priya" -> should find 2 students
    r = client.get("/admin/students?search=Priya")
    assert r.status_code == 200
    assert b"CSE101" in r.data
    assert b"CSE201" in r.data
    assert b"Rahul Nair" not in r.data

    # Search by roll number "ECE101"
    r = client.get("/admin/students?search=ECE101")
    assert r.status_code == 200
    assert b"Rahul Nair" in r.data
    assert b"Priya Patel" not in r.data

    # Filter by department "Electronics"
    r = client.get("/admin/students?department=Electronics")
    assert r.status_code == 200
    assert b"Rahul Nair" in r.data
    assert b"Priya Patel" not in r.data

    # Filter by year=2
    r = client.get("/admin/students?year=2")
    assert r.status_code == 200
    assert b"CSE201" in r.data
    assert b"CSE101" not in r.data

    # Filter by section="B"
    r = client.get("/admin/students?section=B")
    assert r.status_code == 200
    assert b"CSE201" in r.data
    assert b"CSE101" not in r.data


# ─────────────────────────────────────────────────────────────────────────────
# 5. Student Add & Edit via Routes
# ─────────────────────────────────────────────────────────────────────────────
def test_faculty_can_add_student(client, db, base_data):
    """Faculty member can add a student with duplicate validation."""
    sem = base_data["semester"]

    # Login as faculty
    client.post("/login", data={"username": "test_fac", "password": "FacPass@123"})

    # Add student
    r = client.post("/admin/students/add", data={
        "name": "Kavya Sharma",
        "roll_number": "CS2026_K1",
        "student_id": "STU_KAVYA",
        "department": "Computer Science",
        "year": "1",
        "section": "A",
        "email": "kavya@test.com",
        "semester_id": sem.id,
    }, follow_redirects=True)

    assert r.status_code == 200
    assert b"Kavya Sharma" in r.data

    # Try duplicate roll number
    r_dup = client.post("/admin/students/add", data={
        "name": "Duplicate Student",
        "roll_number": "CS2026_K1",
        "semester_id": sem.id,
    }, follow_redirects=True)
    assert b"already assigned to another student" in r_dup.data


def test_edit_student_updates_fields(client, db, base_data):
    """Editing student updates fields and enforces uniqueness."""
    sem = base_data["semester"]
    st = Student(student_id="ED_01", roll_number="ED_ROLL", name="Old Name", semester_id=sem.id)
    db.session.add(st)
    db.session.commit()

    # Login as admin
    client.post("/login", data={"username": "test_admin", "password": "AdminPass@123"})

    # Update
    r = client.post(f"/admin/students/{st.id}/edit", data={
        "name": "Brand New Name",
        "roll_number": "ED_ROLL_NEW",
        "student_id": "ED_01_NEW",
        "department": "Information Technology",
        "year": "2",
        "section": "B",
        "email": "new.email@test.com",
        "semester_id": sem.id,
        "is_active": "y",
    }, follow_redirects=True)

    assert r.status_code == 200
    updated = db.session.get(Student, st.id)
    assert updated.name == "Brand New Name"
    assert updated.roll_number == "ED_ROLL_NEW"
    assert updated.department == "Information Technology"
    assert updated.year == 2
    assert updated.section == "B"


# ─────────────────────────────────────────────────────────────────────────────
# 6. Delete Safeguards
# ─────────────────────────────────────────────────────────────────────────────
def test_soft_delete_preserves_attendance_history(client, db, base_data):
    """Deactivation toggles is_active without wiping attendance records."""
    sem = base_data["semester"]
    sub = base_data["subjects"][0]

    st = Student(student_id="DEL_SAFE", roll_number="DEL_ROLL", name="Safe Delete Student", semester_id=sem.id)
    db.session.add(st)
    db.session.flush()

    att = AttendanceRecord(student_id=st.id, subject_id=sub.id, date=date.today(), status="present")
    db.session.add(att)
    db.session.commit()

    # Login as admin
    client.post("/login", data={"username": "test_admin", "password": "AdminPass@123"})

    # Soft delete / toggle active
    r = client.post(f"/admin/students/{st.id}/delete", data={"action": "deactivate"}, follow_redirects=True)
    assert r.status_code == 200

    refreshed = db.session.get(Student, st.id)
    assert refreshed is not None
    assert refreshed.is_active is False
    # Attendance record is safely preserved!
    assert refreshed.attendances.count() == 1


def test_faculty_safeguard_prevents_hard_delete_with_history(client, db, base_data):
    """Faculty cannot hard-delete a student with attendance history; student is soft-deleted instead."""
    sem = base_data["semester"]
    sub = base_data["subjects"][0]

    st = Student(student_id="FAC_SAFE", roll_number="FAC_SAFE_ROLL", name="Protected Student", semester_id=sem.id)
    db.session.add(st)
    db.session.flush()

    att = AttendanceRecord(student_id=st.id, subject_id=sub.id, date=date.today(), status="present")
    db.session.add(att)
    db.session.commit()

    # Login as faculty
    client.post("/login", data={"username": "test_fac", "password": "FacPass@123"})

    # Attempt hard delete
    r = client.post(f"/admin/students/{st.id}/delete", data={"action": "permanent"}, follow_redirects=True)
    assert r.status_code == 200
    assert b"Safeguard" in r.data or b"safely deactivated" in r.data

    # Student still exists in database!
    check_st = db.session.get(Student, st.id)
    assert check_st is not None
    assert check_st.is_active is False


# ─────────────────────────────────────────────────────────────────────────────
# 7. Bulk Import CSV / Excel
# ─────────────────────────────────────────────────────────────────────────────
def test_bulk_student_csv_import(client, db, base_data):
    """Bulk import CSV imports valid students, skips duplicates, and auto-enrols."""
    sem = base_data["semester"]

    # Login as admin
    client.post("/login", data={"username": "test_admin", "password": "AdminPass@123"})

    csv_data = (
        "student_id,roll_number,name,department,year,section,email\n"
        "STU_IMP_01,IMP_01,Imported Student 1,Computer Science,1,A,imp1@test.com\n"
        "STU_IMP_02,IMP_02,Imported Student 2,Information Technology,2,B,imp2@test.com\n"
        "STU_IMP_03,IMP_01,Duplicate Roll Student,Computer Science,1,A,imp3@test.com\n"  # Duplicate roll in file!
    )

    data = {
        "file": (io.BytesIO(csv_data.encode("utf-8")), "students.csv"),
        "default_semester_id": str(sem.id)
    }

    r = client.post("/admin/students/import", data=data, content_type="multipart/form-data", follow_redirects=True)
    assert r.status_code == 200
    assert b"Successfully imported 2 student(s)" in r.data
    assert b"skipped" in r.data

    # Verify student was imported and enrolled
    st = Student.query.filter_by(roll_number="IMP_01").first()
    assert st is not None
    assert st.name == "Imported Student 1"
    assert st.enrolments.count() == 2  # auto-enrolled in 2 subjects
