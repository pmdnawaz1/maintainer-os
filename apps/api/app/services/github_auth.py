"""GitHub App authentication — generates Installation Access Tokens.

GitHub Apps authenticate as the app (JWT) then exchange for an
installation token scoped to a specific repo installation.
"""

import time
import jwt
import httpx
import structlog
from functools import lru_cache

from app.core.config import settings

log = structlog.get_logger()

GITHUB_API = "https://api.github.com"


def _build_app_jwt() -> str:
    """Build a short-lived JWT signed with the GitHub App private key."""
    now = int(time.time())
    payload = {
        "iat": now - 60,   # issued 60s ago to allow clock drift
        "exp": now + 540,  # valid 9 minutes (max 10)
        "iss": settings.github_app_id,
    }
    return jwt.encode(payload, settings.github_app_private_key, algorithm="RS256")


async def get_installation_token(installation_id: int) -> str:
    """Exchange App JWT for an Installation Access Token.

    Returns a token valid for 1 hour that can call GitHub REST/GraphQL
    APIs with the permissions granted during app installation.
    """
    app_jwt = _build_app_jwt()
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{GITHUB_API}/app/installations/{installation_id}/access_tokens",
            headers={
                "Authorization": f"Bearer {app_jwt}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        resp.raise_for_status()
        data = resp.json()
        log.info("github_installation_token_issued", installation_id=installation_id)
        return data["token"]
