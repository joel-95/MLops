import os
import sys
import time
import json
import yaml
import pickle
from pathlib import Path
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, log_loss


def _load_config():
    for p in ("mlops.yaml", "demo_repo/mlops.yaml"):
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                return yaml.safe_load(f)
    return {}


def train_sklearn(config: dict) -> dict:
    start_time = time.time()

    target_col = config.get("target_column", "species")
    num_features = config.get("numerical_features", [])
    data_path = config.get("dataset_path", "data/iris.csv")

    df = pd.read_csv(data_path)
    X = df[num_features]
    y = df[target_col]

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    X_train, X_test, y_train, y_test = train_test_split(
        X_scaled, y, test_size=0.2, random_state=42, stratify=y
    )

    model = RandomForestClassifier(n_estimators=100, max_depth=4, random_state=42)
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)
    y_proba = model.predict_proba(X_test)

    acc = float(accuracy_score(y_test, y_pred))
    prec = float(precision_score(y_test, y_pred, average="weighted", zero_division=0))
    rec = float(recall_score(y_test, y_pred, average="weighted", zero_division=0))
    f1 = float(f1_score(y_test, y_pred, average="weighted", zero_division=0))
    loss = float(log_loss(y_test, y_proba))
    duration = round(time.time() - start_time, 2)

    os.makedirs("artifacts", exist_ok=True)
    with open("artifacts/model.pkl", "wb") as f:
        pickle.dump({"model": model, "scaler": scaler, "features": num_features}, f)

    return {
        "task_type": "classification",
        "framework": "sklearn",
        "accuracy": round(acc, 4),
        "precision": round(prec, 4),
        "recall": round(rec, 4),
        "f1": round(f1, 4),
        "loss": round(loss, 4),
        "training_time_sec": duration,
        "commit_sha": os.getenv("COMMIT_SHA", "demo_commit_v1"),
        "model_artifact_path": "artifacts/model.pkl",
    }


def train_xgboost_demo(config: dict) -> dict:
    """XGBoost + Optuna TPE training for the demo repo."""
    import xgboost as xgb
    import optuna
    from sklearn.preprocessing import LabelEncoder
    from sklearn.model_selection import cross_val_score

    optuna.logging.set_verbosity(optuna.logging.WARNING)

    start_time = time.time()
    target_col = config.get("target_column", "species")
    num_features = config.get("numerical_features", [])
    data_path = config.get("dataset_path", "data/iris.csv")
    n_trials = config.get("xgboost", {}).get("optuna_trials", 20)

    df = pd.read_csv(data_path)
    X = df[num_features].values
    le = LabelEncoder()
    y = le.fit_transform(df[target_col].values)
    n_classes = len(le.classes_)

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    def objective(trial):
        params = {
            "objective": "multi:softprob",
            "num_class": n_classes,
            "eval_metric": "mlogloss",
            "n_estimators": trial.suggest_int("n_estimators", 50, 400),
            "max_depth": trial.suggest_int("max_depth", 3, 9),
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
            "min_child_weight": trial.suggest_int("min_child_weight", 1, 7),
            "subsample": trial.suggest_float("subsample", 0.6, 1.0),
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.6, 1.0),
            "random_state": 42,
            "verbosity": 0,
        }
        clf = xgb.XGBClassifier(**params)
        scores = cross_val_score(clf, X_scaled, y, cv=3, scoring="f1_weighted")
        return scores.mean()

    study = optuna.create_study(direction="maximize", sampler=optuna.samplers.TPESampler(seed=42))
    study.optimize(objective, n_trials=n_trials, show_progress_bar=False)

    best_params = study.best_params
    best_params.update({
        "objective": "multi:softprob",
        "num_class": n_classes,
        "eval_metric": "mlogloss",
        "random_state": 42,
        "verbosity": 0,
    })

    X_train, X_test, y_train, y_test = train_test_split(
        X_scaled, y, test_size=0.2, random_state=42, stratify=y
    )
    model = xgb.XGBClassifier(**best_params)
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)
    y_proba = model.predict_proba(X_test)

    acc = float(accuracy_score(y_test, y_pred))
    prec = float(precision_score(y_test, y_pred, average="weighted", zero_division=0))
    rec = float(recall_score(y_test, y_pred, average="weighted", zero_division=0))
    f1 = float(f1_score(y_test, y_pred, average="weighted", zero_division=0))
    loss = float(log_loss(y_test, y_proba))
    duration = round(time.time() - start_time, 2)

    os.makedirs("artifacts", exist_ok=True)
    with open("artifacts/model.pkl", "wb") as f:
        pickle.dump({
            "model": model,
            "preprocessor": scaler,
            "label_encoder": le,
            "framework": "xgboost",
            "features": num_features,
            "best_params": best_params,
        }, f)

    return {
        "task_type": "classification",
        "framework": "xgboost",
        "accuracy": round(acc, 4),
        "precision": round(prec, 4),
        "recall": round(rec, 4),
        "f1": round(f1, 4),
        "loss": round(loss, 4),
        "training_time_sec": duration,
        "optuna_best_trial": study.best_trial.number,
        "best_params": best_params,
        "commit_sha": os.getenv("COMMIT_SHA", "demo_commit_v1"),
        "model_artifact_path": "artifacts/model.pkl",
    }


def train():
    config = _load_config()
    framework = config.get("framework", "sklearn").lower()

    print(f"Demo training started (framework={framework})")

    if framework == "xgboost":
        metrics_data = train_xgboost_demo(config)
    else:
        metrics_data = train_sklearn(config)

    with open("metrics.json", "w", encoding="utf-8") as f:
        json.dump(metrics_data, f, indent=2)

    print("Demo training completed. Metrics:", json.dumps(metrics_data, indent=2))


if __name__ == "__main__":
    train()
