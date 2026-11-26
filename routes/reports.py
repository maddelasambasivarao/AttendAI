"""
routes/reports.py – Central Reporting & Export Blueprint for AttendAI.

Handles:
  1. Reports Hub & Navigation Dashboard (/reports).
  2. Individual Student Reports (PDF & Excel).
  3. Department-Wise Reports (PDF & Excel).
  4. Semester-Wise Attendance Matrix (PDF & Excel).
  5. Subject-Wise Attendance Audits (PDF & Excel).
  6. High-Risk Student & Intervention Reports (PDF & Excel).
  7. ML Predictions & Model Snapshots (PDF & Excel).
  8. Raw Data Dumps: Attendance Records, Risk Analysis, Subject Statistics.
  9. Downloadable Bulk Attendance Excel/CSV Templates.
"""

from datetime import date
from flask import (
    Blueprint, render_template, send_file, request, flash, redirect, url_for
)
from flask_login import login_required

from database.models import (
    db, Student, Subject, Semester, AttendanceRecord, PredictionHistory,
    Intervention, Faculty, SystemSetting
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

reports_bp = Blueprint("reports", __name__)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Reports & Data Export Hub
# ─────────────────────────────────────────────────────────────────────────────
@reports_bp.route("/")
@reports_bp.route("/index")
@login_required
def index():
    """Renders the central AttendAI Reporting and Data Export Portal."""
    semesters = Semester.query.order_by(Semester.year.desc(), Semester.name).all()
    active_sem = Semester.query.filter_by(is_active=True).first() or (semesters[0] if semesters else None)

    subjects = Subject.query.order_by(Subject.code).all()
    students = Student.query.filter_by(is_active=True).order_by(Student.name).all()

    # Unique departments
    raw_depts = db.session.query(Student.department).distinct().all()
    departments = sorted([d[0] for d in raw_depts if d[0]])

    counts = {
        "students": len(students),
        "subjects": len(subjects),
        "records": AttendanceRecord.query.count(),
        "high_risk": PredictionHistory.query.filter_by(risk_level="High").count(),
    }

    return render_template(
        "reports/index.html",
        semesters=semesters,
        active_sem=active_sem,
        subjects=subjects,
        students=students,
        departments=departments,
        counts=counts,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 2. Individual Student Reports (PDF & Excel)
# ─────────────────────────────────────────────────────────────────────────────
@reports_bp.route("/pdf/student/<int:student_id>")
@login_required
def pdf_student(student_id: int):
    student = db.session.get(Student, student_id)
    if not student:
        flash(f"Student ID {student_id} not found.", "danger")
        return redirect(url_for("reports.index"))

    buf = build_student_pdf(student_id)
    filename = f"attendai_student_{student.roll_number}_{date.today().strftime('%Y%m%d')}.pdf"
    return send_file(
        buf,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename
    )


@reports_bp.route("/excel/student/<int:student_id>")
@login_required
def excel_student(student_id: int):
    student = db.session.get(Student, student_id)
    if not student:
        flash(f"Student ID {student_id} not found.", "danger")
        return redirect(url_for("reports.index"))

    buf = build_student_excel(student_id)
    filename = f"attendai_student_{student.roll_number}_{date.today().strftime('%Y%m%d')}.xlsx"
    return send_file(
        buf,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=filename
    )


# ─────────────────────────────────────────────────────────────────────────────
# 3. Department-Wise Reports (PDF & Excel)
# ─────────────────────────────────────────────────────────────────────────────
@reports_bp.route("/pdf/department/<path:department>")
@login_required
def pdf_department(department: str):
    semester_id = request.args.get("semester_id", type=int)
    buf = build_department_pdf(department=department, semester_id=semester_id)
    safe_dept = department.replace(" ", "_").lower()
    filename = f"attendai_department_{safe_dept}_{date.today().strftime('%Y%m%d')}.pdf"
    return send_file(
        buf,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename
    )


@reports_bp.route("/excel/department/<path:department>")
@login_required
def excel_department(department: str):
    semester_id = request.args.get("semester_id", type=int)
    buf = build_attendance_records_excel(semester_id=semester_id, department=department)
    safe_dept = department.replace(" ", "_").lower()
    filename = f"attendai_department_{safe_dept}_{date.today().strftime('%Y%m%d')}.xlsx"
    return send_file(
        buf,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=filename
    )


# ─────────────────────────────────────────────────────────────────────────────
# 4. Semester-Wise Reports (PDF & Excel)
# ─────────────────────────────────────────────────────────────────────────────
@reports_bp.route("/pdf/semester/<int:semester_id>")
@login_required
def pdf_semester(semester_id: int):
    sem = db.session.get(Semester, semester_id)
    if not sem:
        flash("Semester not found.", "danger")
        return redirect(url_for("reports.index"))

    buf = build_semester_pdf(semester_id)
    filename = f"attendai_semester_{sem.name.replace(' ', '_')}_{date.today().strftime('%Y%m%d')}.pdf"
    return send_file(
        buf,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename
    )


@reports_bp.route("/excel/semester/<int:semester_id>")
@login_required
def excel_semester(semester_id: int):
    sem = db.session.get(Semester, semester_id)
    if not sem:
        flash("Semester not found.", "danger")
        return redirect(url_for("reports.index"))

    buf = build_semester_matrix_excel(semester_id)
    filename = f"attendai_semester_matrix_{sem.name.replace(' ', '_')}_{date.today().strftime('%Y%m%d')}.xlsx"
    return send_file(
        buf,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=filename
    )


# ─────────────────────────────────────────────────────────────────────────────
# 5. Subject-Wise Reports (PDF & Excel)
# ─────────────────────────────────────────────────────────────────────────────
@reports_bp.route("/pdf/subject/<int:subject_id>")
@login_required
def pdf_subject(subject_id: int):
    subj = db.session.get(Subject, subject_id)
    if not subj:
        flash("Course not found.", "danger")
        return redirect(url_for("reports.index"))

    buf = build_subject_pdf(subject_id)
    filename = f"attendai_subject_{subj.code}_{date.today().strftime('%Y%m%d')}.pdf"
    return send_file(
        buf,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename
    )


@reports_bp.route("/excel/subject/<int:subject_id>")
@login_required
def excel_subject(subject_id: int):
    subj = db.session.get(Subject, subject_id)
    if not subj:
        flash("Course not found.", "danger")
        return redirect(url_for("reports.index"))

    buf = build_attendance_records_excel(subject_id=subject_id)
    filename = f"attendai_subject_{subj.code}_{date.today().strftime('%Y%m%d')}.xlsx"
    return send_file(
        buf,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=filename
    )


# ─────────────────────────────────────────────────────────────────────────────
# 6. High-Risk Student Reports (PDF & Excel)
# ─────────────────────────────────────────────────────────────────────────────
@reports_bp.route("/pdf/high-risk")
@reports_bp.route("/pdf/risk")  # Backwards-compatible alias
@login_required
def pdf_risk():
    semester_id = request.args.get("semester_id", type=int)
    buf = build_high_risk_pdf(semester_id=semester_id)
    filename = f"attendai_high_risk_audit_{date.today().strftime('%Y%m%d')}.pdf"
    return send_file(
        buf,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename
    )


@reports_bp.route("/excel/high-risk")
@login_required
def excel_high_risk():
    semester_id = request.args.get("semester_id", type=int)
    buf = build_risk_analysis_excel(semester_id=semester_id)
    filename = f"attendai_high_risk_audit_{date.today().strftime('%Y%m%d')}.xlsx"
    return send_file(
        buf,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=filename
    )


# ─────────────────────────────────────────────────────────────────────────────
# 7. Machine Learning Predictions Reports (PDF & Excel)
# ─────────────────────────────────────────────────────────────────────────────
@reports_bp.route("/pdf/predictions")
@login_required
def pdf_predictions():
    semester_id = request.args.get("semester_id", type=int)
    buf = build_ml_predictions_pdf(semester_id=semester_id)
    filename = f"attendai_ml_predictions_audit_{date.today().strftime('%Y%m%d')}.pdf"
    return send_file(
        buf,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename
    )


@reports_bp.route("/excel/predictions")
@login_required
def excel_predictions():
    semester_id = request.args.get("semester_id", type=int)
    buf = build_risk_analysis_excel(semester_id=semester_id)
    filename = f"attendai_ml_predictions_audit_{date.today().strftime('%Y%m%d')}.xlsx"
    return send_file(
        buf,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=filename
    )


# ─────────────────────────────────────────────────────────────────────────────
# 8. Raw Data Dumps: Records, Risk Analysis, Subject Statistics (Excel)
# ─────────────────────────────────────────────────────────────────────────────
@reports_bp.route("/excel/attendance-records")
@login_required
def excel_attendance_records():
    semester_id = request.args.get("semester_id", type=int)
    subject_id  = request.args.get("subject_id", type=int)
    department  = request.args.get("department")
    status      = request.args.get("status")

    buf = build_attendance_records_excel(
        semester_id=semester_id,
        subject_id=subject_id,
        department=department,
        status=status
    )
    filename = f"attendai_attendance_records_dump_{date.today().strftime('%Y%m%d')}.xlsx"
    return send_file(
        buf,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=filename
    )


@reports_bp.route("/excel/risk-analysis")
@login_required
def excel_risk_analysis():
    semester_id = request.args.get("semester_id", type=int)
    buf = build_risk_analysis_excel(semester_id=semester_id)
    filename = f"attendai_risk_analysis_summary_{date.today().strftime('%Y%m%d')}.xlsx"
    return send_file(
        buf,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=filename
    )


@reports_bp.route("/excel/subject-statistics")
@login_required
def excel_subject_statistics():
    semester_id = request.args.get("semester_id", type=int)
    buf = build_subject_statistics_excel(semester_id=semester_id)
    filename = f"attendai_subject_statistics_{date.today().strftime('%Y%m%d')}.xlsx"
    return send_file(
        buf,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=filename
    )


# ─────────────────────────────────────────────────────────────────────────────
# 9. Download Bulk Attendance Upload Templates
# ─────────────────────────────────────────────────────────────────────────────
@reports_bp.route("/template/excel")
@login_required
def template_excel():
    buf = build_attendance_upload_template_excel()
    return send_file(
        buf,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name="attendai_attendance_upload_template.xlsx"
    )
