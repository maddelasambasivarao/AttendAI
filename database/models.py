"""
database/models.py – SQLAlchemy ORM models for AttendAI.
Defines all database tables, relationships, constraints, and helper methods:
  1. Users (users)
  2. Students (students)
  3. Faculty (faculty)
  4. Subjects (subjects)
  5. Semesters (semesters)
  6. Student subject enrolments (student_subject_enrolments)
  7. Attendance records (attendance_records)
  8. Attendance edit history (attendance_edit_history) – Audit log
  9. Prediction history (prediction_history)
  10. Interventions (interventions)
"""

from datetime import datetime, date
import re
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy.engine import Engine
from sqlalchemy import event

db = SQLAlchemy()


@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    """Enforces SQLite Foreign Key constraints on all connections."""
    try:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# 1. USER (Auth + Role)
# ─────────────────────────────────────────────────────────────────────────────
class User(UserMixin, db.Model):
    """Login credentials and role for admin / faculty users."""
    __tablename__ = "users"

    id            = db.Column(db.Integer, primary_key=True)
    username      = db.Column(db.String(64), unique=True, nullable=False, index=True)
    email         = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role          = db.Column(db.String(20), nullable=False, default="faculty")
    # role values: 'admin', 'faculty'
    is_active     = db.Column(db.Boolean, default=True)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)

    # ── Relationships ─────────────────────────────────────────────────────────
    faculty_profile = db.relationship(
        "Faculty",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan"
    )
    marked_attendances = db.relationship(
        "AttendanceRecord",
        foreign_keys="AttendanceRecord.marked_by",
        back_populates="marker"
    )
    attendance_corrections = db.relationship(
        "AttendanceEditHistory",
        foreign_keys="AttendanceEditHistory.edited_by",
        back_populates="editor"
    )

    # ── Password helpers ──────────────────────────────────────────────────────
    def set_password(self, password: str):
        """Hashes password securely with salt."""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        """Verifies password against stored secure hash."""
        return check_password_hash(self.password_hash, password)

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    @property
    def is_faculty(self) -> bool:
        return self.role == "faculty"

    @property
    def display_name(self) -> str:
        if self.faculty_profile:
            return self.faculty_profile.name
        return self.username

    def __repr__(self):
        return f"<User {self.username} [{self.role}]>"


# ─────────────────────────────────────────────────────────────────────────────
# 2. FACULTY
# ─────────────────────────────────────────────────────────────────────────────
class Faculty(db.Model):
    """Faculty profile linked to a User account."""
    __tablename__ = "faculty"

    id          = db.Column(db.Integer, primary_key=True)
    user_id     = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    name        = db.Column(db.String(128), nullable=False)
    department  = db.Column(db.String(100), default="Computer Science")
    employee_id = db.Column(db.String(50), unique=True, index=True)
    phone       = db.Column(db.String(20))

    # ── Relationships ─────────────────────────────────────────────────────────
    user          = db.relationship("User", back_populates="faculty_profile")
    subjects      = db.relationship("Subject", back_populates="faculty", lazy="dynamic")
    interventions = db.relationship("Intervention", back_populates="faculty", lazy="dynamic")

    def can_manage_subject(self, subject_id: int) -> bool:
        """Checks if this faculty is assigned to teach the specified subject."""
        return self.subjects.filter_by(id=subject_id).first() is not None

    def __repr__(self):
        return f"<Faculty {self.name} ({self.employee_id})>"


# ─────────────────────────────────────────────────────────────────────────────
# 3. SEMESTER
# ─────────────────────────────────────────────────────────────────────────────
class Semester(db.Model):
    """Academic semester / term."""
    __tablename__ = "semesters"

    id         = db.Column(db.Integer, primary_key=True)
    name       = db.Column(db.String(100), nullable=False, unique=True)   # e.g. "Semester 3 – 2025-26"
    year       = db.Column(db.Integer, nullable=False)
    section    = db.Column(db.String(10), default="A")
    start_date = db.Column(db.Date)
    end_date   = db.Column(db.Date)
    is_active  = db.Column(db.Boolean, default=True)

    # ── Relationships ─────────────────────────────────────────────────────────
    students    = db.relationship("Student", back_populates="semester", lazy="dynamic")
    subjects    = db.relationship("Subject",  back_populates="semester", lazy="dynamic", cascade="all, delete-orphan")
    predictions = db.relationship("PredictionHistory", back_populates="semester", lazy="dynamic", cascade="all, delete-orphan")

    @property
    def progress(self) -> float:
        """Returns semester progress as a float between 0.0 and 1.0."""
        if not self.start_date or not self.end_date:
            return 0.0
        today = date.today()
        total = (self.end_date - self.start_date).days or 1
        elapsed = (today - self.start_date).days
        return max(0.0, min(1.0, elapsed / total))

    def __repr__(self):
        return f"<Semester {self.name}>"


# ─────────────────────────────────────────────────────────────────────────────
# 4. STUDENT
# ─────────────────────────────────────────────────────────────────────────────
class Student(db.Model):
    """
    Student master record.
    Fields:
      - student_id: Unique system / institution ID (e.g. STU2025001)
      - roll_number: Unique class roll number (e.g. CS202501)
      - name: Full name of student
      - department: Academic department
      - year: Study year (1, 2, 3, 4, etc.)
      - section: Class section (A, B, C...)
      - email: Contact email address
      - semester_id: Foreign key to Semester
    """
    __tablename__ = "students"

    id                = db.Column(db.Integer, primary_key=True)
    student_id        = db.Column(db.String(30), unique=True, nullable=False, index=True)
    roll_number       = db.Column(db.String(30), unique=True, nullable=False, index=True)
    name              = db.Column(db.String(128), nullable=False)
    department        = db.Column(db.String(100), default="Computer Science", nullable=False)
    year              = db.Column(db.Integer, default=1, nullable=False)
    section           = db.Column(db.String(10), default="A", nullable=False)
    email             = db.Column(db.String(120), nullable=True)
    phone             = db.Column(db.String(20), nullable=True)
    semester_id       = db.Column(db.Integer, db.ForeignKey("semesters.id", ondelete="RESTRICT"), nullable=False, index=True)
    date_of_admission = db.Column(db.Date, default=date.today)
    is_active         = db.Column(db.Boolean, default=True)
    created_at        = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at        = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # ── Table Constraints ─────────────────────────────────────────────────────
    __table_args__ = (
        db.UniqueConstraint("student_id", name="uq_students_student_id"),
        db.UniqueConstraint("roll_number", name="uq_students_roll_number"),
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    semester      = db.relationship("Semester", back_populates="students")
    attendances   = db.relationship("AttendanceRecord", back_populates="student",
                                    cascade="all, delete-orphan", lazy="dynamic")
    predictions   = db.relationship("PredictionHistory", back_populates="student",
                                    cascade="all, delete-orphan", lazy="dynamic")
    interventions = db.relationship("Intervention", back_populates="student",
                                    cascade="all, delete-orphan", lazy="dynamic")
    enrolments    = db.relationship("StudentSubjectEnrolment", back_populates="student",
                                    cascade="all, delete-orphan", lazy="dynamic")

    def __init__(self, **kwargs):
        # Allow 'full_name' as alias for 'name'
        if "full_name" in kwargs and "name" not in kwargs:
            kwargs["name"] = kwargs.pop("full_name")
        super().__init__(**kwargs)
        # Auto-generate student_id if not provided
        if not self.student_id and self.roll_number:
            self.student_id = f"STU-{self.roll_number}"
        if not self.department:
            self.department = "Computer Science"
        if self.year is None:
            self.year = 1
        if not self.section:
            self.section = "A"

    @property
    def full_name(self) -> str:
        return self.name

    @full_name.setter
    def full_name(self, value: str):
        self.name = value

    @staticmethod
    def validate_email(email_str: str) -> bool:
        """Validates standard email format."""
        if not email_str:
            return True
        pattern = r"^[\w\.-]+@[\w\.-]+\.\w+$"
        return bool(re.match(pattern, email_str.strip()))

    # ── Computed Attendance Helpers (Attended / Conducted * 100) ───────────────
    def get_subject_stats(self, subject_id: int) -> dict:
        """
        Calculates exact attendance statistics for a single subject:
        Formula: (Attended / Conducted) * 100
        """
        records = self.attendances.filter_by(subject_id=subject_id).all()
        conducted = len(records)
        attended  = sum(1 for r in records if r.status in ("present", "late"))
        absent    = sum(1 for r in records if r.status == "absent")
        pct       = round((attended / conducted) * 100, 2) if conducted > 0 else 100.0

        if conducted == 0:
            risk = "Low"
            is_shortage = False
        elif pct < 60.0:
            risk = "High"
            is_shortage = True
        elif pct < 75.0:
            risk = "Medium"
            is_shortage = True
        else:
            risk = "Low"
            is_shortage = False

        return {
            "conducted": conducted,
            "attended": attended,
            "absent": absent,
            "percentage": pct,
            "is_shortage": is_shortage,
            "risk_level": risk,
            "badge_class": "danger" if risk == "High" else ("warning" if risk == "Medium" else "success")
        }

    def get_overall_stats(self) -> dict:
        """
        Calculates overall cumulative attendance statistics across all subjects:
        Formula: (Total Attended / Total Conducted) * 100
        """
        records = self.attendances.all()
        conducted = len(records)
        attended  = sum(1 for r in records if r.status in ("present", "late"))
        absent    = sum(1 for r in records if r.status == "absent")
        pct       = round((attended / conducted) * 100, 2) if conducted > 0 else 100.0

        if conducted == 0:
            risk = "Low"
            is_shortage = False
        elif pct < 60.0:
            risk = "High"
            is_shortage = True
        elif pct < 75.0:
            risk = "Medium"
            is_shortage = True
        else:
            risk = "Low"
            is_shortage = False

        return {
            "conducted": conducted,
            "attended": attended,
            "absent": absent,
            "percentage": pct,
            "is_shortage": is_shortage,
            "risk_level": risk,
            "badge_class": "danger" if risk == "High" else ("warning" if risk == "Medium" else "success")
        }

    def overall_attendance_pct(self) -> float:
        """Shortcut property returning overall attendance percentage."""
        return self.get_overall_stats()["percentage"]

    def subject_attendance_pct(self, subject_id: int) -> float:
        """Shortcut property returning attendance percentage for a specific subject."""
        return self.get_subject_stats(subject_id)["percentage"]

    def latest_prediction(self):
        """Returns the most recent risk prediction for this student."""
        return self.predictions.order_by(PredictionHistory.predicted_at.desc()).first()

    def enroll_in_subject(self, subject_id: int):
        """Enrolls this student into a subject if not already enrolled."""
        existing = StudentSubjectEnrolment.query.filter_by(
            student_id=self.id, subject_id=subject_id
        ).first()
        if not existing:
            enr = StudentSubjectEnrolment(student_id=self.id, subject_id=subject_id)
            db.session.add(enr)
            return enr
        return existing

    def enroll_in_semester_subjects(self):
        """Auto-enrolls student into all subjects offered in their semester."""
        if not self.semester_id:
            return []
        subjects = Subject.query.filter_by(semester_id=self.semester_id).all()
        enrolled_list = []
        for s in subjects:
            enr = self.enroll_in_subject(s.id)
            enrolled_list.append(enr)
        return enrolled_list

    def __repr__(self):
        return f"<Student {self.roll_number} – {self.name} ({self.student_id})>"


# ─────────────────────────────────────────────────────────────────────────────
# 5. SUBJECT
# ─────────────────────────────────────────────────────────────────────────────
class Subject(db.Model):
    """Subject / course offered in a semester."""
    __tablename__ = "subjects"

    id                    = db.Column(db.Integer, primary_key=True)
    name                  = db.Column(db.String(128), nullable=False)
    code                  = db.Column(db.String(20), index=True)
    semester_id           = db.Column(db.Integer, db.ForeignKey("semesters.id", ondelete="CASCADE"), nullable=False, index=True)
    faculty_id            = db.Column(db.Integer, db.ForeignKey("faculty.id", ondelete="SET NULL"), nullable=True)
    total_classes_planned = db.Column(db.Integer, default=0)
    subject_type          = db.Column(db.String(20), default="theory")
    # subject_type: 'theory', 'lab', 'tutorial'

    # ── Relationships ─────────────────────────────────────────────────────────
    semester    = db.relationship("Semester", back_populates="subjects")
    faculty     = db.relationship("Faculty",  back_populates="subjects")
    attendances = db.relationship("AttendanceRecord", back_populates="subject",
                                  cascade="all, delete-orphan", lazy="dynamic")
    enrolments  = db.relationship("StudentSubjectEnrolment", back_populates="subject",
                                  cascade="all, delete-orphan", lazy="dynamic")

    def classes_conducted(self) -> int:
        """
        Returns the number of unique class sessions conducted for this subject.
        A session is uniquely identified by (date, session_slot).
        """
        return db.session.query(
            AttendanceRecord.date, AttendanceRecord.session_slot
        ).filter(AttendanceRecord.subject_id == self.id).distinct().count()

    def enrolled_students(self):
        """Returns query of all active students enrolled in this subject."""
        return (
            Student.query
            .join(StudentSubjectEnrolment, StudentSubjectEnrolment.student_id == Student.id)
            .filter(
                StudentSubjectEnrolment.subject_id == self.id,
                StudentSubjectEnrolment.status == "active",
                Student.is_active == True
            )
            .order_by(Student.roll_number)
        )

    def __repr__(self):
        return f"<Subject {self.code} – {self.name}>"


# ─────────────────────────────────────────────────────────────────────────────
# 6. STUDENT SUBJECT ENROLMENTS
# ─────────────────────────────────────────────────────────────────────────────
class StudentSubjectEnrolment(db.Model):
    """Enrollment mapping between a Student and a Subject."""
    __tablename__ = "student_subject_enrolments"

    id          = db.Column(db.Integer, primary_key=True)
    student_id  = db.Column(db.Integer, db.ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    subject_id  = db.Column(db.Integer, db.ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False, index=True)
    enrolled_at = db.Column(db.DateTime, default=datetime.utcnow)
    status      = db.Column(db.String(20), default="active")  # 'active', 'dropped', 'completed'

    # ── Unique Constraint: one enrollment per student per subject ──────────────
    __table_args__ = (
        db.UniqueConstraint("student_id", "subject_id", name="uq_student_subject_enrolment"),
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    student = db.relationship("Student", back_populates="enrolments")
    subject = db.relationship("Subject", back_populates="enrolments")

    def __repr__(self):
        return f"<StudentSubjectEnrolment Student={self.student_id} Subject={self.subject_id} [{self.status}]>"

# Alias for American spelling
StudentSubjectEnrollment = StudentSubjectEnrolment


# ─────────────────────────────────────────────────────────────────────────────
# 7. ATTENDANCE RECORD
# ─────────────────────────────────────────────────────────────────────────────
class AttendanceRecord(db.Model):
    """
    One attendance entry per student per subject per class session (date + session_slot).
    Prevents duplicate entries for the same student, subject, and class session.
    """
    __tablename__ = "attendance_records"

    id               = db.Column(db.Integer, primary_key=True)
    student_id       = db.Column(db.Integer, db.ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    subject_id       = db.Column(db.Integer, db.ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False, index=True)
    date             = db.Column(db.Date, nullable=False, index=True)
    session_slot     = db.Column(db.Integer, default=1, nullable=False)
    # session_slot: 1, 2, 3... distinguishes multiple sessions on the same date
    status           = db.Column(db.String(10), nullable=False, default="present")
    # status values: 'present', 'absent', 'late', 'excused'
    remarks          = db.Column(db.String(200), nullable=True)
    marked_by        = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    last_modified_by = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at       = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at       = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # ── Unique constraint: strictly prevents duplicate marking for same student, subject, date & session ──
    __table_args__ = (
        db.UniqueConstraint("student_id", "subject_id", "date", "session_slot", name="uq_attendance_session"),
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    student       = db.relationship("Student", back_populates="attendances")
    subject       = db.relationship("Subject", back_populates="attendances")
    marker        = db.relationship("User", foreign_keys=[marked_by], back_populates="marked_attendances")
    last_editor   = db.relationship("User", foreign_keys=[last_modified_by])
    edit_history  = db.relationship(
        "AttendanceEditHistory",
        back_populates="attendance_record",
        cascade="all, delete-orphan",
        order_by="desc(AttendanceEditHistory.edited_at)"
    )

    def is_present(self) -> bool:
        return self.status in ("present", "late")

    @property
    def edit_count(self) -> int:
        return len(self.edit_history) if self.edit_history else 0

    def __repr__(self):
        return f"<Attendance Student={self.student_id} Sub={self.subject_id} Date={self.date} Slot={self.session_slot} [{self.status}]>"


# ─────────────────────────────────────────────────────────────────────────────
# 8. ATTENDANCE EDIT HISTORY (Audit Trail)
# ─────────────────────────────────────────────────────────────────────────────
class AttendanceEditHistory(db.Model):
    """
    Maintains an immutable audit log of all attendance corrections made by
    authorised faculty or administrators.
    """
    __tablename__ = "attendance_edit_history"

    id                   = db.Column(db.Integer, primary_key=True)
    attendance_record_id = db.Column(db.Integer, db.ForeignKey("attendance_records.id", ondelete="CASCADE"), nullable=False, index=True)
    old_status           = db.Column(db.String(10), nullable=False)
    new_status           = db.Column(db.String(10), nullable=False)
    reason               = db.Column(db.String(255), nullable=True)
    edited_by            = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    edited_at            = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    # ── Relationships ─────────────────────────────────────────────────────────
    attendance_record = db.relationship("AttendanceRecord", back_populates="edit_history")
    editor            = db.relationship("User", foreign_keys=[edited_by], back_populates="attendance_corrections")

    def __repr__(self):
        return f"<AttendanceEditHistory Rec={self.attendance_record_id} {self.old_status} -> {self.new_status} by User={self.edited_by}>"


# ─────────────────────────────────────────────────────────────────────────────
# 9. PREDICTION HISTORY
# ─────────────────────────────────────────────────────────────────────────────
class PredictionHistory(db.Model):
    """Snapshot and history of ML risk predictions for a student in a semester."""
    __tablename__ = "prediction_history"

    id                          = db.Column(db.Integer, primary_key=True)
    student_id                  = db.Column(db.Integer, db.ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    semester_id                 = db.Column(db.Integer, db.ForeignKey("semesters.id", ondelete="CASCADE"), nullable=False, index=True)
    attendance_percentage       = db.Column(db.Float)
    risk_probability            = db.Column(db.Float, default=0.0)
    predicted_final_percentage  = db.Column(db.Float)
    risk_level                  = db.Column(db.String(10))
    # risk_level: 'Low', 'Medium', 'High'
    recommendations             = db.Column(db.Text)
    predicted_at                = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    model_version               = db.Column(db.String(30), default="2.0.0")

    # ── Relationships ─────────────────────────────────────────────────────────
    student  = db.relationship("Student",  back_populates="predictions")
    semester = db.relationship("Semester", back_populates="predictions")

    @property
    def risk_badge_class(self) -> str:
        return {"High": "danger", "Medium": "warning", "Low": "success"}.get(self.risk_level, "secondary")

    def __repr__(self):
        return f"<PredictionHistory Student={self.student_id} [{self.risk_level}] prob={self.risk_probability} @ {self.predicted_at}>"

# Backward compatibility alias
RiskPrediction = PredictionHistory


# ─────────────────────────────────────────────────────────────────────────────
# 10. INTERVENTION (Faculty Action Tracking)
# ─────────────────────────────────────────────────────────────────────────────
class Intervention(db.Model):
    """
    Faculty intervention record for an at-risk student.
    Tracks contact history, student explanation, and post-intervention attendance outcome.
    """
    __tablename__ = "interventions"

    id                          = db.Column(db.Integer, primary_key=True)
    student_id                  = db.Column(db.Integer, db.ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    faculty_id                  = db.Column(db.Integer, db.ForeignKey("faculty.id", ondelete="CASCADE"), nullable=False, index=True)
    intervention_type           = db.Column(db.String(50), default="counselling")
    # types: 'counselling', 'meeting', 'parent_contact', 'warning_letter', 'remedial_class', 'email'
    notes                       = db.Column(db.Text)
    intervention_date           = db.Column(db.Date, default=date.today)
    status                      = db.Column(db.String(20), default="open")
    # status: 'open', 'in_progress', 'resolved'

    # ── Tracking Fields (Requirement 9) ────────────────────────────────────────
    student_contacted           = db.Column(db.Boolean, default=True, nullable=False)
    contact_date                = db.Column(db.Date, default=date.today)
    contact_method              = db.Column(db.String(50), default="In-Person Meeting")
    # methods: 'In-Person Meeting', 'Phone Call', 'Email', 'Parent Meeting', 'Official Notice'
    explanation_received        = db.Column(db.Boolean, default=False, nullable=False)
    student_explanation         = db.Column(db.Text, nullable=True)
    # student_explanation: Medical grounds, family emergency, academic burnout, transportation, etc.
    attendance_improved         = db.Column(db.String(20), default="pending", nullable=False)
    # improved: 'improved', 'no_change', 'declined', 'pending'
    attendance_at_intervention  = db.Column(db.Float, nullable=True)
    post_intervention_attendance_pct = db.Column(db.Float, nullable=True)

    follow_up_date              = db.Column(db.Date, nullable=True)
    created_at                  = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at                  = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # ── Relationships ─────────────────────────────────────────────────────────
    student = db.relationship("Student", back_populates="interventions")
    faculty = db.relationship("Faculty", back_populates="interventions")

    @property
    def status_badge_class(self) -> str:
        return {
            "resolved": "success",
            "in_progress": "info",
            "open": "warning"
        }.get(self.status, "secondary")

    @property
    def outcome_badge_class(self) -> str:
        return {
            "improved": "success",
            "declined": "danger",
            "no_change": "warning",
            "pending": "secondary"
        }.get(self.attendance_improved, "secondary")

    def __repr__(self):
        return f"<Intervention Student={self.student_id} Status={self.status} Outcome={self.attendance_improved}>"


# ─────────────────────────────────────────────────────────────────────────────
# 11. SYSTEM SETTING (Configurable Academic Thresholds & Policies)
# ─────────────────────────────────────────────────────────────────────────────
class SystemSetting(db.Model):
    """Stores key-value system configurations (e.g. attendance thresholds, institution info)."""
    __tablename__ = "system_settings"

    key         = db.Column(db.String(64), primary_key=True)
    value       = db.Column(db.String(256), nullable=False)
    description = db.Column(db.String(256), nullable=True)

    @classmethod
    def get(cls, key: str, default: str = "") -> str:
        try:
            s = cls.query.filter_by(key=key).first()
            return s.value if s else default
        except Exception:
            return default

    @classmethod
    def set(cls, key: str, value: str, description: str = None):
        s = cls.query.filter_by(key=key).first()
        if not s:
            s = cls(key=key, value=str(value), description=description)
            db.session.add(s)
        else:
            s.value = str(value)
            if description:
                s.description = description
        db.session.commit()
        return s

    def __repr__(self):
        return f"<SystemSetting {self.key}={self.value}>"


__all__ = [
    "db",
    "User",
    "Faculty",
    "Semester",
    "Student",
    "Subject",
    "StudentSubjectEnrolment",
    "StudentSubjectEnrollment",
    "AttendanceRecord",
    "AttendanceEditHistory",
    "PredictionHistory",
    "RiskPrediction",
    "Intervention",
    "SystemSetting",
]
