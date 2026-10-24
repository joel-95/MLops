"""
AutoMLOps SHAP Explainability Module
======================================
Provides per-prediction TreeSHAP explanations for XGBoost models.
For RandomForest models it falls back to sklearn's feature_importances_.

Adapted from Aegis NIDS ThreatExplainer (ml/explainability.py).
Works with the {model, preprocessor, framework} bundle saved by train_xgboost.py.
"""
import logging
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger("automlops.explainability")


def explain_prediction(
    model_bundle: Dict[str, Any],
    input_dict: Dict[str, Any],
    top_n: int = 3
) -> Dict[str, Any]:
    """
    Generates a human-readable explanation for a single prediction.

    Args:
        model_bundle: The loaded pickle bundle {model, preprocessor, framework?, label_encoder?}
        input_dict:   Raw feature dict as provided by the user
        top_n:        Number of top contributing features to return

    Returns:
        Dict with keys:
            - prediction:   Decoded class label
            - confidence:   Max class probability
            - top_features: List of {feature, value, shap_value, direction} dicts
            - method:       "shap_treexplainer" | "feature_importances" | "unavailable"
            - evidence:     Human-readable strings for each top feature
    """
    model       = model_bundle.get("model")
    preprocessor = model_bundle.get("preprocessor")
    framework   = model_bundle.get("framework", "sklearn")
    le          = model_bundle.get("label_encoder")

    if model is None or preprocessor is None:
        return {"error": "Model bundle incomplete — cannot explain."}

    try:
        X_vec = preprocessor.transform_single(input_dict)
    except Exception as e:
        return {"error": f"Preprocessing failed: {e}"}

    # ── Prediction ──────────────────────────────────────────────────────────────
    try:
        pred_enc = model.predict(X_vec)[0]
        proba    = model.predict_proba(X_vec)[0]
        confidence = round(float(max(proba)), 4)

        if le is not None:
            prediction = le.inverse_transform([int(pred_enc)])[0]
        else:
            prediction = int(pred_enc) if hasattr(pred_enc, "item") else pred_enc
    except Exception as e:
        return {"error": f"Inference failed: {e}"}

    feature_names: List[str] = list(preprocessor.feature_names_out or input_dict.keys())

    # ── SHAP for XGBoost / Aegis NIDS (TreeSHAP — exact, polynomial time) ───────
    if framework in ("xgboost", "aegis_nids"):
        # For Aegis NIDS: run Isolation Forest scoring alongside SHAP
        iso_score = None
        is_anomaly = None
        if framework == "aegis_nids":
            iso_bundle = model_bundle.get("iso_bundle")
            if iso_bundle is not None:
                try:
                    iso_model = iso_bundle["model"]
                    threshold = iso_bundle.get("threshold", 0.5)
                    raw_score = float(-iso_model.score_samples(X_vec)[0])
                    iso_score = round(raw_score, 4)
                    is_anomaly = raw_score > threshold
                except Exception as iso_err:
                    logger.warning(f"[Explainability] IsoForest scoring failed: {iso_err}")

        try:
            import shap
            explainer   = shap.TreeExplainer(model)
            shap_values = explainer.shap_values(X_vec)

            # shap_values shape: (n_samples, n_features, n_classes) for multi:softprob
            pred_class_idx = int(pred_enc)
            if isinstance(shap_values, list):
                sv = shap_values[pred_class_idx][0]
            elif shap_values.ndim == 3:
                sv = shap_values[0, :, pred_class_idx]
            else:
                sv = shap_values[0]

            top_idx   = np.argsort(np.abs(sv))[::-1][:top_n]
            top_feats = _format_features(top_idx, sv, feature_names, X_vec[0], input_dict)

            result = {
                "prediction":   prediction,
                "confidence":   confidence,
                "top_features": top_feats,
                "method":       "shap_treexplainer",
                "evidence":     _build_evidence_strings(top_feats),
            }
            if iso_score is not None:
                result["anomaly_score"] = iso_score
                result["is_anomaly"]    = is_anomaly
            return result
        except Exception as e:
            logger.warning(f"[Explainability] SHAP failed, falling back: {e}")

    # ── Fallback: sklearn feature_importances_ ──────────────────────────────────
    if hasattr(model, "feature_importances_"):
        try:
            importances = model.feature_importances_
            top_idx     = np.argsort(importances)[::-1][:top_n]
            top_feats   = _format_features(top_idx, importances, feature_names, X_vec[0], input_dict)

            return {
                "prediction":   prediction,
                "confidence":   confidence,
                "top_features": top_feats,
                "method":       "feature_importances",
                "evidence":     _build_evidence_strings(top_feats),
            }
        except Exception as e:
            logger.warning(f"[Explainability] feature_importances_ fallback failed: {e}")

    return {
        "prediction":   prediction,
        "confidence":   confidence,
        "top_features": [],
        "method":       "unavailable",
        "evidence":     [],
    }


def _format_features(
    top_idx: np.ndarray,
    scores: np.ndarray,
    feature_names: List[str],
    X_row: np.ndarray,
    input_dict: Dict[str, Any]
) -> List[Dict[str, Any]]:
    result = []
    for i in top_idx:
        fname = feature_names[i] if i < len(feature_names) else f"feature_{i}"
        raw_val = input_dict.get(fname, float(X_row[i]) if i < len(X_row) else None)
        sv = float(scores[i])
        result.append({
            "feature":    fname,
            "value":      raw_val,
            "shap_value": round(sv, 5),
            "direction":  "increases" if sv > 0 else "decreases",
        })
    return result


def _build_evidence_strings(top_feats: List[Dict[str, Any]]) -> List[str]:
    lines = []
    for f in top_feats:
        val = f["value"]
        val_str = f"{val:.4f}" if isinstance(val, float) else str(val)
        lines.append(
            f"{f['feature']} = {val_str} "
            f"({f['direction']} confidence by |{f['shap_value']:.4f}|)"
        )
    return lines
