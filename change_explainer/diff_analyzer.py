import ast
from typing import List, Dict, Any, Optional

KNOWN_HYPERPARAMETERS = {
    "learning_rate", "lr", "n_estimators", "max_depth", "epochs",
    "batch_size", "test_size", "random_state", "c", "gamma",
    "kernel", "alpha", "penalty", "subsample", "colsample_bytree"
}

KNOWN_PREPROCESSING_CALLS = {
    "standardscaler", "minmaxscaler", "onehotencoder", "labelencoder",
    "drop", "fillna", "dropna", "train_test_split", "simpleimputer"
}


def _extract_ast_info(source_code: str) -> Dict[str, Any]:
    """
    Parses Python source code using the AST module to extract:
    - Named keyword arguments across function / class calls
    - Instantiated model classes
    - Preprocessing function/method calls
    """
    info = {
        "params": {},
        "model_classes": set(),
        "preprocessing_calls": set()
    }

    try:
        tree = ast.parse(source_code)
    except SyntaxError:
        return info

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            # 1. Identify function/class name
            func_name = ""
            if isinstance(node.func, ast.Name):
                func_name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                func_name = node.func.attr

            lower_name = func_name.lower()

            # Check if model class name (e.g., ends in Classifier, Regressor, or known names)
            if any(term in lower_name for term in ["classifier", "regressor", "forest", "tree", "svm", "xgb", "lgbm"]):
                info["model_classes"].add(func_name)

            # Check if preprocessing call
            if lower_name in KNOWN_PREPROCESSING_CALLS:
                info["preprocessing_calls"].add(func_name)

            # 2. Extract keyword arguments
            for kw in node.keywords:
                if kw.arg and kw.arg.lower() in KNOWN_HYPERPARAMETERS:
                    val = _node_to_value(kw.value)
                    info["params"][kw.arg] = val

    return info


def _node_to_value(node: ast.AST) -> Any:
    """Converts AST literal node to standard Python value."""
    if isinstance(node, ast.Constant):
        return node.value
    elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USys or ast.UAdd):
        val = _node_to_value(node.operand)
        return -val if isinstance(node.op, ast.USub) else val
    elif isinstance(node, ast.List):
        return [_node_to_value(elt) for elt in node.elts]
    elif isinstance(node, ast.Tuple):
        return tuple(_node_to_value(elt) for elt in node.elts)
    elif isinstance(node, ast.Name):
        return node.id
    return "<complex_expression>"


def analyze_code_diff(old_source: str, new_source: str) -> List[str]:
    """
    Compares two training scripts using AST parsing and returns actionable findings.
    
    Returns:
        List of plain-language strings describing detected changes.
    """
    if not old_source.strip() or not new_source.strip():
        return ["Initial code revision — no previous training script available to diff against."]

    if old_source.strip() == new_source.strip():
        return ["No code or hyperparameter modifications detected in training script."]

    old_info = _extract_ast_info(old_source)
    new_info = _extract_ast_info(new_source)

    findings: List[str] = []

    # 1. Compare Model Classes
    old_models = old_info["model_classes"]
    new_models = new_info["model_classes"]
    if old_models != new_models and new_models:
        old_str = ", ".join(sorted(list(old_models))) or "None"
        new_str = ", ".join(sorted(list(new_models)))
        findings.append(f"Model architecture changed: '{old_str}' → '{new_str}'")

    # 2. Compare Hyperparameters
    all_param_keys = set(old_info["params"].keys()).union(new_info["params"].keys())
    for k in sorted(list(all_param_keys)):
        old_val = old_info["params"].get(k)
        new_val = new_info["params"].get(k)
        if old_val != new_val:
            if old_val is None:
                findings.append(f"Added hyperparameter '{k} = {new_val}'")
            elif new_val is None:
                findings.append(f"Removed hyperparameter '{k}' (was {old_val})")
            else:
                findings.append(f"Hyperparameter '{k}' updated from {old_val} to {new_val}")

    # 3. Compare Preprocessing Calls
    old_prep = old_info["preprocessing_calls"]
    new_prep = new_info["preprocessing_calls"]
    added_prep = new_prep - old_prep
    removed_prep = old_prep - new_prep

    for p in sorted(list(added_prep)):
        findings.append(f"Introduced preprocessing step: '{p}'")
    for p in sorted(list(removed_prep)):
        findings.append(f"Removed preprocessing step: '{p}'")

    if not findings:
        findings.append("Script modified with internal or non-hyperparameter code changes.")

    return findings
