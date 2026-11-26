"""
routes/faculty.py – Faculty blueprint.
Faculty dashboard and intervention management.
"""

from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from database.models import db, Faculty, Student, Semester, Intervention, RiskPrediction, AttendanceRecord
from datetime import date

faculty_bp = Blueprint("faculty", __name__)


def get_current_faculty():
    """Return the Faculty profile for the logged-in user."""
    if current_user.faculty_profile:
        return current_user.faculty_profile
    return None


@faculty_bp.route("/students")
@login_required
def students():
    return redirect(url_for("admin.students", **request.args))


@faculty_bp.route("/dashboard")
@login_required
def dashboard():
    faculty = get_current_faculty()
    active_sem = Semester.query.filter_by(is_active=True).first()

    # Faculty sees their own subjects' students
    if faculty:
        faculty_subjects = faculty.subjects.all()
        subject_ids = [s.id for s in faculty_subjects]
    else:
        faculty_subjects = []
        subject_ids = []

    # Recent attendance records for this faculty's subjects
    recent_records = (
        AttendanceRecord.query
        .filter(AttendanceRecord.subject_id.in_(subject_ids))
        .order_by(AttendanceRecord.date.desc())
        .limit(20)
        .all()
    ) if subject_ids else []

    # Subjects attendance data for Chart.js
    subject_labels = []
    subject_data = []
    total_att_records = 0
    total_present_records = 0

    for s in faculty_subjects:
        recs = AttendanceRecord.query.filter_by(subject_id=s.id).all()
        if recs:
            s_cond = len(recs)
            s_pres = sum(1 for r in recs if r.status in ("present", "late"))
            s_pct = round((s_pres / s_cond) * 100, 1)
            total_att_records += s_cond
            total_present_records += s_pres
        else:
            s_pct = 0.0
        subject_labels.append(s.code or s.name)
        subject_data.append(s_pct)

    avg_faculty_attendance = round((total_present_records / total_att_records * 100), 1) if total_att_records > 0 else 0.0

    # At-risk students in active semester
    at_risk = []
    high_count = 0
    med_count = 0
    low_count = 0

    if active_sem:
        # Get students enrolled in faculty's subjects
        if subject_ids:
            enrolled_student_ids = db.session.query(Student.id).join(
                Student.enrolments
            ).filter(Student.enrolments.property.mapper.class_.subject_id.in_(subject_ids)).distinct().all()
            st_ids = [sid[0] for sid in enrolled_student_ids]
        else:
            st_ids = []

        if st_ids:
            at_risk = (
                RiskPrediction.query
                .filter(
                    RiskPrediction.semester_id == active_sem.id,
                    RiskPrediction.student_id.in_(st_ids),
                    RiskPrediction.risk_level.in_(["High", "Medium"]),
                )
                .order_by(RiskPrediction.predicted_at.desc())
                .all()
            )
            for p in at_risk:
                if p.risk_level == "High":
                    high_count += 1
                elif p.risk_level == "Medium":
                    med_count += 1
            low_count = max(0, len(st_ids) - high_count - med_count)
            total_students_count = len(st_ids)
        else:
            total_students_count = 0
    else:
        total_students_count = 0

    # Open interventions by this faculty
    open_interventions = []
    if faculty:
        open_interventions = (
            faculty.interventions
            .filter(Intervention.status.in_(["open", "in_progress"]))
            .order_by(Intervention.created_at.desc())
            .all()
        )

    stats = {
        "total_students": total_students_count,
        "total_subjects": len(faculty_subjects),
        "average_attendance": avg_faculty_attendance,
        "high_risk": high_count,
        "medium_risk": med_count,
        "low_risk": low_count,
        "subject_labels": subject_labels,
        "subject_data": subject_data,
    }

    return render_template(
        "faculty/dashboard.html",
        faculty=faculty,
        active_sem=active_sem,
        recent_records=recent_records,
        at_risk=at_risk,
        open_interventions=open_interventions,
        stats=stats,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Interventions
# ─────────────────────────────────────────────────────────────────────────────
@faculty_bp.route("/interventions")
@login_required
def interventions():
    faculty = get_current_faculty()
    all_interventions = []
    active_sem = Semester.query.filter_by(is_active=True).first()
    students = []

    if active_sem:
        students = Student.query.filter_by(
            semester_id=active_sem.id, is_active=True
        ).order_by(Student.name).all()

    if faculty:
        all_interventions = (
            faculty.interventions
            .order_by(Intervention.created_at.desc())
            .all()
        )
    elif current_user.is_admin:
        all_interventions = Intervention.query.order_by(Intervention.created_at.desc()).all()

    return render_template(
        "faculty/interventions.html",
        interventions=all_interventions,
        students=students,
    )


@faculty_bp.route("/interventions/add", methods=["POST"])
@login_required
def add_intervention():
    faculty = get_current_faculty()
    if not faculty:
        first_fac = Faculty.query.first()
        faculty = first_fac

    if not faculty:
        flash("Faculty profile not found.", "danger")
        return redirect(url_for("faculty.interventions"))

    student_id        = request.form.get("student_id", type=int)
    intervention_type = request.form.get("intervention_type", "meeting")
    notes             = request.form.get("notes", "").strip()
    follow_up_str     = request.form.get("follow_up_date", "")

    # Requirement 9 tracking fields
    student_contacted = request.form.get("student_contacted") in ("1", "true", "on", "yes")
    contact_method    = request.form.get("contact_method", "In-Person Meeting").strip()
    explanation_rcvd  = request.form.get("explanation_received") in ("1", "true", "on", "yes")
    explanation_text  = request.form.get("student_explanation", "").strip()

    if not student_id:
        flash("Please select a student.", "danger")
        return redirect(url_for("faculty.interventions"))

    student = db.session.get(Student, student_id)
    current_pct = student.overall_attendance_pct() if student else 0.0

    iv = Intervention(
        student_id=student_id,
        faculty_id=faculty.id,
        intervention_type=intervention_type,
        notes=notes,
        intervention_date=date.today(),
        status="in_progress" if student_contacted else "open",
        student_contacted=student_contacted,
        contact_date=date.today(),
        contact_method=contact_method,
        explanation_received=explanation_rcvd,
        student_explanation=explanation_text if explanation_rcvd else None,
        attendance_improved="pending",
        attendance_at_intervention=current_pct,
        follow_up_date=date.fromisoformat(follow_up_str) if follow_up_str else None,
    )
    db.session.add(iv)
    db.session.commit()
    flash("Intervention logged successfully.", "success")
    return redirect(url_for("faculty.interventions"))


@faculty_bp.route("/interventions/<int:iv_id>/update", methods=["POST"])
@login_required
def update_intervention(iv_id):
    iv = db.session.get(Intervention, iv_id)
    if not iv:
        flash("Intervention not found.", "danger")
        return redirect(url_for("faculty.interventions"))

    iv.status = request.form.get("status", iv.status)
    iv.notes  = request.form.get("notes", iv.notes)

    # Update tracking fields
    improved = request.form.get("attendance_improved")
    if improved in ("improved", "no_change", "declined", "pending"):
        iv.attendance_improved = improved

    explanation = request.form.get("student_explanation")
    if explanation:
        iv.explanation_received = True
        iv.student_explanation = explanation.strip()

    if iv.student:
        iv.post_intervention_attendance_pct = iv.student.overall_attendance_pct()

    db.session.commit()
    flash("Intervention updated.", "success")
    return redirect(url_for("faculty.interventions"))
