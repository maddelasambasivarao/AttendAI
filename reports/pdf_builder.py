"""
reports/pdf_builder.py – ReportLab PDF Generation Engine for AttendAI.

Generates professional academic PDF reports:
  1. Individual Student Report (dossier with attendance summary, subject breakdown,
     ML risk probability, attendance projection, recovery math, recommendations).
  2. Department-Wise Attendance Report.
  3. Semester-Wise Attendance Report.
  4. Subject-Wise Attendance Report.
  5. High-Risk Student Interventions & Shortage Audit Report.
  6. Machine Learning Predictions & Risk Model Audit Report.
"""

import os
import io
import json
from datetime import datetime, date
from typing import Optional, List, Dict, Any

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, KeepTogether, HRFlowable
)
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas

from database.models import (
    db, Student, Subject, Semester, AttendanceRecord, PredictionHistory,
    Intervention, SystemSetting, Faculty
)
from ml.recommendations import calculate_attendance_recovery, generate_recommendations
from ml.predict import predict_student_risk


# ── Color Palette ─────────────────────────────────────────────────────────────
NAVY_PRIMARY  = colors.HexColor("#0f2744")
NAVY_LIGHT    = colors.HexColor("#1e3a5f")
CYAN_ACCENT   = colors.HexColor("#0891b2")
SLATE_BG      = colors.HexColor("#f8fafc")
SLATE_BORDER  = colors.HexColor("#e2e8f0")
SLATE_TEXT    = colors.HexColor("#334155")
SLATE_MUTED   = colors.HexColor("#64748b")

COLOR_HIGH    = colors.HexColor("#dc2626")
COLOR_MEDIUM  = colors.HexColor("#d97706")
COLOR_LOW     = colors.HexColor("#059669")


# ── Numbered Canvas for Running Footers ────────────────────────────────────────
class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_footer(num_pages)
            canvas.Canvas.showPage(self)
        canvas.Canvas.save(self)

    def draw_footer(self, page_count):
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(SLATE_MUTED)
        
        # Footer text
        footer_text = "AttendAI – Intelligent Student Attendance Analytics and Risk Prediction System"
        page_text = f"Page {self._pageNumber} of {page_count}"
        
        self.drawString(1.5 * cm, 1.0 * cm, footer_text)
        self.drawRightString(A4[0] - 1.5 * cm, 1.0 * cm, page_text)
        
        # Thin footer line
        self.setStrokeColor(SLATE_BORDER)
        self.setLineWidth(0.5)
        self.line(1.5 * cm, 1.3 * cm, A4[0] - 1.5 * cm, 1.3 * cm)
        self.restoreState()


def get_deployed_model_meta():
    """Retrieves the deployed model name and version dynamically from model_meta.json."""
    meta_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "ml", "models", "model_meta.json")
    if os.path.exists(meta_path):
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                d = json.load(f)
                return d.get("best_model", "Logistic Regression"), d.get("version", "2.0.0")
        except Exception:
            pass
    return "Logistic Regression", "2.0.0"


# ── Common Header Builder ─────────────────────────────────────────────────────
def _create_header_story(title: str, subtitle: str, gen_timestamp: str) -> List[Any]:
    styles = getSampleStyleSheet()
    inst_name = SystemSetting.get("institution_name", "AttendAI Institute of Engineering & Technology")

    title_style = ParagraphStyle(
        "DocTitle",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=15,
        leading=18,
        textColor=NAVY_PRIMARY,
        spaceAfter=2,
    )
    subtitle_style = ParagraphStyle(
        "DocSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=12,
        textColor=SLATE_MUTED,
        spaceAfter=6,
    )
    inst_style = ParagraphStyle(
        "DocInst",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=10,
        leading=13,
        textColor=CYAN_ACCENT,
    )

    story = [
        Paragraph(inst_name.upper(), inst_style),
        Paragraph(f"AttendAI &nbsp;|&nbsp; {title}", title_style),
        Paragraph(f"{subtitle} &nbsp;&bull;&nbsp; <b>Generated on:</b> {gen_timestamp}", subtitle_style),
        HRFlowable(width="100%", thickness=1.5, color=CYAN_ACCENT, spaceBefore=2, spaceAfter=10),
    ]
    return story


# ─────────────────────────────────────────────────────────────────────────────
# 1. INDIVIDUAL STUDENT PDF REPORT
# ─────────────────────────────────────────────────────────────────────────────
def build_student_pdf(student_id: int) -> io.BytesIO:
    """
    Builds a comprehensive individual student attendance & risk dossier PDF.
    Includes:
      - App name & institution header
      - Student details (roll, name, ID, dept, year, section, semester)
      - Cumulative attendance summary
      - Subject-wise breakdown table
      - Risk category (High/Medium/Low) & ML shortage probability
      - Deterministic attendance projection & recovery math
      - Personalized actionable recommendations
      - Generation date & exact timestamp
    """
    student = db.session.get(Student, student_id)
    if not student:
        raise ValueError(f"Student ID {student_id} not found.")

    gen_time_str = datetime.now().strftime("%d %B %Y at %H:%M:%S")

    # Evaluate stats and prediction
    overall_stats = student.get_overall_stats()
    conducted = overall_stats["conducted"]
    attended  = overall_stats["attended"]
    absent    = overall_stats["absent"]
    pct       = overall_stats["percentage"]

    # Subject breakdown
    semester_subjects = Subject.query.filter_by(semester_id=student.semester_id).order_by(Subject.code).all()
    subject_rows = []
    for subj in semester_subjects:
        st_sub = student.get_subject_stats(subj.id)
        subject_rows.append({
            "code": subj.code,
            "name": subj.name,
            "conducted": st_sub["conducted"],
            "attended": st_sub["attended"],
            "absent": st_sub["absent"],
            "pct": st_sub["percentage"],
            "risk": st_sub.get("risk_level", "Low"),
        })

    # ML Prediction & Recovery
    ml_pred = predict_student_risk(student.id)
    risk_level = ml_pred.get("risk_category", "Low")
    risk_prob  = ml_pred.get("risk_probability", 0.0)

    # Recovery math
    remaining = max(0, 40 - conducted)
    recovery = calculate_attendance_recovery(
        total_conducted=conducted,
        classes_attended=attended,
        remaining_classes=remaining,
        target_threshold=75.0
    )

    # Document setup
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=1.5 * cm,
        rightMargin=1.5 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm
    )

    styles = getSampleStyleSheet()
    body_style = ParagraphStyle("Body", parent=styles["Normal"], fontSize=8.5, leading=11, textColor=SLATE_TEXT)
    bold_style = ParagraphStyle("Bold", parent=body_style, fontName="Helvetica-Bold")
    header_style = ParagraphStyle("THeader", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=8.5, leading=11, textColor=colors.white)

    story = _create_header_story(
        title="Student Attendance & Academic Risk Diagnostic Report",
        subtitle=f"Official Academic Dossier for {student.name} ({student.roll_number})",
        gen_timestamp=gen_time_str
    )

    # ── Section 1: Student Details & Overall Summary Table ────────────────────
    risk_c = COLOR_HIGH if risk_level == "High" else (COLOR_MEDIUM if risk_level == "Medium" else COLOR_LOW)
    status_label = "Critical Shortage" if pct < 60 else ("Shortage Warning" if pct < 75 else "Regular Standing")
    
    meta_table_data = [
        [
            Paragraph("<b>Student Name:</b>", body_style), Paragraph(student.name, bold_style),
            Paragraph("<b>Attendance Status:</b>", body_style), Paragraph(f"<font color='{risk_c}'><b>{pct:.1f}%</b> ({status_label})</font>", bold_style)
        ],
        [
            Paragraph("<b>Roll Number:</b>", body_style), Paragraph(student.roll_number, bold_style),
            Paragraph("<b>Total Conducted:</b>", body_style), Paragraph(f"{conducted} class sessions", body_style)
        ],
        [
            Paragraph("<b>Student ID:</b>", body_style), Paragraph(student.student_id, body_style),
            Paragraph("<b>Attended / Absent:</b>", body_style), Paragraph(f"{attended} attended &bull; {absent} absent", body_style)
        ],
        [
            Paragraph("<b>Department:</b>", body_style), Paragraph(student.department or "General", body_style),
            Paragraph("<b>ML Shortage Risk:</b>", body_style), Paragraph(f"<font color='{risk_c}'><b>{risk_level} Risk</b> ({risk_prob * 100:.1f}%)</font>", bold_style)
        ],
        [
            Paragraph("<b>Class / Year / Sec:</b>", body_style), Paragraph(f"Year {student.year} &bull; Section {student.section}", body_style),
            Paragraph("<b>Academic Term:</b>", body_style), Paragraph(student.semester.name if student.semester else "N/A", body_style)
        ],
    ]

    meta_table = Table(meta_table_data, colWidths=[3.2*cm, 5.5*cm, 3.8*cm, 5.5*cm])
    meta_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), SLATE_BG),
        ("BOX", (0, 0), (-1, -1), 0.75, SLATE_BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, SLATE_BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 0.4 * cm))

    # ── Section 2: Subject-Wise Attendance Breakdown Table ────────────────────
    story.append(Paragraph("<b>Subject-Wise Attendance Breakdown</b>", ParagraphStyle("SecTitle", parent=styles["Heading2"], fontSize=11, leading=14, textColor=NAVY_PRIMARY)))
    story.append(Spacer(1, 0.15 * cm))

    subj_table_data = [
        [
            Paragraph("Code", header_style),
            Paragraph("Subject Name", header_style),
            Paragraph("Conducted", header_style),
            Paragraph("Attended", header_style),
            Paragraph("Absent", header_style),
            Paragraph("Attendance %", header_style),
            Paragraph("Status", header_style),
        ]
    ]

    for row in subject_rows:
        r_c = COLOR_HIGH if row["pct"] < 60 else (COLOR_MEDIUM if row["pct"] < 75 else COLOR_LOW)
        subj_table_data.append([
            Paragraph(f"<b>{row['code']}</b>", body_style),
            Paragraph(row["name"], body_style),
            Paragraph(str(row["conducted"]), body_style),
            Paragraph(str(row["attended"]), body_style),
            Paragraph(str(row["absent"]), body_style),
            Paragraph(f"<font color='{r_c}'><b>{row['pct']:.1f}%</b></font>", body_style),
            Paragraph(f"<font color='{r_c}'>{row['risk']}</font>", body_style),
        ])

    subj_table = Table(subj_table_data, colWidths=[2.2*cm, 6.2*cm, 2.0*cm, 2.0*cm, 1.8*cm, 2.3*cm, 2.5*cm])
    subj_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY_PRIMARY),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, SLATE_BG]),
        ("GRID", (0, 0), (-1, -1), 0.5, SLATE_BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(subj_table)
    story.append(Spacer(1, 0.4 * cm))

    # ── Section 3: Deterministic Projections & Recovery Math ──────────────────
    story.append(Paragraph("<b>Deterministic Attendance Projections &amp; Target Recovery Math</b>", ParagraphStyle("SecTitle", parent=styles["Heading2"], fontSize=11, leading=14, textColor=NAVY_PRIMARY)))
    story.append(Spacer(1, 0.15 * cm))

    proj_text_1 = (
        f"<b>Target Threshold:</b> 75.0% &nbsp;&bull;&nbsp; "
        f"<b>Consecutive Classes Needed to Reach 75%:</b> <b>{recovery['classes_needed_for_target']} sessions</b> &nbsp;&bull;&nbsp; "
        f"<b>Safe Misses Buffer:</b> {recovery['safe_skips_remaining']} sessions"
    )
    proj_text_2 = (
        f"<b>Max Possible Final Attendance (100% Future Attendance):</b> <b>{recovery['max_possible_percentage']:.1f}%</b> &nbsp;&bull;&nbsp; "
        f"<b>Mathematical Recovery Status:</b> {'Feasible' if recovery['is_recoverable'] else 'CRITICAL (Mathematically Impossible without condonation)'}"
    )

    proj_data = [
        [Paragraph(proj_text_1, body_style)],
        [Paragraph(proj_text_2, body_style)],
    ]
    proj_table = Table(proj_data, colWidths=[19.0*cm])
    proj_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f0fdf4") if recovery['is_recoverable'] else colors.HexColor("#fef2f2")),
        ("BOX", (0, 0), (-1, -1), 1, COLOR_LOW if recovery['is_recoverable'] else COLOR_HIGH),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(proj_table)
    story.append(Spacer(1, 0.4 * cm))

    # ── Section 4: Personalized Actionable Recommendations ───────────────────
    story.append(Paragraph("<b>Personalized Improvement Recommendations &amp; Guidance</b>", ParagraphStyle("SecTitle", parent=styles["Heading2"], fontSize=11, leading=14, textColor=NAVY_PRIMARY)))
    story.append(Spacer(1, 0.15 * cm))

    tips = ml_pred.get("recommendations", [])
    if not tips:
        tips = generate_recommendations(
            features={
                "total_classes_so_far": conducted,
                "classes_attended": attended,
                "current_percentage": pct,
                "remaining_classes": remaining,
            },
            risk_level=risk_level,
            risk_probability=risk_prob
        )

    rec_items = []
    for tip in tips:
        rec_items.append([Paragraph(f"&bull; {tip}", body_style)])

    rec_table = Table(rec_items, colWidths=[19.0*cm])
    rec_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), SLATE_BG),
        ("BOX", (0, 0), (-1, -1), 0.5, SLATE_BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(rec_table)
    story.append(Spacer(1, 0.4 * cm))

    # ── Section 5: Faculty Advisory Disclaimer ────────────────────────────────
    dep_model, dep_ver = get_deployed_model_meta()
    disclaimer_text = (
        f"<b>Institutional Advisory:</b> This academic risk evaluation is probabilistically inferred using the AttendAI "
        f"{dep_model} classifier (v{dep_ver}). It is intended solely as an early-warning guide for academic mentors and faculty. "
        f"Official disciplinary or condonation actions require verified review by the Department Head."
    )
    story.append(Paragraph(disclaimer_text, ParagraphStyle("Discl", parent=styles["Normal"], fontSize=7.5, leading=10, textColor=SLATE_MUTED)))

    doc.build(story, canvasmaker=NumberedCanvas)
    buffer.seek(0)
    return buffer


# ─────────────────────────────────────────────────────────────────────────────
# 2. DEPARTMENT-WISE PDF REPORT
# ─────────────────────────────────────────────────────────────────────────────
def build_department_pdf(department: str, semester_id: Optional[int] = None) -> io.BytesIO:
    """Builds a summary and student attendance roster for an entire department."""
    gen_time_str = datetime.now().strftime("%d %B %Y at %H:%M:%S")

    query = Student.query.filter(Student.department == department, Student.is_active == True)
    if semester_id:
        query = query.filter(Student.semester_id == semester_id)
    students = query.order_by(Student.roll_number).all()

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=1.5*cm, rightMargin=1.5*cm, topMargin=1.5*cm, bottomMargin=1.5*cm)
    styles = getSampleStyleSheet()

    body_style = ParagraphStyle("Body", parent=styles["Normal"], fontSize=8, leading=10, textColor=SLATE_TEXT)
    h_style = ParagraphStyle("H", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=8.5, leading=11, textColor=colors.white)

    story = _create_header_story(
        title="Department Academic Attendance Report",
        subtitle=f"Department: {department} &nbsp;&bull;&nbsp; Total Students: {len(students)}",
        gen_timestamp=gen_time_str
    )

    # Department Summary Metrics
    total_st = len(students)
    high_c = 0
    med_c  = 0
    low_c  = 0
    att_sum = 0.0

    student_rows = []
    for st in students:
        stat = st.get_overall_stats()
        pct = stat["percentage"]
        att_sum += pct
        pred = st.latest_prediction()
        risk = pred.risk_level if pred else ("High" if pct < 60 else ("Medium" if pct < 75 else "Low"))
        if risk == "High": high_c += 1
        elif risk == "Medium": med_c += 1
        else: low_c += 1

        student_rows.append({
            "roll": st.roll_number,
            "name": st.name,
            "year_sec": f"Yr {st.year}-{st.section}",
            "conducted": stat["conducted"],
            "attended": stat["attended"],
            "pct": pct,
            "risk": risk,
        })

    avg_dept_att = round(att_sum / total_st, 1) if total_st > 0 else 0.0

    sum_card_data = [[
        Paragraph(f"<b>Total Enrolled:</b> {total_st}", body_style),
        Paragraph(f"<b>Dept Average:</b> {avg_dept_att}%", body_style),
        Paragraph(f"<b>High Risk:</b> <font color='red'><b>{high_c}</b></font>", body_style),
        Paragraph(f"<b>Medium Risk:</b> <font color='orange'><b>{med_c}</b></font>", body_style),
        Paragraph(f"<b>Low Risk:</b> <font color='green'><b>{low_c}</b></font>", body_style),
    ]]
    sum_t = Table(sum_card_data, colWidths=[3.8*cm, 3.8*cm, 3.8*cm, 3.8*cm, 3.8*cm])
    sum_t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), SLATE_BG),
        ("BOX", (0, 0), (-1, -1), 0.5, SLATE_BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(sum_t)
    story.append(Spacer(1, 0.4*cm))

    # Table
    t_data = [[
        Paragraph("Roll No", h_style),
        Paragraph("Student Name", h_style),
        Paragraph("Class", h_style),
        Paragraph("Conducted", h_style),
        Paragraph("Attended", h_style),
        Paragraph("Overall %", h_style),
        Paragraph("Risk Tier", h_style),
    ]]

    for r in student_rows:
        rc = COLOR_HIGH if r["risk"] == "High" else (COLOR_MEDIUM if r["risk"] == "Medium" else COLOR_LOW)
        t_data.append([
            Paragraph(f"<b>{r['roll']}</b>", body_style),
            Paragraph(r["name"], body_style),
            Paragraph(r["year_sec"], body_style),
            Paragraph(str(r["conducted"]), body_style),
            Paragraph(str(r["attended"]), body_style),
            Paragraph(f"<font color='{rc}'><b>{r['pct']:.1f}%</b></font>", body_style),
            Paragraph(f"<font color='{rc}'><b>{r['risk']}</b></font>", body_style),
        ])

    st_table = Table(t_data, colWidths=[2.8*cm, 6.2*cm, 2.5*cm, 2.0*cm, 2.0*cm, 2.0*cm, 2.0*cm])
    st_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY_PRIMARY),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, SLATE_BG]),
        ("GRID", (0, 0), (-1, -1), 0.5, SLATE_BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(st_table)

    doc.build(story, canvasmaker=NumberedCanvas)
    buffer.seek(0)
    return buffer


# ─────────────────────────────────────────────────────────────────────────────
# 3. SEMESTER-WISE MASTER PDF REPORT
# ─────────────────────────────────────────────────────────────────────────────
def build_semester_pdf(semester_id: int) -> io.BytesIO:
    """Builds a master semester attendance PDF report."""
    sem = db.session.get(Semester, semester_id)
    if not sem:
        raise ValueError(f"Semester {semester_id} not found.")

    gen_time_str = datetime.now().strftime("%d %B %Y at %H:%M:%S")
    students = Student.query.filter_by(semester_id=sem.id, is_active=True).order_by(Student.roll_number).all()

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=1.5*cm, rightMargin=1.5*cm, topMargin=1.5*cm, bottomMargin=1.5*cm)
    styles = getSampleStyleSheet()

    body_style = ParagraphStyle("Body", parent=styles["Normal"], fontSize=8, leading=10, textColor=SLATE_TEXT)
    h_style = ParagraphStyle("H", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=8.5, leading=11, textColor=colors.white)

    story = _create_header_story(
        title="Semester Master Attendance Statement",
        subtitle=f"Term: {sem.name} &nbsp;&bull;&nbsp; Enrolled Scholars: {len(students)}",
        gen_timestamp=gen_time_str
    )

    t_data = [[
        Paragraph("#", h_style),
        Paragraph("Roll No", h_style),
        Paragraph("Student Name", h_style),
        Paragraph("Department", h_style),
        Paragraph("Conducted", h_style),
        Paragraph("Attended", h_style),
        Paragraph("Attendance %", h_style),
        Paragraph("Risk Tier", h_style),
    ]]

    for i, st in enumerate(students, 1):
        st_stat = st.get_overall_stats()
        pct = st_stat["percentage"]
        pred = st.latest_prediction()
        risk = pred.risk_level if pred else ("High" if pct < 60 else ("Medium" if pct < 75 else "Low"))
        rc = COLOR_HIGH if risk == "High" else (COLOR_MEDIUM if risk == "Medium" else COLOR_LOW)

        t_data.append([
            Paragraph(str(i), body_style),
            Paragraph(f"<b>{st.roll_number}</b>", body_style),
            Paragraph(st.name, body_style),
            Paragraph(st.department or "—", body_style),
            Paragraph(str(st_stat["conducted"]), body_style),
            Paragraph(str(st_stat["attended"]), body_style),
            Paragraph(f"<font color='{rc}'><b>{pct:.1f}%</b></font>", body_style),
            Paragraph(f"<font color='{rc}'><b>{risk}</b></font>", body_style),
        ])

    table = Table(t_data, colWidths=[1.0*cm, 2.8*cm, 5.2*cm, 3.5*cm, 2.0*cm, 2.0*cm, 2.2*cm, 2.0*cm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY_PRIMARY),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, SLATE_BG]),
        ("GRID", (0, 0), (-1, -1), 0.5, SLATE_BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(table)

    doc.build(story, canvasmaker=NumberedCanvas)
    buffer.seek(0)
    return buffer


# ─────────────────────────────────────────────────────────────────────────────
# 4. SUBJECT-WISE PDF REPORT
# ─────────────────────────────────────────────────────────────────────────────
def build_subject_pdf(subject_id: int) -> io.BytesIO:
    """Builds a course-specific attendance audit report."""
    subj = db.session.get(Subject, subject_id)
    if not subj:
        raise ValueError(f"Subject {subject_id} not found.")

    gen_time_str = datetime.now().strftime("%d %B %Y at %H:%M:%S")

    # Get all students enrolled in this subject or in this semester
    students = subj.enrolled_students().all()
    if not students and subj.semester_id:
        students = Student.query.filter_by(semester_id=subj.semester_id, is_active=True).all()

    conducted = subj.classes_conducted()

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=1.5*cm, rightMargin=1.5*cm, topMargin=1.5*cm, bottomMargin=1.5*cm)
    styles = getSampleStyleSheet()

    body_style = ParagraphStyle("Body", parent=styles["Normal"], fontSize=8, leading=10, textColor=SLATE_TEXT)
    h_style = ParagraphStyle("H", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=8.5, leading=11, textColor=colors.white)

    story = _create_header_story(
        title=f"Course Attendance Audit: {subj.code}",
        subtitle=f"Course: {subj.name} &nbsp;&bull;&nbsp; Instructor: {subj.faculty.name if subj.faculty else 'Department'} &nbsp;&bull;&nbsp; Sessions Conducted: {conducted}",
        gen_timestamp=gen_time_str
    )

    t_data = [[
        Paragraph("#", h_style),
        Paragraph("Roll No", h_style),
        Paragraph("Student Name", h_style),
        Paragraph("Department", h_style),
        Paragraph("Attended", h_style),
        Paragraph("Absent", h_style),
        Paragraph("Subject %", h_style),
        Paragraph("Course Status", h_style),
    ]]

    for i, st in enumerate(students, 1):
        stat = st.get_subject_stats(subj.id)
        pct = stat["percentage"]
        rc = COLOR_HIGH if pct < 60 else (COLOR_MEDIUM if pct < 75 else COLOR_LOW)

        t_data.append([
            Paragraph(str(i), body_style),
            Paragraph(f"<b>{st.roll_number}</b>", body_style),
            Paragraph(st.name, body_style),
            Paragraph(st.department or "—", body_style),
            Paragraph(str(stat["attended"]), body_style),
            Paragraph(str(stat["absent"]), body_style),
            Paragraph(f"<font color='{rc}'><b>{pct:.1f}%</b></font>", body_style),
            Paragraph(f"<font color='{rc}'>{stat.get('risk_level', 'Low')}</font>", body_style),
        ])

    table = Table(t_data, colWidths=[1.0*cm, 2.8*cm, 5.5*cm, 3.5*cm, 2.0*cm, 2.0*cm, 2.2*cm, 2.5*cm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY_PRIMARY),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, SLATE_BG]),
        ("GRID", (0, 0), (-1, -1), 0.5, SLATE_BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(table)

    doc.build(story, canvasmaker=NumberedCanvas)
    buffer.seek(0)
    return buffer


# ─────────────────────────────────────────────────────────────────────────────
# 5. HIGH-RISK STUDENTS AUDIT PDF REPORT
# ─────────────────────────────────────────────────────────────────────────────
def build_high_risk_pdf(semester_id: Optional[int] = None) -> io.BytesIO:
    """Builds a targeted High-Risk shortage audit and intervention tracking report."""
    gen_time_str = datetime.now().strftime("%d %B %Y at %H:%M:%S")

    active_sem = db.session.get(Semester, semester_id) if semester_id else Semester.query.filter_by(is_active=True).first()

    query = Student.query.filter_by(is_active=True)
    if active_sem:
        query = query.filter_by(semester_id=active_sem.id)
    students = query.all()

    high_risk_students = []
    for st in students:
        stat = st.get_overall_stats()
        pred = st.latest_prediction()
        prob = pred.risk_probability if pred else (0.85 if stat["percentage"] < 60 else 0.50)
        risk = pred.risk_level if pred else ("High" if stat["percentage"] < 60 else "Medium")
        
        if risk == "High" or stat["percentage"] < 60.0 or prob >= 0.65:
            # Calculate recovery needed
            needed = max(0, int(3 * stat["conducted"] - 4 * stat["attended"]))
            latest_intv = st.interventions.order_by(Intervention.created_at.desc()).first()
            high_risk_students.append({
                "student": st,
                "pct": stat["percentage"],
                "conducted": stat["conducted"],
                "attended": stat["attended"],
                "prob": prob,
                "needed": needed,
                "contacted": "Yes" if latest_intv and latest_intv.student_contacted else "Pending",
                "explanation": (latest_intv.student_explanation[:40] + "...") if latest_intv and latest_intv.student_explanation else "None recorded",
            })

    high_risk_students.sort(key=lambda x: x["pct"])  # lowest attendance first

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=1.5*cm, rightMargin=1.5*cm, topMargin=1.5*cm, bottomMargin=1.5*cm)
    styles = getSampleStyleSheet()

    body_style = ParagraphStyle("Body", parent=styles["Normal"], fontSize=8, leading=10, textColor=SLATE_TEXT)
    h_style = ParagraphStyle("H", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=8.5, leading=11, textColor=colors.white)

    story = _create_header_story(
        title="High-Risk Student Shortage & Intervention Audit",
        subtitle=f"Criteria: Shortage Probability &ge; 65% or Attendance &lt; 60% &nbsp;&bull;&nbsp; Identified: {len(high_risk_students)} Scholars",
        gen_timestamp=gen_time_str
    )

    t_data = [[
        Paragraph("Roll No", h_style),
        Paragraph("Student Name", h_style),
        Paragraph("Dept", h_style),
        Paragraph("Attended", h_style),
        Paragraph("Current %", h_style),
        Paragraph("ML Prob", h_style),
        Paragraph("Classes Req", h_style),
        Paragraph("Contacted", h_style),
        Paragraph("Latest Explanation", h_style),
    ]]

    for r in high_risk_students:
        t_data.append([
            Paragraph(f"<b>{r['student'].roll_number}</b>", body_style),
            Paragraph(r["student"].name, body_style),
            Paragraph(r["student"].department or "—", body_style),
            Paragraph(f"{r['attended']}/{r['conducted']}", body_style),
            Paragraph(f"<font color='red'><b>{r['pct']:.1f}%</b></font>", body_style),
            Paragraph(f"<font color='red'><b>{r['prob']*100:.1f}%</b></font>", body_style),
            Paragraph(f"{r['needed']} classes", body_style),
            Paragraph(r["contacted"], body_style),
            Paragraph(r["explanation"], body_style),
        ])

    table = Table(t_data, colWidths=[2.2*cm, 4.0*cm, 2.0*cm, 1.8*cm, 1.8*cm, 1.8*cm, 1.8*cm, 1.6*cm, 4.0*cm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY_PRIMARY),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, SLATE_BG]),
        ("GRID", (0, 0), (-1, -1), 0.5, SLATE_BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(table)

    doc.build(story, canvasmaker=NumberedCanvas)
    buffer.seek(0)
    return buffer


# ─────────────────────────────────────────────────────────────────────────────
# 6. ML PREDICTIONS AUDIT PDF REPORT
# ─────────────────────────────────────────────────────────────────────────────
def build_ml_predictions_pdf(semester_id: Optional[int] = None) -> io.BytesIO:
    """Builds an audit report of all ML predictions made by the model."""
    gen_time_str = datetime.now().strftime("%d %B %Y at %H:%M:%S")

    query = PredictionHistory.query
    if semester_id:
        query = query.filter_by(semester_id=semester_id)
    predictions = query.order_by(PredictionHistory.predicted_at.desc()).all()

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=1.5*cm, rightMargin=1.5*cm, topMargin=1.5*cm, bottomMargin=1.5*cm)
    styles = getSampleStyleSheet()

    body_style = ParagraphStyle("Body", parent=styles["Normal"], fontSize=8, leading=10, textColor=SLATE_TEXT)
    h_style = ParagraphStyle("H", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=8.5, leading=11, textColor=colors.white)

    dep_model, dep_ver = get_deployed_model_meta()
    story = _create_header_story(
        title="Machine Learning Attendance Risk Model Audit",
        subtitle=f"Model: {dep_model} (v{dep_ver}) &nbsp;&bull;&nbsp; Total Snapshot Records: {len(predictions)}",
        gen_timestamp=gen_time_str
    )

    t_data = [[
        Paragraph("Timestamp", h_style),
        Paragraph("Roll No", h_style),
        Paragraph("Student Name", h_style),
        Paragraph("Attendance %", h_style),
        Paragraph("Risk Probability", h_style),
        Paragraph("Risk Tier", h_style),
        Paragraph("Projected %", h_style),
        Paragraph("Version", h_style),
    ]]

    for p in predictions:
        rc = COLOR_HIGH if p.risk_level == "High" else (COLOR_MEDIUM if p.risk_level == "Medium" else COLOR_LOW)
        t_data.append([
            Paragraph(p.predicted_at.strftime("%Y-%m-%d %H:%M"), body_style),
            Paragraph(p.student.roll_number, body_style),
            Paragraph(p.student.name, body_style),
            Paragraph(f"{p.attendance_percentage:.1f}%", body_style),
            Paragraph(f"<font color='{rc}'><b>{p.risk_probability*100:.1f}%</b></font>", body_style),
            Paragraph(f"<font color='{rc}'><b>{p.risk_level}</b></font>", body_style),
            Paragraph(f"{p.predicted_final_percentage:.1f}%" if p.predicted_final_percentage else "—", body_style),
            Paragraph(p.model_version or "2.0.0", body_style),
        ])

    table = Table(t_data, colWidths=[2.6*cm, 2.5*cm, 4.5*cm, 2.2*cm, 2.5*cm, 2.0*cm, 2.0*cm, 1.7*cm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY_PRIMARY),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, SLATE_BG]),
        ("GRID", (0, 0), (-1, -1), 0.5, SLATE_BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(table)

    doc.build(story, canvasmaker=NumberedCanvas)
    buffer.seek(0)
    return buffer
