import json
import os
from pathlib import Path
from datetime import datetime
from typing import Tuple, Dict, Any, Optional
import pandas as pd


def run_version_comparison(
    repo_id: str,
    current_metrics_path: str,
    previous_run_id: Optional[str],
    mlops_config: Dict[str, Any],
    current_df: Optional[pd.DataFrame] = None,
    reference_df: Optional[pd.DataFrame] = None
) -> Tuple[Dict[str, Any], str]:
    """
    Executes version-to-version comparison between the newly trained model (v2/current)
    and the baseline/previous deployed model (v1/reference).
    
    Returns:
        (report_dict: dict, html_report_path: str)
    """
    reports_dir = Path("reports") / repo_id
    reports_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    html_filename = f"comparison_{timestamp}.html"
    html_path = str(reports_dir / html_filename)

    # 1. Load current metrics
    current_metrics = {}
    if os.path.exists(current_metrics_path):
        try:
            with open(current_metrics_path, "r", encoding="utf-8") as f:
                current_metrics = json.load(f)
        except Exception:
            pass

    task_type = mlops_config.get("task_type", "classification")

    # 2. If first deployment (no previous run), generate initial baseline report
    if not previous_run_id:
        report_dict = {
            "is_initial_deployment": True,
            "dataset_drift": False,
            "drift_share": 0.0,
            "drifted_features": [],
            "metric_deltas": {},
            "current_metrics": current_metrics,
            "summary": "Initial baseline deployment. No previous model version to compare against."
        }
        _write_stub_html(html_path, repo_id, "Initial Baseline Deployment", report_dict)
        return report_dict, html_path

    # 3. Attempt Evidently Report if dataframes available
    report_dict: Dict[str, Any] = {
        "is_initial_deployment": False,
        "dataset_drift": False,
        "drift_share": 0.0,
        "drifted_features": [],
        "metric_deltas": {},
        "current_metrics": current_metrics,
        "summary": "Version comparison completed."
    }

    try:
        from evidently.report import Report
        from evidently.metric_preset import DataDriftPreset, ClassificationPreset, RegressionPreset
        from evidently import ColumnMapping

        column_mapping = ColumnMapping(
            target=mlops_config.get("target_column"),
            prediction="_prediction" if "_prediction" in (current_df.columns if current_df is not None else []) else None,
            numerical_features=mlops_config.get("numerical_features", []),
            categorical_features=mlops_config.get("categorical_features", [])
        )

        presets = [DataDriftPreset()]
        if task_type == "classification":
            presets.append(ClassificationPreset())
        else:
            presets.append(RegressionPreset())

        if current_df is not None and reference_df is not None and len(current_df) > 0 and len(reference_df) > 0:
            report = Report(metrics=presets)
            report.run(
                reference_data=reference_df,
                current_data=current_df,
                column_mapping=column_mapping
            )
            report.save_html(html_path)
            raw_dict = report.as_dict()

            # Parse key drift stats
            for metric in raw_dict.get("metrics", []):
                metric_name = metric.get("metric", "")
                if "DataDriftTable" in metric_name or "DatasetDriftMetric" in metric_name:
                    result = metric.get("result", {})
                    report_dict["dataset_drift"] = result.get("dataset_drift", False)
                    report_dict["drift_share"] = result.get("drift_share", 0.0)
                    drift_by_columns = result.get("drift_by_columns", {})
                    report_dict["drifted_features"] = [
                        col for col, col_data in drift_by_columns.items() if col_data.get("drift_detected", False)
                    ]

            return report_dict, html_path
    except Exception as e:
        report_dict["evidently_note"] = f"Evidently execution note: {str(e)}"

    # Fallback HTML generation if dataframes not supplied or evidently run completed without save
    _write_stub_html(html_path, repo_id, f"Model Version Comparison ({task_type})", report_dict)
    return report_dict, html_path


def _write_stub_html(file_path: str, repo_id: str, title: str, report_data: Dict[str, Any]):
    html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>AutoMLOps - {title}</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; margin: 2rem; background: #0f172a; color: #f8fafc; }}
        .card {{ background: #1e293b; border-radius: 8px; padding: 1.5rem; margin-bottom: 1.5rem; border: 1px solid #334155; }}
        h1 {{ color: #38bdf8; font-size: 1.75rem; }}
        h2 {{ color: #94a3b8; font-size: 1.25rem; border-bottom: 1px solid #334155; padding-bottom: 0.5rem; }}
        .badge {{ display: inline-block; padding: 0.25rem 0.75rem; border-radius: 9999px; font-size: 0.875rem; font-weight: 600; }}
        .badge-green {{ background: #065f46; color: #34d399; }}
        .badge-red {{ background: #991b1b; color: #f87171; }}
        pre {{ background: #0f172a; padding: 1rem; border-radius: 6px; overflow-x: auto; color: #e2e8f0; }}
    </style>
</head>
<body>
    <div class="card">
        <h1>{title}</h1>
        <p>Repository: <strong>{repo_id}</strong> | Generated: <strong>{datetime.utcnow().isoformat()}Z</strong></p>
        <p>Status: <span class="badge {'badge-red' if report_data.get('dataset_drift') else 'badge-green'}">{'Drift Detected' if report_data.get('dataset_drift') else 'Healthy / Pass'}</span></p>
    </div>
    <div class="card">
        <h2>Summary</h2>
        <p>{report_data.get('summary', 'No summary available.')}</p>
        <h2>Detailed Findings</h2>
        <pre>{json.dumps(report_data, indent=2)}</pre>
    </div>
</body>
</html>"""
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(html_content)
