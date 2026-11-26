"""
routes/admin.py – Admin & Faculty Student Management Blueprint.
Handles:
  - Admin dashboard & KPIs
  - Semester management
  - Student CRUD with search, multi-field filters, and academic safeguards
  - Student Excel/CSV bulk import with duplicate detection
  - Subject management
  - Faculty management
"""

import io
import json
import math
import os
import re
from datetime import date, datetime
from functools import wraps

import pandas as pd
from flask import (
    Blueprint, render_template, redirect, url_for, flash, request,
    jsonify, send_file, Response
)
from flask_login import login_required, current_user

from database.models import (
    db, User, Faculty, Semester, Student, Subject,
    AttendanceRecord, PredictionHistory, StudentSubjectEnrolment,
    Intervention, SystemSetting
)

admin_bp = Blueprint("admin", __name__)


# ── Access Control Decorators ─────────────────────────────────────────────────
def admin_required(f):
    """Restricts access to administrators only."""
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if not current_user.is_admin:
            flash("Administrator access required for this action.", "danger")
            return redirect(url_for("auth.index"))
        return f(*args, **kwargs)
    return decorated


def faculty_or_admin_required(f):
    """Allows access to both Administrators and Faculty members."""
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if not (current_user.is_admin or current_user.role == "faculty"):
            flash("Admin or Faculty access required.", "danger")
            return redirect(url_for("auth.index"))
        return f(*args, **kwargs)
    return decorated


# ─────────────────────────────────────────────────────────────────────────────
# Dashboard & Analytics Helper
# ─────────────────────────────────────────────────────────────────────────────
def get_dashboard_analytics(semester_id: int = None) -> dict:
    """
    Computes real-time empirical and ML attendance analytics:
    - 6 KPI cards: total students, total subjects, average attendance %, high-risk, medium-risk, low-risk.
    - 5 Charts data: department-wise, subject-wise, monthly trends, risk distribution, top 10 shortages.
    - Zero fake statistics; returns clean empty states if database has 0 records.
    """
    all_semesters = Semester.query.order_by(Semester.year.desc(), Semester.name).all()

    if semester_id:
        active_semester = db.session.get(Semester, semester_id)
    else:
        active_semester = Semester.query.filter_by(is_active=True).first()
        if not active_semester and all_semesters:
            active_semester = all_semesters[0]

    # Active students query
    students_query = Student.query.filter_by(is_active=True)
    if active_semester:
        students_query = students_query.filter_by(semester_id=active_semester.id)
    active_students = students_query.all()

    total_students = len(active_students)
    total_subjects = Subject.query.filter_by(semester_id=active_semester.id).count() if active_semester else Subject.query.count()
    total_faculty = Faculty.query.count()
    total_records = AttendanceRecord.query.count()

    high_risk_count = 0
    medium_risk_count = 0
    low_risk_count = 0
    total_att_sum = 0.0

    dept_map = {}
    student_stats_list = []

    for st in active_students:
        st_stats = st.get_overall_stats()
        pct = st_stats["percentage"]
        conducted = st_stats["conducted"]
        attended = st_stats["attended"]

        # ML or empirical calibrated tier
        pred = st.latest_prediction()
        if pred and pred.risk_level:
            risk_tier = pred.risk_level
            prob = getattr(pred, "risk_probability", None)
        else:
            if conducted == 0:
                risk_tier = "Low"
                prob = 0.0
            elif pct < 60.0:
                risk_tier = "High"
                prob = 0.85
            elif pct < 75.0:
                risk_tier = "Medium"
                prob = 0.50
            else:
                risk_tier = "Low"
                prob = 0.15

        if risk_tier == "High":
            high_risk_count += 1
        elif risk_tier == "Medium":
            medium_risk_count += 1
        else:
            low_risk_count += 1

        total_att_sum += pct

        # Deterministic shortage deficit and recovery
        deficit = max(0.0, round(75.0 - pct, 1))
        # x >= ceil(3 * conducted - 4 * attended)
        needed = max(0, math.ceil(3 * conducted - 4 * attended))

        student_info = {
            "id": st.id,
            "name": st.name,
            "roll_number": st.roll_number,
            "department": st.department or "General",
            "year": st.year,
            "section": st.section,
            "percentage": pct,
            "conducted": conducted,
            "attended": attended,
            "risk_tier": risk_tier,
            "probability": round(prob * 100, 1) if prob is not None else None,
            "shortage_deficit": deficit,
            "classes_needed": needed,
        }
        student_stats_list.append(student_info)

        # Department map
        dept = st.department or "General"
        dept_map.setdefault(dept, []).append(pct)

    average_attendance = round(total_att_sum / total_students, 1) if total_students > 0 else 0.0

    # 1. Department-wise Chart
    dept_labels = sorted(list(dept_map.keys()))
    dept_data = [round(sum(dept_map[d]) / len(dept_map[d]), 1) for d in dept_labels]
    dept_counts = [len(dept_map[d]) for d in dept_labels]

    # 2. Subject-wise Chart
    subjects_query = Subject.query
    if active_semester:
        subjects_query = subjects_query.filter_by(semester_id=active_semester.id)
    subjects = subjects_query.order_by(Subject.code).all()

    subject_labels = []
    subject_data = []
    subject_conducted = []
    for subj in subjects:
        recs = AttendanceRecord.query.filter_by(subject_id=subj.id).all()
        if recs:
            s_cond = len(recs)
            s_pres = sum(1 for r in recs if r.status in ("present", "late"))
            s_pct = round((s_pres / s_cond) * 100, 1)
        else:
            s_cond = 0
            s_pct = 0.0
        subject_labels.append(subj.code or subj.name)
        subject_data.append(s_pct)
        subject_conducted.append(s_cond)

    # 3. Monthly Trends Chart
    monthly_query = (
        db.session.query(
            db.func.strftime('%Y-%m', AttendanceRecord.date).label('month'),
            db.func.count(AttendanceRecord.id).label('total'),
            db.func.sum(db.case((AttendanceRecord.status.in_(['present', 'late']), 1), else_=0)).label('present')
        )
        .group_by('month')
        .order_by('month')
        .all()
    )
    month_labels = []
    month_data = []
    for m, tot, pres in monthly_query:
        if m:
            try:
                dt = datetime.strptime(m, "%Y-%m")
                m_label = dt.strftime("%b %Y")
            except Exception:
                m_label = m
            pct = round((pres / tot * 100), 1) if tot > 0 else 0.0
            month_labels.append(m_label)
            month_data.append(pct)

    # 4. Risk Distribution Chart
    risk_labels = ["High Risk (<60% or P≥0.65)", "Medium Risk (60-74% or P≥0.35)", "Low Risk (≥75%)"]
    risk_data = [high_risk_count, medium_risk_count, low_risk_count]

    # 5. Top 10 Students with Shortages
    shortages = [s for s in student_stats_list if s["percentage"] < 75.0 and s["conducted"] > 0]
    shortages.sort(key=lambda x: x["percentage"])  # lowest first
    top_10_shortages = shortages[:10]

    return {
        "total_students": total_students,
        "total_subjects": total_subjects,
        "total_faculty": total_faculty,
        "total_records": total_records,
        "average_attendance": average_attendance,
        "high_risk_count": high_risk_count,
        "medium_risk_count": medium_risk_count,
        "low_risk_count": low_risk_count,
        "active_semester": active_semester,
        "all_semesters": all_semesters,
        "selected_semester_id": active_semester.id if active_semester else None,
        # Charts
        "dept_labels": dept_labels,
        "dept_data": dept_data,
        "dept_counts": dept_counts,
        "subject_labels": subject_labels,
        "subject_data": subject_data,
        "subject_conducted": subject_conducted,
        "month_labels": month_labels,
        "month_data": month_data,
        "risk_labels": risk_labels,
        "risk_data": risk_data,
        "top_10_shortages": top_10_shortages,
        "total_shortages_count": len(shortages),
        # Backward-compatibility alias
        "high_risk": high_risk_count,
        "medium_risk": medium_risk_count,
        "low_risk": low_risk_count,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Dashboard Route
# ─────────────────────────────────────────────────────────────────────────────
@admin_bp.route("/dashboard")
@admin_required
def dashboard():
    semester_id = request.args.get("semester_id", type=int)
    analytics = get_dashboard_analytics(semester_id=semester_id)
    return render_template("admin/dashboard.html", stats=analytics, **analytics)


# ─────────────────────────────────────────────────────────────────────────────
# Settings Route
# ─────────────────────────────────────────────────────────────────────────────
@admin_bp.route("/settings", methods=["GET", "POST"])
@admin_required
def settings():
    if request.method == "POST":
        action = request.form.get("action", "thresholds")
        if action == "thresholds":
            att_req   = request.form.get("attendance_required", "75").strip()
            high_th   = request.form.get("high_risk_threshold", "65").strip()
            med_th    = request.form.get("medium_risk_threshold", "35").strip()
            inst_name = request.form.get("institution_name", "AttendAI Institute of Engineering & Technology").strip()
            acad_year = request.form.get("academic_year", "2024-2025").strip()
            active_sem_id = request.form.get("active_semester_id", type=int)

            try:
                att_val  = float(att_req)
                high_val = float(high_th)
                med_val  = float(med_th)
                if not (0 <= att_val <= 100 and 0 <= high_val <= 100 and 0 <= med_val <= 100):
                    flash("Validation Error: Threshold percentages must be between 0 and 100.", "danger")
                    return redirect(url_for("admin.settings"))
                if med_val > high_val:
                    flash("Validation Error: Medium-risk threshold cannot exceed high-risk threshold.", "danger")
                    return redirect(url_for("admin.settings"))
            except ValueError:
                flash("Validation Error: Threshold values must be valid numbers.", "danger")
                return redirect(url_for("admin.settings"))

            SystemSetting.set("attendance_required", att_req, "Minimum required attendance percentage")
            SystemSetting.set("high_risk_threshold", high_th, "High-risk probability threshold percentage")
            SystemSetting.set("medium_risk_threshold", med_th, "Medium-risk probability threshold percentage")
            SystemSetting.set("institution_name", inst_name, "Institution display name")
            SystemSetting.set("academic_year", acad_year, "Current academic calendar year")

            if active_sem_id:
                Semester.query.update({Semester.is_active: False})
                target_sem = db.session.get(Semester, active_sem_id)
                if target_sem:
                    target_sem.is_active = True
                db.session.commit()

            flash("Institutional academic thresholds and settings saved successfully.", "success")
            return redirect(url_for("admin.settings"))

        elif action == "password":
            current_pw = request.form.get("current_password", "")
            new_pw     = request.form.get("new_password", "")
            confirm_pw = request.form.get("confirm_password", "")

            if not current_user.check_password(current_pw):
                flash("Current password is incorrect.", "danger")
            elif new_pw != confirm_pw:
                flash("New passwords do not match.", "danger")
            elif len(new_pw) < 8:
                flash("New password must be at least 8 characters long.", "danger")
            else:
                current_user.set_password(new_pw)
                db.session.commit()
                flash("Administrator password updated successfully.", "success")
            return redirect(url_for("admin.settings"))

    # GET
    settings_data = {
        "attendance_required":   SystemSetting.get("attendance_required", "75"),
        "high_risk_threshold":   SystemSetting.get("high_risk_threshold", "65"),
        "medium_risk_threshold": SystemSetting.get("medium_risk_threshold", "35"),
        "institution_name":      SystemSetting.get("institution_name", "AttendAI Institute of Engineering & Technology"),
        "academic_year":         SystemSetting.get("academic_year", "2024-2025"),
    }
    semesters = Semester.query.order_by(Semester.year.desc(), Semester.name).all()
    active_sem = Semester.query.filter_by(is_active=True).first()

    # Load ML Model Metrics
    metrics_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "ml", "models", "model_metrics.json")
    model_metrics = {}
    if os.path.exists(metrics_path):
        try:
            with open(metrics_path, "r") as f:
                model_metrics = json.load(f)
        except Exception:
            pass

    counts = {
        "students":      Student.query.count(),
        "faculty":       Faculty.query.count(),
        "subjects":      Subject.query.count(),
        "records":       AttendanceRecord.query.count(),
        "predictions":   PredictionHistory.query.count(),
        "interventions": Intervention.query.count(),
    }

    return render_template(
        "admin/settings.html",
        settings=settings_data,
        semesters=semesters,
        active_sem=active_sem,
        model_metrics=model_metrics,
        counts=counts,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Semester Management
# ─────────────────────────────────────────────────────────────────────────────
@admin_bp.route("/semesters")
@admin_required
def semesters():
    all_semesters = Semester.query.order_by(Semester.year.desc(), Semester.name).all()
    return render_template("admin/semesters.html", semesters=all_semesters)


@admin_bp.route("/semesters/add", methods=["POST"])
@admin_required
def add_semester():
    name       = request.form.get("name", "").strip()
    year       = request.form.get("year", type=int)
    section    = request.form.get("section", "A").strip()
    start_date = request.form.get("start_date")
    end_date   = request.form.get("end_date")

    if not name or not year:
        flash("Semester name and year are required.", "danger")
        return redirect(url_for("admin.semesters"))

    if year < 2000 or year > 2100:
        flash("Validation Error: Academic year must be a valid 4-digit calendar year.", "danger")
        return redirect(url_for("admin.semesters"))

    if Semester.query.filter_by(name=name).first():
        flash(f"Semester '{name}' already exists.", "danger")
        return redirect(url_for("admin.semesters"))

    s_date = None
    e_date = None
    if start_date:
        try:
            s_date = date.fromisoformat(start_date)
        except ValueError:
            flash("Validation Error: Invalid start date format.", "danger")
            return redirect(url_for("admin.semesters"))

    if end_date:
        try:
            e_date = date.fromisoformat(end_date)
        except ValueError:
            flash("Validation Error: Invalid end date format.", "danger")
            return redirect(url_for("admin.semesters"))

    if s_date and e_date and s_date > e_date:
        flash("Validation Error: Semester start date cannot be after end date.", "danger")
        return redirect(url_for("admin.semesters"))

    sem = Semester(
        name=name, year=year, section=section,
        start_date=s_date,
        end_date=e_date,
    )
    db.session.add(sem)
    db.session.commit()
    flash(f"Semester '{name}' created successfully.", "success")
    return redirect(url_for("admin.semesters"))


@admin_bp.route("/semesters/<int:sem_id>/toggle-active", methods=["POST"])
@admin_required
def toggle_semester(sem_id):
    sem = db.session.get(Semester, sem_id)
    if not sem:
        flash("Semester not found.", "danger")
        return redirect(url_for("admin.semesters"))

    if not sem.is_active:
        Semester.query.update({"is_active": False})
        sem.is_active = True
    else:
        sem.is_active = False

    db.session.commit()
    flash(f"Semester '{sem.name}' {'activated' if sem.is_active else 'deactivated'}.", "success")
    return redirect(url_for("admin.semesters"))


# ─────────────────────────────────────────────────────────────────────────────
# Student Management: List, Search & Multi-field Filters
# ─────────────────────────────────────────────────────────────────────────────
@admin_bp.route("/students")
@faculty_or_admin_required
def students():
    """
    Student listing with:
      - Search by roll number, name, and student ID
      - Filter by department, year, section, semester, and status
    """
    search_q   = request.args.get("search", "").strip() or request.args.get("q", "").strip()
    sem_id     = request.args.get("semester_id", type=int)
    department = request.args.get("department", "").strip()
    year       = request.args.get("year", type=int)
    section    = request.args.get("section", "").strip()
    status     = request.args.get("status", "all").strip().lower()

    query = Student.query

    # ── Search by roll number, name, or student ID ────────────────────────────
    if search_q:
        pattern = f"%{search_q}%"
        query = query.filter(
            db.or_(
                Student.roll_number.ilike(pattern),
                Student.name.ilike(pattern),
                Student.student_id.ilike(pattern),
            )
        )

    # ── Filter by semester ────────────────────────────────────────────────────
    if sem_id:
        query = query.filter(Student.semester_id == sem_id)

    # ── Filter by department ──────────────────────────────────────────────────
    if department:
        query = query.filter(Student.department == department)

    # ── Filter by year ────────────────────────────────────────────────────────
    if year:
        query = query.filter(Student.year == year)

    # ── Filter by section ─────────────────────────────────────────────────────
    if section:
        query = query.filter(Student.section == section)

    # ── Filter by active status ───────────────────────────────────────────────
    if status == "active":
        query = query.filter(Student.is_active == True)
    elif status == "inactive":
        query = query.filter(Student.is_active == False)

    all_students = query.order_by(Student.roll_number).all()

    # Dropdown lists for filter controls
    semesters = Semester.query.order_by(Semester.year.desc(), Semester.name).all()
    departments = [
        d[0] for d in db.session.query(Student.department).distinct()
        .filter(Student.department != None).order_by(Student.department).all()
    ]
    years = [
        y[0] for y in db.session.query(Student.year).distinct()
        .filter(Student.year != None).order_by(Student.year).all()
    ]
    sections = [
        s[0] for s in db.session.query(Student.section).distinct()
        .filter(Student.section != None).order_by(Student.section).all()
    ]

    # Defaults if DB has no data yet
    if not departments:
        departments = ["Computer Science", "Information Technology", "Electronics", "Mechanical"]
    if not years:
        years = [1, 2, 3, 4]
    if not sections:
        sections = ["A", "B", "C"]

    return render_template(
        "admin/students.html",
        students=all_students,
        semesters=semesters,
        departments=departments,
        years=years,
        sections=sections,
        selected_sem=sem_id,
        selected_dept=department,
        selected_year=year,
        selected_sec=section,
        selected_status=status,
        search_query=search_q,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Add Student (with duplicate prevention & validation)
# ─────────────────────────────────────────────────────────────────────────────
@admin_bp.route("/students/add", methods=["POST"])
@faculty_or_admin_required
def add_student():
    student_id = request.form.get("student_id", "").strip()
    roll       = request.form.get("roll_number", "").strip()
    name       = request.form.get("name", "").strip() or request.form.get("full_name", "").strip()
    department = request.form.get("department", "Computer Science").strip()
    year       = request.form.get("year", 1, type=int)
    section    = request.form.get("section", "A").strip()
    email      = request.form.get("email", "").strip()
    phone      = request.form.get("phone", "").strip()
    sem_id     = request.form.get("semester_id", type=int)

    # ── Required validations ──────────────────────────────────────────────────
    if not name or not roll or not sem_id:
        flash("Full name, roll number, and semester are required.", "danger")
        return redirect(url_for("admin.students"))

    # Auto-generate student_id if left blank
    if not student_id:
        student_id = f"STU-{roll}"

    # ── Prevent duplicate roll number ─────────────────────────────────────────
    if Student.query.filter_by(roll_number=roll).first():
        flash(f"Validation Error: Roll number '{roll}' is already assigned to another student.", "danger")
        return redirect(url_for("admin.students"))

    # ── Prevent duplicate student ID ──────────────────────────────────────────
    if Student.query.filter_by(student_id=student_id).first():
        flash(f"Validation Error: Student ID '{student_id}' is already registered.", "danger")
        return redirect(url_for("admin.students"))

    # ── Verify semester exists ────────────────────────────────────────────────
    sem = db.session.get(Semester, sem_id)
    if not sem:
        flash("Selected semester does not exist.", "danger")
        return redirect(url_for("admin.students"))

    # ── Email format validation ───────────────────────────────────────────────
    if email and not Student.validate_email(email):
        flash(f"Validation Error: Invalid email format '{email}'.", "danger")
        return redirect(url_for("admin.students"))

    # ── Year range check ──────────────────────────────────────────────────────
    if year and (year < 1 or year > 6):
        flash("Validation Error: Academic year must be between 1 and 6.", "danger")
        return redirect(url_for("admin.students"))

    # ── Create student & auto-enroll in semester subjects ──────────────────────
    st = Student(
        student_id=student_id,
        roll_number=roll,
        name=name,
        department=department,
        year=year,
        section=section,
        email=email or None,
        phone=phone or None,
        semester_id=sem_id,
        is_active=True,
    )
    db.session.add(st)
    db.session.flush()

    # Automatically enroll into all subjects belonging to this semester
    enrolled = st.enroll_in_semester_subjects()

    db.session.commit()
    flash(
        f"Student '{name}' (Roll: {roll}, ID: {student_id}) added successfully. "
        f"Enrolled in {len(enrolled)} semester subjects.",
        "success"
    )
    return redirect(url_for("admin.students"))


# ─────────────────────────────────────────────────────────────────────────────
# Edit Student (with duplicate prevention & validation)
# ─────────────────────────────────────────────────────────────────────────────
@admin_bp.route("/students/<int:student_id>/edit", methods=["GET", "POST"])
@faculty_or_admin_required
def edit_student(student_id):
    st = db.session.get(Student, student_id)
    if not st:
        flash("Student not found.", "danger")
        return redirect(url_for("admin.students"))

    semesters = Semester.query.order_by(Semester.year.desc(), Semester.name).all()

    if request.method == "POST":
        new_name     = request.form.get("name", st.name).strip()
        new_sid      = request.form.get("student_id", st.student_id).strip()
        new_roll     = request.form.get("roll_number", st.roll_number).strip()
        department   = request.form.get("department", st.department).strip()
        year         = request.form.get("year", st.year, type=int)
        section      = request.form.get("section", st.section).strip()
        email        = request.form.get("email", "").strip() or None
        phone        = request.form.get("phone", "").strip() or None
        new_sem_id   = request.form.get("semester_id", st.semester_id, type=int)
        is_active    = bool(request.form.get("is_active"))

        if not new_name or not new_roll:
            flash("Student name and roll number cannot be empty.", "danger")
            return redirect(url_for("admin.edit_student", student_id=st.id))

        # Check duplicate roll number across other students
        dup_roll = Student.query.filter(Student.roll_number == new_roll, Student.id != st.id).first()
        if dup_roll:
            flash(f"Roll number '{new_roll}' is already in use by student '{dup_roll.name}'.", "danger")
            return redirect(url_for("admin.edit_student", student_id=st.id))

        # Check duplicate student_id across other students
        if new_sid:
            dup_sid = Student.query.filter(Student.student_id == new_sid, Student.id != st.id).first()
            if dup_sid:
                flash(f"Student ID '{new_sid}' is already in use by student '{dup_sid.name}'.", "danger")
                return redirect(url_for("admin.edit_student", student_id=st.id))
        else:
            new_sid = f"STU-{new_roll}"

        # Email validation
        if email and not Student.validate_email(email):
            flash("Invalid email format.", "danger")
            return redirect(url_for("admin.edit_student", student_id=st.id))

        # Apply updates
        st.name        = new_name
        st.student_id  = new_sid
        st.roll_number = new_roll
        st.department  = department
        st.year        = year or 1
        st.section     = section or "A"
        st.email       = email
        st.phone       = phone
        st.is_active   = is_active

        # If semester changed, re-sync subject enrolments
        if new_sem_id and new_sem_id != st.semester_id:
            st.semester_id = new_sem_id
            st.enroll_in_semester_subjects()

        db.session.commit()
        flash(f"Student '{st.name}' updated successfully.", "success")
        return redirect(url_for("admin.students"))

    return render_template("admin/edit_student.html", student=st, semesters=semesters)


# ─────────────────────────────────────────────────────────────────────────────
# Delete Student (with Academic Safeguards)
# ─────────────────────────────────────────────────────────────────────────────
@admin_bp.route("/students/<int:student_id>/delete", methods=["POST"])
@faculty_or_admin_required
def delete_student(student_id):
    """
    Safe student deletion with safeguards:
      - Default / Faculty: Soft-delete (deactivate) to protect attendance history
      - Admin: Can permanently delete or toggle active
    """
    st = db.session.get(Student, student_id)
    if not st:
        flash("Student not found.", "danger")
        return redirect(url_for("admin.students"))

    action = request.form.get("action", "toggle_active")
    att_count  = st.attendances.count()
    pred_count = st.predictions.count()

    if action == "permanent":
        # ── Safeguard: Non-admin cannot permanently wipe attendance history ──
        if att_count > 0 and not current_user.is_admin:
            st.is_active = False
            db.session.commit()
            flash(
                f"Academic Safeguard: Faculty cannot permanently delete student '{st.name}' "
                f"because {att_count} historical attendance records exist. "
                "Student was safely deactivated instead.",
                "warning"
            )
            return redirect(url_for("admin.students"))

        # Admin or student with no attendance history
        name = st.name
        db.session.delete(st)
        db.session.commit()
        flash(f"Student '{name}' and all associated records have been permanently deleted.", "success")

    elif action == "activate":
        st.is_active = True
        db.session.commit()
        flash(f"Student '{st.name}' has been reactivated.", "success")

    else:
        # Default: Safe toggle deactivation
        st.is_active = not st.is_active
        db.session.commit()
        if st.is_active:
            flash(f"Student '{st.name}' has been reactivated.", "success")
        else:
            flash(
                f"Student '{st.name}' deactivated. Historical attendance ({att_count} records) "
                "safely preserved.",
                "info"
            )

    return redirect(url_for("admin.students"))


# ─────────────────────────────────────────────────────────────────────────────
# Bulk Student Import (CSV / Excel)
# ─────────────────────────────────────────────────────────────────────────────
@admin_bp.route("/students/import", methods=["POST"])
@faculty_or_admin_required
def import_students():
    """
    Import students in bulk from Excel (.xlsx/.xls) or CSV.
    Validates required fields, checks duplicates against file and database,
    and auto-enrolls into semester subjects.
    """
    file          = request.files.get("file")
    default_sem_id = request.form.get("default_semester_id", type=int)

    if not file or not file.filename:
        flash("Please select a valid CSV or Excel file to upload.", "danger")
        return redirect(url_for("admin.students"))

    filename = file.filename.lower()
    allowed_exts = {"csv", "xlsx", "xls"}
    ext = filename.rsplit(".", 1)[-1] if "." in filename else ""

    if ext not in allowed_exts:
        flash("Invalid file format. Only .csv, .xlsx, and .xls files are supported.", "danger")
        return redirect(url_for("admin.students"))

    try:
        if ext == "csv":
            df = pd.read_csv(io.BytesIO(file.read()))
        else:
            df = pd.read_excel(io.BytesIO(file.read()))
    except Exception as e:
        flash(f"Failed to read file: {e}", "danger")
        return redirect(url_for("admin.students"))

    if df.empty:
        flash("The uploaded file contains no data rows.", "warning")
        return redirect(url_for("admin.students"))

    # Normalize column names: strip whitespace, lowercase, replace spaces with underscores
    df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]

    # Map possible column header variations
    col_mapping = {
        "roll": "roll_number", "roll_no": "roll_number", "rollnumber": "roll_number",
        "full_name": "name", "student_name": "name",
        "student_id": "student_id", "studentid": "student_id", "id": "student_id",
        "dept": "department", "branch": "department",
        "sec": "section",
        "sem": "semester", "sem_id": "semester_id", "semester_name": "semester",
    }
    df.rename(columns={c: col_mapping[c] for c in df.columns if c in col_mapping}, inplace=True)

    # Required: roll_number, name
    if "roll_number" not in df.columns or "name" not in df.columns:
        flash(
            "File must contain at least 'roll_number' (or 'roll_no') and 'name' (or 'full_name') columns. "
            f"Columns found: {', '.join(df.columns)}",
            "danger"
        )
        return redirect(url_for("admin.students"))

    # Cache semesters for fast lookup
    all_semesters = Semester.query.all()
    sem_by_id   = {s.id: s for s in all_semesters}
    sem_by_name = {s.name.strip().lower(): s for s in all_semesters}

    # Tracking sets for duplicate detection within the upload
    seen_rolls = set()
    seen_sids  = set()

    imported_count = 0
    skipped_count  = 0
    errors         = []

    for idx, row in df.iterrows():
        row_num = idx + 2  # 1-based, account for header row
        try:
            roll = str(row.get("roll_number", "")).strip()
            name = str(row.get("name", "")).strip()

            if not roll or roll.lower() == "nan":
                errors.append(f"Row {row_num}: Roll number is missing.")
                skipped_count += 1
                continue

            if not name or name.lower() == "nan":
                errors.append(f"Row {row_num}: Name is missing.")
                skipped_count += 1
                continue

            # Student ID
            sid = str(row.get("student_id", "")).strip()
            if not sid or sid.lower() == "nan":
                sid = f"STU-{roll}"

            # Within-file duplicate check
            if roll in seen_rolls:
                errors.append(f"Row {row_num}: Duplicate roll number '{roll}' found in upload file.")
                skipped_count += 1
                continue
            seen_rolls.add(roll)

            if sid in seen_sids:
                errors.append(f"Row {row_num}: Duplicate student ID '{sid}' found in upload file.")
                skipped_count += 1
                continue
            seen_sids.add(sid)

            # Database duplicate check
            if Student.query.filter_by(roll_number=roll).first():
                errors.append(f"Row {row_num}: Roll number '{roll}' already exists in database.")
                skipped_count += 1
                continue

            if Student.query.filter_by(student_id=sid).first():
                errors.append(f"Row {row_num}: Student ID '{sid}' already exists in database.")
                skipped_count += 1
                continue

            # Resolve semester
            target_sem = None
            if "semester_id" in df.columns and pd.notna(row.get("semester_id")):
                try:
                    s_id = int(row["semester_id"])
                    target_sem = sem_by_id.get(s_id)
                except ValueError:
                    pass

            if not target_sem and "semester" in df.columns and pd.notna(row.get("semester")):
                sem_str = str(row["semester"]).strip().lower()
                target_sem = sem_by_name.get(sem_str)

            if not target_sem and default_sem_id:
                target_sem = sem_by_id.get(default_sem_id)

            if not target_sem:
                # Fallback to active semester
                target_sem = Semester.query.filter_by(is_active=True).first()

            if not target_sem:
                errors.append(f"Row {row_num}: No valid semester found for student '{name}'.")
                skipped_count += 1
                continue

            # Optional fields
            department = str(row.get("department", "Computer Science")).strip()
            if not department or department.lower() == "nan":
                department = "Computer Science"

            year_val = row.get("year", 1)
            try:
                year_int = int(year_val) if pd.notna(year_val) else 1
            except (ValueError, TypeError):
                year_int = 1

            section = str(row.get("section", "A")).strip()
            if not section or section.lower() == "nan":
                section = "A"

            email_val = str(row.get("email", "")).strip()
            if email_val.lower() == "nan" or not email_val:
                email_val = None
            elif not Student.validate_email(email_val):
                errors.append(f"Row {row_num}: Invalid email '{email_val}' ignored.")
                email_val = None

            phone_val = str(row.get("phone", "")).strip()
            if phone_val.lower() == "nan" or not phone_val:
                phone_val = None

            # Create student record
            student = Student(
                student_id=sid,
                roll_number=roll,
                name=name,
                department=department,
                year=year_int,
                section=section,
                email=email_val,
                phone=phone_val,
                semester_id=target_sem.id,
                is_active=True,
            )
            db.session.add(student)
            db.session.flush()

            # Auto-enroll in semester subjects
            student.enroll_in_semester_subjects()
            imported_count += 1

        except Exception as e:
            errors.append(f"Row {row_num}: Error {e}")
            skipped_count += 1

    db.session.commit()

    if imported_count > 0:
        flash(f"Successfully imported {imported_count} student(s) with automatic subject enrollments.", "success")
    if skipped_count > 0:
        flash(f"{skipped_count} row(s) were skipped due to validation errors.", "warning")
        if errors:
            preview_errors = "; ".join(errors[:6])
            flash(f"Import Issues: {preview_errors}", "info")

    return redirect(url_for("admin.students"))


# ─────────────────────────────────────────────────────────────────────────────
# Download Student Import Template (CSV)
# ─────────────────────────────────────────────────────────────────────────────
@admin_bp.route("/students/template")
@faculty_or_admin_required
def download_student_template():
    """Returns a sample CSV template for bulk student import."""
    csv_content = (
        "student_id,roll_number,name,department,year,section,email,phone\n"
        "STU2025001,CS202501,Aarav Sharma,Computer Science,1,A,aarav.sharma@attendai.edu,9876543210\n"
        "STU2025002,CS202502,Sneha Patel,Computer Science,1,A,sneha.patel@attendai.edu,9876543211\n"
        "STU2025003,CS202503,Rohan Verma,Information Technology,1,B,rohan.verma@attendai.edu,\n"
    )
    return Response(
        csv_content,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=student_import_template.csv"}
    )


# ─────────────────────────────────────────────────────────────────────────────
# Subject Management
# ─────────────────────────────────────────────────────────────────────────────
@admin_bp.route("/subjects")
@admin_required
def subjects():
    sem_id = request.args.get("semester_id", type=int)
    semesters = Semester.query.order_by(Semester.year.desc(), Semester.name).all()
    faculty_list = Faculty.query.all()
    query = Subject.query
    if sem_id:
        query = query.filter_by(semester_id=sem_id)
    all_subjects = query.order_by(Subject.code).all()
    return render_template(
        "admin/subjects.html",
        subjects=all_subjects,
        semesters=semesters,
        faculty_list=faculty_list,
        selected_sem=sem_id
    )


@admin_bp.route("/subjects/add", methods=["POST"])
@admin_required
def add_subject():
    name       = request.form.get("name", "").strip()
    code       = request.form.get("code", "").strip()
    sem_id     = request.form.get("semester_id", type=int)
    faculty_id = request.form.get("faculty_id", type=int)
    classes    = request.form.get("total_classes_planned", 0, type=int)
    stype      = request.form.get("subject_type", "theory")

    if not name or not sem_id:
        flash("Subject name and semester are required.", "danger")
        return redirect(url_for("admin.subjects"))

    if not code:
        flash("Subject course code is required.", "danger")
        return redirect(url_for("admin.subjects"))

    sem = db.session.get(Semester, sem_id)
    if not sem:
        flash("Selected semester does not exist.", "danger")
        return redirect(url_for("admin.subjects"))

    if faculty_id and not db.session.get(Faculty, faculty_id):
        faculty_id = None

    # Check duplicate course code in the same semester
    dup_sub = Subject.query.filter_by(semester_id=sem_id, code=code).first()
    if dup_sub:
        flash(f"Validation Error: Course code '{code}' already exists in semester '{sem.name}'.", "danger")
        return redirect(url_for("admin.subjects"))

    classes = max(0, classes if classes is not None else 0)

    subj = Subject(
        name=name, code=code, semester_id=sem_id,
        faculty_id=faculty_id, total_classes_planned=classes,
        subject_type=stype
    )
    db.session.add(subj)
    db.session.flush()

    # Automatically enroll all active students of this semester into the new subject
    students_in_sem = Student.query.filter_by(semester_id=sem_id, is_active=True).all()
    for st in students_in_sem:
        st.enroll_in_subject(subj.id)

    db.session.commit()
    flash(f"Subject '{name}' added. Automatically enrolled {len(students_in_sem)} students.", "success")
    return redirect(url_for("admin.subjects"))


@admin_bp.route("/subjects/<int:subject_id>/delete", methods=["POST"])
@admin_required
def delete_subject(subject_id):
    subj = db.session.get(Subject, subject_id)
    if subj:
        name = subj.name
        db.session.delete(subj)
        db.session.commit()
        flash(f"Subject '{name}' deleted.", "success")
    return redirect(url_for("admin.subjects"))


# ─────────────────────────────────────────────────────────────────────────────
# Faculty Management
# ─────────────────────────────────────────────────────────────────────────────
@admin_bp.route("/faculty")
@admin_required
def faculty():
    search = request.args.get("search", "").strip()
    department = request.args.get("department", "").strip()

    query = Faculty.query.join(User).filter(User.role == "faculty")
    if search:
        query = query.filter(
            db.or_(
                Faculty.name.ilike(f"%{search}%"),
                Faculty.employee_id.ilike(f"%{search}%"),
                User.username.ilike(f"%{search}%"),
                User.email.ilike(f"%{search}%")
            )
        )
    if department:
        query = query.filter(Faculty.department == department)

    all_faculty = query.order_by(Faculty.name).all()

    # Unique departments for filter
    raw_depts = db.session.query(Faculty.department).distinct().all()
    departments = sorted([d[0] for d in raw_depts if d[0]])

    return render_template(
        "admin/faculty.html",
        faculty_list=all_faculty,
        departments=departments,
        search_query=search,
        selected_dept=department,
    )


@admin_bp.route("/faculty/add", methods=["POST"])
@admin_required
def add_faculty():
    username = request.form.get("username", "").strip()
    email    = request.form.get("email", "").strip()
    password = request.form.get("password", "")
    fname    = request.form.get("name", "").strip()
    dept     = request.form.get("department", "Computer Science").strip()
    emp_id   = request.form.get("employee_id", "").strip()
    phone    = request.form.get("phone", "").strip()

    if not username or not email or not password or not fname:
        flash("Username, email, password, and full name are required.", "danger")
        return redirect(url_for("admin.faculty"))

    if not Student.validate_email(email):
        flash(f"Validation Error: Invalid email format '{email}'.", "danger")
        return redirect(url_for("admin.faculty"))

    if len(password) < 8:
        flash("Validation Error: Faculty password must be at least 8 characters long.", "danger")
        return redirect(url_for("admin.faculty"))

    if User.query.filter_by(username=username).first():
        flash(f"Username '{username}' is already taken.", "danger")
        return redirect(url_for("admin.faculty"))

    if User.query.filter_by(email=email).first():
        flash(f"Email '{email}' is already registered.", "danger")
        return redirect(url_for("admin.faculty"))

    if emp_id and Faculty.query.filter_by(employee_id=emp_id).first():
        flash(f"Validation Error: Employee ID '{emp_id}' is already registered.", "danger")
        return redirect(url_for("admin.faculty"))

    user = User(username=username, email=email, role="faculty")
    user.set_password(password)
    db.session.add(user)
    db.session.flush()

    f = Faculty(
        user_id=user.id,
        name=fname,
        department=dept,
        employee_id=emp_id or f"FAC-{user.id}",
        phone=phone
    )
    db.session.add(f)
    db.session.commit()
    flash(f"Faculty account for '{fname}' created successfully.", "success")
    return redirect(url_for("admin.faculty"))
