"""
ml/train.py – Train, compare, and evaluate attendance risk classification models.

Models trained and compared:
  1. Logistic Regression (with StandardScaler & class_weight='balanced')
  2. Decision Tree Classifier (with class_weight='balanced')
  3. Random Forest Classifier (with class_weight='balanced')

Methodological Rigor:
  - Student-grouped train/test split (GroupShuffleSplit on student_id) ensures
    zero data leakage between observation snapshots.
  - Class imbalance handled via balanced sample weighting.
  - Comprehensive evaluation: Accuracy, Precision, Recall, F1-Score, Confusion Matrix, and ROC-AUC.
  - Best model persisted with Joblib; metrics and comparison saved to JSON.
"""

import os
import sys
import json
from typing import Dict, Any, Tuple
import numpy as np
import pandas as pd
import joblib

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sklearn.model_selection import GroupShuffleSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.tree import DecisionTreeClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, f1_score,
    roc_auc_score, confusion_matrix, classification_report
)

from ml.features import FEATURE_COLUMNS, TARGET_COLUMN
from ml.data_generator import generate_attendance_dataset, DEFAULT_DATASET_PATH


MODELS_DIR = os.path.join(os.path.dirname(__file__), "models")
MODEL_VERSION = "2.0.0"


def load_or_generate_dataset(dataset_path: str = None) -> pd.DataFrame:
    """Loads existing synthetic snapshot dataset or generates a new one if missing."""
    if dataset_path is None:
        dataset_path = DEFAULT_DATASET_PATH

    if not os.path.exists(dataset_path):
        print(f"Dataset not found at {dataset_path}. Generating benchmark dataset...")
        df = generate_attendance_dataset(output_path=dataset_path)
    else:
        df = pd.read_csv(dataset_path)
        print(f"Loaded {len(df):,} snapshots from {dataset_path}")

    return df


def split_grouped_dataset(
    df: pd.DataFrame,
    test_size: float = 0.20,
    random_state: int = 42
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series, np.ndarray, np.ndarray]:
    """
    Performs a student-grouped train/test split.
    All snapshots of any given student are kept strictly inside EITHER train OR test,
    guaranteeing zero student leakage across observation windows.
    """
    X = df[FEATURE_COLUMNS]
    y = df[TARGET_COLUMN]
    groups = df["student_id"]

    gss = GroupShuffleSplit(n_splits=1, test_size=test_size, random_state=random_state)
    train_idx, test_idx = next(gss.split(X, y, groups))

    X_train, X_test = X.iloc[train_idx], X.iloc[test_idx]
    y_train, y_test = y.iloc[train_idx], y.iloc[test_idx]

    # Verify zero student leakage
    train_students = set(groups.iloc[train_idx])
    test_students  = set(groups.iloc[test_idx])
    assert train_students.isdisjoint(test_students), "Data leakage detected: Student IDs overlap between train and test sets!"

    return X_train, X_test, y_train, y_test, train_idx, test_idx


def get_candidate_models() -> Dict[str, Pipeline]:
    """Builds scikit-learn Pipelines for candidate models with balanced class weighting."""
    return {
        "Logistic Regression": Pipeline([
            ("scaler", StandardScaler()),
            ("classifier", LogisticRegression(
                class_weight="balanced",
                max_iter=1000,
                random_state=42,
                solver="lbfgs"
            ))
        ]),
        "Decision Tree": Pipeline([
            ("classifier", DecisionTreeClassifier(
                max_depth=6,
                min_samples_leaf=5,
                class_weight="balanced",
                random_state=42
            ))
        ]),
        "Random Forest": Pipeline([
            ("classifier", RandomForestClassifier(
                n_estimators=150,
                max_depth=10,
                min_samples_leaf=3,
                class_weight="balanced",
                random_state=42,
                n_jobs=-1
            ))
        ])
    }


def evaluate_model_performance(model: Pipeline, X_test: pd.DataFrame, y_test: pd.Series) -> Dict[str, Any]:
    """Evaluates a trained model pipeline on test data across all required metrics."""
    y_pred = model.predict(X_test)
    y_prob = model.predict_proba(X_test)[:, 1] if hasattr(model, "predict_proba") else None

    acc = float(accuracy_score(y_test, y_pred))
    prec = float(precision_score(y_test, y_pred, zero_division=0))
    rec = float(recall_score(y_test, y_pred, zero_division=0))
    f1 = float(f1_score(y_test, y_pred, zero_division=0))
    roc_auc = float(roc_auc_score(y_test, y_prob)) if y_prob is not None else 0.0
    cm = confusion_matrix(y_test, y_pred).tolist()
    report = classification_report(y_test, y_pred, output_dict=True, zero_division=0)

    return {
        "accuracy": round(acc, 4),
        "precision": round(prec, 4),
        "recall": round(rec, 4),
        "f1_score": round(f1, 4),
        "roc_auc": round(roc_auc, 4),
        "confusion_matrix": cm,
        "classification_report": report
    }


def extract_feature_importances(model: Pipeline, feature_names: list) -> Dict[str, float]:
    """Extracts feature importances or standardized coefficients from the trained pipeline."""
    clf = model.named_steps.get("classifier")
    importances = {}

    if hasattr(clf, "feature_importances_"):
        # Tree-based importances
        for feat, imp in zip(feature_names, clf.feature_importances_):
            importances[feat] = round(float(imp), 4)
    elif hasattr(clf, "coef_"):
        # Normalized absolute coefficients for linear models
        coefs = np.abs(clf.coef_[0])
        total = np.sum(coefs) if np.sum(coefs) > 0 else 1.0
        normalized = coefs / total
        for feat, imp in zip(feature_names, normalized):
            importances[feat] = round(float(imp), 4)

    # Sort descending
    return dict(sorted(importances.items(), key=lambda x: x[1], reverse=True))


def train_and_compare_models(
    dataset_path: str = None,
    save_dir: str = None
) -> Dict[str, Any]:
    """
    Main training workflow:
      1. Loads synthetic snapshot dataset.
      2. Performs student-grouped train/test split.
      3. Trains and compares Logistic Regression, Decision Tree, and Random Forest.
      4. Selects best model (ranked by F1-Score on shortage class).
      5. Persists best model with Joblib and metrics as JSON.
    """
    if save_dir is None:
        save_dir = MODELS_DIR
    os.makedirs(save_dir, exist_ok=True)

    df = load_or_generate_dataset(dataset_path)

    # Student-grouped split
    X_train, X_test, y_train, y_test, train_idx, test_idx = split_grouped_dataset(df)
    n_train_students = df.iloc[train_idx]["student_id"].nunique()
    n_test_students  = df.iloc[test_idx]["student_id"].nunique()

    print("\n" + "=" * 70)
    print("  AttendAI – Machine Learning Model Training & Comparison")
    print("=" * 70)
    print(f"Total Snapshots:    {len(df):,} ({len(X_train):,} train, {len(X_test):,} test)")
    print(f"Students (Grouped): {n_train_students} train students, {n_test_students} test students (Zero Leakage)")
    print(f"Positive Class:     {y_train.sum():,} train shortages ({y_train.mean()*100:.1f}%), {y_test.sum():,} test shortages ({y_test.mean()*100:.1f}%)")
    print(f"Features ({len(FEATURE_COLUMNS)}):    {', '.join(FEATURE_COLUMNS)}")
    print("-" * 70)

    candidate_models = get_candidate_models()
    comparison_results = {}
    best_model_name = None
    best_f1 = -1.0
    best_pipeline = None

    print(f"{'Model Name':<22} | {'Accuracy':<8} | {'Precision':<9} | {'Recall':<8} | {'F1-Score':<8} | {'ROC-AUC':<8}")
    print("-" * 70)

    for name, pipeline in candidate_models.items():
        # Fit model on training set
        pipeline.fit(X_train, y_train)

        # Evaluate strictly on held-out test set
        metrics = evaluate_model_performance(pipeline, X_test, y_test)
        comparison_results[name] = metrics

        print(
            f"{name:<22} | {metrics['accuracy']*100:>7.2f}% | "
            f"{metrics['precision']:>9.4f} | {metrics['recall']:>8.4f} | "
            f"{metrics['f1_score']:>8.4f} | {metrics['roc_auc']:>8.4f}"
        )

        # Rank by F1-Score (balances precision and recall for minority shortage class)
        if metrics["f1_score"] > best_f1:
            best_f1 = metrics["f1_score"]
            best_model_name = name
            best_pipeline = pipeline

    print("-" * 70)
    print(f">> Best Model Selected: {best_model_name} (Test F1-Score: {best_f1:.4f})")

    # Extract feature importances of best model
    best_feat_importances = extract_feature_importances(best_pipeline, FEATURE_COLUMNS)

    # ── Save Best Model & JSON Artifacts ─────────────────────────────────────
    best_model_path   = os.path.join(save_dir, "best_risk_model.joblib")
    legacy_model_path = os.path.join(save_dir, "risk_classifier.joblib")  # for backward compatibility
    comparison_path   = os.path.join(save_dir, "model_comparison.json")
    metrics_path      = os.path.join(save_dir, "model_metrics.json")
    meta_path         = os.path.join(save_dir, "model_meta.json")

    joblib.dump(best_pipeline, best_model_path)
    joblib.dump(best_pipeline, legacy_model_path)

    # Save comparison metrics
    with open(comparison_path, "w", encoding="utf-8") as f:
        json.dump(comparison_results, f, indent=2)

    # Save best model detailed metrics
    best_metrics_payload = {
        "best_model_name": best_model_name,
        "metrics": comparison_results[best_model_name],
        "feature_importances": best_feat_importances,
        "test_sample_size": len(X_test),
        "test_student_count": n_test_students,
    }
    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump(best_metrics_payload, f, indent=2)

    # Save model metadata
    metadata = {
        "version": MODEL_VERSION,
        "best_model": best_model_name,
        "feature_columns": FEATURE_COLUMNS,
        "target_column": TARGET_COLUMN,
        "threshold": 75.0,
        "test_accuracy": comparison_results[best_model_name]["accuracy"],
        "test_f1_score": comparison_results[best_model_name]["f1_score"],
        "test_roc_auc": comparison_results[best_model_name]["roc_auc"],
        "total_dataset_rows": len(df),
        "classes": ["Regular (>=75%)", "Shortage (<75%)"],
    }
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    # ── Compute & Save Threshold Metrics (High=0.65, Medium=0.35) ─────────────
    best_proba = best_pipeline.predict_proba(X_test)[:, 1]

    def _eval_at_thresh(th: float):
        preds = (best_proba >= th).astype(int)
        p = float(precision_score(y_test, preds, zero_division=0))
        r = float(recall_score(y_test, preds, zero_division=0))
        cm = confusion_matrix(y_test, preds).tolist()
        return {
            "threshold": th,
            "precision": round(p, 4),
            "precision_pct": f"{p * 100:.2f}%",
            "recall": round(r, 4),
            "recall_pct": f"{r * 100:.2f}%",
            "confusion_matrix": cm,
            "true_negatives": cm[0][0],
            "false_positives": cm[0][1],
            "false_negatives": cm[1][0],
            "true_positives": cm[1][1],
        }

    thresh_payload = {
        "model_name": best_model_name,
        "model_version": MODEL_VERSION,
        "high_risk": _eval_at_thresh(0.65),
        "medium_risk": _eval_at_thresh(0.35),
        "default_standard": _eval_at_thresh(0.50),
        "test_sample_size": len(X_test),
        "test_student_count": n_test_students,
    }
    thresh_path = os.path.join(save_dir, "threshold_metrics.json")
    with open(thresh_path, "w", encoding="utf-8") as f:
        json.dump(thresh_payload, f, indent=2)

    print(f"\n[Saved] Model Pipeline saved to: {best_model_path}")
    print(f"[Saved] Comparison JSON saved to: {comparison_path}")
    print(f"[Saved] Best Metrics JSON saved to: {metrics_path}")
    print(f"[Saved] Threshold Metrics JSON saved to: {thresh_path}")

    return {
        "best_model_name": best_model_name,
        "comparison": comparison_results,
        "best_metrics": best_metrics_payload,
        "metadata": metadata,
    }


# Backward compatibility aliases
train_model = train_and_compare_models
generate_synthetic_dataset = generate_attendance_dataset


if __name__ == "__main__":
    train_and_compare_models()
