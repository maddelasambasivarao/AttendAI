"""
ml/evaluate.py – Model evaluation and inspection utilities.
Loads the persisted model artifacts, prints the confusion matrix, ROC-AUC,
classification report, and feature importances.
"""

import os
import sys
import json
from typing import Dict, Any
import numpy as np
import joblib

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sklearn.metrics import (
    classification_report, confusion_matrix, accuracy_score,
    precision_score, recall_score, f1_score, roc_auc_score
)

from ml.features import FEATURE_COLUMNS, TARGET_COLUMN


MODELS_DIR = os.path.join(os.path.dirname(__file__), "models")


def get_saved_model(models_dir: str = None):
    """Loads the persisted best model pipeline and its metadata."""
    if models_dir is None:
        models_dir = MODELS_DIR

    model_path = os.path.join(models_dir, "best_risk_model.joblib")
    if not os.path.exists(model_path):
        model_path = os.path.join(models_dir, "risk_classifier.joblib")

    meta_path = os.path.join(models_dir, "model_meta.json")
    if not os.path.exists(model_path):
        raise FileNotFoundError(f"No trained model found at {model_path}.")

    pipeline = joblib.load(model_path)
    meta = {}
    if os.path.exists(meta_path):
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)

    return pipeline, meta


def evaluate_model(X_test, y_test, models_dir: str = None) -> Dict[str, Any]:
    """Evaluates the saved model pipeline against provided test data."""
    pipeline, meta = get_saved_model(models_dir)

    y_pred = pipeline.predict(X_test)
    y_prob = pipeline.predict_proba(X_test)[:, 1] if hasattr(pipeline, "predict_proba") else None

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
        "classification_report": report,
        "model_name": meta.get("best_model", "Trained Model"),
    }


def print_feature_importance(models_dir: str = None):
    """Prints ranked feature importance from the saved model using ASCII formatting."""
    pipeline, meta = get_saved_model(models_dir)
    clf = pipeline.named_steps.get("classifier") if hasattr(pipeline, "named_steps") else pipeline

    feature_cols = meta.get("feature_columns", FEATURE_COLUMNS)
    importances = {}

    if hasattr(clf, "feature_importances_"):
        for feat, imp in zip(feature_cols, clf.feature_importances_):
            importances[feat] = float(imp)
    elif hasattr(clf, "coef_"):
        coefs = np.abs(clf.coef_[0])
        total = np.sum(coefs) if np.sum(coefs) > 0 else 1.0
        normalized = coefs / total
        for feat, imp in zip(feature_cols, normalized):
            importances[feat] = float(imp)
    else:
        print("Model does not expose feature importances or coefficients.")
        return

    sorted_imp = sorted(importances.items(), key=lambda x: x[1], reverse=True)

    print("\n" + "=" * 60)
    print("  Feature Importance Ranking (AttendAI Risk Model)")
    print("=" * 60)
    for rank, (feat, imp) in enumerate(sorted_imp, 1):
        bar_len = int(imp * 35)
        bar = "#" * bar_len
        print(f" {rank:2d}. {feat:<26} | {bar:<35} | {imp*100:>5.2f}%")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    print_feature_importance()
