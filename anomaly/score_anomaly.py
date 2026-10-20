import os
import pickle
from pathlib import Path
from typing import Optional, Tuple, Any
import pandas as pd
import numpy as np


def load_detector(model_path: str, scaler_path: str) -> Tuple[Optional[Any], Optional[Any]]:
    """Loads Isolation Forest model and StandardScaler."""
    if not os.path.exists(model_path) or not os.path.exists(scaler_path):
        return None, None
    try:
        with open(model_path, "rb") as f:
            model = pickle.load(f)
        with open(scaler_path, "rb") as f:
            scaler = pickle.load(f)
        return model, scaler
    except Exception:
        return None, None


def score_requests(
    live_df: pd.DataFrame,
    model_path: str,
    scaler_path: str
) -> pd.DataFrame:
    """
    Appends anomaly_score and is_anomaly (boolean) to the live DataFrame.
    Isolation Forest decision_function returns negative values for anomalies.
    predict returns -1 for outliers, 1 for inliers.
    """
    scored_df = live_df.copy()
    if live_df.empty:
        scored_df["anomaly_score"] = []
        scored_df["is_anomaly"] = []
        return scored_df

    model, scaler = load_detector(model_path, scaler_path)
    if model is None or scaler is None:
        # Default neutral scoring if detector not ready yet
        scored_df["anomaly_score"] = 0.0
        scored_df["is_anomaly"] = False
        return scored_df

    training_features = getattr(model, "training_features_", None)
    if not training_features:
        training_features = [c for c in live_df.columns if not c.startswith("_") and np.issubdtype(live_df[c].dtype, np.number)]

    available_features = [f for f in training_features if f in live_df.columns]
    if not available_features:
        scored_df["anomaly_score"] = 0.0
        scored_df["is_anomaly"] = False
        return scored_df

    X = live_df[available_features].fillna(0).values
    try:
        X_scaled = scaler.transform(X)
        raw_scores = model.decision_function(X_scaled)
        preds = model.predict(X_scaled)

        scored_df["anomaly_score"] = raw_scores
        scored_df["is_anomaly"] = preds == -1
    except Exception:
        scored_df["anomaly_score"] = 0.0
        scored_df["is_anomaly"] = False

    return scored_df


def check_anomaly_rate(scored_df: pd.DataFrame, threshold: float = 0.15) -> Tuple[bool, float]:
    """
    Evaluates whether the proportion of anomalous requests in the batch exceeds threshold.
    Returns: (rate_exceeded: bool, observed_rate: float)
    """
    if scored_df.empty or "is_anomaly" not in scored_df.columns:
        return False, 0.0

    total = len(scored_df)
    anomalies = scored_df["is_anomaly"].sum()
    rate = float(anomalies / total) if total > 0 else 0.0

    return rate >= threshold, rate
