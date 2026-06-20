"""GitHub App authentication — generates Installation Access Tokens.

GitHub Apps authenticate as the app (JWT) then exchange for an
installation token scoped to a specific repo installation.
"""

import time
from dataclasses import dataclass

import httpx
import jwt
import structlog

from app.core.config import settings

log = structlog.get_logger()

GITHUB_API = "https://api.github.com"
_TOKEN_TTL = 3600    # GitHub installation tokens expire in 1 hour
_TOKEN_BUFFER = 300  # proactively refresh 5 minutes before expiry


@dataclass
class _CachedToken:
    token: str
    expires_at: float  # monotonic timestamp


# In-memory per-installation token cache (keyed by installation_id).
_token_cache: dict[int, _CachedToken] = {}


def _build_app_jwt() -> str:
    """Build a short-lived JWT signed with the GitHub App private key."""
    now = int(time.time())
    payload = {
        "iat": now - 60,   # issued 60s ago to allow clock drift
        "exp": now + 540,  # valid 9 minutes (max 10)
        "iss": settings.github_app_id,
    }
    return jwt.encode(payload, settings.github_app_private_key, algorithm="RS256")


async def _fetch_installation_token(installation_id: int) -> tuple[str, float]:
    """Call GitHub API to get a fresh installation token."""
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

    remaining = int(resp.headers.get("x-ratelimit-remaining", 5000))
    if remaining < 10:
        log.warning("github_api_rate_limit_low", remaining=remaining, installation_id=installation_id)

    expires_at = time.monotonic() + _TOKEN_TTL - _TOKEN_BUFFER
    log.info("github_installation_token_issued", installation_id=installation_id)
    return data["token"], expires_at


async def get_installation_token(installation_id: int) -> str:
    """Return a valid installation token, refreshing proactively before expiry."""
    cached = _token_cache.get(installation_id)
    if cached and time.monotonic() < cached.expires_at:
        log.debug("github_token_cache_hit", installation_id=installation_id)
        return cached.token

    token, expires_at = await _fetch_installation_token(installation_id)
    _token_cache[installation_id] = _CachedToken(token=token, expires_at=expires_at)
    return token


def invalidate_token(installation_id: int) -> None:
    """Evict a cached token — call this when GitHub returns 401."""
    _token_cache.pop(installation_id, None)
    log.info("github_token_invalidated", installation_id=installation_id)


def list_cached_installations() -> list[int]:
    """Return installation IDs that currently have a live cached token."""
    now = time.monotonic()
    return [iid for iid, t in _token_cache.items() if now < t.expires_at]
