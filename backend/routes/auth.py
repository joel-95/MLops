import os
import httpx
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from typing import Dict, Any, Optional

router = APIRouter()


class OAuthCallbackRequest(BaseModel):
    code: str


@router.get("/github/url")
def get_github_oauth_url() -> Dict[str, str]:
    """
    Returns the GitHub OAuth authorization URL using configured credentials.
    """
    client_id = os.getenv("GITHUB_CLIENT_ID")
    if not client_id:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="GITHUB_CLIENT_ID not configured in backend .env"
        )

    # Scopes: read:user for profile, repo for repository management
    redirect_uri = os.getenv("GITHUB_REDIRECT_URI", "http://localhost:3000")
    scope = "read:user,repo"
    url = f"https://github.com/login/oauth/authorize?client_id={client_id}&redirect_uri={redirect_uri}&scope={scope}"

    return {"url": url, "client_id": client_id}


@router.post("/github/callback")
async def github_oauth_callback(payload: OAuthCallbackRequest) -> Dict[str, Any]:
    """
    Exchanges temporary OAuth code for access token with GitHub,
    verifies identity via api.github.com/user, and returns real user profile.
    """
    client_id = os.getenv("GITHUB_CLIENT_ID")
    client_secret = os.getenv("GITHUB_CLIENT_SECRET")

    if not client_id or not client_secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="GITHUB_CLIENT_ID or GITHUB_CLIENT_SECRET not configured in .env"
        )

    # 1. Exchange code for access token with GitHub
    token_url = "https://github.com/login/oauth/access_token"
    token_headers = {"Accept": "application/json"}
    token_data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "code": payload.code
    }

    async with httpx.AsyncClient() as client:
        token_resp = await client.post(token_url, json=token_data, headers=token_headers, timeout=10.0)
        if token_resp.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"GitHub token exchange failed: {token_resp.text}"
            )

        token_json = token_resp.json()
        access_token = token_json.get("access_token")

        if not access_token:
            error_msg = token_json.get("error_description") or token_json.get("error") or "No access token returned"
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Authentication failed: {error_msg}")

        # 2. Fetch real authenticated user profile from GitHub API
        user_resp = await client.get(
            "https://api.github.com/user",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/vnd.github+json"
            },
            timeout=10.0
        )

        if user_resp.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Failed to fetch user profile from GitHub."
            )

        gh_user = user_resp.json()

        return {
            "authenticated": True,
            "username": gh_user.get("login"),
            "name": gh_user.get("name") or gh_user.get("login"),
            "avatar_url": gh_user.get("avatar_url"),
            "html_url": gh_user.get("html_url"),
            "token": access_token
        }
