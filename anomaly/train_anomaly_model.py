import os
import pickle
from pathlib import Path
from typing import List, Tuple
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler


def train_anomaly_detector(
    repo_id: str,
    baseline_df: pd.DataFrame,
    numerical_features: List[str],
    output_dir: str = "artifacts",
    n_estimators: int = 200,
    contamination: float = 0.05,
    random_state: int = 42
) -> Tuple[str, str]:
    """
    Fits an Isolation Forest and StandardScaler on baseline numerical training features.
    Saves serialized detector artifacts for online scoring.

    Returns:
        (model_path: str, scaler_path: str)
    """
    save_dir = Path(output_dir) / repo_id
    save_dir.mkdir(parents=True, exist_ok=True)

    model_path = str(save_dir / "anomaly_model.pkl")
    scaler_path = str(save_dir / "anomaly_scaler.pkl")

    valid_features = [f for f in numerical_features if f in baseline_df.columns]
    if not valid_features or len(baseline_df) < 5:
        # Create a dummy model/scaler if baseline is minimal
        X_data = baseline_df[valid_features].fillna(0) if valid_features else pd.DataFrame([[0]], columns=["dummy"])
    else:
        X_data = baseline_df[valid_features].fillna(baseline_df[valid_features].median())

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X_data)

    iso_forest = IsolationForest(
        n_estimators=n_estimators,
        contamination=contamination,
        random_state=random_state,
        n_jobs=-1
    )
    iso_forest.fit(X_scaled)

    # Attach feature metadata to model for validation during scoring
    iso_forest.training_features_ = valid_features

    with open(model_path, "wb") as f:
        pickle.dump(iso_forest, f)

    with open(scaler_path, "wb") as f:
        pickle.dump(scaler, f)

    return model_path, scaler_path
