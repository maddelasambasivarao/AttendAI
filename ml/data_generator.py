"""
ml/data_generator.py – Realistic Historical Attendance Snapshot Dataset Generator.

Objective:
  Simulate realistic student attendance trajectories across an entire semester,
  record multiple observation snapshots at progressive checkpoints, and label
  each snapshot with the ground-truth final outcome (whether final attendance < 75%).

Key Design Principles:
  1. Multiple Snapshots: Observation checkpoints across the semester (e.g., classes 10, 20, 30, 40).
  2. Zero Data Leakage: All features at snapshot T use ONLY information available at class T.
     Future attendance (T+1 to N) is strictly used ONLY to compute the final label.
  3. Realistic Student Archetypes:
     - High Attenders (Regular, 85-98%)
     - Steady Moderate (75-84%)
     - Borderline / At-Risk (65-74%)
     - Declining / Fatigue (starts strong, drops later)
     - Chronic Absentee / Critical (<60% with absence streaks)
  4. Explicit Synthetic Labeling:
     Every record is explicitly tagged as 'synthetic_simulation', stored in
     'dataset/synthetic_attendance_snapshots.csv' separate from any production database.
"""

import os
from typing import List, Dict, Tuple
import numpy as np
import pandas as pd


DATASET_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "dataset")
DEFAULT_DATASET_PATH = os.path.join(DATASET_DIR, "synthetic_attendance_snapshots.csv")


def generate_student_trajectory(
    archetype: str,
    total_classes: int = 50,
    rng: np.random.Generator = None
) -> np.ndarray:
    """
    Simulates a sequence of attendance events (1=present, 0=absent) for one student
    in one subject over total_classes sessions.
    """
    if rng is None:
        rng = np.random.default_rng()

    trajectory = np.zeros(total_classes, dtype=int)

    if archetype == "high_attender":
        # Baseline probability: 90% - 98%
        base_p = rng.uniform(0.90, 0.98)
        trajectory = (rng.uniform(0, 1, size=total_classes) < base_p).astype(int)

    elif archetype == "steady_moderate":
        # Baseline probability: 78% - 85%
        base_p = rng.uniform(0.78, 0.85)
        trajectory = (rng.uniform(0, 1, size=total_classes) < base_p).astype(int)

    elif archetype == "borderline_at_risk":
        # Baseline probability: 67% - 74% (fluctuates around the 75% boundary)
        base_p = rng.uniform(0.67, 0.74)
        trajectory = (rng.uniform(0, 1, size=total_classes) < base_p).astype(int)

    elif archetype == "declining_trend":
        # Starts strong (85-90%) in first 40% of classes, drops to 45-60% later
        split_pt = int(total_classes * 0.4)
        p_early = rng.uniform(0.85, 0.92)
        p_late  = rng.uniform(0.45, 0.60)
        trajectory[:split_pt] = (rng.uniform(0, 1, size=split_pt) < p_early).astype(int)
        trajectory[split_pt:] = (rng.uniform(0, 1, size=total_classes - split_pt) < p_late).astype(int)

    elif archetype == "improving_trend":
        # Starts poorly (45-60%), then after intervention improves to 80-90%
        split_pt = int(total_classes * 0.4)
        p_early = rng.uniform(0.48, 0.60)
        p_late  = rng.uniform(0.80, 0.90)
        trajectory[:split_pt] = (rng.uniform(0, 1, size=split_pt) < p_early).astype(int)
        trajectory[split_pt:] = (rng.uniform(0, 1, size=total_classes - split_pt) < p_late).astype(int)

    elif archetype == "chronic_absentee":
        # Low overall attendance (35-55%) with 3-7 consecutive absence streaks
        base_p = rng.uniform(0.35, 0.55)
        trajectory = (rng.uniform(0, 1, size=total_classes) < base_p).astype(int)
        # Inject one or two absence streaks
        streak_start = rng.integers(5, max(6, total_classes - 10))
        streak_len   = rng.integers(4, 8)
        trajectory[streak_start : min(total_classes, streak_start + streak_len)] = 0

    else:
        # Generic random baseline
        base_p = rng.uniform(0.60, 0.90)
        trajectory = (rng.uniform(0, 1, size=total_classes) < base_p).astype(int)

    return trajectory


def extract_snapshot_features(
    trajectory: np.ndarray,
    snapshot_idx: int,
    total_planned: int,
    cross_subject_pct: float = None
) -> Dict[str, float]:
    """
    Extracts features at a specific class checkpoint.
    STRICT ZERO DATA LEAKAGE: Uses only trajectory[:snapshot_idx].
    """
    history = trajectory[:snapshot_idx]
    classes_so_far = len(history)
    classes_attended = int(np.sum(history))
    current_percentage = round((classes_attended / classes_so_far) * 100, 2) if classes_so_far > 0 else 0.0

    # Consecutive absences immediately prior to snapshot
    consec_absences = 0
    for val in reversed(history):
        if val == 0:
            consec_absences += 1
        else:
            break

    # Attendance in last 10 classes
    window_len = min(10, classes_so_far)
    last_10_slice = history[-window_len:]
    attendance_last_10 = round((np.sum(last_10_slice) / window_len) * 100, 2) if window_len > 0 else current_percentage

    # Previous attendance trend (recent 10 vs overall so far)
    attendance_trend = round(attendance_last_10 - current_percentage, 2)

    # Remaining scheduled classes in the semester
    remaining_classes = max(0, total_planned - classes_so_far)

    # Subject-wise attendance so far
    subject_attendance = current_percentage

    # Overall attendance across subjects so far (defaults to current if not provided)
    overall_attendance = cross_subject_pct if cross_subject_pct is not None else current_percentage

    return {
        "total_classes_so_far": classes_so_far,
        "classes_attended": classes_attended,
        "current_percentage": current_percentage,
        "consecutive_absences": consec_absences,
        "attendance_last_10": attendance_last_10,
        "attendance_trend": attendance_trend,
        "remaining_classes": remaining_classes,
        "subject_attendance": subject_attendance,
        "overall_attendance": overall_attendance,
    }


def generate_attendance_dataset(
    n_students: int = 400,
    classes_per_subject: int = 50,
    snapshot_checkpoints: List[int] = None,
    threshold: float = 75.0,
    seed: int = 42,
    output_path: str = None
) -> pd.DataFrame:
    """
    Generates a full synthetic attendance dataset with multiple snapshots per student
    and subject, strictly avoiding data leakage.

    Args:
        n_students: Number of distinct synthetic students to simulate.
        classes_per_subject: Total classes scheduled for each subject in the semester.
        snapshot_checkpoints: List of class numbers at which snapshots are taken.
        threshold: Configurable minimum attendance requirement (default 75.0%).
        seed: Random seed for reproducibility.
        output_path: Path to save the synthetic CSV file.

    Returns:
        pd.DataFrame containing all snapshot rows.
    """
    rng = np.random.default_rng(seed)

    if snapshot_checkpoints is None:
        # Progressive checkpoints at 20%, 40%, 60%, and 80% through the semester
        snapshot_checkpoints = [10, 20, 30, 40]

    subjects = [
        {"code": "CS601", "name": "Machine Learning"},
        {"code": "CS602", "name": "Database Systems"},
        {"code": "CS603", "name": "Computer Networks"},
        {"code": "MA601", "name": "Applied Mathematics"},
    ]

    archetype_choices = [
        "high_attender",
        "steady_moderate",
        "borderline_at_risk",
        "declining_trend",
        "improving_trend",
        "chronic_absentee"
    ]
    # Realistic distribution of student attendance behaviors
    archetype_probs = [0.42, 0.23, 0.15, 0.08, 0.05, 0.07]

    rows = []

    for s_idx in range(1, n_students + 1):
        student_id = f"SYNTH_STU_{s_idx:04d}"
        # Assign an archetype to this student with slight per-subject noise
        primary_archetype = rng.choice(archetype_choices, p=archetype_probs)

        # Generate full-semester trajectories for all subjects
        student_trajectories = {}
        final_pcts = {}

        for subj in subjects:
            # 80% chance student maintains their primary archetype, 20% random variation
            subj_archetype = primary_archetype if rng.uniform() < 0.80 else rng.choice(archetype_choices, p=archetype_probs)
            traj = generate_student_trajectory(subj_archetype, total_classes=classes_per_subject, rng=rng)
            student_trajectories[subj["code"]] = traj

            # Final ground-truth attendance across the ENTIRE semester
            actual_final_pct = round((np.sum(traj) / classes_per_subject) * 100, 2)
            final_pcts[subj["code"]] = actual_final_pct

        # For each snapshot checkpoint (e.g. class 10, 20, 30, 40)
        for chk in snapshot_checkpoints:
            if chk > classes_per_subject:
                continue

            # Calculate overall cross-subject attendance so far at this checkpoint
            all_attended_so_far = sum(np.sum(student_trajectories[s["code"]][:chk]) for s in subjects)
            all_conducted_so_far = chk * len(subjects)
            cross_subject_pct = round((all_attended_so_far / all_conducted_so_far) * 100, 2)

            for subj in subjects:
                traj = student_trajectories[subj["code"]]
                feats = extract_snapshot_features(
                    trajectory=traj,
                    snapshot_idx=chk,
                    total_planned=classes_per_subject,
                    cross_subject_pct=cross_subject_pct
                )

                actual_final_pct = final_pcts[subj["code"]]
                # Target: Will the student fall below the configured threshold by semester end?
                is_shortage = 1 if actual_final_pct < threshold else 0

                row = {
                    "student_id": student_id,
                    "subject_code": subj["code"],
                    "snapshot_class_num": chk,
                    **feats,
                    "actual_final_percentage": actual_final_pct,
                    "threshold_used": threshold,
                    "is_shortage": is_shortage,
                    "data_source": "synthetic_simulation",
                }
                rows.append(row)

    df = pd.DataFrame(rows)

    if output_path is None:
        output_path = DEFAULT_DATASET_PATH

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    df.to_csv(output_path, index=False)

    # Also write a clear documentation artifact describing the synthetic dataset
    meta_path = os.path.join(os.path.dirname(output_path), "DATASET_METADATA.md")
    with open(meta_path, "w", encoding="utf-8") as f:
        f.write(
            f"# AttendAI Synthetic Attendance Snapshot Dataset\n\n"
            f"**Data Type**: Synthetic Benchmark Simulation (Strictly Separated from Real Student Records)\n"
            f"**Generation Date**: Auto-generated for Machine Learning Training\n"
            f"**Total Records**: {len(df):,} snapshots\n"
            f"**Unique Students**: {n_students:,}\n"
            f"**Subjects**: {len(subjects)} ({', '.join(s['code'] for s in subjects)})\n"
            f"**Checkpoints**: Classes {snapshot_checkpoints}\n"
            f"**Configurable Threshold**: {threshold}%\n"
            f"**Shortage Class Balance**: {df['is_shortage'].mean()*100:.2f}% positive (below threshold)\n\n"
            f"## Zero Data Leakage Policy\n"
            f"Each snapshot at checkpoint $T$ computes features strictly using information from $t \\le T$.\n"
            f"Future attendance ($t > T$) is used solely to construct the ground-truth target variable `is_shortage`.\n"
        )

    return df


if __name__ == "__main__":
    print("Generating AttendAI synthetic attendance dataset...")
    data = generate_attendance_dataset()
    print(f"Generated {len(data)} snapshots for {data['student_id'].nunique()} students.")
    print(f"Shortage rate: {data['is_shortage'].mean() * 100:.2f}%")
    print(f"Saved to: {DEFAULT_DATASET_PATH}")
