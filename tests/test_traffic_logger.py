import os
import shutil
import pytest
from monitoring.traffic_logger import log_prediction, get_recent_traffic, get_traffic_count


@pytest.fixture(autouse=True)
def cleanup_traffic_logs():
    test_dir = "test_traffic_logs"
    os.environ["TRAFFIC_LOGS_DIR"] = test_dir
    yield
    if os.path.exists(test_dir):
        shutil.rmtree(test_dir, ignore_errors=True)


def test_log_and_retrieve_predictions():
    repo_id = "test_repo_traffic"
    input_1 = {"sepal_length": 5.1, "sepal_width": 3.5}
    output_1 = {"prediction": 0, "confidence": 0.95}

    input_2 = {"sepal_length": 6.7, "sepal_width": 3.0}
    output_2 = {"prediction": 1, "confidence": 0.88}

    log_prediction(repo_id, input_1, output_1)
    log_prediction(repo_id, input_2, output_2)

    count = get_traffic_count(repo_id)
    assert count == 2

    df = get_recent_traffic(repo_id, n_records=10)
    assert len(df) == 2
    assert "sepal_length" in df.columns
    assert "_prediction" in df.columns
    assert "_confidence" in df.columns
