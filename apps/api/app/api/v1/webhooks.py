"""GitHub App webhook handler."""

import hashlib
import hmac
import structlog
from fastapi import APIRouter, Header, HTTPException, Request

from app.core.config import settings

log = structlog.get_logger()
router = APIRouter()


def _verify_signature(payload: bytes, signature: str | None) -> None:
    if not settings.github_webhook_secret:
        return
    if not signature or not signature.startswith("sha256="):
        raise HTTPException(status_code=401, detail="Missing webhook signature")
    expected = hmac.new(
        settings.github_webhook_secret.encode(),
        payload,
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(f"sha256={expected}", signature):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")


@router.post("/github")
async def github_webhook(
    request: Request,
    x_github_event: str = Header(...),
    x_hub_signature_256: str | None = Header(None),
) -> dict[str, str]:
    payload = await request.body()
    _verify_signature(payload, x_hub_signature_256)

    body = await request.json()
    action = body.get("action", "")

    log.info("github_webhook_received", event=x_github_event, action=action)

    # Dispatch to background task queue (Celery)
    if x_github_event == "issues":
        _enqueue_triage(body)
    elif x_github_event == "pull_request":
        _enqueue_review(body)

    return {"status": "accepted"}


@router.post("/github")
async def github_webhook_push(
    request: Request,
    x_github_event: str = Header(...),
    x_hub_signature_256: str | None = Header(None),
) -> dict[str, str]:
    """Alias kept for push events — same handler, separate route not needed."""
    return await github_webhook(request, x_github_event, x_hub_signature_256)


def _enqueue_triage(payload: dict) -> None:
    installation_id: int = payload.get("installation", {}).get("id", 0)
    repo: str = payload.get("repository", {}).get("full_name", "")
    issue_number: int = payload.get("issue", {}).get("number", 0)
    log.info("enqueue_triage", installation_id=installation_id, repo=repo, issue=issue_number)
    # Celery task: from app.tasks.triage import run_triage; run_triage.delay(installation_id, repo, issue_number)


def _enqueue_review(payload: dict) -> None:
    installation_id: int = payload.get("installation", {}).get("id", 0)
    repo: str = payload.get("repository", {}).get("full_name", "")
    pr_number: int = payload.get("pull_request", {}).get("number", 0)
    log.info("enqueue_review", installation_id=installation_id, repo=repo, pr=pr_number)
    # Celery task: from app.tasks.review import run_review; run_review.delay(installation_id, repo, pr_number)
