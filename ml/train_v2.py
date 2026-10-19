import os
import time
import json
import yaml
import pickle
from pathlib import Path
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, log_loss

from ml.data.preprocess import preprocess
from ml.mlflow_integration import log_run


def train_v2():
    """
    v2 training variant with tuned hyperparameters (n_estimators=250, max_depth=8)
    designed to showcase AST code diffing and Evidently version comparison.
    """
    start_time = time.time()

    yaml_path = "mlops.yaml" if os.path.exists("mlops.yaml") else "demo_repo/mlops.yaml"
    with open(yaml_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    project_name = config.get("project_name", "mlops-demo")
    target_column = config.get("target_column", "species")
    num_features = config.get("numerical_features", [])
    cat_features = config.get("categorical_features", [])
    dataset_path = config.get("dataset_path", "demo_repo/data/iris.csv")

    df = pd.read_csv(dataset_path)

    # Preprocess
    X_train, X_test, y_train, y_test, preprocessor_bundle = preprocess(
        raw_df=df,
        target_column=target_column,
        numerical_features=num_features,
        categorical_features=cat_features,
        test_size=0.2,
        random_state=42
    )

    # v2: Increased estimators to 250 and deeper trees (max_depth=8)
    model = RandomForestClassifier(
        n_estimators=250,
        max_depth=8,
        random_state=42
    )
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)
    y_proba = model.predict_proba(X_test)

    acc = float(accuracy_score(y_test, y_pred))
    prec = float(precision_score(y_test, y_pred, average="weighted", zero_division=0))
    rec = float(recall_score(y_test, y_pred, average="weighted", zero_division=0))
    f1 = float(f1_score(y_test, y_pred, average="weighted", zero_division=0))
    loss = float(log_loss(y_test, y_proba))

    duration = round(time.time() - start_time, 2)

    artifacts_dir = Path("artifacts")
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    model_artifact_path = str(artifacts_dir / "model.pkl")

    with open(model_artifact_path, "wb") as f:
        pickle.dump({"model": model, "preprocessor": preprocessor_bundle}, f)

    metrics_data = {
        "task_type": "classification",
        "accuracy": round(acc, 4),
        "precision": round(prec, 4),
        "recall": round(rec, 4),
        "f1": round(f1, 4),
        "loss": round(loss, 4),
        "training_time_sec": duration,
        "commit_sha": os.getenv("COMMIT_SHA", "v2-hyperparam-tuned"),
        "model_artifact_path": model_artifact_path
    }

    with open("metrics.json", "w", encoding="utf-8") as f:
        json.dump(metrics_data, f, indent=2)

    params = {
        "model_class": "RandomForestClassifier",
        "n_estimators": 250,
        "max_depth": 8,
        "random_state": 42
    }
    log_run(
        repo_id=project_name,
        params=params,
        metrics=metrics_data,
        model_artifact_path=model_artifact_path,
        run_name="v2_tuned_training"
    )

    print(f"✅ Training v2 completed in {duration}s. Metrics: {metrics_data}")
    return metrics_data


if __name__ == "__main__":
    train_v2()
