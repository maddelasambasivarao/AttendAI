"""
tests/test_ml.py – Comprehensive unit and integration tests for AttendAI ML Pipeline.

Tests:
  1. Synthetic dataset generation with multiple snapshots per student and explicit synthetic labeling.
  2. Zero data leakage verification and student-grouped train/test splitting.
  3. Class imbalance handling with balanced sample weighting.
  4. Candidate models training, comparison, and evaluation (Logistic Regression, Decision Tree, Random Forest).
  5. Empirical metric computation: Accuracy, Precision, Recall, F1, Confusion Matrix, and ROC-AUC.
  6. Model persistence with Joblib and metrics export to JSON.
  7. Inference via ml.predict.predict_risk for High, Medium, and Low risk students.
  8. Extraction of top contributing features for explainable predictions.
  9. Mathematical attendance recovery calculations and feasibility flags.
  10. Database-integrated student prediction from SQLite records.
"""

import os
import json
import tempfile
import pytest
import pandas as pd
import numpy as np

from ml.features import FEATURE_COLUMNS, TARGET_COLUMN
from ml.data_generator import (
    generate_attendance_dataset,
    generate_student_trajectory,
    extract_snapshot_features,
    DEFAULT_DATASET_PATH
)
from ml.train import (
    split_grouped_dataset,
    get_candidate_models,
    evaluate_model_performance,
    train_and_compare_models
)
from ml.predict import predict_risk, get_trained_pipeline
from ml.recommendations import calculate_attendance_recovery, generate_recommendations
from database.models import User, Faculty, Semester, Subject, Student, AttendanceRecord
from datetime import date


# ─────────────────────────────────────────────────────────────────────────────
# 1. Dataset Generation & Zero Data Leakage
# ─────────────────────────────────────────────────────────────────────────────
def test_synthetic_dataset_generation_and_labeling():
    """Dataset is generated with multiple snapshots per student and clearly marked as synthetic."""
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_path = os.path.join(tmpdir, "test_snapshots.csv")
        df = generate_attendance_dataset(
            n_students=20,
            classes_per_subject=40,
            snapshot_checkpoints=[10, 20, 30],
            threshold=75.0,
            output_path=csv_path
        )

        assert os.path.exists(csv_path)
        assert len(df) == 20 * 4 * 3  # 20 students * 4 subjects * 3 checkpoints = 240 rows
        assert set(FEATURE_COLUMNS).issubset(set(df.columns))
        assert TARGET_COLUMN in df.columns
        assert set(df[TARGET_COLUMN].unique()).issubset({0, 1})

        # Explicit synthetic tagging
        assert "data_source" in df.columns
        assert (df["data_source"] == "synthetic_simulation").all()

        # Check metadata file generated
        meta_file = os.path.join(tmpdir, "DATASET_METADATA.md")
        assert os.path.exists(meta_file)
        with open(meta_file, "r", encoding="utf-8") as f:
            content = f.read()
            assert "Synthetic Benchmark Simulation" in content
            assert "Zero Data Leakage Policy" in content


def test_zero_data_leakage_in_snapshots():
    """Features at snapshot T strictly use classes <= T; target uses entire semester."""
    rng = np.random.default_rng(42)
    trajectory = generate_student_trajectory("declining_trend", total_classes=50, rng=rng)

    # Snapshot at class 20
    feats_20 = extract_snapshot_features(trajectory, snapshot_idx=20, total_planned=50)
    assert feats_20["total_classes_so_far"] == 20
    assert feats_20["classes_attended"] == int(np.sum(trajectory[:20]))
    assert feats_20["remaining_classes"] == 30

    # Snapshot at class 35
    feats_35 = extract_snapshot_features(trajectory, snapshot_idx=35, total_planned=50)
    assert feats_35["total_classes_so_far"] == 35
    assert feats_35["classes_attended"] == int(np.sum(trajectory[:35]))
    assert feats_35["remaining_classes"] == 15

    # Features at class 20 do NOT contain information from class 21 to 50
    assert feats_20["classes_attended"] <= feats_35["classes_attended"]


def test_student_grouped_train_test_split():
    """Student-grouped train/test split ensures zero student leakage across splits."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_csv = os.path.join(tmpdir, "grouped_test.csv")
        df = generate_attendance_dataset(
            n_students=30,
            classes_per_subject=40,
            snapshot_checkpoints=[10, 20, 30],
            seed=101,
            output_path=tmp_csv
        )

        X_train, X_test, y_train, y_test, train_idx, test_idx = split_grouped_dataset(df, test_size=0.20)

        train_students = set(df.iloc[train_idx]["student_id"])
        test_students  = set(df.iloc[test_idx]["student_id"])

        # Overlap must be strictly empty set
        assert train_students.isdisjoint(test_students)
        assert len(train_students) > 0
        assert len(test_students) > 0
        assert len(train_students) + len(test_students) == df["student_id"].nunique()


# ─────────────────────────────────────────────────────────────────────────────
# 2. Candidate Models, Training & Evaluation Metrics
# ─────────────────────────────────────────────────────────────────────────────
def test_candidate_models_structure_and_class_weighting():
    """Verifies all 3 models are present with class_weight='balanced'."""
    models = get_candidate_models()
    assert "Logistic Regression" in models
    assert "Decision Tree" in models
    assert "Random Forest" in models

    for name, pipeline in models.items():
        clf = pipeline.named_steps["classifier"]
        assert clf.class_weight == "balanced"


def test_model_comparison_pipeline():
    """Trains and compares all 3 models and verifies all required evaluation metrics."""
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_path = os.path.join(tmpdir, "mini_dataset.csv")
        df = generate_attendance_dataset(
            n_students=40,
            classes_per_subject=40,
            snapshot_checkpoints=[10, 20, 30],
            output_path=csv_path
        )

        results = train_and_compare_models(dataset_path=csv_path, save_dir=tmpdir)

        assert results["best_model_name"] in ("Logistic Regression", "Decision Tree", "Random Forest")
        comparison = results["comparison"]

        for model_name in ("Logistic Regression", "Decision Tree", "Random Forest"):
            assert model_name in comparison
            m = comparison[model_name]
            # Empirical metrics
            assert 0.0 <= m["accuracy"] <= 1.0
            assert 0.0 <= m["precision"] <= 1.0
            assert 0.0 <= m["recall"] <= 1.0
            assert 0.0 <= m["f1_score"] <= 1.0
            assert 0.0 <= m["roc_auc"] <= 1.0

            # Confusion matrix
            cm = m["confusion_matrix"]
            assert len(cm) == 2
            assert len(cm[0]) == 2
            assert sum(cm[0]) + sum(cm[1]) > 0

        # Verify saved artifacts
        assert os.path.exists(os.path.join(tmpdir, "best_risk_model.joblib"))
        assert os.path.exists(os.path.join(tmpdir, "model_comparison.json"))
        assert os.path.exists(os.path.join(tmpdir, "model_metrics.json"))
        assert os.path.exists(os.path.join(tmpdir, "model_meta.json"))


def test_saved_model_artifacts_readable():
    """Verify saved model JSON metrics can be read and parsed."""
    metrics_path = os.path.join(os.path.dirname(__file__), "..", "ml", "models", "model_metrics.json")
    assert os.path.exists(metrics_path)

    with open(metrics_path, "r", encoding="utf-8") as f:
        metrics_data = json.load(f)

    assert "best_model_name" in metrics_data
    assert "metrics" in metrics_data
    assert "accuracy" in metrics_data["metrics"]
    assert "roc_auc" in metrics_data["metrics"]
    assert "f1_score" in metrics_data["metrics"]
    assert "feature_importances" in metrics_data


# ─────────────────────────────────────────────────────────────────────────────
# 3. Inference and Top Contributing Features
# ─────────────────────────────────────────────────────────────────────────────
def test_predict_risk_high_risk_profile():
    """Student with low attendance, absences streak and negative trend is classified High Risk."""
    high_risk_input = {
        "total_classes_so_far": 30,
        "classes_attended": 16,
        "current_percentage": 53.33,
        "consecutive_absences": 4,
        "attendance_last_10": 40.0,
        "attendance_trend": -13.33,
        "remaining_classes": 20,
        "subject_attendance": 53.33,
        "overall_attendance": 55.0,
    }

    res = predict_risk(high_risk_input)

    assert res["risk_category"] == "High"
    assert res["risk_probability"] >= 0.65
    assert res["is_at_risk"] is True
    assert res["current_attendance_pct"] == 53.33
    assert res["predicted_final_pct"] < 75.0

    # Top contributing features
    top_features = res["top_contributing_features"]
    assert len(top_features) > 0
    feature_keys = [f["feature"] for f in top_features]
    assert any(k in ("current_percentage", "consecutive_absences", "attendance_last_10", "attendance_trend") for k in feature_keys)

    # Actionable recommendations generated
    assert len(res["recommendations"]) > 0
    assert any("ATTENDANCE TARGET" in r or "CRITICAL SHORTAGE" in r or "ABSENCE STREAK" in r for r in res["recommendations"])


def test_predict_risk_low_risk_profile():
    """Student with consistent high attendance is classified Low Risk."""
    low_risk_input = {
        "total_classes_so_far": 30,
        "classes_attended": 28,
        "current_percentage": 93.33,
        "consecutive_absences": 0,
        "attendance_last_10": 100.0,
        "attendance_trend": 6.67,
        "remaining_classes": 20,
        "subject_attendance": 93.33,
        "overall_attendance": 91.0,
    }

    res = predict_risk(low_risk_input)

    assert res["risk_category"] == "Low"
    assert res["risk_probability"] < 0.35
    assert res["is_at_risk"] is False
    assert res["predicted_final_pct"] >= 75.0

    # Recommendations praise consistency and calculate safe buffer
    assert any("ON TRACK" in r for r in res["recommendations"])


# ─────────────────────────────────────────────────────────────────────────────
# 4. Mathematical Attendance Recovery Calculations
# ─────────────────────────────────────────────────────────────────────────────
def test_attendance_recovery_calculations():
    """Verify exact formulas for recovery classes needed and maximum possible percentage."""
    # Case A: Recoverable student (conducted=20, attended=12, remaining=30)
    # Target 75%: 3*20 - 4*12 = 60 - 48 = 12 classes needed
    rec_a = calculate_attendance_recovery(
        total_conducted=20, classes_attended=12, remaining_classes=30, target_threshold=75.0
    )
    assert rec_a["classes_needed_for_target"] == 12
    assert rec_a["is_recoverable"] is True
    assert rec_a["can_recover_in_remaining"] is True
    # Max possible: (12 + 30) / 50 * 100 = 84.0%
    assert rec_a["max_possible_percentage"] == 84.0

    # Case B: Mathematically impossible recovery (conducted=40, attended=15, remaining=10)
    # Total classes = 50. Max possible = (15 + 10) / 50 * 100 = 50.0% < 75.0%
    rec_b = calculate_attendance_recovery(
        total_conducted=40, classes_attended=15, remaining_classes=10, target_threshold=75.0
    )
    assert rec_b["is_recoverable"] is False
    assert rec_b["can_recover_in_remaining"] is False
    assert rec_b["max_possible_percentage"] == 50.0
    # Classes needed: 3*40 - 4*15 = 120 - 60 = 60 classes > 10 remaining
    assert rec_b["classes_needed_for_target"] == 60

    # Case C: Already >= 75% (conducted=30, attended=27, remaining=20)
    # Attended = 27 / 30 = 90%. Classes needed = 0
    rec_c = calculate_attendance_recovery(
        total_conducted=30, classes_attended=27, remaining_classes=20, target_threshold=75.0
    )
    assert rec_c["classes_needed_for_target"] == 0
    assert rec_c["safe_skips_remaining"] > 0
    assert rec_c["max_additional_misses"] > 0


def test_max_additional_misses_formula():
    """Verify max additional misses formula: floor(attended + remaining - threshold*(conducted+remaining)).
    Specifically tests 12/20 attended with 20 remaining at 75.0% threshold (expected: 2).
    """
    res = calculate_attendance_recovery(
        total_conducted=20, classes_attended=12, remaining_classes=20, target_threshold=75.0
    )
    # Attended=12, Remaining=20, Total=40. Target threshold=75% of 40 = 30.
    # Max misses = floor(12 + 20 - 0.75 * (20 + 20)) = floor(32 - 30) = 2.
    assert res["max_additional_misses"] == 2
    assert res["safe_skips_remaining"] == 2


# ─────────────────────────────────────────────────────────────────────────────
# 5. Database-Integrated Prediction
# ─────────────────────────────────────────────────────────────────────────────
def test_predict_risk_from_database(db):
    """Calling predict_risk(student_id) extracts features from SQLite and computes risk."""
    # Create test fixtures
    admin = User(username="ml_admin", email="ml_admin@test.com", role="admin")
    admin.set_password("Admin@123")
    db.session.add(admin)
    db.session.flush()

    fac = Faculty(user_id=admin.id, name="Dr. AI", department="CS", employee_id="F999")
    db.session.add(fac)

    sem = Semester(name="ML Sem", year=2025, is_active=True)
    db.session.add(sem)
    db.session.flush()

    sub = Subject(name="ML Theory", code="CS999", semester_id=sem.id, faculty_id=fac.id, total_classes_planned=40)
    db.session.add(sub)
    db.session.flush()

    # Student with 8 attendances: 3 present, 5 absent (37.5%)
    student = Student(
        student_id="STU_ML_TEST",
        roll_number="ML202501",
        name="Test ML Student",
        semester_id=sem.id
    )
    db.session.add(student)
    db.session.flush()

    student.enroll_in_subject(sub.id)

    dates = [date(2025, 9, i) for i in range(1, 9)]
    statuses = ["present", "present", "present", "absent", "absent", "absent", "absent", "absent"]
    for d, s in zip(dates, statuses):
        rec = AttendanceRecord(
            student_id=student.id,
            subject_id=sub.id,
            date=d,
            session_slot=1,
            status=s,
            marked_by=admin.id
        )
        db.session.add(rec)
    db.session.commit()

    # Predict risk directly using student.id
    res = predict_risk(student.id)

    assert res["student_id"] == student.id
    assert res["risk_category"] in ("Medium", "High")
    assert res["risk_probability"] >= 0.50
    assert res["current_attendance_pct"] == 37.5
    assert len(res["top_contributing_features"]) > 0
    assert len(res["recommendations"]) > 0
