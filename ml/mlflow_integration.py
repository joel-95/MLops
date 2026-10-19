import os
import json
from pathlib import Path
from typing import Dict, Any, Optional
import mlflow
from mlflow.tracking import MlflowClient

MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000")


def get_client() -> MlflowClient:
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    return MlflowClient()


def log_run(
    repo_id: str,
    params: Dict[str, Any],
    metrics: Dict[str, Any],
    model_artifact_path: Optional[str] = None,
    run_name: Optional[str] = None,
    tags: Optional[Dict[str, str]] = None
) -> str:
    """
    Logs a training run, parameters, standardized metrics, and model artifact to MLflow.
    
    Returns:
        The created MLflow run_id string.
    """
    try:
        mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
        experiment_name = f"automlops_{repo_id}"
        mlflow.set_experiment(experiment_name)

        run_tags = tags or {}
        run_tags["repo_id"] = repo_id

        with mlflow.start_run(run_name=run_name, tags=run_tags) as active_run:
            run_id = active_run.info.run_id

            # Log params
            for k, v in params.items():
                mlflow.log_param(k, v)

            # Log metrics (numeric only)
            for k, v in metrics.items():
                if isinstance(v, (int, float)):
                    mlflow.log_metric(k, float(v))

            # Log artifact
            if model_artifact_path and os.path.exists(model_artifact_path):
                mlflow.log_artifact(model_artifact_path, artifact_path="model")

            return run_id
    except Exception as e:
        # Graceful fallback for local development without active MLflow server
        local_mock_run_id = f"local_run_{repo_id}_{int(os.getpid())}"
        fallback_dir = Path("artifacts") / repo_id / "mlflow_fallback"
        fallback_dir.mkdir(parents=True, exist_ok=True)
        with open(fallback_dir / f"{local_mock_run_id}.json", "w", encoding="utf-8") as f:
            json.dump({"params": params, "metrics": metrics, "error": str(e)}, f, indent=2)
        return local_mock_run_id


def get_previous_run(repo_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieves the last successfully completed run's parameters and metrics for this repo.
    Returns None if this is the first deployment or no prior runs exist.
    """
    try:
        client = get_client()
        experiment = client.get_experiment_by_name(f"automlops_{repo_id}")
        if not experiment:
            return _get_fallback_run(repo_id)

        runs = client.search_runs(
            experiment_ids=[experiment.experiment_id],
            order_by=["start_time DESC"],
            max_results=5
        )

        for run in runs:
            if run.info.status == "FINISHED":
                return {
                    "run_id": run.info.run_id,
                    "params": run.data.params,
                    "metrics": run.data.metrics,
                    "start_time": run.info.start_time
                }
        return None
    except Exception:
        return _get_fallback_run(repo_id)


def _get_fallback_run(repo_id: str) -> Optional[Dict[str, Any]]:
    fallback_dir = Path("artifacts") / repo_id / "mlflow_fallback"
    if not fallback_dir.exists():
        return None
    files = sorted(fallback_dir.glob("*.json"), key=os.path.getmtime, reverse=True)
    if files:
        with open(files[0], "r", encoding="utf-8") as f:
            data = json.load(f)
            data["run_id"] = files[0].stem
            return data
    return None
