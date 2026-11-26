"""
ml/predict.py – Production inference pipeline for AttendAI Academic Risk Prediction.

Objective:
  Predict whether a student is likely to fall below the configurable minimum
  attendance requirement (default 75%) by the end of the semester.

Returns:
  - risk_probability (float 0.0 to 1.0)
  - risk_category ("Low", "Medium", "High")
  - is_at_risk (bool)
  - predicted_final_pct (float)
  - top_contributing_features (list of explaining features & human descriptions)
  - recommendations (actionable recovery guidance from recommendation engine)
"""

import os
import json
from typing import Dict, Any, Union, List
import numpy as np
import pandas as pd
import joblib

from ml.features import FEATURE_COLUMNS
from ml.data_prep import get_student_ml_features
from ml.recommendations import generate_recommendations, calculate_attendance_recovery


MODELS_DIR = os.path.join(os.path.dirname(__file__), "models")
_cached_pipeline = None
_cached_meta = None


def get_trained_pipeline(models_dir: str = None):
    """Loads and caches the best trained model pipeline."""
    global _cached_pipeline, _cached_meta

    if models_dir is None:
        models_dir = MODELS_DIR

    best_model_path = os.path.join(models_dir, "best_risk_model.joblib")
    meta_path       = os.path.join(models_dir, "model_meta.json")

    # Fallback to legacy path if best_risk_model doesn't exist
    if not os.path.exists(best_model_path):
        legacy_path = os.path.join(models_dir, "risk_classifier.joblib")
        if os.path.exists(legacy_path):
            best_model_path = legacy_path
        else:
            raise FileNotFoundError(
                f"Trained model not found at {best_model_path}. "
                "Run 'python -m ml.train' to train and save the model."
            )

    if _cached_pipeline is None:
        _cached_pipeline = joblib.load(best_model_path)
        if os.path.exists(meta_path):
            with open(meta_path, "r", encoding="utf-8") as f:
                _cached_meta = json.load(f)
        else:
            _cached_meta = {
                "version": "2.0.0",
                "best_model": "Unknown",
                "feature_columns": FEATURE_COLUMNS,
                "threshold": 75.0,
            }

    return _cached_pipeline, _cached_meta


def explain_top_features(
    features: Dict[str, Any],
    pipeline,
    feature_cols: List[str]
) -> List[Dict[str, Any]]:
    """
    Identifies and formats the top contributing factors driving the student's risk score.
    Combines feature weights with student-specific deviations from safe standards.
    """
    contributions = []

    current_pct = float(features.get("current_percentage", 100.0))
    consec      = int(features.get("consecutive_absences", 0))
    trend       = float(features.get("attendance_trend", 0.0))
    last_10     = float(features.get("attendance_last_10", current_pct))
    remaining   = int(features.get("remaining_classes", 20))
    classes_so_far = int(features.get("total_classes_so_far", 10))

    # Inspect pipeline classifier step
    clf = pipeline.named_steps.get("classifier") if hasattr(pipeline, "named_steps") else None

    # Calculate individual impact scores
    # Factor 1: Current percentage deficit
    if current_pct < 75.0:
        deficit = 75.0 - current_pct
        contributions.append({
            "feature": "current_percentage",
            "feature_label": "Current Attendance Percentage",
            "value": f"{current_pct:.1f}%",
            "impact_score": deficit * 1.5,
            "risk_direction": "Negative",
            "explanation": f"Current attendance ({current_pct:.1f}%) is {deficit:.1f}% below the 75% required baseline."
        })
    else:
        contributions.append({
            "feature": "current_percentage",
            "feature_label": "Current Attendance Percentage",
            "value": f"{current_pct:.1f}%",
            "impact_score": -((current_pct - 75.0) * 1.0),
            "risk_direction": "Positive",
            "explanation": f"Current attendance ({current_pct:.1f}%) is in good standing."
        })

    # Factor 2: Consecutive absences streak
    if consec >= 2:
        contributions.append({
            "feature": "consecutive_absences",
            "feature_label": "Consecutive Absences",
            "value": f"{consec} classes",
            "impact_score": consec * 8.0,
            "risk_direction": "Negative",
            "explanation": f"Student has missed {consec} class sessions in a row without present attendance."
        })

    # Factor 3: Recent attendance trend (last 10 vs overall)
    if trend < -3.0:
        contributions.append({
            "feature": "attendance_trend",
            "feature_label": "Attendance Trajectory / Trend",
            "value": f"{trend:+.1f}%",
            "impact_score": abs(trend) * 1.2,
            "risk_direction": "Negative",
            "explanation": f"Recent 10-class attendance is slipping by {abs(trend):.1f}% compared to overall semester rate."
        })
    elif trend > 5.0:
        contributions.append({
            "feature": "attendance_trend",
            "feature_label": "Attendance Trajectory / Trend",
            "value": f"{trend:+.1f}%",
            "impact_score": -trend * 0.8,
            "risk_direction": "Positive",
            "explanation": f"Recent attendance shows an upward recovery trajectory (+{trend:.1f}%)."
        })

    # Factor 4: Recent 10-class performance
    if last_10 < 70.0:
        contributions.append({
            "feature": "attendance_last_10",
            "feature_label": "Recent Attendance (Last 10 Classes)",
            "value": f"{last_10:.1f}%",
            "impact_score": (75.0 - last_10) * 1.3,
            "risk_direction": "Negative",
            "explanation": f"Low attendance in the recent 10-class window ({last_10:.1f}%)."
        })

    # Factor 5: Remaining classes recovery horizon
    if remaining <= 12 and current_pct < 75.0:
        contributions.append({
            "feature": "remaining_classes",
            "feature_label": "Remaining Class Horizon",
            "value": f"{remaining} remaining",
            "impact_score": (15 - remaining) * 3.0,
            "risk_direction": "Negative",
            "explanation": f"Only {remaining} classes remain in the semester, significantly shrinking the mathematical recovery window."
        })

    # Sort descending by impact score
    contributions.sort(key=lambda x: x["impact_score"], reverse=True)
    return contributions[:4]


def predict_risk(
    student_input: Union[int, Dict[str, Any], pd.DataFrame],
    threshold: float = 75.0,
    subject_id: int = None
) -> Dict[str, Any]:
    """
    Predicts attendance shortage risk for a student.

    Args:
        student_input: Either an integer student_id (queries SQLite database),
                       OR a dictionary containing the feature values,
                       OR a single-row DataFrame.
        threshold: Target attendance requirement (default 75.0%).
        subject_id: Optional subject ID filter when querying a student by ID.

    Returns:
        Dict containing:
          - student_id: int or str
          - risk_probability: float (0.0 to 1.0)
          - risk_category: "Low", "Medium", "High"
          - is_at_risk: bool (True if probability >= 0.50 or category != "Low")
          - current_attendance_pct: float
          - predicted_final_pct: float
          - top_contributing_features: list of contributing factor dicts
          - recommendations: list of actionable improvement tips
          - recovery_metrics: mathematical recovery breakdown
          - model_version: str
    """
    # 1. Resolve features
    if isinstance(student_input, int):
        features = get_student_ml_features(student_input, subject_id=subject_id)
        student_identifier = student_input
    elif isinstance(student_input, dict):
        features = student_input.copy()
        student_identifier = features.get("student_id", "Manual_Query")
    elif isinstance(student_input, pd.DataFrame):
        features = student_input.iloc[0].to_dict()
        student_identifier = features.get("student_id", "Manual_Query")
    else:
        raise TypeError(f"Unsupported input type {type(student_input)}. Expected int, dict, or pd.DataFrame.")

    # 2. Extract standard feature row
    feature_row = {}
    for col in FEATURE_COLUMNS:
        feature_row[col] = float(features.get(col, 0.0))

    X = pd.DataFrame([feature_row])[FEATURE_COLUMNS]

    # 3. Model Inference
    try:
        pipeline, meta = get_trained_pipeline()
        probabilities = pipeline.predict_proba(X)[0]

        # In binary classification, probability of class 1 (Shortage < 75%)
        if len(probabilities) == 2:
            risk_prob = float(probabilities[1])
        else:
            # Multi-class fallback
            classes = list(getattr(pipeline, "classes_", [0, 1]))
            if 1 in classes:
                risk_prob = float(probabilities[classes.index(1)])
            else:
                risk_prob = float(probabilities[-1])

        model_name = meta.get("best_model", "Trained Classifier")
        model_ver  = meta.get("version", "2.0.0")

    except Exception:
        # Graceful rule-based fallback if model not loaded
        current_pct = feature_row["current_percentage"]
        if current_pct < 60.0:
            risk_prob = 0.88
        elif current_pct < 75.0:
            risk_prob = 0.62
        else:
            risk_prob = 0.12
        model_name = "Rule-based Fallback"
        model_ver  = "1.0.0-fallback"

    # 4. Risk Category Tiering
    if risk_prob >= 0.65:
        risk_category = "High"
    elif risk_prob >= 0.35:
        risk_category = "Medium"
    else:
        risk_category = "Low"

    is_at_risk = risk_prob >= 0.50

    # 5. Extrapolated Final Attendance Percentage
    current_pct    = feature_row["current_percentage"]
    trend          = feature_row["attendance_trend"]
    conducted      = int(feature_row["total_classes_so_far"])
    attended       = int(feature_row["classes_attended"])
    remaining      = int(feature_row["remaining_classes"])
    total_semester = conducted + remaining

    if total_semester > 0:
        # Estimated attendance rate in remaining classes based on recent trajectory
        recent_run_rate = max(0.0, min(100.0, current_pct + 0.4 * trend)) / 100.0
        predicted_remaining_attended = remaining * recent_run_rate
        predicted_final_pct = round(((attended + predicted_remaining_attended) / total_semester) * 100, 2)
    else:
        predicted_final_pct = current_pct

    # 6. Mathematical Recovery Plan
    recovery_metrics = calculate_attendance_recovery(
        total_conducted=conducted,
        classes_attended=attended,
        remaining_classes=remaining,
        target_threshold=threshold
    )

    # 7. Explain Top Contributing Features
    top_features = explain_top_features(features, pipeline=_cached_pipeline, feature_cols=FEATURE_COLUMNS)

    # 8. Actionable Recommendations
    recommendations = generate_recommendations(
        features=features,
        risk_level=risk_category,
        risk_probability=risk_prob,
        threshold=threshold
    )

    return {
        "student_id": student_identifier,
        "risk_probability": round(risk_prob, 4),
        "risk_category": risk_category,
        "is_at_risk": is_at_risk,
        "current_attendance_pct": round(current_pct, 2),
        "predicted_final_pct": round(predicted_final_pct, 2),
        "threshold": threshold,
        "top_contributing_features": top_features,
        "recommendations": recommendations,
        "recovery_plan": recovery_metrics,
        "model_version": model_ver,
        "model_name": model_name,
        "features": feature_row,
    }


# Convenience alias for external modules
predict_student_risk = predict_risk


if __name__ == "__main__":
    # Self-test sample prediction
    sample_student = {
        "total_classes_so_far": 25,
        "classes_attended": 16,
        "current_percentage": 64.0,
        "consecutive_absences": 3,
        "attendance_last_10": 50.0,
        "attendance_trend": -14.0,
        "remaining_classes": 25,
        "subject_attendance": 64.0,
        "overall_attendance": 66.0,
    }

    print("Running sample risk prediction...")
    res = predict_risk(sample_student)
    print(f"Risk Category:    {res['risk_category']} (Probability: {res['risk_probability']*100:.1f}%)")
    print(f"Current %:        {res['current_attendance_pct']}% -> Predicted Final: {res['predicted_final_pct']}%")
    print("\nTop Contributing Features:")
    for f in res["top_contributing_features"]:
        print(f" - {f['feature_label']}: {f['value']} ({f['explanation']})")
    print("\nRecommendations:")
    for r in res["recommendations"]:
        print(f" * {r}")
