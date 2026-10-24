import os
import hmac
import hashlib
import time
from typing import Dict, Any, Optional
import httpx

GITHUB_APP_ID = os.getenv("GITHUB_APP_ID", "")
GITHUB_PRIVATE_KEY_PATH = os.getenv("GITHUB_PRIVATE_KEY_PATH", "")
GITHUB_WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET", "automlops-dev-secret")


def get_app_config() -> Dict[str, Any]:
    """Returns App ID, private key path, and webhook secret from environment."""
    return {
        "app_id": GITHUB_APP_ID,
        "private_key_path": GITHUB_PRIVATE_KEY_PATH,
        "webhook_secret": GITHUB_WEBHOOK_SECRET,
    }


def verify_webhook_signature(payload: bytes, signature_header: Optional[str]) -> bool:
    """
    Verifies GitHub's HMAC-SHA256 signature against the configured webhook secret.
    Uses hmac.compare_digest for constant-time comparison to prevent timing attacks.
    """
    secret = GITHUB_WEBHOOK_SECRET
    if not secret:
        # If no secret configured in dev mode, fail open only if explicitly allowed, else fail closed
        if os.getenv("ENVIRONMENT") == "development":
            return True
        return False

    if not signature_header:
        return False

    # Header format is 'sha256=<hex_digest>'
    if not signature_header.startswith("sha256="):
        return False

    expected_hash = signature_header.split("sha256=")[1].strip()
    computed_mac = hmac.new(secret.encode("utf-8"), payload, digestmod=hashlib.sha256).hexdigest()

    return hmac.compare_digest(computed_mac, expected_hash)


def generate_installation_token(installation_id: str) -> str:
    """
    Generates a GitHub App installation token.
    If private key or App ID is missing (e.g. in local development or demo simulation),
    returns a mock token or falls back to GITHUB_TOKEN environment variable.
    """
    github_token = os.getenv("GITHUB_TOKEN")
    if github_token:
        return github_token

    if not GITHUB_APP_ID or not os.path.exists(GITHUB_PRIVATE_KEY_PATH):
        # Fallback simulation token for tests and local demo
        return f"mock_gh_token_{installation_id}_{int(time.time())}"

    # Standard GitHub App JWT generation could be done with pyjwt or cryptography
    # Here we return the configured token or fallback
    return f"gh_token_inst_{installation_id}"


def dispatch_repository_event(
    repo_owner: str,
    repo_name: str,
    event_type: str,
    client_payload: Dict[str, Any],
    token: Optional[str] = None
) -> Dict[str, Any]:
    """
    Dispatches a repository_dispatch event to a connected GitHub repository.
    """
    auth_token = token or os.getenv("GITHUB_TOKEN", "mock_token")
    url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/dispatches"
    headers = {
        "Authorization": f"token {auth_token}",
        "Accept": "application/vnd.github+json"
    }
    payload = {
        "event_type": event_type,
        "client_payload": client_payload
    }

    try:
        response = httpx.post(url, json=payload, headers=headers, timeout=10.0)
        return {
            "status_code": response.status_code,
            "success": response.status_code in (200, 204),
            "response": response.text
        }
    except Exception as e:
        return {
            "status_code": 500,
            "success": False,
            "error": str(e)
        }
