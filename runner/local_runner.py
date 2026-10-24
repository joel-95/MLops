"""
AutoMLOps Local Pipeline Runner
================================
Orchestrates the full train → quality-gate → callback pipeline
in a background daemon thread whenever a push/retrain event is received.

Usage:
    # From webhook handler (background thread):
    from runner.local_runner import run_pipeline_for_repo
    threading.Thread(target=run_pipeline_for_repo, args=(repo_id, commit_sha, run_id), daemon=True).start()

    # As a standalone CLI script:
    python -m runner.local_runner
"""
import os
import sys
import json
import time
import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

logger = logging.getLogger("automlops.runner")


def run_pipeline_for_repo(
    repo_id: str,
    commit_sha: str,
    run_id: Optional[str] = None,
    callback_url: Optional[str] = None
) -> Dict[str, Any]:
    """
    Executes the full AutoMLOps pipeline for a given repository:
        1. Mark Run as 'running'
        2. Execute training script (train_v1)
        3. Evaluate quality gate
        4. POST result to /webhook/pipeline-result callback
        5. Update Run record in DB

    Designed to be called from a daemon thread so it never blocks the API response.

    Args:
        repo_id:      The repository ID (e.g., 'repo_iris_classifier_demo')
        commit_sha:   Git commit SHA that triggered this run
        run_id:       Optional existing Run DB record ID to update
        callback_url: Override for BACKEND_URL (defaults to localhost:8000)

    Returns:
        Dict with 'status', 'metrics', and 'quality_gate_result' keys
    """
    # Import here to avoid circular imports at module load time
    from backend.db.models import SessionLocal, Run, Repo
    from ml.train import train_v1
    from ml.quality_gate import check_quality_gate

    db = SessionLocal()
    backend_url = callback_url or os.getenv("BACKEND_CALLBACK_URL", "http://localhost:8000")

    try:
        # 1. Resolve repo config
        repo = db.query(Repo).filter(Repo.id == repo_id).first()
        if not repo:
            logger.error(f"[Runner] Repo '{repo_id}' not found in database. Aborting.")
            return {"status": "error", "reason": f"Repo '{repo_id}' not found"}

        mlops_config = repo.mlops_yaml or {}

        # 2. Find or create Run record
        run_record = None
        if run_id:
            run_record = db.query(Run).filter(Run.id == run_id).first()

        if not run_record:
            # Create a new run record if not provided
            new_run_id = f"run_{repo_id}_{commit_sha[:8]}_{int(datetime.utcnow().timestamp())}"
            run_record = Run(
                id=new_run_id,
                repo_id=repo_id,
                commit_sha=commit_sha,
                status="running",
                triggered_by="local_runner",
                started_at=datetime.utcnow()
            )
            db.add(run_record)
        else:
            run_record.status = "running"

        db.commit()
        logger.info(f"[Runner] Pipeline started for {repo_id} | commit={commit_sha[:7]} | run={run_record.id}")

        # 3. Determine paths based on repo config
        entry_point = mlops_config.get("entry_point", "ml/train.py")
        dataset_path = mlops_config.get("dataset_path", "demo_repo/data/iris.csv")

        # Resolve mlops.yaml path (local repo may have it at root or in demo_repo/)
        mlops_yaml_path = "mlops.yaml"
        if not os.path.exists(mlops_yaml_path):
            mlops_yaml_path = "demo_repo/mlops.yaml"

        # Set COMMIT_SHA env var so train.py can embed it in metrics.json
        os.environ["COMMIT_SHA"] = commit_sha

        # 4. Execute Training
        logger.info(f"[Runner] Starting training for {repo_id}...")
        start_time = time.time()

        try:
            metrics_data = train_v1()
            logger.info(f"[Runner] Training complete in {round(time.time() - start_time, 2)}s | metrics={metrics_data}")
        except Exception as e:
            logger.error(f"[Runner] Training failed: {e}")
            _update_run_status(db, run_record, "failed", {}, "failed")
            _post_callback(backend_url, repo_id, commit_sha, "failed", {})
            return {"status": "failed", "reason": f"Training error: {str(e)}"}

        # 5. Evaluate Quality Gate
        metrics_path = "metrics.json"
        gate_passed, gate_details = check_quality_gate(metrics_path, mlops_yaml_path)
        quality_result = "passed" if gate_passed else "failed"

        logger.info(f"[Runner] Quality gate: {quality_result} | checks={gate_details}")

        # 6. Update Run record in DB
        _update_run_status(db, run_record, quality_result, metrics_data, quality_result)

        # 7. POST callback to backend /webhook/pipeline-result
        # This triggers deploy_model() + on_training_complete() in the backend
        callback_payload = {
            "repo_id": repo_id,
            "commit_sha": commit_sha,
            "status": quality_result,
            "metrics": metrics_data,
            "quality_gate_details": gate_details
        }
        _post_callback(backend_url, repo_id, commit_sha, quality_result, metrics_data)

        logger.info(f"[Runner] Pipeline complete for {repo_id}. Result: {quality_result}")
        return {
            "status": quality_result,
            "metrics": metrics_data,
            "quality_gate_result": gate_details
        }

    except Exception as e:
        logger.exception(f"[Runner] Unexpected pipeline error for {repo_id}: {e}")
        try:
            _post_callback(backend_url, repo_id, commit_sha, "failed", {})
        except Exception:
            pass
        return {"status": "error", "reason": str(e)}
    finally:
        db.close()


def _update_run_status(
    db,
    run_record,
    status: str,
    metrics: Dict[str, Any],
    quality_gate_result: str
) -> None:
    """Updates the Run record in the database."""
    try:
        run_record.status = status
        run_record.quality_gate_result = quality_gate_result
        run_record.metrics_json = metrics
        run_record.completed_at = datetime.utcnow()
        db.commit()
    except Exception as e:
        logger.error(f"[Runner] Failed to update Run record: {e}")


def _post_callback(
    backend_url: str,
    repo_id: str,
    commit_sha: str,
    status: str,
    metrics: Dict[str, Any]
) -> None:
    """POSTs the pipeline result to /webhook/pipeline-result."""
    import urllib.request
    import urllib.error

    callback_url = f"{backend_url}/webhook/pipeline-result"
    payload = {
        "repo_id": repo_id,
        "commit_sha": commit_sha,
        "status": status,
        "metrics": metrics
    }
    payload_bytes = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        callback_url,
        data=payload_bytes,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            logger.info(f"[Runner] Callback posted to {callback_url}: HTTP {resp.status}")
    except urllib.error.URLError as e:
        logger.warning(f"[Runner] Callback post failed (server may be handling restart): {e}")


# ─── Thread-safe pipeline launcher ────────────────────────────────────────────

_pipeline_lock = threading.Lock()
_running_pipelines: set = set()


def launch_pipeline_thread(
    repo_id: str,
    commit_sha: str,
    run_id: Optional[str] = None
) -> bool:
    """
    Spawns run_pipeline_for_repo() in a daemon thread if not already running for this repo.
    Returns True if thread was launched, False if a pipeline for this repo is already running.
    """
    with _pipeline_lock:
        if repo_id in _running_pipelines:
            logger.warning(f"[Runner] Pipeline already running for {repo_id}. Skipping duplicate trigger.")
            return False
        _running_pipelines.add(repo_id)

    def _run_and_cleanup():
        try:
            run_pipeline_for_repo(repo_id, commit_sha, run_id)
        finally:
            with _pipeline_lock:
                _running_pipelines.discard(repo_id)

    t = threading.Thread(target=_run_and_cleanup, daemon=True, name=f"pipeline-{repo_id}")
    t.start()
    logger.info(f"[Runner] Launched pipeline thread for {repo_id} (tid={t.ident})")
    return True


# ─── CLI entrypoint ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )
    # Allow: python -m runner.local_runner [repo_id] [commit_sha]
    _repo_id = sys.argv[1] if len(sys.argv) > 1 else "repo_iris_classifier_demo"
    _commit_sha = sys.argv[2] if len(sys.argv) > 2 else "local-manual"
    logger.info(f"Running pipeline CLI: repo={_repo_id}, commit={_commit_sha}")
    result = run_pipeline_for_repo(_repo_id, _commit_sha)
    print(json.dumps(result, indent=2, default=str))
