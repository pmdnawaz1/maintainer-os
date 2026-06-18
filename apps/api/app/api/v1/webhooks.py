"""GitHub App webhook handler."""

import hashlib
import hmac
import json
import time
from collections import OrderedDict
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Request

from app.core.config import settings

log = structlog.get_logger()
router = APIRouter()

# ── Replay protection: track delivery IDs within a sliding window ──────────────
_seen_deliveries: OrderedDict[str, float] = OrderedDict()
_REPLAY_WINDOW = 300.0  # 5 minutes
_MAX_SEEN_IDS = 10_000


def _check_replay(delivery_id: str) -> None:
    now = time.monotonic()
    cutoff = now - _REPLAY_WINDOW * 2
    while _seen_deliveries:
        oldest_id, oldest_ts = next(iter(_seen_deliveries.items()))
        if oldest_ts < cutoff:
            _seen_deliveries.popitem(last=False)
        else:
            break
    if delivery_id in _seen_deliveries:
        log.warning("webhook_replay_detected", delivery_id=delivery_id)
        raise HTTPException(status_code=409, detail="Duplicate webhook delivery")
    if len(_seen_deliveries) >= _MAX_SEEN_IDS:
        _seen_deliveries.popitem(last=False)
    _seen_deliveries[delivery_id] = now


# ── Rate limiting: sliding window per client IP ────────────────────────────────
_rate_buckets: dict[str, list[float]] = {}
_RATE_LIMIT = 100
_RATE_WINDOW = 60.0  # requests per minute


def rate_limit_dependency(request: Request) -> None:
    client_ip = request.client.host if request.client else "unknown"
    now = time.monotonic()
    bucket = [t for t in _rate_buckets.get(client_ip, []) if now - t < _RATE_WINDOW]
    if len(bucket) >= _RATE_LIMIT:
        log.warning("webhook_rate_limit_exceeded", ip=client_ip)
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    bucket.append(now)
    _rate_buckets[client_ip] = bucket


# ── Signature verification with secret rotation support ───────────────────────

def _verify_signature(payload: bytes, signature: str | None) -> None:
    secrets_raw = settings.github_webhook_secret
    if not secrets_raw:
        return
    if not signature or not signature.startswith("sha256="):
        log.warning("webhook_missing_signature")
        raise HTTPException(status_code=401, detail="Missing webhook signature")
    # Comma-separated secrets for key rotation: any matching secret is accepted
    secrets = [s.strip() for s in secrets_raw.split(",") if s.strip()]
    for secret in secrets:
        expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        if hmac.compare_digest(f"sha256={expected}", signature):
            return
    log.warning("webhook_invalid_signature")
    raise HTTPException(status_code=401, detail="Invalid webhook signature")


# ── Timestamp validation to reject stale replayed requests ────────────────────

def _check_timestamp(date_header: str | None) -> None:
    if not date_header:
        return
    try:
        request_time = parsedate_to_datetime(date_header)
        age = abs((datetime.now(timezone.utc) - request_time).total_seconds())
        if age > _REPLAY_WINDOW:
            log.warning("webhook_timestamp_too_old", age_seconds=age)
            raise HTTPException(status_code=400, detail="Webhook request timestamp too old")
    except (TypeError, ValueError):
        pass  # Unparseable Date header is non-fatal


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
    _check_timestamp(date)

    if x_github_delivery:
        _check_replay(x_github_delivery)

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
