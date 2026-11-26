"""
ml/data_prep.py – Feature engineering and extraction for AttendAI risk prediction.
Queries the SQLite database and transforms student attendance histories into
standardized ML feature vectors for training and live inference.
"""

from typing import Dict, Any, Optional
import pandas as pd
import numpy as np
from datetime import date, timedelta

from ml.features import FEATURE_COLUMNS, extract_features_from_records


def get_student_ml_features(student_id: int, subject_id: Optional[int] = None) -> Dict[str, Any]:
    """
    Extracts the official 9 ML features for a student, optionally scoped to a subject.
    If subject_id is None, features are computed on the student's primary/lowest subject
    with cross-subject context.

    Returns:
        Dict matching ml.features.FEATURE_COLUMNS.
    """
    from database.models import db, Student, Subject, AttendanceRecord

    student = db.session.get(Student, student_id)
    if not student:
        raise ValueError(f"Student with ID {student_id} not found.")

    all_records = student.attendances.order_by(AttendanceRecord.date.asc(), AttendanceRecord.session_slot.asc()).all()
    if not all_records:
        raise ValueError(f"No attendance records recorded for student {student.name} ({student.roll_number}).")

    if subject_id:
        subject = db.session.get(Subject, subject_id)
        sub_records = [r for r in all_records if r.subject_id == subject_id]
        total_planned = subject.total_classes_planned if subject else 50
    else:
        # If no specific subject given, find the subject with lowest attendance % or use all records
        semester_subjects = Subject.query.filter_by(semester_id=student.semester_id).all()
        if semester_subjects:
            # Pick subject with lowest attendance or most records
            sub_stats = [
                (s, student.get_subject_stats(s.id))
                for s in semester_subjects
                if student.get_subject_stats(s.id)["conducted"] > 0
            ]
            if sub_stats:
                lowest_subj, lowest_stat = min(sub_stats, key=lambda x: x[1]["percentage"])
                sub_records = [r for r in all_records if r.subject_id == lowest_subj.id]
                total_planned = lowest_subj.total_classes_planned
            else:
                sub_records = all_records
                total_planned = 50
        else:
            sub_records = all_records
            total_planned = 50

    features = extract_features_from_records(
        records=sub_records,
        total_planned=total_planned,
        all_subject_records=all_records
    )
    features["student_id"] = student.id
    features["roll_number"] = student.roll_number
    features["student_name"] = student.name
    return features


def get_features_for_student(student_id: int) -> dict:
    """
    Extract ML features for a single student from the database.
    Includes both legacy summary metrics and the official ML feature set.
    """
    from database.models import db, Student, Subject

    student = db.session.get(Student, student_id)
    if not student:
        raise ValueError(f"Student {student_id} not found.")

    records = student.attendances.all()
    if not records:
        raise ValueError(f"No attendance records for student {student_id}.")

    # Overall stats
    total = len(records)
    present = sum(1 for r in records if r.status in ("present", "late"))
    overall_pct = round((present / total * 100), 2) if total else 0.0

    # Subject-wise stats
    subjects = Subject.query.filter_by(semester_id=student.semester_id).all()
    sub_pcts = []
    below_75 = 0
    below_60 = 0

    for subj in subjects:
        sub_records = [r for r in records if r.subject_id == subj.id]
        if not sub_records:
            continue
        sub_total = len(sub_records)
        sub_present = sum(1 for r in sub_records if r.status in ("present", "late"))
        pct = round((sub_present / sub_total * 100), 2) if sub_total else 0.0
        sub_pcts.append(pct)
        if pct < 75: below_75 += 1
        if pct < 60: below_60 += 1

    subject_min_pct = min(sub_pcts) if sub_pcts else 0.0
    subject_max_pct = max(sub_pcts) if sub_pcts else 0.0
    subject_avg_pct = round(np.mean(sub_pcts), 2) if sub_pcts else 0.0
    total_subjects  = len(sub_pcts)

    # Consecutive absences
    sorted_records = sorted(records, key=lambda r: (r.date, r.session_slot))
    curr_consec = 0
    for r in reversed(sorted_records):
        if r.status == "absent":
            curr_consec += 1
        else:
            break

    # Last 10 classes attendance
    recent_10 = sorted_records[-10:]
    rec_present = sum(1 for r in recent_10 if r.status in ("present", "late"))
    attendance_last_10 = round((rec_present / len(recent_10) * 100), 2) if recent_10 else overall_pct
    attendance_trend = round(attendance_last_10 - overall_pct, 2)

    sem = student.semester
    semester_week = sem.progress if sem else 0.5
    total_planned = sum(s.total_classes_planned for s in subjects) if subjects else (len(subjects) * 50)
    remaining_classes = max(0, total_planned - total)
    absence_rate = round(((total - present) / total * 100), 2) if total else 0.0

    features = {
        # Official ML Model Features
        "total_classes_so_far": total,
        "classes_attended": present,
        "current_percentage": overall_pct,
        "consecutive_absences": curr_consec,
        "attendance_last_10": attendance_last_10,
        "attendance_trend": attendance_trend,
        "remaining_classes": remaining_classes,
        "subject_attendance": subject_min_pct,
        "overall_attendance": overall_pct,

        # Additional metadata & legacy keys
        "student_id": student_id,
        "overall_attendance_pct": overall_pct,
        "subject_min_pct": subject_min_pct,
        "subject_max_pct": subject_max_pct,
        "subject_avg_pct": subject_avg_pct,
        "subjects_below_75": below_75,
        "subjects_below_60": below_60,
        "recent_trend": attendance_trend,
        "semester_week": semester_week,
        "total_subjects": total_subjects,
        "absence_rate": absence_rate,
        "total_classes": total,
    }
    return features


def get_features_for_all_students(semester_id: int) -> pd.DataFrame:
    """
    Build a feature matrix for all active students in a semester.
    Returns a DataFrame (one row per student).
    """
    from database.models import Student

    students = Student.query.filter_by(semester_id=semester_id, is_active=True).all()
    rows = []
    for st in students:
        try:
            feat = get_features_for_student(st.id)
            rows.append(feat)
        except ValueError:
            pass
    return pd.DataFrame(rows)


def label_risk(overall_pct: float, subject_min_pct: float) -> str:
    """
    Rule-based risk labelling used for fallbacks.
    High   -> overall < 60  OR any subject < 50
    Medium -> overall 60-74 OR any subject 50-74
    Low    -> overall >= 75 AND all subjects >= 75
    """
    if overall_pct < 60 or subject_min_pct < 50:
        return "High"
    elif overall_pct < 75 or subject_min_pct < 75:
        return "Medium"
    else:
        return "Low"
