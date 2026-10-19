import os
import json
import logging
import threading
from datetime import datetime
from typing import Dict, Any, Optional
import pandas as pd

from backend.db.models import SessionLocal, Repo, Run, MonitoringState
from monitoring.traffic_logger import get_recent_traffic
from monitoring.alerts import send_alert
from monitoring.retrain_trigger import trigger_retrain
from comparator.comparator import run_version_comparison
from comparator.production_drift import check_production_drift
from anomaly.score_anomaly import score_requests, check_anomaly_rate
from anomaly.train_anomaly_model import train_anomaly_detector
from change_explainer.diff_analyzer import analyze_code_diff
from change_explainer.report_builder import build_change_report
from ml.mlflow_integration import get_previous_run

logger = logging.getLogger("automlops.monitor")


def monitoring_cycle(repo_id: str) -> Dict[str, Any]:
    """
    Scheduled monitoring evaluation cycle for an actively deployed repository.
    Fetches live prediction requests, assesses data drift & anomaly rate,
    and invokes retraining + alerts if thresholds are breached.
    """
    db = SessionLocal()
    try:
        repo = db.query(Repo).filter(Repo.id == repo_id).first()
        if not repo:
            return {"status": "error", "message": f"Repo {repo_id} not found"}

        mlops_config = repo.mlops_yaml or {}

        # 1. Fetch recent live prediction logs
        live_df = get_recent_traffic(repo_id, n_records=500)
        num_features = mlops_config.get("numerical_features", [])

        if live_df.empty or len(live_df) < 5:
            logger.info(f"Monitoring cycle for {repo_id}: insufficient traffic ({len(live_df)} records).")
            return {
                "status": "skipped",
                "message": f"Insufficient live traffic data ({len(live_df)} records).",
                "traffic_count": len(live_df)
            }

        # 2. Check Anomaly Rate using Isolation Forest
        model_path = os.path.join("artifacts", repo_id, "anomaly_model.pkl")
        scaler_path = os.path.join("artifacts", repo_id, "anomaly_scaler.pkl")

        scored_df = score_requests(live_df, model_path, scaler_path)
        anomaly_exceeded, anomaly_rate = check_anomaly_rate(scored_df, threshold=0.15)

        # 3. Check Production Feature Drift
        # For baseline, try loading training dataset if available
        baseline_path = mlops_config.get("dataset_path")
        baseline_df = None
        if baseline_path and os.path.exists(baseline_path):
            try:
                baseline_df = pd.read_csv(baseline_path)
            except Exception:
                pass

        if baseline_df is None:
            # If training dataset not directly accessible, synthesize minimal baseline from early traffic
            baseline_df = live_df.head(min(50, len(live_df)))

        drift_detected, drifted_cols, drift_html = check_production_drift(
            repo_id=repo_id,
            baseline_df=baseline_df,
            recent_live_df=live_df,
            mlops_config=mlops_config
        )

        # 4. Update Monitoring State in Database
        state = db.query(MonitoringState).filter(MonitoringState.repo_id == repo_id).first()
        if not state:
            state = MonitoringState(repo_id=repo_id)
            db.add(state)

        state.drift_detected = drift_detected
        state.drifted_columns = drifted_cols
        state.anomaly_rate = round(float(anomaly_rate), 4)
        state.production_drift_html = drift_html
        state.last_checked_at = datetime.utcnow()
        db.commit()

        # 5. Evaluate combined signals and trigger automated retraining if required
        should_retrain = drift_detected or anomaly_exceeded
        retrain_result = None

        if should_retrain:
            reasons = []
            if drift_detected:
                reasons.append(f"Data Drift in {drifted_cols}")
            if anomaly_exceeded:
                reasons.append(f"Anomaly Rate {round(anomaly_rate * 100, 1)}% > 15%")
            reason_str = " + ".join(reasons)

            retrain_result = trigger_retrain(
                repo_id=repo_id,
                reason=reason_str,
                details={
                    "drift_detected": drift_detected,
                    "drifted_columns": drifted_cols,
                    "anomaly_rate": anomaly_rate
                }
            )

        return {
            "status": "completed",
            "repo_id": repo_id,
            "drift_detected": drift_detected,
            "drifted_columns": drifted_cols,
            "anomaly_rate": round(anomaly_rate, 4),
            "anomaly_exceeded": anomaly_exceeded,
            "retrain_triggered": should_retrain,
            "retrain_result": retrain_result
        }

    finally:
        db.close()


def on_training_complete(
    repo_id: str,
    metrics_path: str,
    commit_sha: str,
    baseline_df: Optional[pd.DataFrame] = None,
    mlops_config: Optional[Dict[str, Any]] = None,
    new_script_source: Optional[str] = None,
    old_script_source: Optional[str] = None
) -> Dict[str, Any]:
    """
    Executed immediately upon completion of a new training run.
    Runs version comparison, AST diff analysis, and asynchronously starts Isolation Forest training.
    """
    db = SessionLocal()
    try:
        repo = db.query(Repo).filter(Repo.id == repo_id).first()
        config = mlops_config or (repo.mlops_yaml if repo else {})

        # 1. Fetch previous run from MLflow for reference
        prev_run = get_previous_run(repo_id)
        prev_run_id = prev_run.get("run_id") if prev_run else None
        old_metrics = prev_run.get("metrics") if prev_run else {}

        # 2. Run Version Comparison (Evidently)
        comp_report, comp_html = run_version_comparison(
            repo_id=repo_id,
            current_metrics_path=metrics_path,
            previous_run_id=prev_run_id,
            mlops_config=config,
            current_df=baseline_df,
            reference_df=baseline_df
        )

        # 3. Code Diff Analysis (AST)
        code_findings = analyze_code_diff(
            old_source=old_script_source or "",
            new_source=new_script_source or ""
        )

        # 4. Build Change Explainer Report
        current_metrics = {}
        if os.path.exists(metrics_path):
            try:
                with open(metrics_path, "r", encoding="utf-8") as f:
                    current_metrics = json.load(f)
            except Exception:
                pass

        change_report = build_change_report(
            code_findings=code_findings,
            comparator_report=comp_report,
            old_metrics=old_metrics,
            new_metrics=current_metrics
        )

        # 5. Persist Monitoring and Explainer State
        state = db.query(MonitoringState).filter(MonitoringState.repo_id == repo_id).first()
        if not state:
            state = MonitoringState(repo_id=repo_id)
            db.add(state)

        state.version_comparison_html = comp_html
        state.change_explainer_summary = change_report.get("summary")
        state.change_explainer_details = change_report.get("details")
        db.commit()

        # 6. ASYNC Isolation Forest Model Training (Vulnerability Fix 4.3)
        # We start training the Isolation Forest in a background thread so deployment is never blocked!
        if baseline_df is not None and not baseline_df.empty:
            num_features = config.get("numerical_features", [])
            thread = threading.Thread(
                target=train_anomaly_detector,
                kwargs={
                    "repo_id": repo_id,
                    "baseline_df": baseline_df,
                    "numerical_features": num_features,
                    "output_dir": "artifacts"
                },
                daemon=True
            )
            thread.start()
            logger.info(f"Asynchronous Isolation Forest training launched for {repo_id}")

        return {
            "status": "success",
            "version_comparison_html": comp_html,
            "change_report": change_report,
            "async_anomaly_training": True
        }

    finally:
        db.close()
