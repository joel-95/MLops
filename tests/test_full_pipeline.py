import os
import json
import pytest
from pathlib import Path
from sqlalchemy.orm import Session

from backend.db.models import init_db, SessionLocal, Repo, Run, Deployment
from ml.train import train_v1
from ml.quality_gate import check_quality_gate
from runner.local_runner import run_pipeline_for_repo
from deploy.local_deploy import deploy_model, stop_deployment
from monitoring.traffic_logger import log_prediction, get_recent_traffic, get_traffic_count


@pytest.fixture(autouse=True)
def setup_db():
    init_db()


def test_train_v1_produces_valid_metrics_and_model():
    """Verify train_v1 produces metrics.json matching schema and model artifact."""
    metrics = train_v1()
    assert isinstance(metrics, dict)
    assert metrics["task_type"] == "classification"
    assert "accuracy" in metrics
    assert "precision" in metrics
    assert "recall" in metrics
    assert "f1" in metrics
    assert "loss" in metrics
    assert "training_time_sec" in metrics
    assert metrics["accuracy"] >= 0.80

    # Verify metrics.json file
    metrics_path = Path("metrics.json")
    assert metrics_path.exists()
    with open(metrics_path, "r", encoding="utf-8") as f:
        saved_metrics = json.load(f)
    assert saved_metrics["accuracy"] == metrics["accuracy"]

    # Verify model artifact
    model_path = Path(metrics["model_artifact_path"])
    assert model_path.exists()


def test_quality_gate_evaluation():
    """Verify check_quality_gate properly evaluates metrics against mlops.yaml thresholds."""
    yaml_path = "mlops.yaml" if os.path.exists("mlops.yaml") else "demo_repo/mlops.yaml"
    passed, details = check_quality_gate("metrics.json", yaml_path)
    assert passed is True
    assert details["overall"] == "passed"
    assert "accuracy" in details["checks"]
    assert details["checks"]["accuracy"]["passed"] is True


def test_runner_pipeline_execution():
    """Verify local runner executes training, evaluates quality gate, and updates Run DB record."""
    db: Session = SessionLocal()
    test_repo_id = "repo_pipeline_test"
    try:
        # Create test repo record if missing
        repo = db.query(Repo).filter(Repo.id == test_repo_id).first()
        if not repo:
            repo = Repo(
                id=test_repo_id,
                sequential_id=99,
                repo_name="pipeline-test",
                owner="joel-test",
                github_url="https://github.com/joel-test/pipeline-test",
                mlops_yaml={
                    "project_name": "pipeline-test",
                    "framework": "sklearn",
                    "task_type": "classification",
                    "entry_point": "ml/train.py",
                    "metrics_threshold": {"accuracy": 0.70}
                }
            )
            db.add(repo)
            db.commit()

        # Run pipeline
        res = run_pipeline_for_repo(
            repo_id=test_repo_id,
            commit_sha="testsha123",
            callback_url="http://127.0.0.1:9999"  # Dummy callback that runner safely ignores if offline
        )

        assert res["status"] in ("passed", "failed")
        assert "metrics" in res
        assert "accuracy" in res["metrics"]

        # Check DB run record
        run_record = (
            db.query(Run)
            .filter(Run.repo_id == test_repo_id)
            .order_by(Run.started_at.desc())
            .first()
        )
        assert run_record is not None
        assert run_record.status == res["status"]
    finally:
        # Cleanup
        db.query(Run).filter(Run.repo_id == test_repo_id).delete()
        db.query(Repo).filter(Repo.id == test_repo_id).delete()
        db.commit()
        db.close()


def test_traffic_logging_and_query():
    """Verify predictions are logged and retrieved accurately for drift monitoring."""
    test_repo = "repo_traffic_test"
    features = {"sepal_length": 5.1, "sepal_width": 3.5, "petal_length": 1.4, "petal_width": 0.2}
    output = {"prediction": 0, "confidence": 0.98}

    initial_count = get_traffic_count(test_repo)
    log_prediction(test_repo, features, output)
    new_count = get_traffic_count(test_repo)

    assert new_count == initial_count + 1
    recent = get_recent_traffic(test_repo, n_records=5)
    assert not recent.empty
    assert "sepal_length" in recent.columns
