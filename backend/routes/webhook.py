import json
import logging
from datetime import datetime
from fastapi import APIRouter, Request, HTTPException, Header, Depends
from sqlalchemy.orm import Session
from typing import Optional, Dict, Any

from backend.db.models import get_db, Repo, Run, Deployment
from github_app.app_config import verify_webhook_signature
from deploy.local_deploy import deploy_model
from monitoring.monitor import on_training_complete
from monitoring.alerts import send_alert

router = APIRouter()
logger = logging.getLogger("automlops.webhook")


@router.post("/github")
async def github_webhook(
    request: Request,
    x_hub_signature_256: Optional[str] = Header(None),
    x_github_event: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    """
    Receives incoming GitHub webhooks (push, pull_request, etc.).
    Verifies HMAC-SHA256 signature and triggers the training workflow.
    """
    payload_bytes = await request.body()

    # 1. Signature Verification (reject all unverified webhooks)
    if not verify_webhook_signature(payload_bytes, x_hub_signature_256):
        logger.warning("Rejected webhook: Invalid or missing HMAC signature.")
        raise HTTPException(status_code=401, detail="Invalid HMAC-SHA256 signature")

    try:
        payload = json.loads(payload_bytes)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    # Handle push event
    if x_github_event == "push":
        repository = payload.get("repository", {})
        repo_name = repository.get("name")
        owner = repository.get("owner", {}).get("login") or repository.get("owner", {}).get("name")
        commit_sha = payload.get("after") or "head"
        ref = payload.get("ref", "")

        # Look up repo in database
        repo = db.query(Repo).filter((Repo.repo_name == repo_name) | (Repo.id == repo_name)).first()
        if not repo:
            logger.info(f"Ignored push event for unconnected repo: {repo_name}")
            return {"status": "ignored", "reason": "Repository not connected to AutoMLOps"}

        # Record pending Run
        run_record = Run(
            id=f"run_{repo.id}_{commit_sha[:8]}_{int(datetime.utcnow().timestamp())}",
            repo_id=repo.id,
            commit_sha=commit_sha,
            status="pending",
            triggered_by="push",
            started_at=datetime.utcnow()
        )
        db.add(run_record)
        db.commit()

        send_alert(
            f"🚀 Push detected on `{repo.repo_name}` (`{commit_sha[:7]}`). Training pipeline queued on self-hosted runner.",
            severity="info"
        )

        return {
            "status": "queued",
            "run_id": run_record.id,
            "commit_sha": commit_sha,
            "branch": ref
        }

    return {"status": "received", "event": x_github_event}


@router.post("/pipeline-result")
async def pipeline_result_callback(
    payload: Dict[str, Any],
    db: Session = Depends(get_db)
):
    """
    Callback endpoint invoked by GitHub Actions runner or local runner
    when training and quality gate finish.
    """
    repo_id = payload.get("repo_id")
    commit_sha = payload.get("commit_sha", "unknown")
    status = payload.get("status", "failed")  # "passed" | "failed"
    metrics = payload.get("metrics", {})

    repo = db.query(Repo).filter((Repo.id == repo_id) | (Repo.repo_name == repo_id)).first()
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")

    # Update or create Run record
    run_record = (
        db.query(Run)
        .filter(Run.repo_id == repo.id)
        .order_by(Run.started_at.desc())
        .first()
    )

    if not run_record:
        run_record = Run(
            id=f"run_{repo.id}_{commit_sha[:8]}",
            repo_id=repo.id,
            commit_sha=commit_sha,
            status=status,
            started_at=datetime.utcnow()
        )
        db.add(run_record)

    run_record.status = status
    run_record.quality_gate_result = status
    run_record.metrics_json = metrics
    run_record.completed_at = datetime.utcnow()
    db.commit()

    if status == "passed":
        # 1. Quality gate passed -> Deploy model immediately
        deploy_result = deploy_model(
            repo_id=repo.id,
            model_artifact_path=metrics.get("model_artifact_path", "artifacts/model.pkl"),
            commit_sha=commit_sha
        )

        # 2. Trigger Version Comparison, AST Diff, and Async Anomaly Model Training
        try:
            on_training_complete(
                repo_id=repo.id,
                metrics_path="metrics.json",
                commit_sha=commit_sha,
                mlops_config=repo.mlops_yaml
            )
        except Exception as e:
            logger.error(f"Post-training monitoring error: {str(e)}")

        send_alert(
            f"🎉 Quality gate passed! Model `{repo.repo_name}` deployed on port `{deploy_result['port']}`.\n"
            f"Live URL: {deploy_result['tunnel_url']}",
            severity="success"
        )
        return {"status": "deployed", "deployment": deploy_result}
    else:
        send_alert(
            f"❌ Quality gate failed for `{repo.repo_name}` (`{commit_sha[:7]}`). Deployment rejected.",
            severity="critical"
        )
        return {"status": "rejected", "reason": "Quality gate failed"}
