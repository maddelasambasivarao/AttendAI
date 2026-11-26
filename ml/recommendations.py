"""
ml/recommendations.py – Actionable Recommendation Engine for AttendAI.

Calculates:
  1. Exact number of consecutive classes a student must attend to reach or restore >= 75% attendance.
  2. Maximum attainable attendance percentage assuming 100% attendance in all remaining classes.
  3. Safe absences buffer (number of classes a student can afford to miss while staying >= 75%).
  4. Mathematical impossibility flags when even perfect future attendance cannot achieve 75%.
  5. Multi-stakeholder recommendations tailored for the Student, Faculty, and Academic Advisor.
"""

import math
from typing import Dict, List, Any


def calculate_attendance_recovery(
    total_conducted: int,
    classes_attended: int,
    remaining_classes: int,
    target_threshold: float = 75.0
) -> Dict[str, Any]:
    """
    Computes exact mathematical attendance recovery metrics.

    Formulas:
      1. Consecutive classes needed to reach target threshold T (e.g. 0.75):
         (Attended + x) / (Conducted + x) >= T
         x * (1 - T) >= T * Conducted - Attended
         x >= (T * Conducted - Attended) / (1 - T)
         For T = 0.75: x >= (0.75 * Conducted - Attended) / 0.25 = 3 * Conducted - 4 * Attended

      2. Maximum additional misses while staying >= target threshold T:
         (Attended + Remaining - misses) / (Conducted + Remaining) >= T
         misses <= (Attended + Remaining) - T * (Conducted + Remaining)
         max_additional_misses = floor((Attended + Remaining) - T * (Conducted + Remaining))
         (NOTE: Strictly NO division by (1 - threshold) because total semester classes are fixed)
    """
    t_ratio = target_threshold / 100.0
    current_pct = round((classes_attended / total_conducted * 100), 2) if total_conducted > 0 else 100.0
    total_semester_classes = total_conducted + remaining_classes

    # Maximum possible final attendance if student attends 100% of remaining classes
    if total_semester_classes > 0:
        max_possible_pct = round(
            ((classes_attended + remaining_classes) / total_semester_classes) * 100, 2
        )
    else:
        max_possible_pct = current_pct

    # Consecutive classes needed to reach target_threshold
    if current_pct >= target_threshold:
        classes_needed = 0
    else:
        # Needed: (T * conducted - attended) / (1 - T)
        raw_needed = (t_ratio * total_conducted - classes_attended) / (1.0 - t_ratio)
        classes_needed = max(0, math.ceil(raw_needed))

    # Safe skips / max additional misses allowed:
    # Exact formula: floor(attended + remaining - threshold * (conducted + remaining))
    # Strictly NO division by (1 - threshold).
    if total_semester_classes > 0:
        raw_skips = (classes_attended + remaining_classes) - (t_ratio * total_semester_classes)
        safe_skips = max(0, math.floor(raw_skips))
    else:
        safe_skips = 0

    # Feasibility check
    is_recoverable = max_possible_pct >= target_threshold
    can_recover_in_remaining = classes_needed <= remaining_classes if classes_needed > 0 else True

    return {
        "current_percentage": current_pct,
        "classes_conducted": total_conducted,
        "classes_attended": classes_attended,
        "remaining_classes": remaining_classes,
        "total_semester_classes": total_semester_classes,
        "classes_needed_for_target": classes_needed,
        "max_possible_percentage": max_possible_pct,
        "safe_skips_remaining": safe_skips,
        "max_additional_misses": safe_skips,
        "is_recoverable": is_recoverable,
        "can_recover_in_remaining": can_recover_in_remaining,
        "target_threshold": target_threshold,
    }


def generate_recommendations(
    features: dict,
    risk_level: str = "Medium",
    risk_probability: float = 0.5,
    threshold: float = 75.0
) -> List[str]:
    """
    Generates structured, clear, and actionable improvement recommendations
    based on mathematical recovery analysis and student risk patterns.

    Args:
        features: Feature dict containing total_classes_so_far, classes_attended,
                  remaining_classes, current_percentage, consecutive_absences, etc.
        risk_level: 'High', 'Medium', or 'Low'
        risk_probability: Predicted probability of falling below threshold (0.0 to 1.0)
        threshold: Target attendance percentage (default 75.0)

    Returns:
        List of actionable recommendation strings.
    """
    conducted   = int(features.get("total_classes_so_far", features.get("total_classes", 0)))
    attended    = int(features.get("classes_attended", 0))
    current_pct = float(features.get("current_percentage", features.get("overall_attendance_pct", 0.0)))
    remaining   = int(features.get("remaining_classes", 20))
    consec      = int(features.get("consecutive_absences", 0))
    trend       = float(features.get("attendance_trend", features.get("recent_trend", 0.0)))
    last_10     = float(features.get("attendance_last_10", current_pct))

    recovery = calculate_attendance_recovery(
        total_conducted=conducted,
        classes_attended=attended,
        remaining_classes=remaining,
        target_threshold=threshold
    )

    needed = recovery["classes_needed_for_target"]
    max_poss = recovery["max_possible_percentage"]
    safe_skips = recovery["safe_skips_remaining"]
    is_recoverable = recovery["is_recoverable"]

    tips = []

    # ── 1. Critical Mathematical Status ──────────────────────────────────────
    if not is_recoverable:
        tips.append(
            f"[CRITICAL SHORTAGE] Even with 100% attendance in all {remaining} remaining classes, "
            f"your maximum possible attendance is {max_poss:.1f}%, which is below the mandatory {threshold}% threshold. "
            f"Official medical condonation or HOD approval is mandatory to avoid detention."
        )
    elif needed > 0:
        if needed <= remaining:
            tips.append(
                f"[ATTENDANCE TARGET] You must attend the next {needed} consecutive class(es) without absence "
                f"to restore your attendance to {threshold}%. You have {remaining} class(es) remaining."
            )
        else:
            tips.append(
                f"[URGENT ACTION] Restoring attendance to {threshold}% requires {needed} classes, but only {remaining} "
                f"regular sessions remain. Request compensatory lectures or remedial assignments immediately."
            )
    else:
        tips.append(
            f"[ON TRACK] Your attendance is currently {current_pct:.1f}% (above the {threshold}% minimum). "
            f"You have a buffer of up to {safe_skips} class absence(s) across the remaining {remaining} sessions."
        )

    # ── 2. Consecutive Absences & Recent Trend Warnings ──────────────────────
    if consec >= 3:
        tips.append(
            f"[ABSENCE STREAK] You have missed {consec} class session(s) in a row. "
            f"Extended absence streaks accelerate detention risk. Submit leave verification or doctor's note promptly."
        )

    if trend < -5.0:
        tips.append(
            f"[NEGATIVE TRAJECTORY] Your recent 10-class attendance ({last_10:.1f}%) is {abs(trend):.1f}% lower than your "
            f"earlier performance. Break this downward slip immediately by attending all upcoming sessions."
        )
    elif trend > 5.0:
        tips.append(
            f"[POSITIVE RECOVERY] Your recent attendance has improved by +{trend:.1f}%. Keep up this consistent effort!"
        )

    # ── 3. Stakeholder Role-Specific Guidance ────────────────────────────────
    if risk_level == "High" or risk_probability >= 0.65:
        tips.append(
            "[ADVISOR INTERVENTION] Schedule an urgent meeting with your faculty mentor. "
            "Formal notification will be dispatched to academic council."
        )
        tips.append(
            "[REMEDIAL ACTION] Enroll in peer study groups or make-up tutorial sessions for topics missed during absences."
        )
    elif risk_level == "Medium" or risk_probability >= 0.35:
        tips.append(
            "[PREVENTIVE ACTION] Set calendar reminders for daily timetable slots and avoid unexcused absences on Mondays and Fridays."
        )

    return tips
