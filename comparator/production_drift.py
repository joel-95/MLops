import os
import json
from pathlib import Path
from datetime import datetime
from typing import Tuple, List, Dict, Any
import pandas as pd
import numpy as np


def check_production_drift(
    repo_id: str,
    baseline_df: pd.DataFrame,
    recent_live_df: pd.DataFrame,
    mlops_config: Dict[str, Any]
) -> Tuple[bool, List[str], str]:
    """
    Checks for production feature drift between training baseline and recent live traffic.
    Uses Evidently DataDriftPreset (no classification/regression preset, as live traffic lacks labels).

    Returns:
        (drift_detected: bool, drifted_columns: list[str], html_report_path: str)
    """
    reports_dir = Path("reports") / repo_id
    reports_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    html_path = str(reports_dir / f"drift_{timestamp}.html")

    numerical_features = mlops_config.get("numerical_features", [])
    categorical_features = mlops_config.get("categorical_features", [])
    all_features = [f for f in numerical_features + categorical_features if f in baseline_df.columns and f in recent_live_df.columns]

    if not all_features or len(recent_live_df) < 5 or len(baseline_df) < 5:
        # Insufficient data to reliably test distribution drift
        _write_drift_html(html_path, repo_id, False, [], "Insufficient sample size to assess data drift.")
        return False, [], html_path

    drift_detected = False
    drifted_columns: List[str] = []

    try:
        from evidently.report import Report
        from evidently.metric_preset import DataDriftPreset
        from evidently import ColumnMapping

        column_mapping = ColumnMapping(
            numerical_features=[f for f in numerical_features if f in all_features],
            categorical_features=[f for f in categorical_features if f in all_features]
        )

        report = Report(metrics=[DataDriftPreset()])
        report.run(
            reference_data=baseline_df[all_features],
            current_data=recent_live_df[all_features],
            column_mapping=column_mapping
        )
        report.save_html(html_path)
        raw_dict = report.as_dict()

        for metric in raw_dict.get("metrics", []):
            if "DataDriftTable" in metric.get("metric", "") or "DatasetDriftMetric" in metric.get("metric", ""):
                res = metric.get("result", {})
                drift_detected = res.get("dataset_drift", False)
                drift_by_cols = res.get("drift_by_columns", {})
                drifted_columns = [
                    col for col, data in drift_by_cols.items() if data.get("drift_detected", False)
                ]
                break

        return drift_detected, drifted_columns, html_path

    except Exception as e:
        # Statistical fallback using Kolmogorov-Smirnov test for numerical features
        from scipy import stats
        for col in numerical_features:
            if col in baseline_df.columns and col in recent_live_df.columns:
                try:
                    b_vals = baseline_df[col].dropna()
                    l_vals = recent_live_df[col].dropna()
                    if len(b_vals) > 5 and len(l_vals) > 5:
                        ks_stat, p_val = stats.ks_2samp(b_vals, l_vals)
                        if p_val < 0.05:
                            drifted_columns.append(col)
                except Exception:
                    pass

        drift_detected = len(drifted_columns) > (len(all_features) / 3)
        summary = f"Statistical KS fallback applied ({len(drifted_columns)} drifted columns detected). Note: {str(e)}"
        _write_drift_html(html_path, repo_id, drift_detected, drifted_columns, summary)
        return drift_detected, drifted_columns, html_path


def _write_drift_html(file_path: str, repo_id: str, drift: bool, drifted_cols: List[str], note: str):
    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>AutoMLOps - Production Drift Report</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; margin: 2rem; background: #0f172a; color: #f8fafc; }}
        .card {{ background: #1e293b; border-radius: 8px; padding: 1.5rem; margin-bottom: 1.5rem; border: 1px solid #334155; }}
        h1 {{ color: #38bdf8; }}
        .badge {{ display: inline-block; padding: 0.25rem 0.75rem; border-radius: 9999px; font-size: 0.875rem; font-weight: 600; }}
        .badge-green {{ background: #065f46; color: #34d399; }}
        .badge-red {{ background: #991b1b; color: #f87171; }}
    </style>
</head>
<body>
    <div class="card">
        <h1>Production Data Drift Report</h1>
        <p>Repository: <strong>{repo_id}</strong> | Timestamp: <strong>{datetime.utcnow().isoformat()}Z</strong></p>
        <p>Status: <span class="badge {'badge-red' if drift else 'badge-green'}">{'Drift Detected' if drift else 'Normal / In-Distribution'}</span></p>
        <p>{note}</p>
        <h3>Drifted Columns:</h3>
        <p>{', '.join(drifted_cols) if drifted_cols else 'None'}</p>
    </div>
</body>
</html>"""
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(html)
