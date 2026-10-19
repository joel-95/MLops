import sqlite3
import json
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List
import pandas as pd

DEFAULT_LOGS_DIR = os.getenv("TRAFFIC_LOGS_DIR", "logs")


def _get_db_path(repo_id: str) -> Path:
    repo_dir = Path(DEFAULT_LOGS_DIR) / repo_id
    repo_dir.mkdir(parents=True, exist_ok=True)
    return repo_dir / "traffic.db"


def init_traffic_db(repo_id: str) -> None:
    """Initializes the SQLite traffic table for a given repo."""
    db_path = _get_db_path(repo_id)
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS predictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                input_json TEXT NOT NULL,
                output_json TEXT NOT NULL,
                prediction_val TEXT,
                confidence REAL
            )
            """
        )
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON predictions(timestamp);")
        conn.commit()


def log_prediction(repo_id: str, input_dict: Dict[str, Any], output_dict: Dict[str, Any]) -> int:
    """
    Logs an inference request and response to the repo's SQLite traffic store.
    
    Args:
        repo_id: Identifier of the repository
        input_dict: Dictionary of input features passed to /predict
        output_dict: Dictionary returned by predict()

    Returns:
        The inserted row ID
    """
    init_traffic_db(repo_id)
    db_path = _get_db_path(repo_id)

    prediction_val = str(output_dict.get("prediction", ""))
    confidence = output_dict.get("confidence")
    if confidence is not None:
        try:
            confidence = float(confidence)
        except (ValueError, TypeError):
            confidence = None

    timestamp_str = datetime.utcnow().isoformat()

    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO predictions (timestamp, input_json, output_json, prediction_val, confidence)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                timestamp_str,
                json.dumps(input_dict),
                json.dumps(output_dict),
                prediction_val,
                confidence
            )
        )
        conn.commit()
        return cursor.lastrowid


def get_recent_traffic(repo_id: str, n_records: int = 500) -> pd.DataFrame:
    """
    Fetches the most recent n_records prediction requests as a pandas DataFrame,
    with input feature keys flattened as columns.
    
    Returns:
        pd.DataFrame containing feature columns + timestamp, prediction, confidence.
    """
    db_path = _get_db_path(repo_id)
    if not db_path.exists():
        return pd.DataFrame()

    with sqlite3.connect(db_path) as conn:
        query = """
            SELECT id, timestamp, input_json, prediction_val, confidence
            FROM predictions
            ORDER BY id DESC
            LIMIT ?
        """
        cursor = conn.cursor()
        cursor.execute(query, (n_records,))
        rows = cursor.fetchall()

    if not rows:
        return pd.DataFrame()

    records: List[Dict[str, Any]] = []
    for row in reversed(rows):  # Chronological order
        row_id, ts, input_json_str, pred_val, conf = row
        try:
            input_features = json.loads(input_json_str)
        except Exception:
            input_features = {}

        record = dict(input_features)
        record["_timestamp"] = ts
        record["_prediction"] = pred_val
        record["_confidence"] = conf
        records.append(record)

    return pd.DataFrame(records)


def get_traffic_count(repo_id: str) -> int:
    """Returns the total number of logged predictions for this repo."""
    db_path = _get_db_path(repo_id)
    if not db_path.exists():
        return 0
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM predictions")
        return cursor.fetchone()[0]
