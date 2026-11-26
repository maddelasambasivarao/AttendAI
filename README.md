# AttendAI – Intelligent Student Attendance Analytics & Academic Risk Prediction System

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.0.3-brightgreen.svg)](https://palletsprojects.com/p/flask/)
[![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.0.31-red.svg)](https://www.sqlalchemy.org/)
[![Scikit-Learn](https://img.shields.io/badge/Scikit--Learn-1.5.1-orange.svg)](https://scikit-learn.org/)
[![Tests](https://img.shields.io/badge/pytest-104%20passed-success.svg)](https://pytest.org/)
[![License](https://img.shields.io/badge/License-Academic%20Evaluation-lightgrey.svg)]()

> **AttendAI** is an enterprise-grade academic SaaS platform engineered for higher education institutions. It bridges the gap between passive attendance tracking and proactive student retention by combining daily operational roll-call logging, supervised machine learning shortage prediction, closed-form deterministic recovery mathematics, closed-loop faculty counseling, and institutional compliance reporting.

---

## Table of Contents
1. [Core Features](#core-features)
2. [Technology Stack](#technology-stack)
3. [System Architecture](#system-architecture)
4. [Final Folder Structure](#final-folder-structure)
5. [Prerequisites & Installation](#prerequisites--installation)
6. [Database Setup & Seeding](#database-setup--seeding)
7. [Machine Learning Workflow](#machine-learning-workflow)
8. [Running the Application](#running-the-application)
9. [Running the Test Suite](#running-the-test-suite)
10. [Local Demo Credentials](#local-demo-credentials)
11. [Academic Governance & Synthetic Data Notice](#academic-governance--synthetic-data-notice)

---

## Core Features

- **Role-Based Access Control**: Dual-persona authentication (Administrator and Faculty) with `scrypt` password hashing, session expiration, and Open Redirect prevention.
- **Academic Management**: Comprehensive management of Semesters, Curriculum Subjects, Faculty Members, and Student Rosters with unique roll number and course code validation.
- **Operational Attendance Roll-Call**: Multi-student daily session recording with atomic database commits and duplicate session detection.
- **Bulk CSV / Excel Ingestion**: Fast batch import of historical student rosters and attendance records with schema error checking.
- **Supervised ML Risk Prediction**: Pre-trained machine learning classifier forecasting probability of end-term attendance shortage (< 75%) with zero data leakage.
- **Deterministic Attendance Recovery**: Exact closed-form algebraic solver calculating consecutive classes needed, safe absences buffer, and mathematical impossibility detection.
- **Closed-Loop Faculty Intervention Tracker**: Auditable log capturing student outreach, contact mode (In-person, Phone, Email), reasons for absence, and outcome monitoring.
- **Academic SaaS Dashboard**: Responsive, clean navy-slate UI powered by Bootstrap 5 and Chart.js featuring KPI cards, trend charts, and empty-state safeguards.
- **Compliance Reporting & Export**: Formal 9-element ReportLab PDF generation and multi-tab OpenPyXL Excel exports matching database records.

---

## Technology Stack

| Layer | Component | Version / Specification |
| :--- | :--- | :--- |
| **Backend Framework** | Python / Flask | Python 3.10+, Flask 3.0.3, Werkzeug 3.0.3 |
| **Authentication & Sessions** | Flask-Login | Flask-Login 0.6.3 with scrypt hashing |
| **Database & ORM** | SQLite / SQLAlchemy | SQLAlchemy 2.0.31, SQLite 3 (`PRAGMA foreign_keys=ON`) |
| **Machine Learning** | Scikit-learn, Pandas, NumPy | Scikit-learn 1.5.1, Pandas 2.2.2, NumPy 1.26.4, Joblib 1.4.2 |
| **Document Generation** | ReportLab & OpenPyXL | ReportLab 4.2.2, OpenPyXL 3.1.5, python-docx 1.2.0 |
| **Frontend UI** | HTML5, CSS3, Bootstrap 5, Chart.js | Bootstrap 5.3.3, Chart.js 4.4.1 |
| **Test Automation** | pytest & pytest-flask | pytest 8.3.2, pytest-flask 1.3.0 (104 tests) |

---

## System Architecture

```
                          ┌─────────────────────────────────────────────────────┐
                          │                 PRESENTATION TIER                   │
                          │   Bootstrap 5 · Chart.js · Jinja2 · Academic SaaS   │
                          └──────────────────────────┬──────────────────────────┘
                                                     │ HTTP / JSON
                                                     ▼
                          ┌─────────────────────────────────────────────────────┐
                          │                 APPLICATION TIER                    │
                          │        Flask 3.0 Blueprints & Middleware            │
                          │  auth · admin · faculty · attendance · risk · reports│
                          └─────────────┬─────────────────────────┬─────────────┘
                                        │                         │
                                        ▼                         ▼
            ┌──────────────────────────────────────┐  ┌─────────────────────────┐
            │       MACHINE LEARNING TIER          │  │     PERSISTENCE TIER    │
            │ Scikit-learn Pipeline (Joblib)       │  │ SQLAlchemy 2.0 ORM      │
            │ Zero-Leakage Feature Extraction      │  │ SQLite with Foreign     │
            │ Deterministic Recovery Solver        │  │ Key Pragmas Enforced    │
            └──────────────────────────────────────┘  └─────────────────────────┘
```

---

## Final Folder Structure

```
d:\AttendAI\
├── app.py                      # Application factory, blueprint registration & error handlers
├── config.py                   # Environment configurations (Development, Testing, Production)
├── requirements.txt            # Locked project dependencies
├── seed.py                     # Database initialization and demo seeding script
├── build_report.py             # Script generating M.Tech Internship Report (.docx)
├── AttendAI_MTech_Internship_Report.docx # Formally styled M.Tech report
├── README.md                   # Complete system documentation
├── attendai.db                 # Seeded SQLite operational database
├── database/
│   ├── __init__.py             # Database package initialization
│   └── models.py               # SQLAlchemy models (User, Student, Attendance, Intervention)
├── dataset/
│   ├── DATASET_METADATA.md     # Governance documentation for benchmark dataset
│   └── synthetic_attendance_snapshots.csv # 6,400 synthetic snapshot benchmark rows
├── ml/
│   ├── __init__.py
│   ├── data_generator.py       # Longitudinal synthetic snapshot generator
│   ├── data_prep.py            # Feature transformation & GroupKFold splitting
│   ├── evaluate.py             # Model inspection & feature importance utility
│   ├── features.py             # Feature column definitions & metadata
│   ├── predict.py              # Real-time inference & batch risk prediction
│   ├── recommendations.py      # Closed-form recovery math & action generator
│   ├── train.py                # Model training, comparison & Joblib persistence
│   └── models/
│       ├── best_risk_model.joblib   # Persisted deployed model pipeline
│       ├── model_comparison.json    # Full comparison metrics across LR, DT, and RF
│       ├── model_meta.json          # Model metadata, versioning & feature columns
│       └── model_metrics.json       # Detailed evaluation metrics for best model
├── reports/
│   ├── __init__.py
│   ├── excel_builder.py        # Multi-tab OpenPyXL spreadsheet generation
│   └── pdf_builder.py          # 9-element ReportLab PDF report generation
├── routes/
│   ├── __init__.py
│   ├── admin.py                # Admin dashboard, faculty/student CRUD, settings
│   ├── analytics.py            # Attendance analytics & subject-wise distributions
│   ├── attendance.py           # Daily roll-call entry, bulk upload, audit logs
│   ├── auth.py                 # Login, logout, password change, open redirect check
│   ├── faculty.py              # Faculty dashboard & roster views
│   ├── reports.py              # Institutional report downloads & templates
│   └── risk.py                 # ML risk monitoring, recovery math, interventions
├── static/
│   ├── css/
│   │   └── style.css           # Academic SaaS custom styling (Navy/Slate/Cyan)
│   └── js/
│       ├── analytics.js        # Analytics visualizers
│       └── dashboard.js        # Chart.js dashboard charts
├── templates/
│   ├── base.html               # Master layout with responsive sidebar & nav
│   ├── admin/                  # Admin management templates
│   ├── analytics/              # Attendance analytics templates
│   ├── attendance/             # Daily roll-call, bulk import & history templates
│   ├── auth/                   # Authentication & login templates
│   ├── faculty/                # Faculty operational templates
│   ├── reports/                # Institutional reports landing portal
│   └── risk/                   # ML risk monitoring & intervention templates
├── tests/
│   ├── __init__.py
│   ├── conftest.py             # pytest fixtures (app, client, db, demo data)
│   ├── test_attendance.py      # Attendance entry, duplicate checks & audit tests
│   ├── test_dashboard_and_pages.py # View rendering & KPI card verification
│   ├── test_ml.py              # Feature extraction, leakage prevention & math tests
│   ├── test_models.py          # Database integrity & password hashing tests
│   ├── test_qa_master.py       # Master regression, security & boundary tests
│   ├── test_reporting_and_export.py # PDF & Excel export verification tests
│   ├── test_risk_monitoring.py # Risk monitoring, batch inference & intervention tests
│   ├── test_routes.py          # Route guard & authentication tests
│   └── test_student_management.py # Student CRUD & safeguard tests
└── uploads/                    # Temporary storage for bulk import files
```

---

## Prerequisites & Installation

### 1. Prerequisites
- Python 3.10 or higher
- Git (optional, for version control)

### 2. Environment Setup
Clone or navigate to the project directory and create a virtual environment:
```bash
cd d:\AttendAI
python -m venv venv

# Activate Virtual Environment:
# On Windows (Command Prompt):
venv\Scripts\activate.bat
# On Windows (PowerShell):
venv\Scripts\Activate.ps1
# On Linux / macOS:
source venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

---

## Database Setup & Seeding

AttendAI includes an automated initialization and seeding script that configures the SQLite database schema with full referential integrity and populates realistic demo records:

```bash
pip install -r requirements.txt
```

**Seeded Entities**:
- Recreates all tables cleanly (`PRAGMA foreign_keys=ON`)
- Creates 1 local demo Administrator account (`admin`)
- Creates 3 Faculty accounts across departments
- Sets up an active academic semester with 5 curriculum subjects
- Registers 16 enrolled students across Computer Science, Information Technology, and Electronics
- Populates 576 daily session attendance records
- Generates initial ML risk predictions and faculty intervention records

---

## Machine Learning Workflow

### Train & Compare Models
Execute the training pipeline to extract zero-leakage features, train Logistic Regression, Decision Tree, and Random Forest classifiers, evaluate them on a held-out test partition, and persist the best model:

```bash
python ml/train.py
```

### Inspect Evaluation Metrics & Feature Importance
```bash
python ml/evaluate.py
```

### Actual Empirical Benchmark Results:
- **Test Sample Size**: 1,280 snapshots (80 held-out student groups; Zero Data Leakage)
- **Deployed Classifier**: Logistic Regression (v2.0.0, `class_weight='balanced'`)
  - **Overall Accuracy**: 83.98%
  - **Shortage Precision**: 73.20%
  - **Shortage Recall (Sensitivity)**: **84.91%** (Detects 377 of 444 shortages)
  - **F1-Score**: 0.7862
  - **ROC-AUC**: **0.9281**
  - **Confusion Matrix**: `TN=698, FP=138, FN=67, TP=377`
- **Calibrated Risk Threshold Metrics (`ml/models/threshold_metrics.json`)**:
  - **High Risk ($\theta = 0.65$)**: Precision = **81.31%**, Recall = **78.38%** (`TP=348, FP=80, FN=96, TN=756`)
  - **Medium Risk ($\theta = 0.35$)**: Recall = **90.09%**, Precision = **65.36%** (`TP=400, FP=212, FN=44, TN=624`)

---

## Running the Application

Launch the local Flask development server:
```bash
python app.py
```
Open your browser and navigate to:
```
http://127.0.0.1:5000/
```

---

## Running the Test Suite

The AttendAI test suite features **104 automated unit, integration, and security tests** across 9 test modules:

```bash
pytest -v
```

To run a specific test suite:
```bash
# Run Master QA Suite:
pytest tests/test_qa_master.py -v

# Run Reporting & Export Tests:
pytest tests/test_reporting_and_export.py -v

# Run ML & Recovery Math Tests:
pytest tests/test_ml.py -v
```

---

## Local Demo Credentials

> [!NOTE]
> These credentials apply strictly to the local seeded database (`seed.py`).

| Role | Username | Password | Access Level |
| :--- | :--- | :--- | :--- |
| **Administrator** | `admin` | `Admin@123` | Full system governance, faculty/student CRUD, semester/subject setup, institutional settings, reports. |
| **Faculty (CSE)** | `faculty1` | `Faculty@123` | Assigned subjects roll-call, attendance editing, student risk analysis, intervention logging. |
| **Faculty (IT)** | `faculty2` | `Faculty@123` | Assigned IT subjects roll-call, student analytics, counseling documentation. |
| **Faculty (ECE)** | `faculty3` | `Faculty@123` | Assigned ECE subjects roll-call, student analytics, counseling documentation. |

---

## Academic Governance & Synthetic Data Notice

- **Compliance with Student Privacy**: To respect educational privacy regulations (FERPA / GDPR), all machine learning training and validation datasets in `dataset/` are **controlled synthetic simulations** (6,400 snapshots across 400 virtual student profiles).
- **Separation of Concerns**: Operational attendance records in the database remain completely separate from training data.
- **Deterministic Rigor**: All recovery projections, safe buffer computations, and reporting metrics are derived from exact algebraic formulas and database ground truth.

---

## Project Artifacts
- **M.Tech Internship Report**: [`AttendAI_MTech_Internship_Report.docx`](file:///d:/AttendAI/AttendAI_MTech_Internship_Report.docx)
- **Architecture Plan**: [`AttendAI_Architecture_Plan.md`](file:///c:/Users/HP/.gemini/antigravity/brain/675e1e65-15e6-4c4d-b843-3eef62656cff/AttendAI_Architecture_Plan.md)
