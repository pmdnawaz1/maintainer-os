"""Shared webhook verification utilities.

Extracted from webhooks.py so any webhook consumer (GitHub, future Stripe,
custom integrations, etc.) can reuse signature, replay, timestamp, and
rate-limit checks without duplicating the implementation.
"""

import hashlib
import hmac
import time
from collections import OrderedDict
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import structlog
from fastapi import HTTPException, Request

log = structlog.get_logger()

# ── Replay protection ─────────────────────────────────────────────────────────
_seen_deliveries: OrderedDict[str, float] = OrderedDict()
REPLAY_WINDOW = 300.0  # seconds
_MAX_SEEN_IDS = 10_000


def check_replay(delivery_id: str) -> None:
    """Reject duplicate deliveries within the replay window.

    Uses a bounded OrderedDict to track seen IDs. Evicts entries older than
    2× the replay window to bound memory usage.
    """
    now = time.monotonic()
    cutoff = now - REPLAY_WINDOW * 2
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


# ── Signature verification ────────────────────────────────────────────────────

def verify_hmac_signature(
    payload: bytes,
    signature: str | None,
    secrets_raw: str | None,
    *,
    prefix: str = "sha256=",
) -> None:
    """Verify an HMAC-SHA256 signature against one or more comma-separated secrets.

    Supports secret rotation: any matching secret is accepted. Pass
    ``secrets_raw`` as a comma-separated string (e.g. ``"oldSecret,newSecret"``).
    """
    if not secrets_raw:
        return
    if not signature or not signature.startswith(prefix):
        log.warning("webhook_missing_signature")
        raise HTTPException(status_code=401, detail="Missing webhook signature")
    secrets = [s.strip() for s in secrets_raw.split(",") if s.strip()]
    for secret in secrets:
        expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        if hmac.compare_digest(f"{prefix}{expected}", signature):
            return
    log.warning("webhook_invalid_signature")
    raise HTTPException(status_code=401, detail="Invalid webhook signature")


# ── Timestamp validation ──────────────────────────────────────────────────────

def check_timestamp(date_header: str | None, max_age: float = REPLAY_WINDOW) -> None:
    """Reject requests whose Date header is older than *max_age* seconds."""
    if not date_header:
        return
    try:
        request_time = parsedate_to_datetime(date_header)
        age = abs((datetime.now(timezone.utc) - request_time).total_seconds())
        if age > max_age:
            log.warning("webhook_timestamp_too_old", age_seconds=age)
            raise HTTPException(
                status_code=400, detail="Webhook request timestamp too old"
            )
    except (TypeError, ValueError):
        pass  # Unparseable Date header is non-fatal


# ── Rate limiting ─────────────────────────────────────────────────────────────
_rate_buckets: dict[str, list[float]] = {}
RATE_LIMIT = 100
RATE_WINDOW = 60.0  # requests per minute


def check_rate_limit(request: Request, limit: int = RATE_LIMIT, window: float = RATE_WINDOW) -> None:
    """Sliding-window rate limiter keyed by client IP."""
    client_ip = request.client.host if request.client else "unknown"
    now = time.monotonic()
    bucket = [t for t in _rate_buckets.get(client_ip, []) if now - t < window]
    if len(bucket) >= limit:
        log.warning("webhook_rate_limit_exceeded", ip=client_ip)
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    bucket.append(now)
    _rate_buckets[client_ip] = bucket
