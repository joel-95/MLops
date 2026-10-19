import yaml
from typing import Tuple, List, Dict, Any, Optional

VALID_FRAMEWORKS = {"sklearn", "pytorch", "tensorflow"}
VALID_TASK_TYPES = {"classification", "regression"}

CLASSIFICATION_METRICS = {"accuracy", "precision", "recall", "f1", "loss"}
REGRESSION_METRICS = {"rmse", "mae", "r_squared", "loss"}

REQUIRED_FIELDS = [
    "framework",
    "task_type",
    "entry_point",
    "predict_module",
    "target_column",
    "metrics_threshold",
    "dependencies",
]


def validate_repo(yaml_content: str, repo_file_list: List[str]) -> Tuple[bool, List[str]]:
    """
    Validates a connected repo's structure and mlops.yaml manifest.
    
    Args:
        yaml_content: Raw YAML string content of mlops.yaml
        repo_file_list: List of relative file paths present in the repository

    Returns:
        (is_valid: bool, errors: list[str])
    """
    errors: List[str] = []

    # Normalize file list to forward slashes for cross-platform comparison
    normalized_repo_files = set(f.replace("\\", "/").lstrip("/") for f in repo_file_list)

    # 1. Parse YAML
    try:
        config: Optional[Dict[str, Any]] = yaml.safe_load(yaml_content)
        if not isinstance(config, dict):
            return False, ["mlops.yaml is empty or does not define a valid YAML dictionary mapping."]
    except yaml.YAMLError as e:
        return False, [f"Failed to parse mlops.yaml: {str(e)}"]

    # 2. Check required top-level fields
    for field in REQUIRED_FIELDS:
        if field not in config or config[field] is None:
            errors.append(f"Missing required field in mlops.yaml: '{field}'.")

    if errors:
        return False, errors

    # 3. Check framework
    framework = str(config.get("framework", "")).lower()
    if framework not in VALID_FRAMEWORKS:
        errors.append(
            f"Invalid framework '{framework}'. Must be one of: {sorted(list(VALID_FRAMEWORKS))}."
        )

    # 4. Check task_type
    task_type = str(config.get("task_type", "")).lower()
    if task_type not in VALID_TASK_TYPES:
        errors.append(
            f"Invalid task_type '{task_type}'. Must be one of: {sorted(list(VALID_TASK_TYPES))}."
        )

    # 5. Check entry_point file exists
    entry_point = str(config.get("entry_point", "")).replace("\\", "/").lstrip("/")
    if not entry_point:
        errors.append("Field 'entry_point' cannot be empty.")
    elif entry_point not in normalized_repo_files:
        errors.append(
            f"entry_point '{entry_point}' not found in repository. Checked against {len(normalized_repo_files)} repo files."
        )

    # 6. Check predict_module file exists
    predict_module = str(config.get("predict_module", "")).replace("\\", "/").lstrip("/")
    if not predict_module:
        errors.append("Field 'predict_module' cannot be empty.")
    elif predict_module not in normalized_repo_files:
        errors.append(
            f"predict_module '{predict_module}' not found in repository."
        )

    # 7. Check dependencies file exists
    dependencies = str(config.get("dependencies", "")).replace("\\", "/").lstrip("/")
    if not dependencies:
        errors.append("Field 'dependencies' cannot be empty.")
    elif dependencies not in normalized_repo_files:
        errors.append(
            f"dependencies '{dependencies}' not found in repository."
        )

    # 8. Check target_column is non-empty
    target_col = config.get("target_column")
    if not isinstance(target_col, str) or not target_col.strip():
        errors.append("Field 'target_column' must be a non-empty string.")

    # 9. Check feature lists
    num_features = config.get("numerical_features", [])
    cat_features = config.get("categorical_features", [])
    if not isinstance(num_features, list) or not isinstance(cat_features, list):
        errors.append("Fields 'numerical_features' and 'categorical_features' must both be lists.")
    elif len(num_features) == 0 and len(cat_features) == 0:
        errors.append("At least one feature list ('numerical_features' or 'categorical_features') must be non-empty.")

    # 10. Check metrics_threshold keys match task_type
    metrics_threshold = config.get("metrics_threshold")
    if not isinstance(metrics_threshold, dict) or len(metrics_threshold) == 0:
        errors.append("Field 'metrics_threshold' must be a non-empty dictionary of metric target thresholds.")
    else:
        allowed_metrics = CLASSIFICATION_METRICS if task_type == "classification" else REGRESSION_METRICS
        for metric_name, val in metrics_threshold.items():
            if metric_name not in allowed_metrics:
                errors.append(
                    f"Metric '{metric_name}' is not allowed for task_type '{task_type}'. "
                    f"Permitted metrics: {sorted(list(allowed_metrics))}."
                )
            if not isinstance(val, (int, float)):
                errors.append(f"Threshold for metric '{metric_name}' must be numeric (got {type(val).__name__}).")

    return len(errors) == 0, errors
