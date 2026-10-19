import pytest
from backend.services.validator import validate_repo

VALID_CLASSIFICATION_YAML = """
framework: "sklearn"
task_type: "classification"
entry_point: "ml/train.py"
predict_module: "ml/predict.py"
target_column: "species"
numerical_features:
  - "sepal_length"
  - "sepal_width"
categorical_features: []
metrics_threshold:
  accuracy: 0.85
  precision: 0.80
dependencies: "requirements.txt"
"""

VALID_REGRESSION_YAML = """
framework: "sklearn"
task_type: "regression"
entry_point: "ml/train.py"
predict_module: "ml/predict.py"
target_column: "price"
numerical_features:
  - "square_feet"
categorical_features: []
metrics_threshold:
  rmse: 15.0
  r_squared: 0.80
dependencies: "requirements.txt"
"""

FILE_LIST = ["ml/train.py", "ml/predict.py", "requirements.txt"]


def test_valid_classification_repo():
    is_valid, errors = validate_repo(VALID_CLASSIFICATION_YAML, FILE_LIST)
    assert is_valid is True
    assert errors == []


def test_valid_regression_repo():
    is_valid, errors = validate_repo(VALID_REGRESSION_YAML, FILE_LIST)
    assert is_valid is True
    assert errors == []


def test_missing_required_field():
    bad_yaml = """
framework: "sklearn"
task_type: "classification"
    """
    is_valid, errors = validate_repo(bad_yaml, FILE_LIST)
    assert is_valid is False
    assert any("entry_point" in e for e in errors)


def test_invalid_framework():
    bad_yaml = VALID_CLASSIFICATION_YAML.replace('framework: "sklearn"', 'framework: "keras_custom"')
    is_valid, errors = validate_repo(bad_yaml, FILE_LIST)
    assert is_valid is False
    assert any("Invalid framework" in e for e in errors)


def test_missing_files_in_repo():
    is_valid, errors = validate_repo(VALID_CLASSIFICATION_YAML, ["other.py"])
    assert is_valid is False
    assert any("entry_point" in e for e in errors)
    assert any("predict_module" in e for e in errors)


def test_classification_metric_mismatch_with_regression():
    # Attempting to declare RMSE for a classification model
    bad_yaml = VALID_CLASSIFICATION_YAML.replace("accuracy: 0.85", "rmse: 10.0")
    is_valid, errors = validate_repo(bad_yaml, FILE_LIST)
    assert is_valid is False
    assert any("not allowed for task_type 'classification'" in e for e in errors)
