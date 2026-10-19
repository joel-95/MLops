import json
import pytest
from ml.quality_gate import check_quality_gate


def test_quality_gate_classification_pass(tmp_path):
    metrics_file = tmp_path / "metrics.json"
    yaml_file = tmp_path / "mlops.yaml"

    metrics_file.write_text(json.dumps({
        "task_type": "classification",
        "accuracy": 0.92,
        "precision": 0.88,
        "loss": 0.15
    }))

    yaml_file.write_text("""
task_type: "classification"
metrics_threshold:
  accuracy: 0.85
  precision: 0.80
  loss: 0.30
""")

    passed, details = check_quality_gate(str(metrics_file), str(yaml_file))
    assert passed is True
    assert details["overall"] == "passed"
    assert details["checks"]["accuracy"]["passed"] is True
    assert details["checks"]["loss"]["passed"] is True


def test_quality_gate_classification_fail(tmp_path):
    metrics_file = tmp_path / "metrics.json"
    yaml_file = tmp_path / "mlops.yaml"

    metrics_file.write_text(json.dumps({
        "task_type": "classification",
        "accuracy": 0.75,  # Below 0.85 threshold
        "precision": 0.88
    }))

    yaml_file.write_text("""
task_type: "classification"
metrics_threshold:
  accuracy: 0.85
  precision: 0.80
""")

    passed, details = check_quality_gate(str(metrics_file), str(yaml_file))
    assert passed is False
    assert details["overall"] == "failed"
    assert details["checks"]["accuracy"]["passed"] is False
    assert details["checks"]["precision"]["passed"] is True


def test_quality_gate_regression_pass(tmp_path):
    metrics_file = tmp_path / "metrics.json"
    yaml_file = tmp_path / "mlops.yaml"

    metrics_file.write_text(json.dumps({
        "task_type": "regression",
        "rmse": 4.2,  # Lower than threshold 5.0
        "r_squared": 0.91  # Higher than threshold 0.85
    }))

    yaml_file.write_text("""
task_type: "regression"
metrics_threshold:
  rmse: 5.0
  r_squared: 0.85
""")

    passed, details = check_quality_gate(str(metrics_file), str(yaml_file))
    assert passed is True
    assert details["checks"]["rmse"]["passed"] is True
    assert details["checks"]["r_squared"]["passed"] is True
