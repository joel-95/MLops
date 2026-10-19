import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend.db.models import init_db

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_database():
    init_db()


def test_health_endpoint():
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "healthy"


def test_connect_repo_flow():
    payload = {
        "github_url": "https://github.com/joel-test/ml-test-repo",
        "owner": "joel-test",
        "yaml_content": """
framework: "sklearn"
task_type: "classification"
entry_point: "ml/train.py"
predict_module: "ml/predict.py"
target_column: "label"
numerical_features: ["feat_1"]
categorical_features: []
metrics_threshold:
  accuracy: 0.80
dependencies: "requirements.txt"
        """,
        "repo_file_list": ["ml/train.py", "ml/predict.py", "requirements.txt"]
    }

    # 1. Connect
    res = client.post("/repos/connect", json=payload)
    assert res.status_code == 201
    data = res.json()
    assert data["repo_id"] == "repo_ml_test_repo"
    assert data["assigned_port"] >= 8001
    assert "generated_workflow" in data

    # 2. Get Status
    res_status = client.get(f"/status/{data['repo_id']}")
    assert res_status.status_code == 200
    status_json = res_status.json()
    assert status_json["repo_id"] == data["repo_id"]
    assert "monitoring" in status_json
    assert "deployment" in status_json
    assert "reports" in status_json

    # 3. List
    res_list = client.get("/repos")
    assert res_list.status_code == 200
    assert any(r["id"] == data["repo_id"] for r in res_list.json())

    # 4. Retrain
    res_retrain = client.post(f"/repos/{data['repo_id']}/retrain", json={"reason": "test"})
    assert res_retrain.status_code == 200

    # 5. Disconnect
    res_del = client.delete(f"/repos/{data['repo_id']}")
    assert res_del.status_code == 200
