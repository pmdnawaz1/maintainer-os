"""GitHub App webhook handler."""

import json

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Request

from app.core.config import settings
from app.api.v1.common_webhooks import (
    check_rate_limit,
    check_replay,
    check_timestamp,
    verify_hmac_signature,
)

log = structlog.get_logger()
router = APIRouter()


def _verify_signature(payload: bytes, signature: str | None) -> None:
    verify_hmac_signature(payload, signature, settings.github_webhook_secret)


def rate_limit_dependency(request: Request) -> None:
    check_rate_limit(request)


# ── Main webhook endpoint ──────────────────────────────────────────────────────

@router.post("/github")
async def github_webhook(
    request: Request,
    x_github_event: str = Header(...),
    x_hub_signature_256: str | None = Header(None),
    x_github_delivery: str | None = Header(None),
    date: str | None = Header(None),
    _rl: None = Depends(rate_limit_dependency),
) -> dict[str, str]:
    payload = await request.body()
    _verify_signature(payload, x_hub_signature_256)
    check_timestamp(date)

    if x_github_delivery:
        check_replay(x_github_delivery)

    try:
        body = json.loads(payload)
    except json.JSONDecodeError:
        log.warning("webhook_malformed_payload", event=x_github_event)
        raise HTTPException(status_code=400, detail="Malformed JSON payload")

    action = body.get("action", "")
    log.info("github_webhook_received", event=x_github_event, action=action, delivery=x_github_delivery)

    match x_github_event:
        case "issues" if action == "opened":
            _enqueue_triage(body)
        case "pull_request" if action == "opened":
            _enqueue_review(body)
        case "push":
            _handle_push(body)
        case "release" if action in ("published", "created"):
            _handle_release(body)
        case "discussion" if action in ("created", "answered"):
            _handle_discussion(body)
        case "check_run" if action == "completed":
            _handle_check_run(body)
        case "check_suite" if action == "completed":
            _handle_check_suite(body)

    return {"status": "accepted"}


# ── Enqueue helpers ────────────────────────────────────────────────────────────

def _enqueue_triage(payload: dict) -> None:
    from app.tasks.triage import run_triage

    installation_id: int = payload.get("installation", {}).get("id", 0)
    repo: str = payload.get("repository", {}).get("full_name", "")
    issue_number: int = payload.get("issue", {}).get("number", 0)

    run_triage.delay(installation_id, repo, issue_number)
    log.info("enqueue_triage", installation_id=installation_id, repo=repo, issue=issue_number)


def _enqueue_review(payload: dict) -> None:
    from app.tasks.review import run_review

    installation_id: int = payload.get("installation", {}).get("id", 0)
    repo: str = payload.get("repository", {}).get("full_name", "")
    pr_number: int = payload.get("pull_request", {}).get("number", 0)

    run_review.delay(installation_id, repo, pr_number)
    log.info("enqueue_review", installation_id=installation_id, repo=repo, pr=pr_number)


# ── Event-specific handlers ────────────────────────────────────────────────────

def _handle_push(payload: dict) -> None:
    repo: str = payload.get("repository", {}).get("full_name", "")
    ref: str = payload.get("ref", "")
    commits: int = len(payload.get("commits", []))
    log.info("webhook_push", repo=repo, ref=ref, commits=commits)


def _handle_release(payload: dict) -> None:
    repo: str = payload.get("repository", {}).get("full_name", "")
    tag: str = payload.get("release", {}).get("tag_name", "")
    action: str = payload.get("action", "")
    log.info("webhook_release", repo=repo, tag=tag, action=action)


def _handle_discussion(payload: dict) -> None:
    repo: str = payload.get("repository", {}).get("full_name", "")
    discussion_number: int = payload.get("discussion", {}).get("number", 0)
    action: str = payload.get("action", "")
    log.info("webhook_discussion", repo=repo, discussion=discussion_number, action=action)


def _handle_check_run(payload: dict) -> None:
    repo: str = payload.get("repository", {}).get("full_name", "")
    check_name: str = payload.get("check_run", {}).get("name", "")
    conclusion: str | None = payload.get("check_run", {}).get("conclusion")
    log.info("webhook_check_run", repo=repo, check=check_name, conclusion=conclusion)


def _handle_check_suite(payload: dict) -> None:
    repo: str = payload.get("repository", {}).get("full_name", "")
    conclusion: str | None = payload.get("check_suite", {}).get("conclusion")
    log.info("webhook_check_suite", repo=repo, conclusion=conclusion)
