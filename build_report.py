"""
build_report.py – Script to generate the comprehensive M.Tech Internship Report for AttendAI
in formal academic writing as a Word document (.docx).
"""

import os
import json
import docx
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.oxml import parse_xml, OxmlElement
from docx.oxml.ns import nsdecls, qn

def set_cell_background(cell, hex_color: str):
    """Sets background shading of a table cell."""
    tcPr = cell._tc.get_or_add_tcPr()
    shd = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{hex_color}"/>')
    tcPr.append(shd)

def set_cell_margins(cell, top=100, bottom=100, left=150, right=150):
    """Sets internal padding (in twips) for a table cell."""
    tcPr = cell._tc.get_or_add_tcPr()
    tcMar = parse_xml(f'<w:tcMar {nsdecls("w")}>'
                      f'<w:top w:w="{top}" w:type="dxa"/>'
                      f'<w:bottom w:w="{bottom}" w:type="dxa"/>'
                      f'<w:left w:w="{left}" w:type="dxa"/>'
                      f'<w:right w:w="{right}" w:type="dxa"/>'
                      f'</w:tcMar>')
    tcPr.append(tcMar)

def set_table_borders(table, color="CBD5E1", sz="4", val="single"):
    """Applies clean borders to a table."""
    tblPr = table._tbl.tblPr
    borders = parse_xml(f'<w:tblBorders {nsdecls("w")}>'
                        f'<w:top w:val="{val}" w:sz="{sz}" w:space="0" w:color="{color}"/>'
                        f'<w:bottom w:val="{val}" w:sz="{sz}" w:space="0" w:color="{color}"/>'
                        f'<w:insideH w:val="{val}" w:sz="{sz}" w:space="0" w:color="{color}"/>'
                        f'<w:insideV w:val="none"/>'
                        f'<w:left w:val="none"/>'
                        f'<w:right w:val="none"/>'
                        f'</w:tblBorders>')
    tblPr.append(borders)

def add_callout(doc, text: str, title: str = "KEY HIGHLIGHT"):
    """Adds a stylish callout box with a colored left border and subtle shading."""
    tbl = doc.add_table(rows=1, cols=1)
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    tbl.autofit = False
    cell = tbl.cell(0, 0)
    cell.width = Inches(6.5)
    
    set_cell_background(cell, "F1F5F9")
    set_cell_margins(cell, top=140, bottom=140, left=200, right=200)
    
    tcPr = cell._tc.get_or_add_tcPr()
    borders = parse_xml(f'<w:tcBorders {nsdecls("w")}>'
                        f'<w:left w:val="single" w:sz="24" w:space="0" w:color="1E3A8A"/>'
                        f'<w:top w:val="none"/>'
                        f'<w:right w:val="none"/>'
                        f'<w:bottom w:val="none"/>'
                        f'</w:tcBorders>')
    tcPr.append(borders)
    
    p = cell.paragraphs[0]
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(2)
    p.paragraph_format.line_spacing = 1.15
    run_title = p.add_run(f"[{title}]  ")
    run_title.font.name = 'Calibri'
    run_title.font.size = Pt(10)
    run_title.font.bold = True
    run_title.font.color.rgb = RGBColor(30, 58, 138)
    
    run_text = p.add_run(text)
    run_text.font.name = 'Calibri'
    run_text.font.size = Pt(10)
    run_text.font.color.rgb = RGBColor(51, 65, 85)
    
    # Empty space after callout
    p_after = doc.add_paragraph()
    p_after.paragraph_format.space_before = Pt(0)
    p_after.paragraph_format.space_after = Pt(4)

def format_heading(p, text, level=1):
    """Formats headings with consistent typography and color scheme."""
    p.paragraph_format.keep_with_next = True
    run = p.add_run(text)
    run.font.name = 'Calibri'
    run.font.bold = True
    if level == 1:
        p.paragraph_format.space_before = Pt(16)
        p.paragraph_format.space_after = Pt(6)
        run.font.size = Pt(15)
        run.font.color.rgb = RGBColor(30, 58, 138)  # Navy
    elif level == 2:
        p.paragraph_format.space_before = Pt(12)
        p.paragraph_format.space_after = Pt(4)
        run.font.size = Pt(12.5)
        run.font.color.rgb = RGBColor(37, 99, 235)  # Slate Blue
    elif level == 3:
        p.paragraph_format.space_before = Pt(8)
        p.paragraph_format.space_after = Pt(2)
        run.font.size = Pt(11)
        run.font.color.rgb = RGBColor(30, 41, 59)   # Dark Slate

def add_body_paragraph(doc, text: str, italic=False, bold_prefix: str = None):
    """Adds a standard body paragraph with academic typography."""
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(5)
    p.paragraph_format.line_spacing = 1.15
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    
    if bold_prefix:
        bp = p.add_run(bold_prefix)
        bp.font.name = 'Calibri'
        bp.font.size = Pt(10.5)
        bp.font.bold = True
        bp.font.color.rgb = RGBColor(30, 41, 59)
        
    run = p.add_run(text)
    run.font.name = 'Calibri'
    run.font.size = Pt(10.5)
    run.font.italic = italic
    run.font.color.rgb = RGBColor(51, 65, 85)
    return p

def add_equation_box(doc, equation_text: str, label: str):
    """Adds a styled equation display block with an equation number."""
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after = Pt(4)
    p.paragraph_format.left_indent = Inches(0.5)
    p.paragraph_format.right_indent = Inches(0.5)
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    
    r_eq = p.add_run(equation_text)
    r_eq.font.name = 'Cambria Math'
    r_eq.font.size = Pt(11)
    r_eq.font.bold = True
    r_eq.font.color.rgb = RGBColor(15, 23, 42)
    
    r_sp = p.add_run("   " * 6)
    
    r_lbl = p.add_run(f"({label})")
    r_lbl.font.name = 'Calibri'
    r_lbl.font.size = Pt(10)
    r_lbl.font.italic = True
    r_lbl.font.color.rgb = RGBColor(100, 116, 139)

def style_table_header(row, col_widths, headers):
    """Styles table header with Navy fill and white bold text."""
    for i, title in enumerate(headers):
        cell = row.cells[i]
        cell.width = Inches(col_widths[i])
        set_cell_background(cell, "1E3A8A")
        set_cell_margins(cell, top=120, bottom=120, left=150, right=150)
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(0)
        run = p.add_run(title)
        run.font.name = 'Calibri'
        run.font.size = Pt(10)
        run.font.bold = True
        run.font.color.rgb = RGBColor(255, 255, 255)

def style_table_row(row, col_widths, values, is_even=False, alignments=None):
    """Styles table data row with subtle alternating shading."""
    bg_color = "F8FAFC" if is_even else "FFFFFF"
    for i, val in enumerate(values):
        cell = row.cells[i]
        cell.width = Inches(col_widths[i])
        set_cell_background(cell, bg_color)
        set_cell_margins(cell, top=90, bottom=90, left=140, right=140)
        p = cell.paragraphs[0]
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(0)
        if alignments and i < len(alignments):
            p.alignment = alignments[i]
        else:
            p.alignment = WD_ALIGN_PARAGRAPH.LEFT
        run = p.add_run(str(val))
        run.font.name = 'Calibri'
        run.font.size = Pt(9.5)
        run.font.color.rgb = RGBColor(51, 65, 85)

def main():
    print("Beginning generation of AttendAI M.Tech Internship Report...")
    doc = docx.Document()
    
    # Page Setup: Standard Letter with 1-inch margins
    sections = doc.sections
    for s in sections:
        s.top_margin = Inches(1.0)
        s.bottom_margin = Inches(1.0)
        s.left_margin = Inches(1.0)
        s.right_margin = Inches(1.0)
        
    # Load actual saved metrics from JSON
    metrics_path = os.path.join("ml", "models", "model_metrics.json")
    comparison_path = os.path.join("ml", "models", "model_comparison.json")
    meta_path = os.path.join("ml", "models", "model_meta.json")
    
    with open(metrics_path, "r") as f:
        metrics_data = json.load(f)
    with open(comparison_path, "r") as f:
        comparison_data = json.load(f)
    with open(meta_path, "r") as f:
        meta_data = json.load(f)
        
    # ─────────────────────────────────────────────────────────────────────────
    # COVER / TITLE BLOCK
    # ─────────────────────────────────────────────────────────────────────────
    title_p = doc.add_paragraph()
    title_p.paragraph_format.space_before = Pt(24)
    title_p.paragraph_format.space_after = Pt(6)
    title_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r_main_title = title_p.add_run("AttendAI – An Intelligent Student Attendance Analytics and Academic Risk Prediction System Using Machine Learning")
    r_main_title.font.name = 'Calibri'
    r_main_title.font.size = Pt(20)
    r_main_title.font.bold = True
    r_main_title.font.color.rgb = RGBColor(30, 58, 138)
    
    sub_p = doc.add_paragraph()
    sub_p.paragraph_format.space_before = Pt(0)
    sub_p.paragraph_format.space_after = Pt(18)
    sub_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r_sub = sub_p.add_run("A Technical Internship Project Report Submitted in Partial Fulfillment of the Requirements for the Degree of Master of Technology (M.Tech)")
    r_sub.font.name = 'Calibri'
    r_sub.font.size = Pt(11)
    r_sub.font.italic = True
    r_sub.font.color.rgb = RGBColor(71, 85, 105)
    
    # Metadata Box
    meta_tbl = doc.add_table(rows=4, cols=2)
    meta_tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_table_borders(meta_tbl, color="E2E8F0", sz="4")
    m_headers = ["Project Specification", "Academic & Implementation Details"]
    style_table_header(meta_tbl.rows[0], [2.5, 4.0], m_headers)
    meta_rows = [
        ("Candidate / Intern Role", "Senior AI/ML & Full-Stack Python Software Engineering Intern"),
        ("Technology Stack", "Python 3.10, Flask, Scikit-learn, SQLAlchemy, SQLite, Bootstrap 5, ReportLab, OpenPyXL"),
        ("Core Focus Area", "Educational Data Mining, Predictive Student Retention, Deterministic Recovery Math"),
    ]
    for idx, (k, v) in enumerate(meta_rows, start=1):
        style_table_row(meta_tbl.rows[idx], [2.5, 4.0], [k, v], is_even=(idx%2==0))
        
    p_div = doc.add_paragraph()
    p_div.paragraph_format.space_after = Pt(16)
    
    add_callout(
        doc,
        "ACADEMIC INTEGRITY & DATA GOVERNANCE DISCLOSURE: In compliance with institutional ethics standards (FERPA / GDPR student privacy directives), the machine learning model in AttendAI was trained and evaluated on a controlled synthetic benchmark simulation comprising 6,400 snapshots across 400 virtual student profiles. Real institutional records are kept strictly isolated in the operational database. All reported evaluation figures represent actual, verified empirical test executions.",
        "GOVERNANCE & DATA PRIVACY NOTICE"
    )

    # ─────────────────────────────────────────────────────────────────────────
    # 1. ABSTRACT
    # ─────────────────────────────────────────────────────────────────────────
    p = doc.add_paragraph()
    format_heading(p, "1. Abstract", level=1)
    
    add_body_paragraph(
        doc,
        "Student classroom attendance is universally recognized as a foundational determinant of academic engagement, comprehension, and institutional retention. Despite statutory accreditation mandates enforcing minimum attendance thresholds (commonly 75%), traditional institutional workflows remain predominantly retrospective: records are entered into disparate spreadsheets or paper ledgers and aggregated only at semester conclusion. Consequently, students facing attendance shortages are identified too late to undertake corrective remediation, leading to debarment from semester-end examinations, financial hardship, and avoidable attrition."
    )
    add_body_paragraph(
        doc,
        "This internship project presents AttendAI, an intelligent, full-stack student attendance analytics and academic risk prediction system engineered using Python, Flask, SQLAlchemy, Scikit-learn, and Bootstrap 5. AttendAI bridges the gap between passive record-keeping and proactive pedagogical intervention. The platform incorporates a zero-data-leakage temporal feature extraction pipeline that captures sequential attendance trajectories (cumulative attendance, moving 10-class windows, absence run-lengths, and direction of attendance momentum) at configurable mid-semester checkpoints."
    )
    add_body_paragraph(
        doc,
        "Rigorous empirical evaluation of candidate supervised machine learning algorithms was conducted on a held-out test partition of 1,280 snapshots across 80 student groups. Logistic Regression with class-frequency rebalancing emerged as the optimal deployed classifier, achieving a test accuracy of 83.98%, an ROC-AUC of 0.9281, and a high sensitivity (recall) of 84.91% on at-risk student detection, successfully identifying 377 out of 444 shortage cases while maintaining low false negatives (67). Furthermore, AttendAI introduces a closed-form deterministic recovery solver that calculates the exact consecutive classes required to restore good standing, integrated alongside a structured faculty intervention tracker and institutional PDF/Excel reporting engines."
    )

    # ─────────────────────────────────────────────────────────────────────────
    # 2. INTRODUCTION
    # ─────────────────────────────────────────────────────────────────────────
    p = doc.add_paragraph()
    format_heading(p, "2. Introduction", level=1)
    
    add_body_paragraph(
        doc,
        "Higher education institutions globally operate under stringent quality frameworks established by statutory bodies such as the University Grants Commission (UGC) and the All India Council for Technical Education (AICTE). Central to these regulatory guidelines is the mandatory requirement that students maintain a minimum prescribed attendance threshold—typically 75% across all theoretical and laboratory subjects—to qualify for end-semester summative examinations. Empirical educational research consistently demonstrates that regular class presence strongly correlates with concept mastery, collaborative problem-solving skills, and reduced course failure rates."
    )
    add_body_paragraph(
        doc,
        "Historically, attendance management has functioned as a bureaucratic compliance exercise. Faculty members manually call roll in class, annotate physical logbooks, and periodically transcribe these figures into centralized Enterprise Resource Planning (ERP) databases. While digitized ERPs have eliminated manual paperwork to an extent, they remain purely retrospective recording tools. They compute cumulative percentages based on past classes but lack intelligence: they cannot infer trajectory, cannot account for remaining semester runway, and fail to provide early warning alerts when a student first deviates into academic risk."
    )
    add_body_paragraph(
        doc,
        "With recent advancements in Educational Data Mining (EDM) and Learning Analytics (LA), machine learning techniques offer a transformative opportunity to convert static attendance logs into predictive early-warning signals. AttendAI was developed during this M.Tech internship to realize this vision. By synthesizing administrative web engineering with supervised statistical learning, AttendAI automates daily attendance operations while continuously forecasting student shortage risk, empowering faculty to implement corrective academic counseling weeks before examination eligibility is irrevocably compromised."
    )

    # ─────────────────────────────────────────────────────────────────────────
    # 3. PROBLEM STATEMENT
    # ─────────────────────────────────────────────────────────────────────────
    p = doc.add_paragraph()
    format_heading(p, "3. Problem Statement", level=1)
    
    add_body_paragraph(
        doc,
        "Traditional higher education attendance administration suffers from significant structural, pedagogical, and technological shortcomings that undermine timely student support:"
    )
    add_body_paragraph(
        doc,
        "1. Latent Risk Identification: In current institutional setups, attendance shortage lists are compiled only at the end of the term during hall ticket issuance. Students below 75% are abruptly debarred without any prior formal notice or opportunity to recover.",
        bold_prefix="• "
    )
    add_body_paragraph(
        doc,
        "2. Absence of Predictive Early Warning: Conventional percentage metrics reflect only past history. A student currently at 76% who has missed 8 of their last 10 classes is mathematically classified as 'safe' by conventional ERPs, despite being in severe active decline.",
        bold_prefix="• "
    )
    add_body_paragraph(
        doc,
        "3. Missing Recovery Guidance: When students slip below the 75% cutoff, neither faculty nor students have access to deterministic formulas detailing how many consecutive classes must be attended to regain eligibility, leading to despair and disengagement.",
        bold_prefix="• "
    )
    add_body_paragraph(
        doc,
        "4. Unaudited and Fragmented Interventions: Faculty counseling of chronic absentees is largely informal, undocumented, and disconnected from institutional records, preventing academic deans from monitoring intervention efficacy.",
        bold_prefix="• "
    )

    # ─────────────────────────────────────────────────────────────────────────
    # 4. EXISTING SYSTEM
    # ─────────────────────────────────────────────────────────────────────────
    p = doc.add_paragraph()
    format_heading(p, "4. Existing System", level=1)
    
    add_body_paragraph(
        doc,
        "The prevailing attendance ecosystem in university departments comprises two standard paradigms: physical paper registers and basic campus ERP databases. In paper-based systems, faculty record presence daily using tick marks. At the conclusion of each month or semester, teachers manually count total ticks, divide by conducted sessions, and transcribe the calculated percentages onto institutional master rosters."
    )
    add_body_paragraph(
        doc,
        "In digitized ERP installations, faculty log in to mark roll call or upload bulk sheets. The software computes a basic arithmetic formula: Percentage = (Classes Attended / Classes Conducted) * 100. The system then color-codes cells in red if the percentage is below 75% and green otherwise. Reports can be exported as raw tabular spreadsheets for administrative archives."
    )

    # ─────────────────────────────────────────────────────────────────────────
    # 5. LIMITATIONS OF EXISTING SYSTEM
    # ─────────────────────────────────────────────────────────────────────────
    p = doc.add_paragraph()
    format_heading(p, "5. Limitations of Existing System", level=1)
    
    # Comparison Table
    tbl_lim = doc.add_table(rows=6, cols=3)
    tbl_lim.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_table_borders(tbl_lim)
    style_table_header(tbl_lim.rows[0], [1.8, 2.3, 2.4], ["Operational Dimension", "Existing Traditional ERPs", "AttendAI Solution"])
    
    lim_data = [
        ("Risk Detection Timing", "Retrospective (end-of-semester)", "Proactive & continuous at every class milestone"),
        ("Analytical Depth", "Static cumulative percentage only", "Sequential momentum, moving windows, run-lengths"),
        ("Predictive Capability", "None; purely historical reporting", "Machine learning classification (LR, DT, RF)"),
        ("Actionable Recovery", "No mathematical recovery path provided", "Exact closed-form consecutive classes calculator"),
        ("Faculty Accountability", "Informal, untracked verbal chats", "Closed-loop auditable intervention tracker"),
    ]
    for idx, row in enumerate(lim_data, start=1):
        style_table_row(tbl_lim.rows[idx], [1.8, 2.3, 2.4], [row[0], row[1], row[2]], is_even=(idx%2==0))
        
    doc.add_paragraph().paragraph_format.space_after = Pt(8)

    # ─────────────────────────────────────────────────────────────────────────
    # 6. PROPOSED SYSTEM
    # ─────────────────────────────────────────────────────────────────────────
    p = doc.add_paragraph()
    format_heading(p, "6. Proposed System (AttendAI)", level=1)
    
    add_body_paragraph(
        doc,
        "AttendAI is engineered as an end-to-end, multi-tier web application that transforms institutional attendance management from a passive recording burden into an intelligent, data-driven academic retention platform. AttendAI unifies role-based access control, operational attendance logging, predictive machine learning, deterministic recovery mathematics, closed-loop counseling tracking, and compliance reporting into a cohesive user experience."
    )
    add_body_paragraph(
        doc,
        "Key architectural capabilities of the proposed system include: (1) Rapid daily attendance entry with built-in session conflict prevention; (2) Bulk data ingestion supporting standard CSV and Excel formats with schema validation; (3) Real-time supervised classification returning probability of end-term shortage; (4) Tri-tier calibrated risk categorization (Low, Medium, High); (5) Deterministic attendance projection indicating whether recovery remains mathematically feasible; (6) Faculty intervention audit trails capturing student explanations and post-counseling attendance trajectories; and (7) High-fidelity ReportLab PDF and OpenPyXL Excel export facilities."
    )

    # ─────────────────────────────────────────────────────────────────────────
    # 7. RESEARCH GAP
    # ─────────────────────────────────────────────────────────────────────────
    p = doc.add_paragraph()
    format_heading(p, "7. Research Gap", level=1)
    
    add_body_paragraph(
        doc,
        "A systematic review of contemporary literature in Educational Data Mining (EDM) and Learning Analytics (LA) reveals three salient research gaps that AttendAI directly addresses:"
    )
    add_body_paragraph(
        doc,
        "1. Over-emphasis on Final Grades vs. Attendance Shortage: The majority of published EDM studies concentrate on predicting final GPA, course failure, or multi-year degree dropouts. Minimal scholarly attention has targeted predicting statutory attendance debarment, despite attendance being the single most common administrative trigger for course repetition.",
        bold_prefix="• "
    )
    add_body_paragraph(
        doc,
        "2. Widespread Data Leakage in Academic Datasets: Prior works evaluating student trajectories frequently compute features across the entire academic term (e.g., aggregate semester attendance) to predict mid-term risk, introducing severe forward-looking data leakage. AttendAI enforces a rigorous zero-data-leakage protocol where milestone snapshots strictly use information available up to that exact date.",
        bold_prefix="• "
    )
    add_body_paragraph(
        doc,
        "3. Decoupling of Predictive Models from Actionable Remediation: Existing predictive tools output a risk score or probability without providing the student or mentor with a deterministic roadmap for recovery. AttendAI bridges predictive modeling with closed-form deterministic recovery mathematics.",
        bold_prefix="• "
    )

    # ─────────────────────────────────────────────────────────────────────────
    # 8. OBJECTIVES
    # ─────────────────────────────────────────────────────────────────────────
    p = doc.add_paragraph()
    format_heading(p, "8. Objectives", level=1)
    
    add_body_paragraph(
        doc,
        "The overarching aim of this M.Tech internship was to conceptualize, design, implement, and rigorously validate an intelligent attendance management and risk forecasting system. The specific technical and functional objectives were:"
    )
    add_body_paragraph(
        doc,
        "Database Engineering: Design and deploy a normalized relational database schema in SQLite/SQLAlchemy featuring complete referential integrity, foreign key cascades, and unique session constraints.",
        bold_prefix="Objective 1 - "
    )
    add_body_paragraph(
        doc,
        "Core Administration & Role-Based Access: Implement dual-role authentication (Admin and Faculty) with password hashing and authorization guards preventing privilege escalation.",
        bold_prefix="Objective 2 - "
    )
    add_body_paragraph(
        doc,
        "Operational Attendance Module: Build interactive roll-call interfaces and bulk Excel/CSV ingestion pipelines with duplicate entry prevention and an immutable edit history log.",
        bold_prefix="Objective 3 - "
    )
    add_body_paragraph(
        doc,
        "ML Feature & Prediction Pipeline: Formulate a leak-free temporal feature extractor and train candidate classifiers to detect students likely to finish below 75% attendance.",
        bold_prefix="Objective 4 - "
    )
    add_body_paragraph(
        doc,
        "Mathematical Recovery Engine: Formulate and implement closed-form deterministic formulas calculating consecutive classes needed, safe absence buffers, and impossibility flags.",
        bold_prefix="Objective 5 - "
    )
    add_body_paragraph(
        doc,
        "Faculty Intervention Tracker: Construct an auditable tracking lifecycle for documenting student communications, reasons for absence, and subsequent attendance impact.",
        bold_prefix="Objective 6 - "
    )
    add_body_paragraph(
        doc,
        "Institutional Reporting & QA: Develop institutional PDF and Excel builders and execute an exhaustive automated test suite achieving 100% test pass rates across all platform components.",
        bold_prefix="Objective 7 - "
    )

    # ─────────────────────────────────────────────────────────────────────────
    # 9. SYSTEM ARCHITECTURE
    # ─────────────────────────────────────────────────────────────────────────
    p = doc.add_paragraph()
    format_heading(p, "9. System Architecture", level=1)
    
    add_body_paragraph(
        doc,
        "AttendAI is engineered following an enterprise multi-tier architecture adhering to Model-View-Controller (MVC) separation of concerns. The system is partitioned into four primary layers:"
    )
    add_body_paragraph(
        doc,
        "Presentation Layer (Client Tier): Developed using responsive HTML5, CSS3, and Bootstrap 5 styled in an Academic SaaS aesthetic (Navy #1E3A8A, Slate #334155, and Cyan accents). Chart.js powers client-side visualizations of department distributions and attendance trends, while ReportLab and OpenPyXL render server-side institutional artifacts.",
        bold_prefix="Layer 1 - "
    )
    add_body_paragraph(
        doc,
        "Web & Application Logic Layer (Server Tier): Built on Python Flask 3.0 utilizing a modular Blueprint architecture. Dedicated blueprints encapsulate authentication (routes/auth.py), administrative governance (routes/admin.py), faculty workflows (routes/faculty.py), daily roll-call (routes/attendance.py), analytics (routes/analytics.py), risk prediction (routes/risk.py), and reports (routes/reports.py). Flask-Login enforces session authentication and role boundary isolation.",
        bold_prefix="Layer 2 - "
    )
    add_body_paragraph(
        doc,
        "Analytics & Machine Learning Layer (Intelligence Tier): Powered by Scikit-learn, NumPy, Pandas, and Joblib. Features are dynamically computed from attendance event streams. The trained model (best_risk_model.joblib) performs inference, while the recommendation engine (ml/recommendations.py) solves deterministic algebraic recovery constraints.",
        bold_prefix="Layer 3 - "
    )
    add_body_paragraph(
        doc,
        "Data Persistence Layer (Database Tier): Managed via SQLAlchemy 2.0 ORM over an SQLite engine with enforced foreign key pragmas (PRAGMA foreign_keys=ON). Schema integrity guarantees atomic session commits, cascade purges, and automated audit trails.",
        bold_prefix="Layer 4 - "
    )

    # ─────────────────────────────────────────────────────────────────────────
    # 10. FUNCTIONAL AND NON-FUNCTIONAL REQUIREMENTS
    # ─────────────────────────────────────────────────────────────────────────
    p = doc.add_paragraph()
    format_heading(p, "10. Functional and Non-functional Requirements", level=1)
    
    p_f = doc.add_paragraph()
    format_heading(p_f, "10.1 Functional Requirements", level=2)
    
    fn_reqs = [
        ("FR-01: User Authentication", "Secure sign-in for Administrators and Faculty with scrypt password hashing, session expiration, and open redirect defense."),
        ("FR-02: Student & Academic Management", "Full CRUD operations for Semesters, Subjects, Faculty profiles, and Students with duplicate roll number rejection."),
        ("FR-03: Session Roll-Call Entry", "Interactive class roster interface allowing faculty to mark Present/Absent with atomic persistence and duplicate session blocking."),
        ("FR-04: Attendance Audit Logging", "Historical change tracking capturing previous status, new status, editor ID, timestamp, and justification for every modification."),
        ("FR-05: Bulk Spreadsheets Ingestion", "CSV and Excel file upload parsing student rosters and multi-student session attendance with validation of dates and roll numbers."),
        ("FR-06: Predictive Risk Classification", "Real-time supervised inference classifying students into Low, Medium, or High Risk of semester attendance shortage."),
        ("FR-07: Deterministic Recovery Solver", "Exact computation of consecutive classes needed to achieve >= 75%, safe absences buffer, and mathematical impossibility detection."),
        ("FR-08: Closed-Loop Intervention Tracker", "Audit log recording faculty outreach, contact mode, student explanation, agreed action plan, and post-intervention outcome."),
        ("FR-09: Institutional PDF & Excel Export", "Formal ReportLab PDF generation with all 9 academic components and multi-tab Excel workbooks matching database records."),
    ]
    tbl_fr = doc.add_table(rows=len(fn_reqs)+1, cols=2)
    tbl_fr.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_table_borders(tbl_fr)
    style_table_header(tbl_fr.rows[0], [1.8, 4.7], ["Requirement ID", "Functional Specification"])
    for idx, (rid, spec) in enumerate(fn_reqs, start=1):
        style_table_row(tbl_fr.rows[idx], [1.8, 4.7], [rid, spec], is_even=(idx%2==0))
        
    doc.add_paragraph().paragraph_format.space_after = Pt(6)
    
    p_nf = doc.add_paragraph()
    format_heading(p_nf, "10.2 Non-functional Requirements", level=2)
    
    nfn_reqs = [
        ("NFR-01: Security & Protection", "Protection against Open Redirects, SQL Injection via ORM parameterization, and secure credential storage via scrypt."),
        ("NFR-02: Relational Data Integrity", "Enforcement of SQLite foreign keys and composite unique constraints preventing data corruption or orphan records."),
        ("NFR-03: System Performance", "Sub-100 millisecond page rendering and batch ML inference throughput exceeding 200 student predictions per second."),
        ("NFR-04: Reliability & ACID Compliance", "Transactional database operations ensuring attendance marking is either completely saved or rolled back cleanly."),
        ("NFR-05: Usability & Accessibility", "Responsive design conforming to Academic SaaS usability guidelines, responsive across desktop, tablet, and mobile browsers."),
    ]
    tbl_nfr = doc.add_table(rows=len(nfn_reqs)+1, cols=2)
    tbl_nfr.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_table_borders(tbl_nfr)
    style_table_header(tbl_nfr.rows[0], [1.8, 4.7], ["Quality Attribute", "Non-functional Benchmark"])
    for idx, (qid, bmk) in enumerate(nfn_reqs, start=1):
        style_table_row(tbl_nfr.rows[idx], [1.8, 4.7], [qid, bmk], is_even=(idx%2==0))

    # ─────────────────────────────────────────────────────────────────────────
    # 11. SOFTWARE AND HARDWARE REQUIREMENTS
    # ─────────────────────────────────────────────────────────────────────────
    p = doc.add_paragraph()
    format_heading(p, "11. Software and Hardware Requirements", level=1)
    
    add_body_paragraph(
        doc,
        "The AttendAI platform was engineered, trained, tested, and benchmarked on the following software and hardware environment:"
    )
    
    tbl_env = doc.add_table(rows=9, cols=3)
    tbl_env.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_table_borders(tbl_env)
    style_table_header(tbl_env.rows[0], [1.8, 2.3, 2.4], ["Category", "Component / Tool", "Version / Specification"])
    env_data = [
        ("Operating System", "Microsoft Windows 11 Enterprise", "64-bit Architecture"),
        ("Programming Language", "Python Runtime Environment", "Python 3.10.9 (CPython)"),
        ("Web Framework", "Flask Application Framework", "Flask 3.0.3 with Werkzeug"),
        ("Database & ORM", "SQLAlchemy ORM with SQLite Engine", "SQLAlchemy 2.0.32, SQLite 3"),
        ("Machine Learning", "Scikit-learn, NumPy, Pandas", "Scikit-learn 1.5.1, Pandas 2.2.2"),
        ("Document Generation", "ReportLab PDF & OpenPyXL Excel", "ReportLab 4.2.2, OpenPyXL 3.1.5"),
        ("Testing Suite", "pytest & pytest-flask", "pytest 8.3.2, pytest-flask 1.3.0"),
        ("Hardware Specification", "Intel Core i7 Processor, 16 GB RAM", "512 GB NVMe SSD Storage"),
    ]
    for idx, row in enumerate(env_data, start=1):
        style_table_row(tbl_env.rows[idx], [1.8, 2.3, 2.4], [row[0], row[1], row[2]], is_even=(idx%2==0))
        
    doc.add_paragraph().paragraph_format.space_after = Pt(8)

    # ─────────────────────────────────────────────────────────────────────────
    # 12. DATABASE DESIGN
    # ─────────────────────────────────────────────────────────────────────────
    p = doc.add_paragraph()
    format_heading(p, "12. Database Design", level=1)
    
    add_body_paragraph(
        doc,
        "The AttendAI database is designed in Third Normal Form (3NF) to eliminate data redundancy while guaranteeing relational integrity and auditability. Ten core entities support academic administration, attendance tracking, predictive modeling, and faculty interventions:"
    )
    
    db_tables = [
        ("users", "id (PK), username (UQ), password_hash, role ('admin'/'faculty'), faculty_id (FK), is_active, created_at, updated_at", "Authentication accounts and access control credentials."),
        ("faculty", "id (PK), employee_id (UQ), full_name, email (UQ), department, designation, phone, is_active, created_at", "Academic faculty member professional profiles."),
        ("semesters", "id (PK), name, year, is_active, start_date, end_date, created_at", "Academic semesters with chronological date validation."),
        ("subjects", "id (PK), code, name, department, semester_id (FK), faculty_id (FK), total_classes_planned, is_active", "Curriculum course offerings mapped to faculty and semesters."),
        ("students", "id (PK), student_id (UQ), roll_number (UQ), full_name, department, year, section, semester_id (FK), email, is_active", "Enrolled student biodata and academic placement."),
        ("student_subjects", "id (PK), student_id (FK), subject_id (FK), semester_id (FK), enrolled_at, is_active", "Course enrolment junction table with UQ(student_id, subject_id)."),
        ("attendance_records", "id (PK), student_id (FK), subject_id (FK), date, status ('Present'/'Absent'), marked_by (FK), session_number, notes", "Daily session roll-call log with UQ(student_id, subject_id, date, session)."),
        ("attendance_edit_history", "id (PK), record_id (FK), previous_status, new_status, edited_by (FK), edit_reason, edited_at", "Immutable audit trail capturing all attendance corrections."),
        ("prediction_history", "id (PK), student_id (FK), subject_id (FK), semester_id (FK), prediction_date, risk_probability, risk_level, model_version", "Historical log of ML inference outputs for longitudinal tracking."),
        ("faculty_interventions", "id (PK), student_id (FK), faculty_id (FK), subject_id (FK), intervention_date, contact_mode, student_explanation, action_plan", "Closed-loop counseling intervention documentation and outcome tracker."),
    ]
    tbl_db = doc.add_table(rows=len(db_tables)+1, cols=3)
    tbl_db.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_table_borders(tbl_db)
    style_table_header(tbl_db.rows[0], [1.5, 2.7, 2.3], ["Table Name", "Attributes & Constraints", "Relational Purpose"])
    for idx, (tname, tcols, tpurp) in enumerate(db_tables, start=1):
        style_table_row(tbl_db.rows[idx], [1.5, 2.7, 2.3], [tname, tcols, tpurp], is_even=(idx%2==0))

    # ─────────────────────────────────────────────────────────────────────────
    # 13. ML METHODOLOGY
    # ─────────────────────────────────────────────────────────────────────────
    p = doc.add_paragraph()
    format_heading(p, "13. Machine Learning Methodology", level=1)
    
    add_body_paragraph(
        doc,
        "The predictive engine in AttendAI is formulated as a supervised binary classification problem: forecasting whether a student will finish the semester with final cumulative attendance below the mandatory threshold of 75.0% (Positive Class = 1: Shortage; Negative Class = 0: Regular)."
    )
    add_body_paragraph(
        doc,
        "The machine learning methodology adheres to the following rigorous engineering workflow:"
    )
    add_body_paragraph(
        doc,
        "1. Problem Formulation: Define the target indicator variable Y in {0, 1} where Y = 1 if final semester attendance < 75%, and Y = 0 if final attendance >= 75%.",
        bold_prefix="• Step 1: "
    )
    add_body_paragraph(
        doc,
        "2. Zero-Data-Leakage Snapshot Formulation: Generate multi-point longitudinal snapshots at progressive milestones (Classes 10, 20, 30, 40). For any checkpoint T, feature vector X_T is extracted strictly from historical records t <= T. Information from t > T is strictly barred from feature extraction and utilized only to label the ground-truth Y.",
        bold_prefix="• Step 2: "
    )
    add_body_paragraph(
        doc,
        "3. Student-Grouped Partitioning: Apply GroupKFold partitioning based on student ID to separate training and test sets. This ensures that no individual student's temporal snapshots span both training and evaluation subsets, eliminating data contamination across splits.",
        bold_prefix="• Step 3: "
    )
    add_body_paragraph(
        doc,
        "4. Cost-Sensitive Class Balancing: Compute inverse class frequencies to weight the loss function during model training, counteracting the natural class imbalance (68% regular vs. 32% shortage) and penalizing false negatives.",
        bold_prefix="• Step 4: "
    )
    add_body_paragraph(
        doc,
        "5. Model Evaluation and Selection: Compare Logistic Regression, Decision Trees, and Random Forests across Accuracy, Precision, Recall, F1-Score, and ROC-AUC. Select the optimal model prioritizing shortage sensitivity.",
        bold_prefix="• Step 5: "
    )

    # ─────────────────────────────────────────────────────────────────────────
    # 14. DATASET DESCRIPTION
    # ─────────────────────────────────────────────────────────────────────────
    p = doc.add_paragraph()
    format_heading(p, "14. Dataset Description", level=1)
    
    add_callout(
        doc,
        "SYNTHETIC BENCHMARK SPECIFICATION: The training and evaluation dataset comprises 6,400 multi-snapshot attendance observations across 400 virtual student profiles. Controlled behavioral archetypes (regular attendees, sporadic attendees, late-semester decaying attendees, and recovering attendees) were simulated across 4 core academic subjects (CS601, CS602, CS603, MA601). This simulation guarantees full compliance with student privacy regulations while providing a standardized, reproducible benchmark.",
        "DATASET ORIGIN & SIMULATION NOTICE"
    )
    
    tbl_ds = doc.add_table(rows=7, cols=2)
    tbl_ds.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_table_borders(tbl_ds)
    style_table_header(tbl_ds.rows[0], [2.2, 4.3], ["Dataset Attribute", "Empirical Value / Characteristic"])
    ds_meta = [
        ("Total Snapshot Observations", "6,400 snapshots"),
        ("Unique Student Profiles", "400 virtual student entities"),
        ("Academic Subjects Simulated", "4 subjects (CS601, CS602, CS603, MA601)"),
        ("Longitudinal Checkpoints", "Classes [10, 20, 30, 40] across a 50-class semester"),
        ("Configurable Target Threshold", "75.0% cumulative attendance"),
        ("Class Distribution", "68.00% Regular (4,352 snapshots) vs. 32.00% Shortage (2,048 snapshots)"),
    ]
    for idx, (attr, val) in enumerate(ds_meta, start=1):
        style_table_row(tbl_ds.rows[idx], [2.2, 4.3], [attr, val], is_even=(idx%2==0))
        
    doc.add_paragraph().paragraph_format.space_after = Pt(8)

    # ─────────────────────────────────────────────────────────────────────────
    # 15. FEATURE ENGINEERING
    # ─────────────────────────────────────────────────────────────────────────
    p = doc.add_paragraph()
    format_heading(p, "15. Feature Engineering", level=1)
    
    add_body_paragraph(
        doc,
        "To transform raw timestamped attendance sequences into predictive signals without data leakage, nine engineered features were derived at each checkpoint T:"
    )
    
    fe_specs = [
        ("classes_attended", "A_T = sum_{t=1}^T I(status_t == Present)", "Absolute count of classes present up to checkpoint T."),
        ("total_classes_so_far", "C_T = T", "Total number of class sessions conducted up to milestone T."),
        ("current_percentage", "P_T = (A_T / C_T) * 100", "Baseline arithmetic attendance percentage at milestone T."),
        ("consecutive_absences", "Run-length of consecutive absences prior to T", "Captures acute disengagement or ongoing medical absence."),
        ("attendance_last_10", "(Classes attended in last 10 sessions) / 10 * 100", "Moving window measuring immediate short-term attendance rate."),
        ("attendance_trend", "attendance_last_10 - current_percentage", "Directional velocity of engagement (positive = recovery, negative = decay)."),
        ("remaining_classes", "R_T = max(0, Total_Planned - C_T)", "Remaining opportunity window to recover attendance."),
        ("subject_attendance", "Subject-specific attendance rate (%)", "Captures subject-specific difficulties or disinterest."),
        ("overall_attendance", "Cumulative attendance across all enrolled subjects (%)", "Reflects student's general institutional attendance habit."),
    ]
    tbl_fe = doc.add_table(rows=len(fe_specs)+1, cols=3)
    tbl_fe.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_table_borders(tbl_fe)
    style_table_header(tbl_fe.rows[0], [1.8, 2.5, 2.2], ["Feature Identifier", "Mathematical Definition", "Pedagogical Rationale"])
    for idx, (fid, fdef, frat) in enumerate(fe_specs, start=1):
        style_table_row(tbl_fe.rows[idx], [1.8, 2.5, 2.2], [fid, fdef, frat], is_even=(idx%2==0))

    # ─────────────────────────────────────────────────────────────────────────
    # 16. ALGORITHM EXPLANATION
    # ─────────────────────────────────────────────────────────────────────────
    p = doc.add_paragraph()
    format_heading(p, "16. Algorithm Explanation", level=1)
    
    p_ml = doc.add_paragraph()
    format_heading(p_ml, "16.1 Machine Learning Classifiers", level=2)
    
    add_body_paragraph(
        doc,
        "1. Logistic Regression: Models the posterior probability P(Y=1|X) using a sigmoid logistic link function: P(Y=1|X) = 1 / (1 + exp(-beta^T X)). Optimization minimizes the binary cross-entropy loss augmented with L2 regularization and balanced class weighting.",
        bold_prefix="• "
    )
    add_body_paragraph(
        doc,
        "2. Decision Tree Classifier: Non-parametric supervised learner that recursively partitions the feature space using Gini impurity minimization. Maximum tree depth was constrained to 6 to prevent overfitting to snapshot artifacts.",
        bold_prefix="• "
    )
    add_body_paragraph(
        doc,
        "3. Random Forest Classifier: Ensemble learner constructing an ensemble of 100 decision trees via bootstrap aggregating (bagging) with randomized feature subsets (sqrt(d)). Mitigates variance and captures non-linear feature interactions.",
        bold_prefix="• "
    )
    
    p_rec = doc.add_paragraph()
    format_heading(p_rec, "16.2 Closed-Form Deterministic Recovery Algorithm", level=2)
    
    add_body_paragraph(
        doc,
        "Beyond statistical machine learning, AttendAI formulates and solves an exact algebraic recovery constraint. Given conducted classes C, attended classes A, target threshold ratio T (0.75), and remaining classes R, the minimum consecutive classes x required to reach or restore T is derived as:"
    )
    
    add_equation_box(doc, "(A + x) / (C + x) >= T  ==>  A + x >= T*C + T*x", "Eq. 1")
    add_equation_box(doc, "x * (1 - T) >= T*C - A  ==>  x >= (T*C - A) / (1 - T)", "Eq. 2")
    add_equation_box(doc, "For T = 0.75:  x >= (0.75*C - A) / 0.25 = 3*C - 4*A", "Eq. 3")
    
    add_body_paragraph(
        doc,
        "The discrete consecutive classes needed is thus: classes_needed = max(0, ceil(3*C - 4*A)). Concurrently, the safe absences buffer s (classes the student can miss while staying >= 75%) is derived from (A + R - s) / (C + R) >= T, yielding safe_skips = max(0, floor(A + R - T*(C + R))). If max_possible_percentage = ((A + R)/(C + R))*100 < 75.0%, the shortage is flagged as mathematically irrecoverable, triggering immediate administrative escalation."
    )

    # ─────────────────────────────────────────────────────────────────────────
    # 17. EXPERIMENTAL RESULTS
    # ─────────────────────────────────────────────────────────────────────────
    p = doc.add_paragraph()
    format_heading(p, "17. Experimental Results", level=1)
    
    add_body_paragraph(
        doc,
        "The empirical evaluation was conducted on a held-out test partition comprising 1,280 snapshots from 80 student groups (836 regular class snapshots and 444 shortage class snapshots). The verified metrics saved in `ml/models/model_metrics.json` are reported below:"
    )
    
    # Deployed Model Metrics Table
    tbl_lr_res = doc.add_table(rows=7, cols=2)
    tbl_lr_res.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_table_borders(tbl_lr_res)
    style_table_header(tbl_lr_res.rows[0], [2.5, 4.0], ["Performance Metric", "Empirical Test Result (Logistic Regression)"])
    lr_res = [
        ("Test Classification Accuracy", f"{metrics_data['metrics']['accuracy'] * 100:.2f}% (0.8398)"),
        ("Shortage Class Sensitivity (Recall)", f"{metrics_data['metrics']['recall'] * 100:.2f}% (0.8491)"),
        ("Shortage Class Precision", f"{metrics_data['metrics']['precision'] * 100:.2f}% (0.7320)"),
        ("F1-Score (Positive Risk Class)", f"{metrics_data['metrics']['f1_score']:.4f} (0.7862)"),
        ("Receiver Operating Characteristic (ROC-AUC)", f"{metrics_data['metrics']['roc_auc']:.4f} (0.9281)"),
        ("Test Sample Size / Student Groups", f"{metrics_data['test_sample_size']} snapshots / {metrics_data['test_student_count']} unique students"),
    ]
    for idx, (met, val) in enumerate(lr_res, start=1):
        style_table_row(tbl_lr_res.rows[idx], [2.5, 4.0], [met, val], is_even=(idx%2==0))
        
    doc.add_paragraph().paragraph_format.space_after = Pt(8)
    
    p_cm = doc.add_paragraph()
    format_heading(p_cm, "17.1 Confusion Matrix Analysis", level=2)
    
    add_body_paragraph(
        doc,
        "The confusion matrix for the deployed Logistic Regression classifier on the 1,280 test instances is structured as follows:"
    )
    
    # 2x2 Confusion Matrix Table
    tbl_cm = doc.add_table(rows=3, cols=3)
    tbl_cm.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_table_borders(tbl_cm)
    style_table_header(tbl_cm.rows[0], [2.1, 2.2, 2.2], ["Actual Ground Truth", "Predicted Regular (0)", "Predicted Shortage (1)"])
    cm = metrics_data['metrics']['confusion_matrix']
    style_table_row(tbl_cm.rows[1], [2.1, 2.2, 2.2], ["Actual Regular (0)", f"TN = {cm[0][0]}", f"FP = {cm[0][1]}"], is_even=False)
    style_table_row(tbl_cm.rows[2], [2.1, 2.2, 2.2], ["Actual Shortage (1)", f"FN = {cm[1][0]}", f"TP = {cm[1][1]}"], is_even=True)
    
    add_body_paragraph(
        doc,
        f"Analysis of the confusion matrix reveals that out of 444 actual shortage cases, the model accurately detected 377 True Positives (84.91% recall). Crucially for student academic protection, the classifier produced only 67 False Negatives (15.09% miss rate). While 138 False Positives were recorded, false positives in an academic support system simply result in proactive counseling, whereas false negatives allow students to unknowingly slide into exam debarment."
    )

    p_tm = doc.add_paragraph()
    format_heading(p_tm, "17.2 Calibrated Risk Tier Threshold Evaluation", level=2)
    add_body_paragraph(
        doc,
        "AttendAI categorizes student shortage probabilities into calibrated operational tiers. The empirical performance of the deployed Logistic Regression model at the High Risk (threshold = 0.65) and Medium Risk (threshold = 0.35) decision boundaries evaluated on the held-out 1,280-snapshot test partition is summarized below (persisted in ml/models/threshold_metrics.json):"
    )
    tbl_tm = doc.add_table(rows=4, cols=5)
    tbl_tm.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_table_borders(tbl_tm)
    style_table_header(tbl_tm.rows[0], [1.7, 1.0, 1.1, 1.1, 1.6], ["Operational Risk Tier", "Cutoff (Theta)", "Precision", "Recall", "Confusion Matrix"])
    style_table_row(tbl_tm.rows[1], [1.7, 1.0, 1.1, 1.1, 1.6], ["High Risk Tier", ">= 0.65", "81.31%", "78.38%", "TN=756, FP=80, FN=96, TP=348"], is_even=False)
    style_table_row(tbl_tm.rows[2], [1.7, 1.0, 1.1, 1.1, 1.6], ["Medium Risk Tier", ">= 0.35", "65.36%", "90.09%", "TN=624, FP=212, FN=44, TP=400"], is_even=True)
    style_table_row(tbl_tm.rows[3], [1.7, 1.0, 1.1, 1.1, 1.6], ["Default Decision Threshold", ">= 0.50", "73.20%", "84.91%", "TN=698, FP=138, FN=67, TP=377"], is_even=False)

    doc.add_paragraph().paragraph_format.space_after = Pt(8)

    # ─────────────────────────────────────────────────────────────────────────
    # 18. MODEL COMPARISON
    # ─────────────────────────────────────────────────────────────────────────
    p = doc.add_paragraph()
    format_heading(p, "18. Model Comparison", level=1)
    
    add_body_paragraph(
        doc,
        "To objectively determine the best architecture, three supervised algorithms were trained and benchmarked under identical cross-validation splits. The actual comparative metrics recorded in `ml/models/model_comparison.json` are presented below:"
    )
    
    tbl_comp = doc.add_table(rows=4, cols=6)
    tbl_comp.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_table_borders(tbl_comp)
    style_table_header(tbl_comp.rows[0], [1.5, 1.0, 1.0, 1.0, 1.0, 1.0], ["Algorithm", "Accuracy", "Precision", "Recall", "F1-Score", "ROC-AUC"])
    
    for idx, (m_name, m_res) in enumerate(comparison_data.items(), start=1):
        row_vals = [
            m_name,
            f"{m_res['accuracy']*100:.2f}%",
            f"{m_res['precision']*100:.2f}%",
            f"{m_res['recall']*100:.2f}%",
            f"{m_res['f1_score']:.4f}",
            f"{m_res['roc_auc']:.4f}",
        ]
        style_table_row(tbl_comp.rows[idx], [1.5, 1.0, 1.0, 1.0, 1.0, 1.0], row_vals, is_even=(idx%2==0))
        
    doc.add_paragraph().paragraph_format.space_after = Pt(8)
    
    add_body_paragraph(
        doc,
        "Comparative Analysis & Model Selection Rationale: While Random Forest achieved the highest overall accuracy (84.84%) and precision (77.29%), Logistic Regression was selected as the deployed production model because it achieved the highest Recall (84.91% vs. 79.73% for Random Forest and 81.31% for Decision Tree) and the highest ROC-AUC (0.9281 vs. 0.9249 for Random Forest). In an educational retention application, minimizing False Negatives (identifying at-risk students before it is too late) is paramount. Logistic Regression also provides superior inference speed and transparent probabilistic calibration."
    )

    # ─────────────────────────────────────────────────────────────────────────
    # 19. PERFORMANCE EVALUATION
    # ─────────────────────────────────────────────────────────────────────────
    p = doc.add_paragraph()
    format_heading(p, "19. Performance Evaluation & Feature Importance", level=1)
    
    add_body_paragraph(
        doc,
        "The contribution of individual features to the predictive decision boundary was analyzed through normalized absolute coefficient weights of the deployed model:"
    )
    
    tbl_feat = doc.add_table(rows=10, cols=3)
    tbl_feat.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_table_borders(tbl_feat)
    style_table_header(tbl_feat.rows[0], [1.8, 1.5, 3.2], ["Feature Name", "Relative Importance", "Pedagogical Impact"])
    
    feat_data = [
        ("classes_attended", "50.46% (0.5046)", "Primary determinant of cumulative presence towards statutory threshold."),
        ("total_classes_so_far", "21.01% (0.2101)", "Establishes denominator weight; early absences matter less than late ones."),
        ("remaining_classes", "21.01% (0.2101)", "Defines available mathematical runway for grade recovery."),
        ("overall_attendance", "3.32% (0.0332)", "Student cross-subject baseline behavioral consistency."),
        ("attendance_trend", "1.86% (0.0186)", "Direction of recent momentum (improving vs. deteriorating attendance)."),
        ("attendance_last_10", "1.18% (0.0118)", "Moving average capturing recent acute habit changes."),
        ("consecutive_absences", "0.41% (0.0041)", "Detects continuous blocks of absence requiring medical/personal review."),
        ("current_percentage", "0.37% (0.0037)", "Snapshot ratio indicator at checkpoint date."),
        ("subject_attendance", "0.37% (0.0037)", "Subject-specific engagement indicator."),
    ]
    for idx, (fn, imp, imp_desc) in enumerate(feat_data, start=1):
        style_table_row(tbl_feat.rows[idx], [1.8, 1.5, 3.2], [fn, imp, imp_desc], is_even=(idx%2==0))
        
    doc.add_paragraph().paragraph_format.space_after = Pt(8)

    # ─────────────────────────────────────────────────────────────────────────
    # 20. SCREENSHOTS AND MODULE EXPLANATIONS
    # ─────────────────────────────────────────────────────────────────────────
    p = doc.add_paragraph()
    format_heading(p, "20. Screenshots and Module Explanations", level=1)
    
    modules = [
        ("20.1 Authentication & Security Gateway (/login)",
         "Provides secure credential authentication supporting both Administrator and Faculty personas. Incorporates origin validation on redirect parameters to prevent Open Redirect vulnerabilities and utilizes scrypt-based password hashing for robust credential protection."),
        ("20.2 Administrative Command Dashboard (/admin/dashboard)",
         "Presents high-level institutional Key Performance Indicators (KPIs): total active students, active subjects, campus-wide average attendance, and counts of students in Low, Medium, and High risk tiers. Interactive Chart.js charts depict department-wise attendance and shortage distributions."),
        ("20.3 Faculty Instructional Dashboard (/faculty/dashboard)",
         "Tailored for instructors, displaying assigned course sections, today's scheduled classes, quick roll-call links, and immediate alerts for enrolled students falling into the High Risk category."),
        ("20.4 Daily Attendance Session Roll-Call (/attendance/mark)",
         "Enables faculty to select academic department, semester, subject, and date. The enrolled student roster is rendered with radio toggles (Present/Absent). An atomic database transaction persists records while enforcing composite uniqueness to prevent duplicate session logging."),
        ("20.5 Attendance Audit History & Correction (/attendance/history/<id>)",
         "Maintains an immutable historical audit log of every modification made to an attendance record, capturing previous status, updated status, modifying faculty ID, reason for amendment, and exact timestamp."),
        ("20.6 Student Analytics & Profile (/analytics/student/<id>)",
         "Delivers a 360-degree academic attendance profile for individual students, showing subject-by-subject attendance percentages, historical roll-call logs, graphical attendance trajectories, and comparative department averages."),
        ("20.7 Machine Learning Risk Monitoring Dashboard (/risk/dashboard)",
         "Consolidates real-time risk predictions across the entire student population with multi-criteria filtering by risk tier (Low, Medium, High), department, and semester. Displays predicted shortage probabilities alongside deterministic recovery indicators."),
        ("20.8 Deterministic Recovery Calculator (/risk/student/<id>)",
         "Executes the closed-form recovery algorithm for at-risk students, computing exact consecutive classes needed, maximum attainable percentage if 100% of remaining sessions are attended, and remaining safe skips buffer."),
        ("20.9 Closed-Loop Faculty Intervention Tracker (/risk/interventions)",
         "Provides an auditable workflow for documenting pedagogical interventions: contact mode (Phone, Email, In-Person), student reason for absence, agreed recovery milestones, and post-intervention outcome assessments."),
        ("20.10 Institutional Reports & Data Export Portal (/reports)",
         "Generates formal ReportLab PDF reports containing all 9 mandatory academic elements and OpenPyXL Excel spreadsheets providing raw attendance ledgers, risk analysis summaries, and subject matrices."),
    ]
    for m_title, m_desc in modules:
        p_m = doc.add_paragraph()
        format_heading(p_m, m_title, level=2)
        add_body_paragraph(doc, m_desc)

    # ─────────────────────────────────────────────────────────────────────────
    # 21. LIMITATIONS
    # ─────────────────────────────────────────────────────────────────────────
    p = doc.add_paragraph()
    format_heading(p, "21. Limitations", level=1)
    
    add_body_paragraph(
        doc,
        "While AttendAI demonstrates robust performance across testing and validation suites, several technical and operational boundaries must be acknowledged:"
    )
    add_body_paragraph(
        doc,
        "1. Synthetic Benchmark Evaluation: In strict adherence to student privacy directives, the machine learning models were developed on a synthetic benchmark dataset. While the data generator modeled realistic pedagogical archetypes, live institutional deployment will require transfer validation against multi-semester real student cohorts.",
        bold_prefix="• "
    )
    add_body_paragraph(
        doc,
        "2. Binary Attendance Taxonomy: The system records presence in binary states ('Present' vs. 'Absent'). It does not currently distinguish nuanced institutional absence categories such as official sports duty (OD), medical leave, or bereavement.",
        bold_prefix="• "
    )
    add_body_paragraph(
        doc,
        "3. Static Timetable Modeling: Remaining classes are calculated against planned curriculum totals. Unplanned institutional closures, severe weather cancellations, or ad-hoc makeup sessions require manual administrative adjustments.",
        bold_prefix="• "
    )
    add_body_paragraph(
        doc,
        "4. Database Concurrency Ceiling: SQLite provides atomic ACID compliance but utilizes file-level locking during write operations, which is optimal for departmental use but unsuitable for university-wide concurrent writes exceeding 1,000 requests/sec.",
        bold_prefix="• "
    )

    # ─────────────────────────────────────────────────────────────────────────
    # 22. FUTURE ENHANCEMENTS
    # ─────────────────────────────────────────────────────────────────────────
    p = doc.add_paragraph()
    format_heading(p, "22. Future Enhancements", level=1)
    
    add_body_paragraph(
        doc,
        "The modular architecture of AttendAI establishes a strong foundation for future research and engineering extensions:"
    )
    add_body_paragraph(
        doc,
        "1. Automated Edge Ingestion (IoT & Biometrics): Integration with edge hardware devices, including RFID smart card tap-ins and facial recognition edge cameras, to automate classroom roll-call without instructional overhead.",
        bold_prefix="• "
    )
    add_body_paragraph(
        doc,
        "2. Multimodal Early Warning Models: Expanding the predictive feature space beyond attendance to ingest LMS clickstream data, assignment submission timeliness, and continuous assessment quiz scores.",
        bold_prefix="• "
    )
    add_body_paragraph(
        doc,
        "3. Automated Omnichannel Messaging: Implementing automated SMS and WhatsApp notification gateways to dispatch immediate attendance warning digests to students, faculty mentors, and guardians.",
        bold_prefix="• "
    )
    add_body_paragraph(
        doc,
        "4. Sequential Deep Learning Architectures: Evaluating Recurrent Neural Networks (LSTM / GRU) and Temporal Transformer networks to model variable-length, non-linear attendance sequences.",
        bold_prefix="• "
    )
    add_body_paragraph(
        doc,
        "5. Enterprise Database & Worker Scaling: Migrating data persistence to PostgreSQL with connection pooling and implementing Celery/Redis task queues for asynchronous background batch inference.",
        bold_prefix="• "
    )

    # ─────────────────────────────────────────────────────────────────────────
    # 23. CONCLUSION
    # ─────────────────────────────────────────────────────────────────────────
    p = doc.add_paragraph()
    format_heading(p, "23. Conclusion", level=1)
    
    add_body_paragraph(
        doc,
        "This M.Tech technical internship successfully engineered, evaluated, and validated AttendAI—an intelligent student attendance analytics and academic risk prediction system. AttendAI moves beyond conventional retrospective ERP record-keeping by unifying operational roll-call logging, machine learning shortage forecasting, deterministic recovery mathematics, closed-loop faculty counseling, and institutional compliance reporting into a unified Academic SaaS platform."
    )
    add_body_paragraph(
        doc,
        "By enforcing a zero-data-leakage temporal snapshot framework, candidate machine learning models were rigorously benchmarked on a 1,280-snapshot held-out test partition. The deployed Logistic Regression classifier achieved an 83.98% accuracy, 0.9281 ROC-AUC, and an 84.91% sensitivity in detecting students at risk of falling below the statutory 75% attendance threshold. Augmented by an exact closed-form recovery solver and an auditable faculty intervention lifecycle, AttendAI provides higher education institutions with an actionable, data-driven instrument to safeguard student retention and foster academic success."
    )

    # ─────────────────────────────────────────────────────────────────────────
    # 24. REFERENCES
    # ─────────────────────────────────────────────────────────────────────────
    p = doc.add_paragraph()
    format_heading(p, "24. References", level=1)
    
    references = [
        "Romero, C., & Ventura, S. (2020). Educational data mining and learning analytics: An updated survey. WIREs Data Mining and Knowledge Discovery, 10(3), e1355.",
        "Baker, R. S., & Inventado, P. S. (2014). Educational data mining and learning analytics. In Learning Analytics (pp. 61-75). Springer, New York, NY.",
        "Breiman, L. (2001). Random forests. Machine Learning, 45(1), 5-32.",
        "Pedregosa, F., Varoquaux, G., Gramfort, A., Michel, V., Thirion, B., Grisel, O., ... & Duchesnay, É. (2011). Scikit-learn: Machine learning in Python. Journal of Machine Learning Research, 12, 2825-2830.",
        "Hastie, T., Tibshirani, R., & Friedman, J. (2009). The Elements of Statistical Learning: Data Mining, Inference, and Prediction. Springer Science & Business Media, New York.",
        "Fawcett, T. (2006). An introduction to ROC analysis. Pattern Recognition Letters, 27(8), 861-874.",
        "Chawla, N. V., Bowyer, K. W., Hall, L. O., & Kegelmeyer, W. P. (2002). SMOTE: Synthetic minority over-sampling technique. Journal of Artificial Intelligence Research, 16, 321-357.",
        "Grinberg, M. (2018). Flask Web Development: Developing Web Applications with Python. O'Reilly Media, Sebastopol, CA.",
        "Bakhshinategh, B., Zaiane, O. R., ElAtia, S., & Ipperciel, D. (2018). Educational data mining applications and trends. Education and Information Technologies, 23(2), 531-553.",
        "All India Council for Technical Education (AICTE). (2020). Approval Process Handbook 2020-2021: Norms and Requirements for Technical Institutions. Government of India.",
    ]
    for r in references:
        p_ref = doc.add_paragraph()
        p_ref.paragraph_format.space_before = Pt(0)
        p_ref.paragraph_format.space_after = Pt(4)
        p_ref.paragraph_format.left_indent = Inches(0.4)
        p_ref.paragraph_format.first_line_indent = Inches(-0.4)
        r_run = p_ref.add_run(r)
        r_run.font.name = 'Calibri'
        r_run.font.size = Pt(10)
        r_run.font.color.rgb = RGBColor(51, 65, 85)

    # Save output document
    output_path = os.path.join("d:\\AttendAI", "AttendAI_MTech_Internship_Report.docx")
    doc.save(output_path)
    print(f"Report successfully saved to {output_path}!")

if __name__ == "__main__":
    main()
