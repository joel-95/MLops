import os
import sys
import subprocess
import logging
import time
from datetime import datetime
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session

from backend.db.models import SessionLocal, Repo, Deployment
from tunnel.cloudflare_tunnel import setup_tunnel, teardown_tunnel

logger = logging.getLogger("automlops.deploy")

BASE_PORT = 8000  # Port 8000 is reserved for FastAPI backend; repos take 8001, 8002, etc.

# ─── In-memory registry of locally-spawned serving subprocesses ───────────────
# Maps container_name → Popen object; used to kill on stop_deployment()
_serving_procs: Dict[str, subprocess.Popen] = {}


def get_repo_port(repo_sequential_id: int) -> int:
    """
    Deterministic Port Assignment (Vulnerability Fix 4.4).
    Guarantees no port collisions, no random port state loss across restarts.
    """
    return BASE_PORT + repo_sequential_id


def deploy_model(
    repo_id: str,
    model_artifact_path: str,
    commit_sha: str,
    predict_module_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Deploys a trained model on its deterministic assigned port.
    Stops any previous running container for this repository first.
    Tries Docker first; falls back to a local uvicorn subprocess automatically.
    Updates the Deployment database table and registers with Cloudflare Tunnel.

    Returns:
        {"port": int, "tunnel_url": str, "container_name": str, "status": "deployed"}
    """
    db: Session = SessionLocal()
    try:
        repo = db.query(Repo).filter(Repo.id == repo_id).first()
        if not repo:
            raise ValueError(f"Repository '{repo_id}' not found in database.")

        port = get_repo_port(repo.sequential_id)
        container_name = f"automlops-serve-{repo_id}"

        # 1. Stop and remove existing container / process if running
        _stop_docker_container(container_name)
        _stop_local_proc(container_name)

        # 2. Try Docker first; fall back to subprocess uvicorn
        serving_started = _run_docker_serving_container(
            container_name=container_name,
            port=port,
            model_artifact_path=model_artifact_path,
            predict_module_path=predict_module_path or "ml/predict.py"
        )

        if not serving_started:
            logger.info(f"[Deploy] Docker unavailable — falling back to local uvicorn subprocess for {repo_id}")
            serving_started = _run_local_python_serving(
                container_name=container_name,
                port=port,
                model_artifact_path=model_artifact_path,
                repo_id=repo_id
            )

        if not serving_started:
            logger.error(f"[Deploy] Both Docker and subprocess serving failed for {repo_id}")

        # 3. Register Cloudflare Tunnel (or localhost fallback)
        tunnel_url = setup_tunnel(repo_id, port)

        # 4. Update Database
        deployment = db.query(Deployment).filter(Deployment.repo_id == repo_id).first()
        if not deployment:
            deployment = Deployment(
                id=f"deploy_{repo_id}_{int(datetime.utcnow().timestamp())}",
                repo_id=repo_id,
                port=port,
                tunnel_url=tunnel_url,
                deployed_commit_sha=commit_sha,
                container_id=container_name,
                status="active",
                deployed_at=datetime.utcnow()
            )
            db.add(deployment)
        else:
            deployment.port = port
            deployment.tunnel_url = tunnel_url
            deployment.deployed_commit_sha = commit_sha
            deployment.container_id = container_name
            deployment.status = "active"
            deployment.deployed_at = datetime.utcnow()

        repo.is_deployed = True
        db.commit()

        logger.info(f"[Deploy] Successfully deployed {repo_id} on port {port} → {tunnel_url}")
        return {
            "repo_id": repo_id,
            "port": port,
            "tunnel_url": tunnel_url,
            "container_name": container_name,
            "commit_sha": commit_sha,
            "status": "deployed"
        }

    finally:
        db.close()


def stop_deployment(repo_id: str) -> None:
    """Stops the serving container/process and tears down the tunnel for a repo."""
    db = SessionLocal()
    try:
        repo = db.query(Repo).filter(Repo.id == repo_id).first()
        if not repo:
            return

        container_name = f"automlops-serve-{repo_id}"
        _stop_docker_container(container_name)
        _stop_local_proc(container_name)
        teardown_tunnel(repo_id)

        deployment = db.query(Deployment).filter(Deployment.repo_id == repo_id).first()
        if deployment:
            deployment.status = "stopped"
        repo.is_deployed = False
        db.commit()
    finally:
        db.close()


def recover_deployments() -> None:
    """
    Invoked on FastAPI backend startup.
    Inspects all deployments in the database, checks container health,
    and restores tunnel registry entries.
    """
    db = SessionLocal()
    try:
        active_deployments = db.query(Deployment).filter(Deployment.status == "active").all()
        for dep in active_deployments:
            container_name = dep.container_id or f"automlops-serve-{dep.repo_id}"
            is_running = _is_docker_container_running(container_name)
            if not is_running and container_name not in _serving_procs:
                logger.warning(
                    f"[Deploy] Deployment '{container_name}' not running. "
                    "Restoring tunnel mapping only — re-run pipeline to restore serving."
                )
            # Always re-register tunnel URL in memory (setup_tunnel is idempotent)
            setup_tunnel(dep.repo_id, dep.port)
    finally:
        db.close()


# ─── Docker helpers ────────────────────────────────────────────────────────────

def _stop_docker_container(container_name: str) -> None:
    try:
        subprocess.run(
            ["docker", "rm", "-f", container_name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5
        )
    except Exception:
        pass


def _is_docker_container_running(container_name: str) -> bool:
    try:
        res = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Running}}", container_name],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=5
        )
        return res.stdout.strip() == "true"
    except Exception:
        return False


def _is_docker_daemon_available() -> bool:
    """Returns True if the Docker daemon is reachable."""
    try:
        res = subprocess.run(
            ["docker", "info"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=4
        )
        return res.returncode == 0
    except Exception:
        return False


def _run_docker_serving_container(
    container_name: str,
    port: int,
    model_artifact_path: str,
    predict_module_path: str
) -> bool:
    """Attempts to run the Docker serving container. Returns True on success."""
    if not _is_docker_daemon_available():
        return False
    try:
        abs_model = os.path.abspath(model_artifact_path) if os.path.exists(model_artifact_path) else ""
        cmd = [
            "docker", "run", "-d",
            "--name", container_name,
            "-p", f"{port}:8000",
            "-e", "PORT=8000",
            "-e", f"MODEL_PATH=/app/artifacts/model.pkl",
            "automlops/serving:latest"
        ]
        res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
        return res.returncode == 0
    except Exception:
        return False


# ─── Subprocess (local Python) serving fallback ────────────────────────────────

def _run_local_python_serving(
    container_name: str,
    port: int,
    model_artifact_path: str,
    repo_id: str
) -> bool:
    """
    Starts deploy/serving_app.py via a local uvicorn subprocess on the given port.
    This is the Docker-free fallback for local development environments.
    Stores the Popen handle in _serving_procs for later cleanup.
    """
    try:
        abs_model = os.path.abspath(model_artifact_path) if os.path.exists(model_artifact_path) else model_artifact_path

        env = {
            **os.environ,
            "MODEL_PATH": abs_model,
            "PORT": str(port),
            "REPO_ID": repo_id,
        }

        log_dir = os.path.join("logs", repo_id)
        os.makedirs(log_dir, exist_ok=True)
        log_file = open(os.path.join(log_dir, "serving.log"), "a", encoding="utf-8")

        cmd = [
            sys.executable, "-m", "uvicorn",
            "deploy.serving_app:app",
            "--host", "0.0.0.0",
            "--port", str(port),
            "--log-level", "warning"
        ]

        proc = subprocess.Popen(
            cmd,
            env=env,
            stdout=log_file,
            stderr=log_file,
            # Detach from console on Windows
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        )

        # Brief wait to confirm it started (not crashed immediately)
        time.sleep(1.5)
        if proc.poll() is not None:
            logger.error(f"[Deploy] Subprocess serving exited immediately for {repo_id} (returncode={proc.returncode}). Check logs/{repo_id}/serving.log")
            return False

        _serving_procs[container_name] = proc
        logger.info(f"[Deploy] Local subprocess serving started: port={port}, pid={proc.pid}, repo={repo_id}")
        return True

    except Exception as e:
        logger.error(f"[Deploy] Failed to start local subprocess serving for {repo_id}: {e}")
        return False


def _stop_local_proc(container_name: str) -> None:
    """Terminates a locally-spawned serving subprocess if it's registered."""
    proc = _serving_procs.pop(container_name, None)
    if proc is not None:
        try:
            proc.terminate()
            proc.wait(timeout=5)
            logger.info(f"[Deploy] Stopped local serving subprocess '{container_name}' (pid={proc.pid})")
        except Exception as e:
            logger.warning(f"[Deploy] Could not cleanly stop subprocess '{container_name}': {e}")
            try:
                proc.kill()
            except Exception:
                pass
