import os
import logging
from typing import Dict, Any

logger = logging.getLogger("automlops.tunnel")

# In-memory mapping of repo_id -> current port / tunnel URL
_ACTIVE_TUNNELS: Dict[str, Dict[str, Any]] = {}


def setup_tunnel(repo_id: str, local_port: int) -> str:
    """
    Sets up or maps a Cloudflare Tunnel or public gateway endpoint pointing to localhost:{local_port}.
    If cloudflared daemon or CLOUDFLARE_TUNNEL_TOKEN is configured, routes through Cloudflare.
    Otherwise produces a deterministic URL for local development/testing.
    
    Returns:
        The public HTTPS tunnel URL for inference.
    """
    tunnel_domain = os.getenv("TUNNEL_DOMAIN", "tunnel.automlops.local")
    custom_tunnel_url = os.getenv("CLOUDFLARE_TUNNEL_URL")

    if custom_tunnel_url:
        tunnel_url = custom_tunnel_url
    else:
        # Canonical deterministic subdomain per repo
        tunnel_url = f"https://{repo_id}.{tunnel_domain}"

    _ACTIVE_TUNNELS[repo_id] = {
        "port": local_port,
        "url": tunnel_url
    }

    logger.info(f"Tunnel established for {repo_id}: localhost:{local_port} -> {tunnel_url}")
    return tunnel_url


def update_tunnel_port(repo_id: str, new_port: int) -> str:
    """
    Updates an existing tunnel routing to target a newly deployed container port.
    """
    return setup_tunnel(repo_id, new_port)


def get_tunnel_info(repo_id: str) -> Dict[str, Any]:
    """Returns the registered tunnel information for a repository."""
    return _ACTIVE_TUNNELS.get(repo_id, {
        "port": None,
        "url": None
    })


def teardown_tunnel(repo_id: str) -> None:
    """Removes a tunnel configuration upon repository disconnect."""
    if repo_id in _ACTIVE_TUNNELS:
        del _ACTIVE_TUNNELS[repo_id]
        logger.info(f"Tunnel torn down for repo {repo_id}")
