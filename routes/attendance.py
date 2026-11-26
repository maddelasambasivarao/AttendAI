"""
routes/attendance.py – Complete Attendance Management Blueprint.
Handles:
  1. Multi-level filter marking: Department, Year, Section, Semester, Subject, Date, Session.
  2. Displaying enrolled students and marking Present / Absent.
  3. Saving to SQLite with duplicate prevention for (student, subject, date, session).
  4. Authorised record correction with immutable audit trail (AttendanceEditHistory).
  5. Bulk CSV and Excel upload with robust handling of missing values, invalid dates, and duplicates.
  6. Automatic attendance percentage calculation: (Attended / Conducted) × 100.
  7. Individual student attendance history with timeline and audit logs.
  8. Subject-wise and semester-wise attendance reports.
"""

import io
from datetime import date, datetime
import pandas as pd
from flask import (
    Blueprint, render_template, redirect, url_for, flash,
    request, jsonify, Response
)
from flask_login import login_required, current_user

from database.models import (
    db, Student, Subject, Semester, Faculty, User,
    AttendanceRecord, AttendanceEditHistory, StudentSubjectEnrolment
)

attendance_bp = Blueprint("attendance", __name__)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Mark Attendance (Daily / Session Session Marking)
# ─────────────────────────────────────────────────────────────────────────────
@attendance_bp.route("/mark", methods=["GET", "POST"])
@login_required
def mark():
    """
    Attendance Marking Interface:
    1. Faculty selects Department, Year, Section, Semester, Subject, Date, and Session Slot.
    2. Displays all enrolled students matching criteria.
    3. Allows marking each student Present or Absent.
    4. Saves to SQLite and strictly prevents duplicate entries.
    5. Updates existing records with edit history audit logs if modified.
    """
    # Filter parameters
    department   = request.values.get("department", "").strip()
    year         = request.values.get("year", type=int)
    section      = request.values.get("section", "").strip()
    sem_id       = request.values.get("semester_id", type=int)
    sub_id       = request.values.get("subject_id", type=int)
    date_str     = request.values.get("attendance_date", "").strip()
    session_slot = request.values.get("session_slot", 1, type=int)

    # Resolve date (default to today)
    try:
        att_date = date.fromisoformat(date_str) if date_str else date.today()
    except (ValueError, TypeError):
        att_date = date.today()

    semesters = Semester.query.order_by(Semester.year.desc(), Semester.name).all()
    if not sem_id and semesters:
        # Default to active semester
        active_sem = next((s for s in semesters if s.is_active), semesters[0])
        sem_id = active_sem.id

    selected_sem = db.session.get(Semester, sem_id) if sem_id else None

    # Available subjects for selected semester
    subjects_query = Subject.query.filter_by(semester_id=sem_id) if sem_id else Subject.query
    subjects = subjects_query.order_by(Subject.code, Subject.name).all()

    # Dropdown lists for department, year, section
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

    selected_sub = db.session.get(Subject, sub_id) if sub_id else None
    students = []
    existing_records_map = {}
    already_marked = False

    if selected_sub and selected_sem:
        # Query enrolled students for this subject matching department, year, section
        stud_query = (
            Student.query
            .join(StudentSubjectEnrolment, StudentSubjectEnrolment.student_id == Student.id)
            .filter(
                StudentSubjectEnrolment.subject_id == selected_sub.id,
                StudentSubjectEnrolment.status == "active",
                Student.semester_id == selected_sem.id,
                Student.is_active == True,
            )
        )

        if department:
            stud_query = stud_query.filter(Student.department == department)
        if year:
            stud_query = stud_query.filter(Student.year == year)
        if section:
            stud_query = stud_query.filter(Student.section == section)

        students = stud_query.order_by(Student.roll_number).all()

        # Fallback: if no students are enrolled in mapping table, query students of that semester/section
        if not students:
            fb_query = Student.query.filter_by(semester_id=selected_sem.id, is_active=True)
            if department:
                fb_query = fb_query.filter(Student.department == department)
            if year:
                fb_query = fb_query.filter(Student.year == year)
            if section:
                fb_query = fb_query.filter(Student.section == section)
            students = fb_query.order_by(Student.roll_number).all()

            # Auto-enroll them so they stay mapped
            for st in students:
                st.enroll_in_subject(selected_sub.id)
            db.session.commit()

        # Check existing attendance records for (subject_id, date, session_slot)
        existing_records = AttendanceRecord.query.filter_by(
            subject_id=selected_sub.id,
            date=att_date,
            session_slot=session_slot
        ).all()

        if existing_records:
            already_marked = True
            existing_records_map = {r.student_id: r for r in existing_records}

    # ── Handle Submission (POST) ──────────────────────────────────────────────
    if request.method == "POST" and selected_sub and selected_sem:
        inserted = 0
        updated  = 0
        unchanged = 0

        for st in students:
            submitted_status = request.form.get(f"status_{st.id}", "absent").strip().lower()
            submitted_remarks = request.form.get(f"remarks_{st.id}", "").strip()

            if submitted_status not in ("present", "absent", "late", "excused"):
                submitted_status = "absent"

            # Check if record already exists for (student_id, subject_id, date, session_slot)
            existing = AttendanceRecord.query.filter_by(
                student_id=st.id,
                subject_id=selected_sub.id,
                date=att_date,
                session_slot=session_slot
            ).first()

            if existing:
                # If status or remarks changed, update record and log audit trail
                if existing.status != submitted_status or existing.remarks != submitted_remarks:
                    old_status = existing.status
                    existing.status = submitted_status
                    existing.remarks = submitted_remarks
                    existing.last_modified_by = current_user.id
                    existing.updated_at = datetime.utcnow()

                    # Audit History Log
                    audit = AttendanceEditHistory(
                        attendance_record_id=existing.id,
                        old_status=old_status,
                        new_status=submitted_status,
                        reason="Session marking update",
                        edited_by=current_user.id,
                        edited_at=datetime.utcnow()
                    )
                    db.session.add(audit)
                    updated += 1
                else:
                    unchanged += 1
            else:
                # Insert new record
                rec = AttendanceRecord(
                    student_id=st.id,
                    subject_id=selected_sub.id,
                    date=att_date,
                    session_slot=session_slot,
                    status=submitted_status,
                    remarks=submitted_remarks or None,
                    marked_by=current_user.id,
                    last_modified_by=current_user.id
                )
                db.session.add(rec)
                inserted += 1

        db.session.commit()
        flash(
            f"Attendance saved for {selected_sub.code} on {att_date.strftime('%d %b %Y')} "
            f"(Session {session_slot}): {inserted} marked, {updated} updated, {unchanged} unchanged.",
            "success"
        )
        return redirect(url_for(
            "attendance.mark",
            department=department,
            year=year,
            section=section,
            semester_id=selected_sem.id,
            subject_id=selected_sub.id,
            attendance_date=att_date.isoformat(),
            session_slot=session_slot
        ))

    return render_template(
        "attendance/mark.html",
        semesters=semesters,
        subjects=subjects,
        students=students,
        departments=departments,
        years=years,
        sections=sections,
        selected_dept=department,
        selected_year=year,
        selected_sec=section,
        selected_sem=selected_sem,
        selected_sub=selected_sub,
        att_date=att_date,
        session_slot=session_slot,
        existing_records_map=existing_records_map,
        already_marked=already_marked,
        today=date.today().isoformat()
    )


# ─────────────────────────────────────────────────────────────────────────────
# 2. View Attendance Records & Filtering
# ─────────────────────────────────────────────────────────────────────────────
@attendance_bp.route("/view")
@login_required
def view():
    """
    Search and filter attendance records across subjects, students, date ranges,
    and status.
    """
    semesters    = Semester.query.order_by(Semester.year.desc(), Semester.name).all()
    sem_id       = request.args.get("semester_id", type=int)
    sub_id       = request.args.get("subject_id",  type=int)
    student_id   = request.args.get("student_id",  type=int)
    search_q     = request.args.get("search", "").strip()
    status_filter = request.args.get("status", "all").strip().lower()
    date_from    = request.args.get("date_from")
    date_to      = request.args.get("date_to")

    subjects = []
    students = []
    records  = []

    if not sem_id and semesters:
        active_sem = next((s for s in semesters if s.is_active), semesters[0])
        sem_id = active_sem.id

    if sem_id:
        subjects = Subject.query.filter_by(semester_id=sem_id).order_by(Subject.code).all()
        students = Student.query.filter_by(semester_id=sem_id, is_active=True).order_by(Student.roll_number).all()

        query = AttendanceRecord.query.join(Student).join(Subject).filter(Student.semester_id == sem_id)

        if sub_id:
            query = query.filter(AttendanceRecord.subject_id == sub_id)
        if student_id:
            query = query.filter(AttendanceRecord.student_id == student_id)
        if search_q:
            query = query.filter(
                db.or_(
                    Student.name.ilike(f"%{search_q}%"),
                    Student.roll_number.ilike(f"%{search_q}%"),
                    Student.student_id.ilike(f"%{search_q}%")
                )
            )
        if status_filter in ("present", "absent", "late", "excused"):
            query = query.filter(AttendanceRecord.status == status_filter)
        if date_from:
            try:
                query = query.filter(AttendanceRecord.date >= date.fromisoformat(date_from))
            except ValueError:
                pass
        if date_to:
            try:
                query = query.filter(AttendanceRecord.date <= date.fromisoformat(date_to))
            except ValueError:
                pass

        records = query.order_by(AttendanceRecord.date.desc(), AttendanceRecord.session_slot.desc()).limit(300).all()

    return render_template(
        "attendance/view.html",
        semesters=semesters,
        subjects=subjects,
        students=students,
        records=records,
        selected_sem=sem_id,
        selected_sub=sub_id,
        selected_student=student_id,
        search_q=search_q,
        status_filter=status_filter,
        date_from=date_from or "",
        date_to=date_to or ""
    )


# ─────────────────────────────────────────────────────────────────────────────
# 3. Authorised Record Correction (with Audit History Log)
# ─────────────────────────────────────────────────────────────────────────────
@attendance_bp.route("/correct/<int:record_id>", methods=["POST"])
@login_required
def correct_record(record_id):
    """
    Allows authorised faculty or admin to correct an individual attendance entry.
    Saves the edit to the AttendanceEditHistory audit log.
    """
    record = db.session.get(AttendanceRecord, record_id)
    if not record:
        flash("Attendance record not found.", "danger")
        return redirect(url_for("attendance.view"))

    # Authorization check: Admin or faculty assigned to the subject
    subject = record.subject
    is_authorized = current_user.is_admin or (
        current_user.faculty_profile and current_user.faculty_profile.id == subject.faculty_id
    )

    if not is_authorized:
        flash("Unauthorized: Only the assigned faculty or an administrator can correct attendance.", "danger")
        return redirect(url_for("attendance.view"))

    new_status = request.form.get("status", "").strip().lower()
    reason     = request.form.get("reason", "").strip()

    if new_status not in ("present", "absent", "late", "excused"):
        flash("Invalid attendance status.", "danger")
        return redirect(url_for("attendance.view"))

    if not reason:
        reason = "Correction made by faculty"

    old_status = record.status
    if old_status != new_status:
        record.status = new_status
        record.last_modified_by = current_user.id
        record.updated_at = datetime.utcnow()

        # Immutable audit history entry
        audit = AttendanceEditHistory(
            attendance_record_id=record.id,
            old_status=old_status,
            new_status=new_status,
            reason=reason,
            edited_by=current_user.id,
            edited_at=datetime.utcnow()
        )
        db.session.add(audit)
        db.session.commit()

        flash(
            f"Record updated for {record.student.name}: Status changed from {old_status.title()} "
            f"to {new_status.title()} (Logged in audit trail).",
            "success"
        )
    else:
        flash("No change in attendance status.", "info")

    # Redirect back to where request came from
    referer = request.referrer
    if referer and ("student" in referer or "report" in referer):
        return redirect(referer)
    return redirect(url_for("attendance.view", subject_id=record.subject_id))


# ─────────────────────────────────────────────────────────────────────────────
# 4. View Audit Log for a Record (JSON endpoint)
# ─────────────────────────────────────────────────────────────────────────────
@attendance_bp.route("/history/<int:record_id>")
@login_required
def record_history(record_id):
    """Returns JSON edit history for an attendance record."""
    record = db.session.get(AttendanceRecord, record_id)
    if not record:
        return jsonify({"error": "Record not found"}), 404

    history_entries = []
    for h in record.edit_history:
        history_entries.append({
            "id": h.id,
            "old_status": h.old_status.capitalize(),
            "new_status": h.new_status.capitalize(),
            "reason": h.reason or "No reason specified",
            "edited_by": h.editor.display_name if h.editor else "Unknown User",
            "edited_at": h.edited_at.strftime("%d %b %Y, %H:%M UTC")
        })

    return jsonify({
        "record_id": record.id,
        "student": record.student.name,
        "roll_number": record.student.roll_number,
        "subject": record.subject.name,
        "date": record.date.isoformat(),
        "history": history_entries
    })


# ─────────────────────────────────────────────────────────────────────────────
# 5. Bulk Upload via CSV and Excel
# ─────────────────────────────────────────────────────────────────────────────
@attendance_bp.route("/import", methods=["GET", "POST"])
@login_required
def bulk_import():
    """
    Bulk imports attendance records from CSV or Excel (.xlsx/.xls).
    Handles:
      - Missing values
      - Invalid dates
      - Duplicate sessions (updates existing with audit log reason)
      - Roll number resolution
    """
    semesters = Semester.query.order_by(Semester.year.desc()).all()
    subjects  = Subject.query.order_by(Subject.code).all()

    if request.method == "POST":
        file             = request.files.get("file")
        default_sub_id   = request.form.get("subject_id", type=int)
        default_date_str = request.form.get("default_date", "").strip()
        default_session  = request.form.get("default_session", 1, type=int)

        if not file or not file.filename:
            flash("Please choose a CSV or Excel file to upload.", "danger")
            return redirect(url_for("attendance.bulk_import"))

        filename = file.filename.lower()
        ext = filename.rsplit(".", 1)[-1] if "." in filename else ""
        if ext not in ("csv", "xlsx", "xls"):
            flash("Only .csv, .xlsx, and .xls files are allowed.", "danger")
            return redirect(url_for("attendance.bulk_import"))

        try:
            if ext == "csv":
                df = pd.read_csv(io.BytesIO(file.read()))
            else:
                df = pd.read_excel(io.BytesIO(file.read()))
        except Exception as e:
            flash(f"Could not parse file: {e}", "danger")
            return redirect(url_for("attendance.bulk_import"))

        if df.empty:
            flash("Uploaded file contains no rows.", "warning")
            return redirect(url_for("attendance.bulk_import"))

        # Clean column names
        df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]

        # Column aliases
        aliases = {
            "roll": "roll_number", "roll_no": "roll_number", "rollno": "roll_number",
            "attendance": "status", "attendance_status": "status",
            "attendance_date": "date",
            "slot": "session_slot", "session": "session_slot", "period": "session_slot",
            "subject_code": "code", "sub_code": "code"
        }
        df.rename(columns={c: aliases[c] for c in df.columns if c in aliases}, inplace=True)

        if "roll_number" not in df.columns:
            flash(f"File must contain a 'roll_number' column. Found: {', '.join(df.columns)}", "danger")
            return redirect(url_for("attendance.bulk_import"))

        # Default date fallback
        default_att_date = None
        if default_date_str:
            try:
                default_att_date = date.fromisoformat(default_date_str)
            except ValueError:
                default_att_date = date.today()
        else:
            default_att_date = date.today()

        # Cache subjects & students for quick lookup
        subject_map_by_code = {s.code.strip().upper(): s for s in Subject.query.all() if s.code}
        subject_map_by_id   = {s.id: s for s in Subject.query.all()}
        student_map_by_roll = {s.roll_number.strip().upper(): s for s in Student.query.all()}
        student_map_by_sid  = {s.student_id.strip().upper(): s for s in Student.query.all()}

        inserted_count = 0
        updated_count  = 0
        skipped_count  = 0
        errors         = []

        for idx, row in df.iterrows():
            row_num = idx + 2
            try:
                # 1. Resolve student
                roll_raw = str(row.get("roll_number", "")).strip().upper()
                if not roll_raw or roll_raw == "NAN":
                    errors.append(f"Row {row_num}: Roll number is missing.")
                    skipped_count += 1
                    continue

                student = student_map_by_roll.get(roll_raw) or student_map_by_sid.get(roll_raw)
                if not student:
                    errors.append(f"Row {row_num}: Student with Roll '{roll_raw}' not found.")
                    skipped_count += 1
                    continue

                # 2. Resolve subject
                target_sub = None
                if "code" in df.columns and pd.notna(row.get("code")):
                    code_val = str(row["code"]).strip().upper()
                    target_sub = subject_map_by_code.get(code_val)

                if not target_sub and "subject_id" in df.columns and pd.notna(row.get("subject_id")):
                    try:
                        s_id = int(row["subject_id"])
                        target_sub = subject_map_by_id.get(s_id)
                    except ValueError:
                        pass

                if not target_sub and default_sub_id:
                    target_sub = subject_map_by_id.get(default_sub_id)

                if not target_sub:
                    errors.append(f"Row {row_num}: Subject could not be resolved.")
                    skipped_count += 1
                    continue

                # Auto-enroll student into subject if not yet enrolled
                student.enroll_in_subject(target_sub.id)

                # 3. Resolve Date (handles missing or invalid date safely)
                rec_date = None
                if "date" in df.columns and pd.notna(row.get("date")):
                    date_val = row["date"]
                    try:
                        parsed_dt = pd.to_datetime(date_val)
                        rec_date = parsed_dt.date()
                    except Exception:
                        errors.append(f"Row {row_num}: Invalid date format '{date_val}'.")
                        skipped_count += 1
                        continue
                else:
                    rec_date = default_att_date

                # 4. Resolve session slot
                rec_session = default_session
                if "session_slot" in df.columns and pd.notna(row.get("session_slot")):
                    try:
                        rec_session = int(row["session_slot"])
                    except (ValueError, TypeError):
                        rec_session = 1

                # 5. Resolve status (handles missing values: defaults to 'absent')
                status_raw = str(row.get("status", "absent")).strip().lower()
                if status_raw in ("p", "present", "1", "true", "yes"):
                    status = "present"
                elif status_raw in ("l", "late"):
                    status = "late"
                elif status_raw in ("e", "excused"):
                    status = "excused"
                else:
                    status = "absent"

                remarks_val = str(row.get("remarks", "")).strip()
                if remarks_val.lower() == "nan":
                    remarks_val = None

                # 6. Duplicate prevention & update handling
                existing = AttendanceRecord.query.filter_by(
                    student_id=student.id,
                    subject_id=target_sub.id,
                    date=rec_date,
                    session_slot=rec_session
                ).first()

                if existing:
                    if existing.status != status or existing.remarks != remarks_val:
                        old_st = existing.status
                        existing.status = status
                        existing.remarks = remarks_val
                        existing.last_modified_by = current_user.id
                        existing.updated_at = datetime.utcnow()

                        # Audit history entry
                        audit = AttendanceEditHistory(
                            attendance_record_id=existing.id,
                            old_status=old_st,
                            new_status=status,
                            reason="Bulk upload update",
                            edited_by=current_user.id,
                            edited_at=datetime.utcnow()
                        )
                        db.session.add(audit)
                        updated_count += 1
                    else:
                        skipped_count += 1
                else:
                    # Insert new
                    new_rec = AttendanceRecord(
                        student_id=student.id,
                        subject_id=target_sub.id,
                        date=rec_date,
                        session_slot=rec_session,
                        status=status,
                        remarks=remarks_val,
                        marked_by=current_user.id,
                        last_modified_by=current_user.id
                    )
                    db.session.add(new_rec)
                    inserted_count += 1

            except Exception as e:
                errors.append(f"Row {row_num}: {e}")
                skipped_count += 1

        db.session.commit()

        flash(
            f"Bulk Upload Complete: {inserted_count} new records added, "
            f"{updated_count} existing records updated, {skipped_count} skipped.",
            "success"
        )
        if errors:
            preview_errs = "; ".join(errors[:5])
            flash(f"Upload warnings: {preview_errs}", "warning")

        return redirect(url_for("attendance.view"))

    return render_template(
        "attendance/import.html",
        semesters=semesters,
        subjects=subjects,
        today=date.today().isoformat()
    )


# ─────────────────────────────────────────────────────────────────────────────
# 6. Download Bulk Attendance Template
# ─────────────────────────────────────────────────────────────────────────────
@attendance_bp.route("/template")
@login_required
def download_template():
    """Generates a downloadable CSV template for bulk attendance."""
    sample_csv = (
        "roll_number,date,session_slot,status,remarks,code\n"
        "CS202501,2025-09-01,1,present,,CS601\n"
        "CS202502,2025-09-01,1,present,,CS601\n"
        "CS202503,2025-09-01,1,absent,Medical Leave,CS601\n"
        "CS202504,2025-09-01,1,present,,CS601\n"
    )
    return Response(
        sample_csv,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=attendance_upload_template.csv"}
    )


# ─────────────────────────────────────────────────────────────────────────────
# 7. Individual Student Attendance History
# ─────────────────────────────────────────────────────────────────────────────
@attendance_bp.route("/student/<int:student_id>")
@login_required
def student_history(student_id):
    """
    Displays the complete attendance history for a single student:
      - Overall (Attended / Conducted) × 100
      - Subject-wise breakdown
      - Chronological attendance logs with edit history audit badges
      - Authorised inline correction modal
    """
    student = db.session.get(Student, student_id)
    if not student:
        flash("Student not found.", "danger")
        return redirect(url_for("attendance.view"))

    # Subject filter
    sub_id = request.args.get("subject_id", type=int)
    status_filter = request.args.get("status", "all").strip().lower()

    # Calculate overall stats
    overall_stats = student.get_overall_stats()

    # Calculate stats for all subjects of the student's semester
    semester_subjects = Subject.query.filter_by(semester_id=student.semester_id).order_by(Subject.code).all()
    subject_stats_list = []
    for subj in semester_subjects:
        stats = student.get_subject_stats(subj.id)
        stats["subject"] = subj
        subject_stats_list.append(stats)

    # Detailed attendance records for student
    rec_query = AttendanceRecord.query.filter_by(student_id=student.id)
    if sub_id:
        rec_query = rec_query.filter_by(subject_id=sub_id)
    if status_filter in ("present", "absent", "late", "excused"):
        rec_query = rec_query.filter_by(status=status_filter)

    attendance_logs = rec_query.order_by(
        AttendanceRecord.date.desc(), AttendanceRecord.session_slot.desc()
    ).all()

    return render_template(
        "attendance/student_history.html",
        student=student,
        overall_stats=overall_stats,
        subject_stats_list=subject_stats_list,
        attendance_logs=attendance_logs,
        semester_subjects=semester_subjects,
        selected_sub_id=sub_id,
        status_filter=status_filter
    )


# ─────────────────────────────────────────────────────────────────────────────
# 8. Subject-wise Attendance Report
# ─────────────────────────────────────────────────────────────────────────────
@attendance_bp.route("/report/subject/<int:subject_id>")
@login_required
def subject_report(subject_id):
    """
    Generates a comprehensive subject-wise report:
      - Total classes conducted = distinct (date, session_slot)
      - Enrolled students roster with Attended, Absent, and Percentage
      - Shortage identification (< 75%) and Critical risk (< 60%)
      - Statistical summary
    """
    subject = db.session.get(Subject, subject_id)
    if not subject:
        flash("Subject not found.", "danger")
        return redirect(url_for("attendance.view"))

    conducted = subject.classes_conducted()
    students  = subject.enrolled_students().all()

    roster = []
    total_percentage = 0.0
    shortage_count   = 0
    critical_count   = 0

    for st in students:
        stats = st.get_subject_stats(subject.id)
        pct   = stats["percentage"]
        total_percentage += pct

        if pct < 60.0:
            critical_count += 1
            shortage_count += 1
        elif pct < 75.0:
            shortage_count += 1

        roster.append({
            "student": st,
            "attended": stats["attended"],
            "absent": stats["absent"],
            "conducted": stats["conducted"],
            "percentage": pct,
            "risk_level": stats["risk_level"],
            "badge_class": stats["badge_class"]
        })

    avg_percentage = round(total_percentage / len(students), 2) if students else 0.0

    return render_template(
        "attendance/subject_report.html",
        subject=subject,
        conducted=conducted,
        students=students,
        roster=roster,
        avg_percentage=avg_percentage,
        shortage_count=shortage_count,
        critical_count=critical_count
    )


# ─────────────────────────────────────────────────────────────────────────────
# 9. Semester-wise Attendance Report
# ─────────────────────────────────────────────────────────────────────────────
@attendance_bp.route("/report/semester/<int:semester_id>")
@login_required
def semester_report(semester_id):
    """
    Generates a full semester-wide attendance report:
      - Master matrix: Students (rows) × Subjects (columns)
      - Individual subject percentages and cumulative overall percentage
      - Highlights students with attendance shortage
    """
    sem = db.session.get(Semester, semester_id)
    if not sem:
        flash("Semester not found.", "danger")
        return redirect(url_for("attendance.view"))

    subjects = Subject.query.filter_by(semester_id=sem.id).order_by(Subject.code).all()
    students = Student.query.filter_by(semester_id=sem.id, is_active=True).order_by(Student.roll_number).all()

    matrix_rows = []
    shortage_student_count = 0

    for st in students:
        row_data = {
            "student": st,
            "subject_pcts": {},
            "has_shortage": False,
        }

        for subj in subjects:
            stats = st.get_subject_stats(subj.id)
            row_data["subject_pcts"][subj.id] = stats
            if stats["is_shortage"] and stats["conducted"] > 0:
                row_data["has_shortage"] = True

        overall = st.get_overall_stats()
        row_data["overall"] = overall
        if overall["is_shortage"]:
            row_data["has_shortage"] = True

        if row_data["has_shortage"]:
            shortage_student_count += 1

        matrix_rows.append(row_data)

    return render_template(
        "attendance/semester_report.html",
        semester=sem,
        subjects=subjects,
        matrix_rows=matrix_rows,
        shortage_student_count=shortage_student_count,
        total_students=len(students)
    )
