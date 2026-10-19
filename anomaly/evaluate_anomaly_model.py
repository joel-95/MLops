import numpy as np
import pandas as pd
from typing import List, Dict, Any, Tuple
from sklearn.metrics import precision_recall_fscore_support
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import IsolationForest


def generate_synthetic_anomalies(
    baseline_df: pd.DataFrame,
    numerical_features: List[str],
    anomaly_ratio: float = 0.3,
    random_state: int = 42
) -> Tuple[pd.DataFrame, np.ndarray]:
    """
    Synthesizes anomalies by independently permuting feature values across columns.
    This preserves each feature's individual marginal distribution while breaking
    the joint covariance / correlation structure.

    Returns:
        (combined_df: pd.DataFrame, ground_truth_labels: np.ndarray [1 for anomaly, 0 for normal])
    """
    np.random.seed(random_state)
    n_samples = len(baseline_df)
    n_anomalies = max(5, int(n_samples * anomaly_ratio))

    normal_df = baseline_df[numerical_features].dropna().copy()
    normal_labels = np.zeros(len(normal_df), dtype=int)

    # Sample rows to permute
    anomaly_df = normal_df.sample(n=min(n_anomalies, len(normal_df)), replace=True, random_state=random_state).copy()

    # Independently shuffle each column
    for col in numerical_features:
        anomaly_df[col] = np.random.permutation(anomaly_df[col].values)

    anomaly_labels = np.ones(len(anomaly_df), dtype=int)

    combined_df = pd.concat([normal_df, anomaly_df], ignore_index=True)
    labels = np.concatenate([normal_labels, anomaly_labels])

    return combined_df, labels


def evaluate_isolation_forest(
    baseline_df: pd.DataFrame,
    numerical_features: List[str],
    contamination: float = 0.05,
    random_state: int = 42
) -> Dict[str, Any]:
    """
    Fits Isolation Forest on baseline data and evaluates detection of synthetic anomalies.
    Returns precision, recall, and f1 score.
    """
    combined_df, true_labels = generate_synthetic_anomalies(
        baseline_df, numerical_features, random_state=random_state
    )

    scaler = StandardScaler()
    X = combined_df[numerical_features].values
    X_scaled = scaler.fit_transform(X)

    iso = IsolationForest(
        contamination=contamination,
        random_state=random_state,
        n_estimators=150
    )
    iso.fit(X_scaled)
    preds = iso.predict(X_scaled)

    # -1 is anomaly in sklearn, convert to 1 for anomaly, 0 for inlier
    pred_labels = np.where(preds == -1, 1, 0)

    precision, recall, f1, _ = precision_recall_fscore_support(
        true_labels, pred_labels, average="binary", zero_division=0
    )

    return {
        "contamination": contamination,
        "precision": round(float(precision), 4),
        "recall": round(float(recall), 4),
        "f1": round(float(f1), 4),
        "total_samples": len(combined_df),
        "synthetic_anomalies": int(true_labels.sum())
    }


def contamination_sweep(
    baseline_df: pd.DataFrame,
    numerical_features: List[str],
    contaminations: List[float] = None
) -> List[Dict[str, Any]]:
    """
    Sweeps contamination parameters to generate sensitivity analysis metrics.
    """
    sweep_vals = contaminations or [0.01, 0.03, 0.05, 0.08, 0.10, 0.15, 0.20]
    results = []
    for c in sweep_vals:
        res = evaluate_isolation_forest(baseline_df, numerical_features, contamination=c)
        results.append(res)
    return results
