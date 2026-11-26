"""tests/test_models.py – Unit tests for SQLAlchemy ORM models."""

from database.models import User, Faculty, Semester, Student, Subject, AttendanceRecord
from datetime import date


def test_user_password_hashing(db):
    """Password hash and check work correctly."""
    u = User(username="testuser", email="t@test.com", role="faculty")
    u.set_password("Secret@123")
    db.session.add(u)
    db.session.commit()

    assert u.check_password("Secret@123") is True
    assert u.check_password("wrong") is False


def test_user_is_admin(db):
    u = User(username="adm", email="adm@test.com", role="admin")
    u.set_password("p")
    db.session.add(u)
    db.session.commit()
    assert u.is_admin is True


def test_semester_progress(db):
    """Semester.progress returns value in 0–1 range."""
    sem = Semester(
        name="Test Sem",
        year=2025,
        start_date=date(2025, 1, 1),
        end_date=date(2025, 6, 30),
    )
    db.session.add(sem)
    db.session.commit()
    assert 0.0 <= sem.progress <= 1.0


def test_student_overall_attendance(db):
    """overall_attendance_pct returns correct percentage."""
    sem = Semester(name="Sem A", year=2025)
    db.session.add(sem)
    db.session.flush()

    st = Student(name="Alice", roll_number="T001", semester_id=sem.id)
    db.session.add(st)
    db.session.flush()

    subj = Subject(name="Math", code="M101", semester_id=sem.id)
    db.session.add(subj)
    db.session.flush()

    # 3 present, 1 absent → 75%
    for i, status in enumerate(["present", "present", "present", "absent"]):
        rec = AttendanceRecord(
            student_id=st.id, subject_id=subj.id,
            date=date(2025, 9, i + 1), status=status
        )
        db.session.add(rec)
    db.session.commit()

    assert st.overall_attendance_pct() == 75.0
