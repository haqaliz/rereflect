"""
outreach_sender — the shared per-recipient outreach send helper
(outreach-core aspect).

Both send paths (playbook `send_email` step, bulk campaign task) call this
helper so opt-out, cooldown, List-Unsubscribe and the Resend call live in
exactly one place per process — the two copies must not drift.

Send contract (check order, each loud, never silent):

    1. opt-out flag (in-DB, `customer_health_scores.outreach_opt_out`,
       checked at send time, never at queue time)
    2. cooldown key in Redis (DB 1, `outreach_cooldown:{org_id}:{email}`,
       TTL `OUTREACH_COOLDOWN_HOURS`, default 24 — shared with the bulk path)
    3. `RESEND_API_KEY` unset → `failed: email not configured`
    4. send via `src.email._send_email` with a `List-Unsubscribe` header;
       on success set the cooldown key; on failure `failed: resend send failed`

Returns ``{"ok": bool, "status": "sent|skipped|failed", "reason": str}`` —
never raises on send failure (callers record the dict).

Cooldown semantics mirror `automation_churn_trigger`/`automation_feedback_trigger`:
Redis DB 1, `_get_redis()` returns None (cooldowns disabled, never raises) when
Redis is unavailable.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
from typing import Optional

from sqlalchemy.orm import Session

from src import email as email_module
from src.models import CustomerHealth

logger = logging.getLogger(__name__)

# Shared with backend-api's `outreach_sender_contract.OUTREACH_COOLDOWN_PREFIX`
# (pinned by tests in both suites) so both send paths write the same key.
OUTREACH_COOLDOWN_PREFIX = "outreach_cooldown"
OUTREACH_COOLDOWN_HOURS_DEFAULT = 24

_redis_client = None


def _get_redis():
    """Return a shared Redis client (db=1), or None if Redis is unavailable.

    Mirrors `automation_churn_trigger._get_redis` behaviour: on connection
    failure, cooldowns are simply disabled — never raises.
    """
    global _redis_client
    if _redis_client is None:
        try:
            import redis

            from src.config import get_redis_url

            _redis_client = redis.from_url(
                get_redis_url(1),
                decode_responses=True,
                socket_connect_timeout=2,
            )
            _redis_client.ping()
        except Exception as exc:
            logger.warning(
                "outreach_sender: Redis unavailable — outreach cooldowns disabled: %s",
                exc,
            )
            _redis_client = None
    return _redis_client


def _cooldown_hours() -> int:
    """OUTREACH_COOLDOWN_HOURS (default 24); unparseable values log + fall back."""
    raw = os.getenv("OUTREACH_COOLDOWN_HOURS", str(OUTREACH_COOLDOWN_HOURS_DEFAULT))
    try:
        return int(raw)
    except (TypeError, ValueError):
        logger.warning(
            "outreach_sender: OUTREACH_COOLDOWN_HOURS=%r unparseable — using %s",
            raw,
            OUTREACH_COOLDOWN_HOURS_DEFAULT,
        )
        return OUTREACH_COOLDOWN_HOURS_DEFAULT


def make_unsubscribe_token(org_id: int, customer_email: str) -> str:
    """Stateless HMAC-SHA256 token over ``'{org_id}:{email}'``, keyed by
    `LLM_ENCRYPTION_KEY`.

    The token is self-describing — ``'{org_id}:{normalized_email}:{hex digest}'``
    — so the backend's public unsubscribe endpoint can recover org + email
    from the token alone and verify the digest. Byte-compatible with the
    backend's canonical `outreach_tokens.make_unsubscribe_token`.
    """
    email = customer_email.strip().lower()
    key = os.environ.get("LLM_ENCRYPTION_KEY", "")
    if not key:
        raise ValueError("LLM_ENCRYPTION_KEY environment variable is not set")
    payload = f"{org_id}:{email}"
    digest = hmac.new(
        key.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"{payload}:{digest}"


def _check_cooldown(org_id: int, customer_email: str) -> bool:
    """True if this org/email pair is still in cooldown (skip it)."""
    r = _get_redis()
    if r is None:
        return False
    key = f"{OUTREACH_COOLDOWN_PREFIX}:{org_id}:{customer_email}"
    try:
        return bool(r.exists(key))
    except Exception as exc:
        logger.warning("outreach_sender: cooldown check failed: %s", exc)
        return False


def _set_cooldown(org_id: int, customer_email: str) -> None:
    """Set the cooldown key with TTL = OUTREACH_COOLDOWN_HOURS * 3600."""
    r = _get_redis()
    if r is None:
        return
    key = f"{OUTREACH_COOLDOWN_PREFIX}:{org_id}:{customer_email}"
    try:
        r.setex(key, _cooldown_hours() * 3600, "1")
    except Exception as exc:
        logger.warning("outreach_sender: failed to set cooldown: %s", exc)


def send_outreach_email(
    db: Session,
    org_id: int,
    customer_email: str,
    subject: str,
    body: str,
    *,
    product_name: str,
    template_key: Optional[str] = None,
) -> dict:
    """Send one outreach email honoring opt-out + cooldown, loudly.

    `subject`/`body` are the final strings (the caller renders a registry
    template or a draft); `product_name`/`template_key` are provenance for
    the caller's audit trail. Returns ``{ok, status, reason}`` — never raises
    on send failure.
    """
    email = customer_email.strip().lower()

    # 1. Opt-out flag — checked in-DB at send time (never at queue time).
    health = (
        db.query(CustomerHealth)
        .filter(
            CustomerHealth.organization_id == org_id,
            CustomerHealth.customer_email == email,
        )
        .first()
    )
    if health is not None and health.outreach_opt_out:
        return {"ok": False, "status": "skipped", "reason": "opted out"}

    # 2. Cooldown key — shared with the bulk path; a customer can never be
    #    emailed twice in the same window.
    if _check_cooldown(org_id, email):
        return {"ok": False, "status": "skipped", "reason": "in cooldown"}

    # 3. Loud no-key failure — never a false success.
    if not email_module.RESEND_API_KEY:
        return {"ok": False, "status": "failed", "reason": "email not configured"}

    # 4. Send with a tokenized List-Unsubscribe header.
    token = make_unsubscribe_token(org_id, email)
    unsubscribe_url = f"{email_module.APP_URL}/outreach/unsubscribe?token={token}"
    sent = email_module._send_email(
        to=email,
        subject=subject,
        html="",
        text=body,
        extra_headers={"List-Unsubscribe": f"<{unsubscribe_url}>"},
    )
    if not sent:
        return {"ok": False, "status": "failed", "reason": "resend send failed"}

    _set_cooldown(org_id, email)
    return {"ok": True, "status": "sent", "reason": ""}
