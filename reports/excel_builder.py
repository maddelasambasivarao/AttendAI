"""
reports/excel_builder.py – OpenPyXL Excel Generation Engine for AttendAI.

Generates professional Excel workbooks:
  1. Attendance Records Log (full session-by-session log with audit details).
  2. Risk Analysis & Recovery Metrics (ML probabilities, risk tiers, recovery math).
  3. Subject-Wise Statistics (curriculum course aggregates, averages, shortage counts).
  4. Semester-Wise Master Matrix (cross-tabulation of students by subjects).
  5. Department-Wise Attendance Report.
  6. Individual Student Attendance Dossier (multi-sheet workbook).
  7. Attendance Upload Template (pre-styled .xlsx template for bulk imports).
"""

import io
from datetime import date, datetime
from typing import Optional, List, Dict, Any

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from database.models import (
    db, Student, Subject, Semester, AttendanceRecord, PredictionHistory,
    Intervention, SystemSetting, Faculty, User
)
from ml.recommendations import calculate_attendance_recovery
from ml.predict import predict_student_risk, predict_risk


# ── Common Style Constants ────────────────────────────────────────────────────
NAVY_HEADER_FILL   = PatternFill("solid", fgColor="0F2744")
CYAN_HEADER_FILL   = PatternFill("solid", fgColor="0891B2")
LIGHT_HEADER_FILL  = PatternFill("solid", fgColor="F1F5F9")

FILL_HIGH_RISK     = PatternFill("solid", fgColor="FEE2E2")  # soft red
FILL_MEDIUM_RISK   = PatternFill("solid", fgColor="FEF3C7")  # soft amber
FILL_LOW_RISK      = PatternFill("solid", fgColor="DCFCE7")  # soft green

FONT_WHITE_BOLD    = Font(name="Calibri", bold=True, color="FFFFFF", size=11)
FONT_DARK_BOLD     = Font(name="Calibri", bold=True, color="0F172A", size=11)
FONT_MUTED_SMALL   = Font(name="Calibri", italic=True, color="64748B", size=9)

FONT_RED           = Font(name="Calibri", bold=True, color="B91C1C", size=10)
FONT_AMBER         = Font(name="Calibri", bold=True, color="B45309", size=10)
FONT_GREEN         = Font(name="Calibri", bold=True, color="047857", size=10)

THIN_BORDER = Border(
    left=Side(style="thin", color="CBD5E1"),
    right=Side(style="thin", color="CBD5E1"),
    top=Side(style="thin", color="CBD5E1"),
    bottom=Side(style="thin", color="CBD5E1"),
)

CENTER_ALIGN = Alignment(horizontal="center", vertical="center")
LEFT_ALIGN   = Alignment(horizontal="left", vertical="center")
RIGHT_ALIGN  = Alignment(horizontal="right", vertical="center")


def _auto_fit_columns(ws, min_width: int = 12, padding: int = 4):
    """Automatically scales worksheet column widths to fit content."""
    for col in ws.columns:
        col_letter = get_column_letter(col[0].column)
        max_len = 0
        for cell in col:
            val_str = str(cell.value or "")
            if "\n" in val_str:
                val_str = max(val_str.split("\n"), key=len)
            max_len = max(max_len, len(val_str))
        ws.column_dimensions[col_letter].width = max(max_len + padding, min_width)


# ─────────────────────────────────────────────────────────────────────────────
# 1. ATTENDANCE RECORDS LOG (Raw Database Dump)
# ─────────────────────────────────────────────────────────────────────────────
def build_attendance_records_excel(
    semester_id: Optional[int] = None,
    subject_id: Optional[int] = None,
    department: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    status: Optional[str] = None
) -> io.BytesIO:
    """Exports raw attendance records matching database filters exactly."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Attendance Records Log"

    # Query with filters
    query = AttendanceRecord.query.join(Student).join(Subject)
    if semester_id:
        query = query.filter(Student.semester_id == semester_id)
    if subject_id:
        query = query.filter(AttendanceRecord.subject_id == subject_id)
    if department:
        query = query.filter(Student.department == department)
    if start_date:
        query = query.filter(AttendanceRecord.date >= start_date)
    if end_date:
        query = query.filter(AttendanceRecord.date <= end_date)
    if status and status != "all":
        query = query.filter(AttendanceRecord.status == status)

    records = query.order_by(AttendanceRecord.date.desc(), AttendanceRecord.session_slot, Student.roll_number).all()

    # Title Banner
    ws.merge_cells("A1:K1")
    ws["A1"] = "AttendAI – Attendance Session Records Log"
    ws["A1"].font = Font(name="Calibri", bold=True, color="FFFFFF", size=14)
    ws["A1"].fill = NAVY_HEADER_FILL
    ws["A1"].alignment = LEFT_ALIGN
    ws.row_dimensions[1].height = 32

    ws.merge_cells("A2:K2")
    ws["A2"] = f"Total Exported Records: {len(records)}  |  Export Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    ws["A2"].font = FONT_MUTED_SMALL
    ws.row_dimensions[2].height = 18

    # Table Headers
    headers = [
        "Record ID", "Date", "Session Slot", "Course Code", "Course Name",
        "Roll Number", "Student Name", "Department", "Class/Section", "Status", "Remarks"
    ]
    header_row = 4
    ws.row_dimensions[header_row].height = 24
    for col_idx, h in enumerate(headers, 1):
        cell = ws.cell(row=header_row, column=col_idx, value=h)
        cell.fill = CYAN_HEADER_FILL
        cell.font = FONT_WHITE_BOLD
        cell.alignment = CENTER_ALIGN
        cell.border = THIN_BORDER

    # Populate Data
    for row_idx, r in enumerate(records, start=header_row + 1):
        ws.row_dimensions[row_idx].height = 20
        c1 = ws.cell(row=row_idx, column=1, value=r.id)
        c2 = ws.cell(row=row_idx, column=2, value=r.date.isoformat())
        c3 = ws.cell(row=row_idx, column=3, value=f"Session {r.session_slot}")
        c4 = ws.cell(row=row_idx, column=4, value=r.subject.code if r.subject else "—")
        c5 = ws.cell(row=row_idx, column=5, value=r.subject.name if r.subject else "—")
        c6 = ws.cell(row=row_idx, column=6, value=r.student.roll_number if r.student else "—")
        c7 = ws.cell(row=row_idx, column=7, value=r.student.name if r.student else "—")
        c8 = ws.cell(row=row_idx, column=8, value=r.student.department or "—")
        c9 = ws.cell(row=row_idx, column=9, value=f"Yr {r.student.year}-{r.student.section}")
        c10 = ws.cell(row=row_idx, column=10, value=r.status.upper())
        c11 = ws.cell(row=row_idx, column=11, value=r.remarks or "")

        for c in (c1, c2, c3, c4, c5, c6, c7, c8, c9, c10, c11):
            c.border = THIN_BORDER
            c.alignment = CENTER_ALIGN if c in (c1, c2, c3, c4, c6, c9, c10) else LEFT_ALIGN

        # Status coloring
        if r.status == "present":
            c10.fill = FILL_LOW_RISK
            c10.font = FONT_GREEN
        elif r.status == "absent":
            c10.fill = FILL_HIGH_RISK
            c10.font = FONT_RED
        else:
            c10.fill = FILL_MEDIUM_RISK
            c10.font = FONT_AMBER

    _auto_fit_columns(ws, min_width=12)
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer


# ─────────────────────────────────────────────────────────────────────────────
# 2. RISK ANALYSIS & RECOVERY METRICS EXCEL
# ─────────────────────────────────────────────────────────────────────────────
def build_risk_analysis_excel(semester_id: Optional[int] = None) -> io.BytesIO:
    """Exports academic risk predictions and mathematical recovery projections."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Academic Risk Analysis"

    query = Student.query.filter_by(is_active=True)
    if semester_id:
        query = query.filter_by(semester_id=semester_id)
    students = query.order_by(Student.roll_number).all()

    # Title Banner
    ws.merge_cells("A1:M1")
    ws["A1"] = "AttendAI – Student Academic Risk & Recovery Analytics"
    ws["A1"].font = Font(name="Calibri", bold=True, color="FFFFFF", size=14)
    ws["A1"].fill = NAVY_HEADER_FILL
    ws["A1"].alignment = LEFT_ALIGN
    ws.row_dimensions[1].height = 32

    ws.merge_cells("A2:M2")
    ws["A2"] = f"Total Evaluated Students: {len(students)}  |  Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    ws["A2"].font = FONT_MUTED_SMALL
    ws.row_dimensions[2].height = 18

    headers = [
        "Student ID", "Roll Number", "Full Name", "Department", "Class",
        "Classes Conducted", "Classes Attended", "Attendance %",
        "ML Shortage Prob", "Risk Tier", "Classes Needed for 75%", "Max Possible %", "Feasibility"
    ]
    header_row = 4
    ws.row_dimensions[header_row].height = 24
    for col_idx, h in enumerate(headers, 1):
        cell = ws.cell(row=header_row, column=col_idx, value=h)
        cell.fill = CYAN_HEADER_FILL
        cell.font = FONT_WHITE_BOLD
        cell.alignment = CENTER_ALIGN
        cell.border = THIN_BORDER

    for row_idx, st in enumerate(students, start=header_row + 1):
        ws.row_dimensions[row_idx].height = 20
        stat = st.get_overall_stats()
        conducted = stat["conducted"]
        attended = stat["attended"]
        pct = stat["percentage"]

        pred = st.latest_prediction()
        prob = pred.risk_probability if pred else (0.85 if pct < 60 else (0.50 if pct < 75 else 0.15))
        risk_level = pred.risk_level if pred else ("High" if pct < 60 else ("Medium" if pct < 75 else "Low"))

        remaining = max(0, 40 - conducted)
        recovery = calculate_attendance_recovery(conducted, attended, remaining, 75.0)

        cells = [
            ws.cell(row=row_idx, column=1, value=st.student_id),
            ws.cell(row=row_idx, column=2, value=st.roll_number),
            ws.cell(row=row_idx, column=3, value=st.name),
            ws.cell(row=row_idx, column=4, value=st.department or "—"),
            ws.cell(row=row_idx, column=5, value=f"Yr {st.year}-{st.section}"),
            ws.cell(row=row_idx, column=6, value=conducted),
            ws.cell(row=row_idx, column=7, value=attended),
            ws.cell(row=row_idx, column=8, value=f"{pct:.1f}%"),
            ws.cell(row=row_idx, column=9, value=f"{prob * 100:.1f}%"),
            ws.cell(row=row_idx, column=10, value=risk_level),
            ws.cell(row=row_idx, column=11, value=recovery["classes_needed_for_target"]),
            ws.cell(row=row_idx, column=12, value=f"{recovery['max_possible_percentage']:.1f}%"),
            ws.cell(row=row_idx, column=13, value="Feasible" if recovery["is_recoverable"] else "CRITICAL"),
        ]

        for c in cells:
            c.border = THIN_BORDER
            c.alignment = LEFT_ALIGN if c.column in (3, 4) else CENTER_ALIGN

        # Color coding
        if risk_level == "High":
            cells[7].fill = FILL_HIGH_RISK
            cells[7].font = FONT_RED
            cells[9].fill = FILL_HIGH_RISK
            cells[9].font = FONT_RED
        elif risk_level == "Medium":
            cells[7].fill = FILL_MEDIUM_RISK
            cells[7].font = FONT_AMBER
            cells[9].fill = FILL_MEDIUM_RISK
            cells[9].font = FONT_AMBER
        else:
            cells[7].fill = FILL_LOW_RISK
            cells[7].font = FONT_GREEN
            cells[9].fill = FILL_LOW_RISK
            cells[9].font = FONT_GREEN

        if not recovery["is_recoverable"]:
            cells[12].fill = FILL_HIGH_RISK
            cells[12].font = FONT_RED

    _auto_fit_columns(ws, min_width=12)
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer


# ─────────────────────────────────────────────────────────────────────────────
# 3. SUBJECT-WISE STATISTICS EXCEL
# ─────────────────────────────────────────────────────────────────────────────
def build_subject_statistics_excel(semester_id: Optional[int] = None) -> io.BytesIO:
    """Exports course-by-course performance and attendance statistics."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Course Performance Statistics"

    query = Subject.query
    if semester_id:
        query = query.filter_by(semester_id=semester_id)
    subjects = query.order_by(Subject.code).all()

    # Title Banner
    ws.merge_cells("A1:I1")
    ws["A1"] = "AttendAI – Curriculum Course Attendance Performance Audit"
    ws["A1"].font = Font(name="Calibri", bold=True, color="FFFFFF", size=14)
    ws["A1"].fill = NAVY_HEADER_FILL
    ws["A1"].alignment = LEFT_ALIGN
    ws.row_dimensions[1].height = 32

    headers = [
        "Course Code", "Course Name", "Faculty Instructor", "Semester",
        "Classes Planned", "Sessions Conducted", "Enrolled Scholars",
        "Average Attendance %", "Students Below 75%"
    ]
    header_row = 3
    ws.row_dimensions[header_row].height = 24
    for col_idx, h in enumerate(headers, 1):
        cell = ws.cell(row=header_row, column=col_idx, value=h)
        cell.fill = CYAN_HEADER_FILL
        cell.font = FONT_WHITE_BOLD
        cell.alignment = CENTER_ALIGN
        cell.border = THIN_BORDER

    for row_idx, s in enumerate(subjects, start=header_row + 1):
        ws.row_dimensions[row_idx].height = 20
        recs = AttendanceRecord.query.filter_by(subject_id=s.id).all()
        cond = len(recs)
        pres = sum(1 for r in recs if r.status in ("present", "late"))
        avg_pct = round(pres / cond * 100, 1) if cond > 0 else 0.0

        enrolled = s.enrolled_students().count()
        if enrolled == 0 and s.semester_id:
            enrolled = Student.query.filter_by(semester_id=s.semester_id, is_active=True).count()

        # Count students under 75%
        shortage_count = 0
        students = s.enrolled_students().all() or Student.query.filter_by(semester_id=s.semester_id, is_active=True).all()
        for st in students:
            stat = st.get_subject_stats(s.id)
            if stat["conducted"] > 0 and stat["percentage"] < 75.0:
                shortage_count += 1

        cells = [
            ws.cell(row=row_idx, column=1, value=s.code),
            ws.cell(row=row_idx, column=2, value=s.name),
            ws.cell(row=row_idx, column=3, value=s.faculty.name if s.faculty else "Unassigned"),
            ws.cell(row=row_idx, column=4, value=s.semester.name if s.semester else "—"),
            ws.cell(row=row_idx, column=5, value=s.total_classes_planned),
            ws.cell(row=row_idx, column=6, value=s.classes_conducted()),
            ws.cell(row=row_idx, column=7, value=enrolled),
            ws.cell(row=row_idx, column=8, value=f"{avg_pct:.1f}%"),
            ws.cell(row=row_idx, column=9, value=shortage_count),
        ]

        for c in cells:
            c.border = THIN_BORDER
            c.alignment = LEFT_ALIGN if c.column in (2, 3) else CENTER_ALIGN

        # Color average %
        if avg_pct < 60:
            cells[7].fill = FILL_HIGH_RISK
            cells[7].font = FONT_RED
        elif avg_pct < 75:
            cells[7].fill = FILL_MEDIUM_RISK
            cells[7].font = FONT_AMBER
        else:
            cells[7].fill = FILL_LOW_RISK
            cells[7].font = FONT_GREEN

        if shortage_count > 0:
            cells[8].fill = FILL_MEDIUM_RISK

    _auto_fit_columns(ws, min_width=12)
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer


# ─────────────────────────────────────────────────────────────────────────────
# 4. SEMESTER-WISE MASTER MATRIX EXCEL
# ─────────────────────────────────────────────────────────────────────────────
def build_semester_matrix_excel(semester_id: int) -> io.BytesIO:
    """Cross-tabulates all students by curriculum subjects with overall %."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Semester Matrix"

    sem = db.session.get(Semester, semester_id)
    if not sem:
        raise ValueError(f"Semester {semester_id} not found.")

    students = Student.query.filter_by(semester_id=sem.id, is_active=True).order_by(Student.roll_number).all()
    subjects = Subject.query.filter_by(semester_id=sem.id).order_by(Subject.code).all()

    # Title
    ws.merge_cells("A1:D1")
    ws["A1"] = f"AttendAI – Semester Attendance Grid: {sem.name}"
    ws["A1"].font = Font(name="Calibri", bold=True, color="FFFFFF", size=13)
    ws["A1"].fill = NAVY_HEADER_FILL
    ws["A1"].alignment = LEFT_ALIGN
    ws.row_dimensions[1].height = 28

    header_row = 3
    ws.row_dimensions[header_row].height = 28

    # Base headers
    base_headers = ["Roll No", "Student Name", "Department", "Class"]
    for col_idx, h in enumerate(base_headers, 1):
        cell = ws.cell(row=header_row, column=col_idx, value=h)
        cell.fill = CYAN_HEADER_FILL
        cell.font = FONT_WHITE_BOLD
        cell.alignment = CENTER_ALIGN
        cell.border = THIN_BORDER

    # Subject headers
    for idx, subj in enumerate(subjects, start=len(base_headers) + 1):
        cell = ws.cell(row=header_row, column=idx, value=f"{subj.code}\n({subj.name})")
        cell.fill = NAVY_HEADER_FILL
        cell.font = FONT_WHITE_BOLD
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = THIN_BORDER

    # Cumulative headers
    total_cols = len(base_headers) + len(subjects)
    ov_cell = ws.cell(row=header_row, column=total_cols + 1, value="Overall %")
    ov_cell.fill = CYAN_HEADER_FILL
    ov_cell.font = FONT_WHITE_BOLD
    ov_cell.alignment = CENTER_ALIGN
    ov_cell.border = THIN_BORDER

    rk_cell = ws.cell(row=header_row, column=total_cols + 2, value="Risk Tier")
    rk_cell.fill = CYAN_HEADER_FILL
    rk_cell.font = FONT_WHITE_BOLD
    rk_cell.alignment = CENTER_ALIGN
    rk_cell.border = THIN_BORDER

    # Populate rows
    for row_idx, st in enumerate(students, start=header_row + 1):
        ws.row_dimensions[row_idx].height = 20
        ws.cell(row=row_idx, column=1, value=st.roll_number).border = THIN_BORDER
        ws.cell(row=row_idx, column=2, value=st.name).border = THIN_BORDER
        ws.cell(row=row_idx, column=3, value=st.department or "—").border = THIN_BORDER
        ws.cell(row=row_idx, column=4, value=f"Yr {st.year}-{st.section}").border = THIN_BORDER

        for idx, subj in enumerate(subjects, start=len(base_headers) + 1):
            sub_stat = st.get_subject_stats(subj.id)
            pct = sub_stat["percentage"]
            cell = ws.cell(row=row_idx, column=idx, value=f"{pct:.1f}%")
            cell.alignment = CENTER_ALIGN
            cell.border = THIN_BORDER
            if pct < 60:
                cell.fill = FILL_HIGH_RISK
                cell.font = FONT_RED
            elif pct < 75:
                cell.fill = FILL_MEDIUM_RISK
                cell.font = FONT_AMBER

        overall = st.get_overall_stats()
        ov_pct = overall["percentage"]
        pred = st.latest_prediction()
        risk = pred.risk_level if pred else ("High" if ov_pct < 60 else ("Medium" if ov_pct < 75 else "Low"))

        c_ov = ws.cell(row=row_idx, column=total_cols + 1, value=f"{ov_pct:.1f}%")
        c_ov.alignment = CENTER_ALIGN
        c_ov.border = THIN_BORDER
        c_ov.font = Font(bold=True)

        c_rk = ws.cell(row=row_idx, column=total_cols + 2, value=risk)
        c_rk.alignment = CENTER_ALIGN
        c_rk.border = THIN_BORDER
        c_rk.font = Font(bold=True)

        if risk == "High":
            c_ov.fill = FILL_HIGH_RISK
            c_rk.fill = FILL_HIGH_RISK
            c_rk.font = FONT_RED
        elif risk == "Medium":
            c_ov.fill = FILL_MEDIUM_RISK
            c_rk.fill = FILL_MEDIUM_RISK
            c_rk.font = FONT_AMBER
        else:
            c_ov.fill = FILL_LOW_RISK
            c_rk.fill = FILL_LOW_RISK
            c_rk.font = FONT_GREEN

    _auto_fit_columns(ws, min_width=12)
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer


# ─────────────────────────────────────────────────────────────────────────────
# 5. INDIVIDUAL STUDENT EXCEL WORKBOOK (Multi-Sheet)
# ─────────────────────────────────────────────────────────────────────────────
def build_student_excel(student_id: int) -> io.BytesIO:
    """Builds a multi-tab workbook for a single student."""
    wb = openpyxl.Workbook()
    student = db.session.get(Student, student_id)
    if not student:
        raise ValueError(f"Student {student_id} not found.")

    # Sheet 1: Summary & Projections
    ws_sum = wb.active
    ws_sum.title = "Student Profile"

    ws_sum.merge_cells("A1:D1")
    ws_sum["A1"] = f"AttendAI – Academic Profile: {student.name} ({student.roll_number})"
    ws_sum["A1"].font = Font(name="Calibri", bold=True, color="FFFFFF", size=13)
    ws_sum["A1"].fill = NAVY_HEADER_FILL
    ws_sum["A1"].alignment = LEFT_ALIGN

    stat = student.get_overall_stats()
    ml_pred = predict_student_risk(student.id)
    recovery = calculate_attendance_recovery(stat["conducted"], stat["attended"], max(0, 40 - stat["conducted"]), 75.0)

    # Left Column (Metadata)
    meta_pairs = [
        ("Full Name", student.name),
        ("Roll Number", student.roll_number),
        ("Student ID", student.student_id),
        ("Department", student.department or "General"),
        ("Year & Section", f"Year {student.year}, Section {student.section}"),
        ("Academic Term", student.semester.name if student.semester else "—"),
    ]
    for idx, (lbl, val) in enumerate(meta_pairs, start=3):
        c1 = ws_sum.cell(row=idx, column=1, value=lbl)
        c2 = ws_sum.cell(row=idx, column=2, value=val)
        c1.font = FONT_DARK_BOLD
        c1.fill = LIGHT_HEADER_FILL
        c1.border = THIN_BORDER
        c2.border = THIN_BORDER

    # Right Column (Key Performance Indicators & ML Projections)
    kpi_pairs = [
        ("Total Sessions Conducted", stat["conducted"]),
        ("Total Sessions Attended", stat["attended"]),
        ("Overall Attendance %", stat["percentage"]),
        ("ML Shortage Probability %", round(ml_pred.get("risk_probability", 0.0) * 100, 1)),
        ("Calibrated Risk Tier", ml_pred.get("risk_category", "Low")),
        ("Classes Needed for 75%", recovery["classes_needed_for_target"]),
        ("Max Attainable %", round(recovery["max_possible_percentage"], 1)),
        ("Recovery Feasibility", "Feasible" if recovery["is_recoverable"] else "CRITICAL"),
    ]
    for idx, (lbl, val) in enumerate(kpi_pairs, start=3):
        c3 = ws_sum.cell(row=idx, column=3, value=lbl)
        c4 = ws_sum.cell(row=idx, column=4, value=val)
        c3.font = FONT_DARK_BOLD
        c3.fill = LIGHT_HEADER_FILL
        c3.border = THIN_BORDER
        c4.border = THIN_BORDER
        if isinstance(val, (int, float)):
            c4.alignment = RIGHT_ALIGN
        else:
            c4.alignment = CENTER_ALIGN

    _auto_fit_columns(ws_sum, min_width=15)

    # Sheet 2: Subject Breakdown
    ws_sub = wb.create_sheet(title="Subject Breakdown")
    sub_headers = ["Code", "Course Name", "Conducted", "Attended", "Absent", "Percentage %", "Status"]
    for col_idx, h in enumerate(sub_headers, 1):
        cell = ws_sub.cell(row=1, column=col_idx, value=h)
        cell.fill = CYAN_HEADER_FILL
        cell.font = FONT_WHITE_BOLD
        cell.border = THIN_BORDER
        cell.alignment = CENTER_ALIGN

    subjects = Subject.query.filter_by(semester_id=student.semester_id).order_by(Subject.code).all()
    for row_idx, s in enumerate(subjects, start=2):
        s_stat = student.get_subject_stats(s.id)
        ws_sub.cell(row=row_idx, column=1, value=s.code).border = THIN_BORDER
        ws_sub.cell(row=row_idx, column=2, value=s.name).border = THIN_BORDER
        c_c = ws_sub.cell(row=row_idx, column=3, value=s_stat["conducted"])
        c_c.border = THIN_BORDER
        c_c.alignment = RIGHT_ALIGN
        c_a = ws_sub.cell(row=row_idx, column=4, value=s_stat["attended"])
        c_a.border = THIN_BORDER
        c_a.alignment = RIGHT_ALIGN
        c_ab = ws_sub.cell(row=row_idx, column=5, value=s_stat["absent"])
        c_ab.border = THIN_BORDER
        c_ab.alignment = RIGHT_ALIGN
        c_pct = ws_sub.cell(row=row_idx, column=6, value=s_stat["percentage"])
        c_pct.border = THIN_BORDER
        c_pct.alignment = RIGHT_ALIGN
        ws_sub.cell(row=row_idx, column=7, value=s_stat.get("risk_level", "Low")).border = THIN_BORDER

    _auto_fit_columns(ws_sub, min_width=12)

    # Sheet 3: Attendance Logs
    ws_log = wb.create_sheet(title="Attendance Session Log")
    log_headers = ["Date", "Session Slot", "Course Code", "Course Name", "Status", "Remarks"]
    for col_idx, h in enumerate(log_headers, 1):
        cell = ws_log.cell(row=1, column=col_idx, value=h)
        cell.fill = NAVY_HEADER_FILL
        cell.font = FONT_WHITE_BOLD
        cell.border = THIN_BORDER
        cell.alignment = CENTER_ALIGN

    logs = student.attendances.order_by(AttendanceRecord.date.desc(), AttendanceRecord.session_slot).all()
    for row_idx, l in enumerate(logs, start=2):
        ws_log.cell(row=row_idx, column=1, value=l.date.isoformat()).border = THIN_BORDER
        ws_log.cell(row=row_idx, column=2, value=f"Session {l.session_slot}").border = THIN_BORDER
        ws_log.cell(row=row_idx, column=3, value=l.subject.code if l.subject else "—").border = THIN_BORDER
        ws_log.cell(row=row_idx, column=4, value=l.subject.name if l.subject else "—").border = THIN_BORDER
        c_st = ws_log.cell(row=row_idx, column=5, value=l.status.upper())
        c_st.border = THIN_BORDER
        c_st.alignment = CENTER_ALIGN
        ws_log.cell(row=row_idx, column=6, value=l.remarks or "").border = THIN_BORDER

        if l.status == "present": c_st.fill = FILL_LOW_RISK
        elif l.status == "absent": c_st.fill = FILL_HIGH_RISK

    _auto_fit_columns(ws_log, min_width=12)
    log_headers = ["Date", "Session Slot", "Course Code", "Course Name", "Status", "Remarks"]
    for col_idx, h in enumerate(log_headers, 1):
        cell = ws_log.cell(row=1, column=col_idx, value=h)
        cell.fill = NAVY_HEADER_FILL
        cell.font = FONT_WHITE_BOLD
        cell.border = THIN_BORDER
        cell.alignment = CENTER_ALIGN

    logs = student.attendances.order_by(AttendanceRecord.date.desc(), AttendanceRecord.session_slot).all()
    for row_idx, l in enumerate(logs, start=2):
        ws_log.cell(row=row_idx, column=1, value=l.date.isoformat()).border = THIN_BORDER
        ws_log.cell(row=row_idx, column=2, value=f"Session {l.session_slot}").border = THIN_BORDER
        ws_log.cell(row=row_idx, column=3, value=l.subject.code if l.subject else "—").border = THIN_BORDER
        ws_log.cell(row=row_idx, column=4, value=l.subject.name if l.subject else "—").border = THIN_BORDER
        c_st = ws_log.cell(row=row_idx, column=5, value=l.status.upper())
        c_st.border = THIN_BORDER
        c_st.alignment = CENTER_ALIGN
        ws_log.cell(row=row_idx, column=6, value=l.remarks or "").border = THIN_BORDER

        if l.status == "present": c_st.fill = FILL_LOW_RISK
        elif l.status == "absent": c_st.fill = FILL_HIGH_RISK

    _auto_fit_columns(ws_log, min_width=12)

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer


# ─────────────────────────────────────────────────────────────────────────────
# 6. ATTENDANCE UPLOAD EXCEL TEMPLATE
# ─────────────────────────────────────────────────────────────────────────────
def build_attendance_upload_template_excel() -> io.BytesIO:
    """Builds a pre-formatted Excel workbook template for bulk attendance upload."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Attendance Upload Template"

    # Header Row
    headers = ["roll_number", "date", "session_slot", "status", "remarks", "code"]
    ws.row_dimensions[1].height = 26
    for col_idx, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_idx, value=h)
        cell.fill = CYAN_HEADER_FILL
        cell.font = FONT_WHITE_BOLD
        cell.alignment = CENTER_ALIGN
        cell.border = THIN_BORDER

    # Sample rows
    sample_rows = [
        ("CS202501", date.today().isoformat(), 1, "present", "", "CS701"),
        ("CS202502", date.today().isoformat(), 1, "present", "", "CS701"),
        ("CS202503", date.today().isoformat(), 1, "absent", "Sick Leave", "CS701"),
        ("CS202504", date.today().isoformat(), 1, "late", "Traffic Delay", "CS701"),
    ]

    for row_idx, r in enumerate(sample_rows, start=2):
        ws.row_dimensions[row_idx].height = 20
        for col_idx, val in enumerate(r, 1):
            cell = ws.cell(row=row_idx, column=col_idx, value=val)
            cell.border = THIN_BORDER
            cell.alignment = CENTER_ALIGN if col_idx in (1, 2, 3, 4, 6) else LEFT_ALIGN

    # Instruction Sheet
    ws_info = wb.create_sheet(title="Upload Instructions")
    ws_info.merge_cells("A1:C1")
    ws_info["A1"] = "AttendAI – Bulk Attendance Upload Guidelines"
    ws_info["A1"].font = Font(name="Calibri", bold=True, size=13, color="FFFFFF")
    ws_info["A1"].fill = NAVY_HEADER_FILL

    guidelines = [
        ("roll_number", "Required", "Exact student class roll number matching the student directory (e.g. CS202501)."),
        ("date", "Required", "Session date formatted as YYYY-MM-DD (e.g. 2025-02-15)."),
        ("session_slot", "Required", "Class period number (typically 1, 2, 3, or 4)."),
        ("status", "Required", "Accepts: 'present', 'absent', or 'late' (case-insensitive)."),
        ("remarks", "Optional", "Optional reason or note (e.g. Medical leave, Sports duty)."),
        ("code", "Optional", "Course subject code (e.g. CS701). If omitted, UI default selection applies."),
    ]

    ws_info.cell(row=3, column=1, value="Column Name").font = FONT_DARK_BOLD
    ws_info.cell(row=3, column=2, value="Requirement").font = FONT_DARK_BOLD
    ws_info.cell(row=3, column=3, value="Description").font = FONT_DARK_BOLD

    for row_idx, (c, req, desc) in enumerate(guidelines, start=4):
        ws_info.cell(row=row_idx, column=1, value=c).border = THIN_BORDER
        ws_info.cell(row=row_idx, column=2, value=req).border = THIN_BORDER
        ws_info.cell(row=row_idx, column=3, value=desc).border = THIN_BORDER

    _auto_fit_columns(ws, min_width=14)
    _auto_fit_columns(ws_info, min_width=18)

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer
