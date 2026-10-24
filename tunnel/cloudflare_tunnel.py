"""
Cloudflare Tunnel Manager
==========================
Manages the lifecycle of Cloudflare Tunnel (cloudflared) processes per deployment.

In production: attempts to start a real cloudflared quick-tunnel that generates
a public HTTPS URL (*.trycloudflare.com) for the given port.

In development / when cloudflared is unavailable: falls back gracefully to a
localhost URL, which is still fully functional for local testing and demo.

Registry:
    _tunnel_registry maps repo_id → {"url": str, "proc": Popen | None}
"""
import os
import re
import time
import subprocess
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger("automlops.tunnel")

# In-memory registry: repo_id → {"url": str, "proc": Optional[Popen]}
_tunnel_registry: Dict[str, Dict[str, Any]] = {}

CLOUDFLARED_BIN = os.getenv("CLOUDFLARED_BIN", "cloudflared")


def setup_tunnel(repo_id: str, port: int) -> str:
    """
    Establishes (or re-registers) a tunnel for the given repo and port.

    Tries cloudflared quick-tunnel first. Falls back to localhost URL if:
    - cloudflared binary is not found
    - quick-tunnel process fails to start
    - CLOUDFLARE_TUNNEL_DISABLED env var is set

    Returns:
        Public HTTPS URL (cloudflare) or http://localhost:{port} (fallback)
    """
    # Return cached URL if already registered
    existing = _tunnel_registry.get(repo_id)
    if existing and existing.get("url"):
        # Verify the process is still alive (if subprocess)
        proc = existing.get("proc")
        if proc is None or proc.poll() is None:
            return existing["url"]

    # Check if cloudflare tunnels are explicitly disabled
    if os.getenv("CLOUDFLARE_TUNNEL_DISABLED", "false").lower() in ("1", "true", "yes"):
        return _register_localhost(repo_id, port)

    # Attempt real cloudflared quick-tunnel
    try:
        cloudflare_url = _start_cloudflared_quick_tunnel(repo_id, port)
        if cloudflare_url:
            _tunnel_registry[repo_id] = {"url": cloudflare_url, "proc": None}
            logger.info(f"[Tunnel] Cloudflare tunnel active for {repo_id}: {cloudflare_url}")
            return cloudflare_url
    except Exception as e:
        logger.warning(f"[Tunnel] cloudflared failed for {repo_id}: {e}. Using localhost fallback.")

    return _register_localhost(repo_id, port)


def teardown_tunnel(repo_id: str) -> None:
    """
    Tears down the tunnel for a given repo.
    Terminates the cloudflared subprocess if one was started.
    """
    entry = _tunnel_registry.pop(repo_id, None)
    if entry:
        proc = entry.get("proc")
        if proc is not None:
            try:
                proc.terminate()
                proc.wait(timeout=5)
                logger.info(f"[Tunnel] cloudflared process terminated for {repo_id}")
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass


def get_tunnel_url(repo_id: str) -> Optional[str]:
    """Returns the current tunnel URL for a repo, or None if not registered."""
    entry = _tunnel_registry.get(repo_id)
    return entry["url"] if entry else None


# ─── Internal helpers ──────────────────────────────────────────────────────────

def _register_localhost(repo_id: str, port: int) -> str:
    """Registers and returns a localhost fallback URL."""
    url = f"http://localhost:{port}"
    _tunnel_registry[repo_id] = {"url": url, "proc": None}
    logger.info(f"[Tunnel] Localhost fallback registered for {repo_id}: {url}")
    return url


def _start_cloudflared_quick_tunnel(repo_id: str, port: int) -> Optional[str]:
    """
    Starts a cloudflared quick-tunnel subprocess and extracts the generated URL.
    Quick tunnels (trycloudflare.com) require no account or config file.

    Returns the tunnel URL string, or None if it couldn't be extracted.
    """
    cmd = [CLOUDFLARED_BIN, "tunnel", "--url", f"http://localhost:{port}", "--no-autoupdate"]

    log_dir = os.path.join("logs", repo_id)
    os.makedirs(log_dir, exist_ok=True)

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace"
    )

    # Wait up to 12 seconds for the URL to appear in stderr output
    url_pattern = re.compile(r"https://[a-z0-9\-]+\.trycloudflare\.com")
    deadline = time.time() + 12

    while time.time() < deadline:
        if proc.poll() is not None:
            logger.warning(f"[Tunnel] cloudflared exited unexpectedly for {repo_id}")
            return None
        try:
            line = proc.stderr.readline()
            if line:
                match = url_pattern.search(line)
                if match:
                    tunnel_url = match.group(0)
                    _tunnel_registry[repo_id] = {"url": tunnel_url, "proc": proc}
                    return tunnel_url
        except Exception:
            break
        time.sleep(0.2)

    # Timed out waiting for URL — kill the process
    proc.terminate()
    return None
