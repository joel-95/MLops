import yaml
from datetime import datetime
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func

from backend.db.models import get_db, Repo, Run, Deployment
from backend.services.validator import validate_repo
from cicd.workflow_generator import generate_workflow
from deploy.local_deploy import stop_deployment
from monitoring.retrain_trigger import trigger_retrain

router = APIRouter()


class ConnectRepoRequest(BaseModel):
    github_url: str
    owner: Optional[str] = None
    yaml_content: Optional[str] = None
    repo_file_list: Optional[List[str]] = None


class RetrainRequest(BaseModel):
    reason: Optional[str] = "manual_trigger"


@router.post("/connect", status_code=status.HTTP_201_CREATED)
def connect_repo(payload: ConnectRepoRequest, db: Session = Depends(get_db)):
    """
    Registers a new GitHub repository with AutoMLOps.
    Validates mlops.yaml and assigns a deterministic sequential ID for port allocation.
    """
    github_url = payload.github_url.strip()
    repo_name = github_url.rstrip("/").split("/")[-1].replace(".git", "")
    owner = payload.owner or (github_url.rstrip("/").split("/")[-2] if len(github_url.split("/")) >= 2 else "user")
    repo_id = f"repo_{repo_name.lower().replace('-', '_')}"

    # Check if already connected
    existing = db.query(Repo).filter(Repo.id == repo_id).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Repository '{repo_name}' is already connected."
        )

    # 1. Validation: if yaml_content provided, validate immediately; else use default demo template
    yaml_content = payload.yaml_content
    file_list = payload.repo_file_list or ["ml/train.py", "ml/predict.py", "requirements.txt"]

    if yaml_content:
        is_valid, errors = validate_repo(yaml_content, file_list)
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"message": "mlops.yaml validation failed", "errors": errors}
            )
        parsed_yaml = yaml.safe_load(yaml_content)
    else:
        # Default starter manifest
        parsed_yaml = {
            "project_name": repo_name,
            "framework": "sklearn",
            "task_type": "classification",
            "entry_point": "ml/train.py",
            "predict_module": "ml/predict.py",
            "target_column": "target",
            "numerical_features": ["feature_1", "feature_2"],
            "categorical_features": [],
            "metrics_threshold": {"accuracy": 0.85},
            "dependencies": "requirements.txt"
        }

    # 2. Assign Next Sequential ID (Guarantees Port 8000 + seq_id)
    max_seq_id = db.query(func.max(Repo.sequential_id)).scalar()
    next_seq_id = 1 if max_seq_id is None else max_seq_id + 1

    # 3. Create Repo Record
    repo = Repo(
        id=repo_id,
        sequential_id=next_seq_id,
        repo_name=repo_name,
        github_url=github_url,
        owner=owner,
        mlops_yaml=parsed_yaml,
        is_deployed=False,
        created_at=datetime.utcnow()
    )
    db.add(repo)
    db.commit()
    db.refresh(repo)

    # 4. Generate CI/CD Workflow
    workflow_yaml = generate_workflow(parsed_yaml)

    return {
        "message": "Repository successfully connected to AutoMLOps",
        "repo_id": repo.id,
        "repo_name": repo.repo_name,
        "sequential_id": repo.sequential_id,
        "assigned_port": 8000 + repo.sequential_id,
        "mlops_config": parsed_yaml,
        "generated_workflow": workflow_yaml
    }


@router.get("")
def list_repos(db: Session = Depends(get_db)):
    """Lists all connected repositories and their current status."""
    repos = db.query(Repo).all()
    results = []
    for r in repos:
        latest_run = (
            db.query(Run)
            .filter(Run.repo_id == r.id)
            .order_by(Run.started_at.desc())
            .first()
        )
        deployment = db.query(Deployment).filter(Deployment.repo_id == r.id).first()
        results.append({
            "id": r.id,
            "repo_name": r.repo_name,
            "github_url": r.github_url,
            "owner": r.owner,
            "port": 8000 + r.sequential_id,
            "is_deployed": r.is_deployed,
            "latest_run_status": latest_run.status if latest_run else "no_runs",
            "tunnel_url": deployment.tunnel_url if deployment and deployment.status == "active" else None,
            "created_at": r.created_at.isoformat()
        })
    return results


@router.delete("/{repo_id}")
def disconnect_repo(repo_id: str, db: Session = Depends(get_db)):
    """Disconnects a repo, stops active serving containers, and removes DB records."""
    repo = db.query(Repo).filter(Repo.id == repo_id).first()
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")

    stop_deployment(repo_id)
    db.delete(repo)
    db.commit()

    return {"message": f"Repository '{repo_id}' successfully disconnected and resources freed."}


@router.post("/{repo_id}/retrain")
def manual_retrain(repo_id: str, payload: RetrainRequest, db: Session = Depends(get_db)):
    """
    Manually triggers automated retraining, bypassing the circuit breaker.
    """
    repo = db.query(Repo).filter(Repo.id == repo_id).first()
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")

    result = trigger_retrain(
        repo_id=repo_id,
        reason=payload.reason or "manual_user_override",
        force=True
    )
    return result
