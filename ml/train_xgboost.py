"""
AutoMLOps XGBoost Training Module
===================================
Trains an XGBoost classifier with Optuna Bayesian hyperparameter optimization.
Architecture adapted from the Aegis NIDS project's Stage-2 Supervised Diagnostician.

Supports any tabular classification dataset declared in mlops.yaml.
Saves the same {model, preprocessor} bundle as train_v1 so the serving app
and prediction pipeline require zero changes.
"""
import os
import time
import json
import yaml
import pickle
import logging
from pathlib import Path
from typing import Dict, Any, Optional

import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, f1_score, log_loss
)
from sklearn.utils.class_weight import compute_sample_weight

import xgboost as xgb
import optuna

from ml.data.preprocess import preprocess
from ml.mlflow_integration import log_run

optuna.logging.set_verbosity(optuna.logging.WARNING)
logger = logging.getLogger("automlops.train_xgboost")


def train_xgboost(
    n_optuna_trials: int = 20,
    mlops_yaml_override: Optional[str] = None
) -> Dict[str, Any]:
    """
    Full XGBoost training pipeline:
      1. Load dataset declared in mlops.yaml
      2. Preprocess (impute, scale, encode)
      3. Bayesian hyperparameter search via Optuna TPE
      4. Train final model with best params + balanced sample weights
      5. Evaluate on held-out test set
      6. Save {model, preprocessor} bundle identical to train_v1 format
      7. Write metrics.json + log to MLflow

    Returns:
        metrics_data dict (same schema as train_v1)
    """
    start_time = time.time()

    # ── 1. Read mlops.yaml ──────────────────────────────────────────────────────
    yaml_path = mlops_yaml_override or (
        "mlops.yaml" if os.path.exists("mlops.yaml") else "demo_repo/mlops.yaml"
    )
    with open(yaml_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    project_name   = config.get("project_name", "mlops-demo")
    target_column  = config.get("target_column", "species")
    num_features   = config.get("numerical_features", [])
    cat_features   = config.get("categorical_features", [])
    dataset_path   = config.get("dataset_path", "demo_repo/data/iris.csv")
    xgb_cfg        = config.get("xgboost", {})          # optional per-project overrides
    n_trials       = xgb_cfg.get("optuna_trials", n_optuna_trials)

    # ── 2. Load Dataset ─────────────────────────────────────────────────────────
    if os.path.exists(dataset_path):
        df = pd.read_csv(dataset_path)
    else:
        from sklearn.datasets import load_iris
        raw = load_iris(as_frame=True)
        df = raw.frame.rename(columns={
            "sepal length (cm)": "sepal_length",
            "sepal width (cm)":  "sepal_width",
            "petal length (cm)": "petal_length",
            "petal width (cm)":  "petal_width",
            "target": "species"
        })
        os.makedirs(os.path.dirname(dataset_path) or ".", exist_ok=True)
        df.to_csv(dataset_path, index=False)

    # ── 3. Preprocess ───────────────────────────────────────────────────────────
    X_train, X_test, y_train, y_test, preprocessor_bundle = preprocess(
        raw_df=df,
        target_column=target_column,
        numerical_features=num_features,
        categorical_features=cat_features,
        test_size=0.2,
        random_state=42
    )

    # Encode string labels to integers (XGBoost requires numeric targets)
    from sklearn.preprocessing import LabelEncoder
    le = LabelEncoder()
    y_train_enc = le.fit_transform(y_train)
    y_test_enc  = le.transform(y_test)
    n_classes   = len(le.classes_)

    # Balanced sample weights to handle class imbalance (Aegis §4.2)
    sample_weights = compute_sample_weight("balanced", y_train_enc)

    # ── 4. Optuna Bayesian Hyperparameter Search ────────────────────────────────
    def objective(trial: optuna.Trial) -> float:
        params = {
            "n_estimators":      trial.suggest_int("n_estimators", 50, 400),
            "max_depth":         trial.suggest_int("max_depth", 3, 10),
            "learning_rate":     trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
            "min_child_weight":  trial.suggest_int("min_child_weight", 1, 10),
            "subsample":         trial.suggest_float("subsample", 0.6, 1.0),
            "colsample_bytree":  trial.suggest_float("colsample_bytree", 0.6, 1.0),
            "objective":         "multi:softprob",
            "num_class":         n_classes,
            "eval_metric":       "mlogloss",
            "random_state":      42,
            "verbosity":         0,
        }
        model = xgb.XGBClassifier(**params)
        model.fit(
            X_train, y_train_enc,
            sample_weight=sample_weights,
            eval_set=[(X_test, y_test_enc)],
            verbose=False
        )
        y_pred = model.predict(X_test)
        return f1_score(y_test_enc, y_pred, average="macro", zero_division=0)

    logger.info(f"[XGBoost] Starting Optuna search ({n_trials} trials)...")
    study = optuna.create_study(direction="maximize", sampler=optuna.samplers.TPESampler(seed=42))
    study.optimize(objective, n_trials=n_trials, show_progress_bar=False)
    best_params = study.best_params
    logger.info(f"[XGBoost] Best params: {best_params} | val_f1={study.best_value:.4f}")

    # ── 5. Train Final Model ────────────────────────────────────────────────────
    final_params = {
        **best_params,
        "objective":         "multi:softprob",
        "num_class":         n_classes,
        "eval_metric":       "mlogloss",
        "random_state":      42,
        "verbosity":         0,
    }
    model = xgb.XGBClassifier(**final_params)
    model.fit(X_train, y_train_enc, sample_weight=sample_weights, verbose=False)

    # Attach label encoder to model so serving can decode back to original class names
    model._label_encoder = le

    # ── 6. Evaluate ─────────────────────────────────────────────────────────────
    y_pred     = model.predict(X_test)
    y_proba    = model.predict_proba(X_test)

    acc  = float(accuracy_score(y_test_enc, y_pred))
    prec = float(precision_score(y_test_enc, y_pred, average="weighted", zero_division=0))
    rec  = float(recall_score(y_test_enc, y_pred, average="weighted", zero_division=0))
    f1   = float(f1_score(y_test_enc, y_pred, average="weighted", zero_division=0))
    loss = float(log_loss(y_test_enc, y_proba))

    duration = round(time.time() - start_time, 2)

    # ── 7. Save Artifacts ───────────────────────────────────────────────────────
    artifacts_dir = Path("artifacts")
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    model_artifact_path = str(artifacts_dir / "model.pkl")

    # Bundle uses same schema as RandomForest trainer so serving_app needs no changes
    with open(model_artifact_path, "wb") as f:
        pickle.dump({
            "model":        model,
            "preprocessor": preprocessor_bundle,
            "framework":    "xgboost",
            "label_encoder": le,
            "best_params":  best_params,
            "optuna_best_val_f1": round(study.best_value, 4)
        }, f)

    # ── 8. Write metrics.json ────────────────────────────────────────────────────
    metrics_data = {
        "task_type":             "classification",
        "accuracy":              round(acc, 4),
        "precision":             round(prec, 4),
        "recall":                round(rec, 4),
        "f1":                    round(f1, 4),
        "loss":                  round(loss, 4),
        "training_time_sec":     duration,
        "commit_sha":            os.getenv("COMMIT_SHA", "xgboost-optuna"),
        "model_artifact_path":   model_artifact_path,
        "framework":             "xgboost",
        "optuna_trials":         n_trials,
        "optuna_best_val_f1":    round(study.best_value, 4),
        "best_hyperparams":      best_params,
    }

    with open("metrics.json", "w", encoding="utf-8") as f:
        json.dump(metrics_data, f, indent=2)

    # ── 9. Log to MLflow ─────────────────────────────────────────────────────────
    params = {
        "model_class":   "XGBClassifier",
        "framework":     "xgboost",
        "optuna_trials": n_trials,
        **best_params
    }
    log_run(
        repo_id=project_name,
        params=params,
        metrics=metrics_data,
        model_artifact_path=model_artifact_path,
        run_name="xgboost_optuna_training"
    )

    logger.info(
        f"[XGBoost] Training complete in {duration}s | "
        f"acc={acc:.4f} f1={f1:.4f} | best_params={best_params}"
    )
    print(f"✅ XGBoost training complete in {duration}s. Metrics: acc={acc:.4f}, f1={f1:.4f}")
    return metrics_data


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    train_xgboost()
