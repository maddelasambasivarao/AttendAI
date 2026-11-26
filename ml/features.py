"""
ml/features.py – Central feature schema and feature extraction utilities.
Ensures consistency between training and live inference pipelines.
"""

from typing import List, Dict, Any
import numpy as np


FEATURE_COLUMNS: List[str] = [
    "total_classes_so_far",
    "classes_attended",
    "current_percentage",
    "consecutive_absences",
    "attendance_last_10",
    "attendance_trend",
    "remaining_classes",
    "subject_attendance",
    "overall_attendance",
]

TARGET_COLUMN: str = "is_shortage"


def extract_features_from_records(
    records: list,
    total_planned: int = 50,
    all_subject_records: list = None
) -> Dict[str, float]:
    """
    Extracts the official ML feature dictionary from a list of AttendanceRecord
    objects for a student in a specific subject.

    Args:
        records: AttendanceRecord objects for this student & subject, sorted by date & slot.
        total_planned: Total classes planned in the semester for this subject.
        all_subject_records: Optional list of all records across all subjects for the student.

    Returns:
        Dict mapping feature names to numerical values.
    """
    if not records:
        return {
            "total_classes_so_far": 0,
            "classes_attended": 0,
            "current_percentage": 100.0,
            "consecutive_absences": 0,
            "attendance_last_10": 100.0,
            "attendance_trend": 0.0,
            "remaining_classes": total_planned,
            "subject_attendance": 100.0,
            "overall_attendance": 100.0,
        }

    # Sort chronologically
    sorted_records = sorted(records, key=lambda r: (r.date, r.session_slot))
    total_so_far = len(sorted_records)
    attended_so_far = sum(1 for r in sorted_records if r.status in ("present", "late"))
    current_pct = round((attended_so_far / total_so_far) * 100, 2) if total_so_far > 0 else 100.0

    # Consecutive absences immediately prior to the latest record
    consec = 0
    for r in reversed(sorted_records):
        if r.status == "absent":
            consec += 1
        else:
            break

    # Attendance in the last 10 classes
    window = sorted_records[-10:]
    window_attended = sum(1 for r in window if r.status in ("present", "late"))
    attendance_last_10 = round((window_attended / len(window)) * 100, 2) if window else current_pct

    # Attendance trend (last 10 vs overall)
    trend = round(attendance_last_10 - current_pct, 2)

    # Remaining classes
    remaining = max(0, total_planned - total_so_far)

    # Cross-subject overall attendance
    if all_subject_records:
        all_tot = len(all_subject_records)
        all_att = sum(1 for r in all_subject_records if r.status in ("present", "late"))
        overall_pct = round((all_att / all_tot) * 100, 2) if all_tot > 0 else current_pct
    else:
        overall_pct = current_pct

    return {
        "total_classes_so_far": total_so_far,
        "classes_attended": attended_so_far,
        "current_percentage": current_pct,
        "consecutive_absences": consec,
        "attendance_last_10": attendance_last_10,
        "attendance_trend": trend,
        "remaining_classes": remaining,
        "subject_attendance": current_pct,
        "overall_attendance": overall_pct,
    }
