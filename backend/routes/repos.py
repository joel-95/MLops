import os
import yaml
import numpy as np
import httpx
from datetime import datetime
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Header, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func

from backend.db.models import get_db, Repo, Run, Deployment
from backend.services.validator import validate_repo
from cicd.workflow_generator import generate_workflow
from deploy.local_deploy import stop_deployment
from monitoring.retrain_trigger import trigger_retrain
from monitoring.traffic_logger import log_prediction, get_traffic_count

router = APIRouter()


# ─── Request / Response Models ─────────────────────────────────────────────────

class ConnectRepoRequest(BaseModel):
    github_url: str
    owner: Optional[str] = None
    yaml_content: Optional[str] = None
    repo_file_list: Optional[List[str]] = None


class RetrainRequest(BaseModel):
    reason: Optional[str] = "manual_trigger"


class PredictRequest(BaseModel):
    features: Dict[str, Any]


class SimulateTrafficRequest(BaseModel):
    mode: str = "normal"      # "normal" | "drifted"
    n_samples: int = 100


# ─── Repository CRUD ──────────────────────────────────────────────────────────

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


# ─── Pipeline Trigger ─────────────────────────────────────────────────────────

@router.post("/{repo_id}/run-pipeline")
def run_pipeline(repo_id: str, db: Session = Depends(get_db)):
    """
    Manually triggers the full training pipeline for a repository.
    Spawns the runner in a background daemon thread and returns immediately.
    """
    repo = db.query(Repo).filter(Repo.id == repo_id).first()
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")

    commit_sha = f"manual-{int(datetime.utcnow().timestamp())}"
    run_id = f"run_{repo_id}_{commit_sha}_{int(datetime.utcnow().timestamp())}"

    # Create Run record immediately so the UI can see it
    run_record = Run(
        id=run_id,
        repo_id=repo_id,
        commit_sha=commit_sha,
        status="pending",
        triggered_by="manual",
        started_at=datetime.utcnow()
    )
    db.add(run_record)
    db.commit()

    # Launch pipeline in background
    from runner.local_runner import launch_pipeline_thread
    launched = launch_pipeline_thread(
        repo_id=repo_id,
        commit_sha=commit_sha,
        run_id=run_id
    )

    return {
        "status": "queued" if launched else "duplicate_skipped",
        "run_id": run_id,
        "message": "Pipeline triggered. Training will start momentarily." if launched else "A pipeline for this repo is already running."
    }


# ─── Inference Proxy ──────────────────────────────────────────────────────────

@router.post("/{repo_id}/predict")
async def predict(repo_id: str, payload: PredictRequest, db: Session = Depends(get_db)):
    """
    Forwards an inference request to the deployed model's serving endpoint
    and logs the prediction for monitoring.
    """
    repo = db.query(Repo).filter(Repo.id == repo_id).first()
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")

    deployment = db.query(Deployment).filter(
        Deployment.repo_id == repo_id,
        Deployment.status == "active"
    ).first()

    if not deployment:
        raise HTTPException(
            status_code=503,
            detail="No active deployment found. Run the training pipeline first."
        )

    # Forward request to the serving process
    serve_url = f"http://localhost:{deployment.port}/predict"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(serve_url, json={"features": payload.features})
        result = resp.json()
    except httpx.ConnectError:
        raise HTTPException(
            status_code=503,
            detail=f"Serving process on port {deployment.port} is not responding. Re-run the pipeline."
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Inference proxy error: {str(e)}")

    # Log to traffic store for monitoring
    try:
        log_prediction(repo_id, payload.features, result)
    except Exception:
        pass

    return result


# ─── Traffic Simulation ───────────────────────────────────────────────────────

@router.post("/{repo_id}/simulate-traffic")
async def simulate_traffic(
    repo_id: str,
    payload: SimulateTrafficRequest,
    db: Session = Depends(get_db)
):
    """
    Simulates production traffic for drift detection testing.

    mode='normal'  — generates feature vectors from the training distribution
    mode='drifted' — generates feature vectors with artificially shifted petal_length
                     (3× shift) to immediately trigger Evidently drift detection
    """
    repo = db.query(Repo).filter(Repo.id == repo_id).first()
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")

    mlops_config = repo.mlops_yaml or {}
    num_features = mlops_config.get("numerical_features", ["sepal_length", "sepal_width", "petal_length", "petal_width"])
    n = max(1, min(payload.n_samples, 500))  # Cap at 500
    mode = payload.mode.lower()

    rng = np.random.default_rng(seed=None)  # Non-deterministic seed for realistic simulation

    samples_logged = 0

    for _ in range(n):
        if mode == "drifted":
            # Strongly shifted distribution — petal_length 3× off normal
            # This is designed to immediately trigger Evidently data drift detection
            sample = {
                "sepal_length": float(rng.normal(5.8, 0.5)),
                "sepal_width":  float(rng.normal(3.1, 0.4)),
                "petal_length": float(rng.normal(12.0, 1.5)),   # 3x normal (normally ~3.7)
                "petal_width":  float(rng.normal(2.5, 0.8)),
            }
            confidence = float(rng.uniform(0.45, 0.72))   # Lower confidence = model confused
        else:
            # Normal distribution matching Iris training data
            sample = {
                "sepal_length": float(rng.normal(5.8, 0.5)),
                "sepal_width":  float(rng.normal(3.1, 0.35)),
                "petal_length": float(rng.normal(3.7, 1.2)),
                "petal_width":  float(rng.normal(1.2, 0.6)),
            }
            confidence = float(rng.uniform(0.82, 0.99))

        # Only keep features that are in the repo's feature list
        filtered_sample = {k: v for k, v in sample.items() if k in num_features} if num_features else sample

        # Simulate class prediction
        prediction = int(rng.integers(0, 3))

        output = {
            "prediction": prediction,
            "confidence": round(confidence, 4),
            "simulated": True,
            "mode": mode
        }

        try:
            log_prediction(repo_id, filtered_sample, output)
            samples_logged += 1
        except Exception:
            pass

    return {
        "status": "ok",
        "repo_id": repo_id,
        "mode": mode,
        "samples_requested": n,
        "samples_logged": samples_logged,
        "total_traffic_logged": get_traffic_count(repo_id),
        "message": (
            f"{'⚠️ Drifted' if mode == 'drifted' else '🟢 Normal'} traffic simulation complete. "
            f"{samples_logged} samples logged. Run a monitoring cycle to detect {'drift' if mode == 'drifted' else 'stability'}."
        )
    }


# ─── GitHub API Integration ───────────────────────────────────────────────────

@router.get("/github/user-repos")
async def get_user_repos(authorization: Optional[str] = Header(None)):
    """
    Fetches the authenticated user's GitHub repositories via GitHub API.
    Requires Authorization: Bearer <github_token> header or GITHUB_TOKEN env var.
    """
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split("Bearer ", 1)[1].strip()
    if not token:
        token = os.getenv("GITHUB_TOKEN")
    if not token:
        raise HTTPException(
            status_code=401,
            detail="No GitHub token provided. Pass Authorization: Bearer <token> header or set GITHUB_TOKEN env var."
        )

    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.get(
                "https://api.github.com/user/repos",
                headers=headers,
                params={"per_page": 100, "sort": "pushed", "type": "all"}
            )
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"GitHub API request failed: {str(e)}")

    if resp.status_code == 401:
        raise HTTPException(status_code=401, detail="GitHub token is invalid or expired.")
    if not resp.ok:
        raise HTTPException(status_code=resp.status_code, detail=f"GitHub API error: {resp.text}")

    repos_raw = resp.json()
    return [
        {
            "name": r.get("name"),
            "full_name": r.get("full_name"),
            "html_url": r.get("html_url"),
            "description": r.get("description"),
            "language": r.get("language"),
            "updated_at": r.get("updated_at"),
            "private": r.get("private", False)
        }
        for r in repos_raw
        if isinstance(r, dict)
    ]


@router.get("/github/repo-tree")
async def get_repo_tree(
    owner: str,
    repo: str,
    authorization: Optional[str] = Header(None)
):
    """
    Fetches the full file tree of a GitHub repository and attempts to read its
    mlops.yaml content (if present).

    Query params:
        owner: GitHub username or org (e.g. 'joel-95')
        repo:  Repository name (e.g. 'iris-classifier-demo')
    """
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split("Bearer ", 1)[1].strip()
    if not token:
        token = os.getenv("GITHUB_TOKEN")

    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"token {token}"
        headers["X-GitHub-Api-Version"] = "2022-11-28"

    async with httpx.AsyncClient(timeout=15.0) as client:
        # 1. Get default branch
        repo_resp = await client.get(
            f"https://api.github.com/repos/{owner}/{repo}",
            headers=headers
        )
        if not repo_resp.ok:
            raise HTTPException(
                status_code=repo_resp.status_code,
                detail=f"Repository '{owner}/{repo}' not found or not accessible."
            )
        default_branch = repo_resp.json().get("default_branch", "main")

        # 2. Fetch recursive file tree
        tree_resp = await client.get(
            f"https://api.github.com/repos/{owner}/{repo}/git/trees/{default_branch}",
            headers=headers,
            params={"recursive": "1"}
        )
        if not tree_resp.ok:
            raise HTTPException(status_code=tree_resp.status_code, detail="Failed to fetch repo tree.")

        tree_data = tree_resp.json()
        file_list = [
            item["path"]
            for item in tree_data.get("tree", [])
            if item.get("type") == "blob"
        ]

        # 3. Try to fetch mlops.yaml content
        mlops_yaml_content = None
        for yaml_path in ["mlops.yaml", "mlops.yml", ".automlops/mlops.yaml"]:
            if yaml_path in file_list:
                content_resp = await client.get(
                    f"https://api.github.com/repos/{owner}/{repo}/contents/{yaml_path}",
                    headers=headers,
                    params={"ref": default_branch}
                )
                if content_resp.ok:
                    import base64
                    content_data = content_resp.json()
                    encoded = content_data.get("content", "")
                    try:
                        mlops_yaml_content = base64.b64decode(encoded).decode("utf-8")
                    except Exception:
                        pass
                break

    return {
        "owner": owner,
        "repo": repo,
        "default_branch": default_branch,
        "file_count": len(file_list),
        "file_list": file_list,
        "mlops_yaml_content": mlops_yaml_content,
        "mlops_yaml_found": mlops_yaml_content is not None
    }


# ─── Manual Retrain ───────────────────────────────────────────────────────────

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
