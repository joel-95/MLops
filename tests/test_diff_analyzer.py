import pytest
from change_explainer.diff_analyzer import analyze_code_diff

OLD_SCRIPT = """
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler

scaler = StandardScaler()
model = RandomForestClassifier(n_estimators=100, max_depth=4, learning_rate=0.01)
"""

NEW_SCRIPT = """
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler

scaler = StandardScaler()
model = RandomForestClassifier(n_estimators=250, max_depth=8, learning_rate=0.001)
"""

MODEL_CHANGE_SCRIPT = """
from sklearn.ensemble import GradientBoostingClassifier
model = GradientBoostingClassifier(n_estimators=100)
"""


def test_diff_analyzer_hyperparameter_changes():
    findings = analyze_code_diff(OLD_SCRIPT, NEW_SCRIPT)
    assert len(findings) > 0
    assert any("n_estimators" in f and "100 to 250" in f for f in findings)
    assert any("max_depth" in f and "4 to 8" in f for f in findings)
    assert any("learning_rate" in f and "0.01 to 0.001" in f for f in findings)


def test_diff_analyzer_model_architecture_change():
    findings = analyze_code_diff(OLD_SCRIPT, MODEL_CHANGE_SCRIPT)
    assert any("Model architecture changed" in f for f in findings)


def test_diff_analyzer_identical_scripts():
    findings = analyze_code_diff(OLD_SCRIPT, OLD_SCRIPT)
    assert findings == ["No code or hyperparameter modifications detected in training script."]
