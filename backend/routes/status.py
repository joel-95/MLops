from datetime import datetime, timedelta
from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.db.models import get_db, Repo, Run, Deployment, MonitoringState, Retrain
from monitoring.retrain_trigger import check_circuit_breaker, MAX_AUTO_RETRAINS_PER_24H

router = APIRouter()


@router.get("/{repo_id}")
def get_status(repo_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    """
    Returns the unified platform status for a repository, strictly adhering
    to the contract established in Section 2.3 of the AutoMLOps specification.
    """
    repo = db.query(Repo).filter(Repo.id == repo_id).first()
    if not repo:
        raise HTTPException(status_code=404, detail=f"Repository '{repo_id}' not found")

    # 1. Latest Run
    latest_run = (
        db.query(Run)
        .filter(Run.repo_id == repo_id)
        .order_by(Run.started_at.desc())
        .first()
    )

    latest_run_dict = None
    if latest_run:
        latest_run_dict = {
            "run_id": latest_run.id,
            "commit_sha": latest_run.commit_sha,
            "status": latest_run.status,
            "triggered_by": latest_run.triggered_by,
            "started_at": latest_run.started_at.isoformat() if latest_run.started_at else None,
            "completed_at": latest_run.completed_at.isoformat() if latest_run.completed_at else None,
            "metrics": latest_run.metrics_json or {},
            "quality_gate": latest_run.quality_gate_result or "unknown"
        }

    # 2. Deployment Details
    deployment = db.query(Deployment).filter(Deployment.repo_id == repo_id).first()
    deployment_dict = {
        "status": deployment.status if deployment else "inactive",
        "url": deployment.tunnel_url if deployment and deployment.status == "active" else None,
        "port": deployment.port if deployment else (8000 + repo.sequential_id),
        "deployed_commit_sha": deployment.deployed_commit_sha if deployment else None,
        "deployed_at": deployment.deployed_at.isoformat() if deployment and deployment.deployed_at else None
    }

    # 3. Monitoring State & Circuit Breaker
    monitoring_state = db.query(MonitoringState).filter(MonitoringState.repo_id == repo_id).first()
    is_allowed, retrain_count_24h = check_circuit_breaker(repo_id, db=db)
    circuit_breaker_active = not is_allowed

    monitoring_dict = {
        "drift_detected": monitoring_state.drift_detected if monitoring_state else False,
        "drifted_columns": monitoring_state.drifted_columns if monitoring_state else [],
        "anomaly_rate": monitoring_state.anomaly_rate if monitoring_state else 0.0,
        "anomaly_threshold": monitoring_state.anomaly_threshold if monitoring_state else 0.15,
        "last_checked_at": monitoring_state.last_checked_at.isoformat() if monitoring_state and monitoring_state.last_checked_at else None,
        "retrain_count_24h": retrain_count_24h,
        "circuit_breaker_active": circuit_breaker_active,
        "max_retrains_limit": MAX_AUTO_RETRAINS_PER_24H
    }

    # 4. Reports & Change Explainer
    v_html = monitoring_state.version_comparison_html if monitoring_state else None
    d_html = monitoring_state.production_drift_html if monitoring_state else None

    reports_dict = {
        "version_comparison_html": v_html.replace("\\", "/") if v_html else None,
        "production_drift_html": d_html.replace("\\", "/") if d_html else None,
        "change_explainer": {
            "summary": (monitoring_state.change_explainer_summary if monitoring_state else None)
                       or "No version changes analyzed yet.",
            "details": (monitoring_state.change_explainer_details if monitoring_state else None)
                       or ["Initial deployment active."]
        }
    }

    return {
        "repo_id": repo.id,
        "repo_name": repo.repo_name,
        "github_url": repo.github_url,
        "latest_run": latest_run_dict,
        "deployment": deployment_dict,
        "monitoring": monitoring_dict,
        "reports": reports_dict
    }
