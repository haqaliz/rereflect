"""
Celery task: deliver_webhook (M3.1 Phase 2).

Handles:
- HTTP POST to the webhook URL with HMAC-SHA256 signature + custom headers
- Delivery logging (WebhookDelivery row)
- Exponential backoff retries via Celery countdown (60s, 300s, 1800s)
- Auto-disable after 10 consecutive failures
- Fire-and-forget mode (single attempt, no retries)
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
from typing import Any, Dict, Optional

import httpx

from src.celery_app import celery_app
from src.database import get_db_session
from src.models import WebhookEndpoint, WebhookDelivery

logger = logging.getLogger(__name__)

# Retry countdowns (seconds) for exponential backoff: attempt 2→1 min, 3→5 min, 4→30 min
_RETRY_COUNTDOWNS = [60, 300, 1800]
_MAX_RETRIES = 3
_AUTO_DISABLE_THRESHOLD = 10
_REQUEST_TIMEOUT = 10.0  # seconds


# ---------------------------------------------------------------------------
# Encryption helpers (Fernet, same key as backend-api)
# ---------------------------------------------------------------------------

def _decrypt(token: str) -> str:
    """Decrypt a Fernet-encrypted string using LLM_ENCRYPTION_KEY."""
    from cryptography.fernet import Fernet
    key = os.environ.get("LLM_ENCRYPTION_KEY")
    if not key:
        raise ValueError("LLM_ENCRYPTION_KEY is not set")
    return Fernet(key.encode()).decrypt(token.encode()).decode()


# ---------------------------------------------------------------------------
# Celery task
# ---------------------------------------------------------------------------

@celery_app.task(
    name="src.tasks.webhook_delivery.deliver_webhook",
    bind=False,
    max_retries=_MAX_RETRIES,
    ignore_result=True,
)
def deliver_webhook(
    webhook_id: int,
    payload_dict: Dict[str, Any],
    attempt: int = 1,
    db_session=None,  # injectable for testing; production uses get_db_session()
) -> None:
    """
    POST the webhook payload to the registered URL.

    Parameters
    ----------
    webhook_id:
        Primary key of the WebhookEndpoint row.
    payload_dict:
        Pre-built JSON-serialisable payload dict (built by the dispatcher).
    attempt:
        Current attempt number (1 = first try, up to 4 with retries).
    db_session:
        Optional database session (injected in tests; omit in production).
    """
    if db_session is not None:
        # Test path — use the provided session directly
        _run_delivery(webhook_id, payload_dict, attempt, db_session)
    else:
        with get_db_session() as session:
            _run_delivery(webhook_id, payload_dict, attempt, session)


# ---------------------------------------------------------------------------
# Core delivery logic (separated so tests can inject a session)
# ---------------------------------------------------------------------------

def _run_delivery(
    webhook_id: int,
    payload_dict: Dict[str, Any],
    attempt: int,
    db,
) -> None:
    """Perform the HTTP delivery and record the result."""
    webhook: Optional[WebhookEndpoint] = (
        db.query(WebhookEndpoint).filter(WebhookEndpoint.id == webhook_id).first()
    )
    if webhook is None:
        logger.warning("deliver_webhook: webhook %s not found — skipping", webhook_id)
        return

    if not webhook.is_active:
        logger.info("deliver_webhook: webhook %s is inactive — skipping", webhook_id)
        return

    # Serialize payload
    payload_bytes = json.dumps(payload_dict, default=str).encode()

    # HMAC-SHA256 signature
    raw_secret = _decrypt(webhook.signing_secret)
    signature_hex = hmac.new(
        raw_secret.encode(), payload_bytes, hashlib.sha256
    ).hexdigest()

    headers: Dict[str, str] = {
        "Content-Type": "application/json",
        "X-Rereflect-Signature": f"sha256={signature_hex}",
    }

    # Merge custom headers (Fernet-encrypted JSON)
    if webhook.custom_headers:
        try:
            custom = json.loads(_decrypt(webhook.custom_headers))
            headers.update(custom)
        except Exception as exc:
            logger.warning(
                "deliver_webhook: failed to decrypt custom headers for webhook %s: %s",
                webhook_id, exc,
            )

    # Perform HTTP POST
    start = time.monotonic()
    response_code: Optional[int] = None
    response_body: Optional[str] = None
    error_message: Optional[str] = None
    success = False

    try:
        response = httpx.post(
            webhook.url,
            content=payload_bytes,
            headers=headers,
            timeout=_REQUEST_TIMEOUT,
        )
        latency_ms = int((time.monotonic() - start) * 1000)
        response_code = response.status_code
        response_body = response.text[:1024]
        success = response.is_success
    except Exception as exc:
        latency_ms = int((time.monotonic() - start) * 1000)
        error_message = str(exc)
        logger.warning(
            "deliver_webhook: network error for webhook %s attempt %s: %s",
            webhook_id, attempt, exc,
        )

    # Determine delivery status and handle retries / failure counting
    if success:
        delivery_status = "sent"
        webhook.consecutive_failures = 0
    else:
        _handle_failure(webhook, attempt, webhook_id, payload_dict)
        # Determine recorded status after potential retry scheduling
        is_final_attempt = (
            webhook.retry_mode == "fire_and_forget"
            or attempt > _MAX_RETRIES
        )
        delivery_status = "failed" if is_final_attempt else "retrying"

    # Persist delivery log
    delivery = WebhookDelivery(
        webhook_id=webhook_id,
        event=payload_dict.get("event", ""),
        feedback_id=payload_dict.get("data", {}).get("feedback", {}).get("id"),
        status=delivery_status,
        attempt=attempt,
        response_code=response_code,
        response_body=response_body,
        error_message=error_message,
        latency_ms=latency_ms,
        payload=payload_dict,
    )
    db.add(delivery)
    db.commit()

    logger.info(
        "deliver_webhook: webhook=%s event=%s attempt=%s status=%s code=%s latency=%sms",
        webhook_id,
        payload_dict.get("event"),
        attempt,
        delivery_status,
        response_code,
        latency_ms,
    )


@celery_app.task(
    name="src.tasks.webhook_delivery.purge_old_webhook_deliveries",
    ignore_result=True,
)
def purge_old_webhook_deliveries() -> dict:
    """
    Weekly Celery Beat task: delete WebhookDelivery rows older than 30 days.

    Retention policy per PRD §10: deliveries > 30 days are purged weekly.
    """
    from datetime import datetime, timedelta, timezone

    cutoff = datetime.now(timezone.utc) - timedelta(days=30)

    with get_db_session() as db:
        deleted = (
            db.query(WebhookDelivery)
            .filter(WebhookDelivery.created_at < cutoff)
            .delete(synchronize_session=False)
        )
        db.commit()

    logger.info("purge_old_webhook_deliveries: deleted %s rows older than %s", deleted, cutoff)
    return {"deleted": deleted}


def _dispatch_analysis_webhooks(feedback, db) -> None:
    """
    Called from the analysis task after AI analysis completes.

    Dispatches up to three webhook events:
    - ``feedback.analyzed``   — always fired after successful analysis
    - ``feedback.urgent``     — fired if feedback.is_urgent is True
    - ``feedback.category_match`` — fired if feedback.tags matches any webhook filter

    Each event is dispatched independently; a failure in one does not affect the others.
    """
    from src.models import WebhookEndpoint
    from datetime import datetime, timezone
    import json

    org_id = feedback.organization_id
    feedback_tags = feedback.tags or []

    # Load all active webhooks for this org once
    webhooks = (
        db.query(WebhookEndpoint)
        .filter(
            WebhookEndpoint.organization_id == org_id,
            WebhookEndpoint.is_active.is_(True),
        )
        .all()
    )

    def _make_payload(event_type: str, extra: dict = None) -> dict:
        """Build the canonical payload dict for analysis-triggered events."""
        created_at = feedback.created_at
        if isinstance(created_at, datetime):
            created_at = created_at.isoformat()

        payload = {
            "event": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "organization_id": org_id,
            "data": {
                "feedback": {
                    "id": feedback.id,
                    "text": feedback.text,
                    "sentiment_label": getattr(feedback, "sentiment_label", None),
                    "sentiment_score": getattr(feedback, "sentiment_score", None),
                    "tags": feedback_tags,
                    "is_urgent": bool(feedback.is_urgent),
                    "churn_risk_score": getattr(feedback, "churn_risk_score", None),
                    "pain_point_category": getattr(feedback, "pain_point_category", None),
                    "feature_request_category": getattr(feedback, "feature_request_category", None),
                    "workflow_status": getattr(feedback, "workflow_status", "new"),
                    "assigned_to": getattr(feedback, "assigned_to", None),
                    "customer_email": getattr(feedback, "customer_email", None),
                    "source": getattr(feedback, "source", None),
                    "created_at": created_at,
                }
            },
        }
        if extra:
            payload["data"].update(extra)
        return payload

    for wh in webhooks:
        events = wh.events or []

        # feedback.analyzed
        if "feedback.analyzed" in events:
            payload = _make_payload("feedback.analyzed")
            payload["webhook_id"] = wh.id
            celery_app.send_task(
                "src.tasks.webhook_delivery.deliver_webhook",
                args=[wh.id, payload],
            )

        # feedback.urgent
        if "feedback.urgent" in events and feedback.is_urgent:
            payload = _make_payload("feedback.urgent")
            payload["webhook_id"] = wh.id
            celery_app.send_task(
                "src.tasks.webhook_delivery.deliver_webhook",
                args=[wh.id, payload],
            )

        # feedback.category_match
        if "feedback.category_match" in events:
            filters = wh.category_filters or []
            if not filters:
                matched = feedback_tags
            else:
                matched = list(set(filters) & set(feedback_tags))
            if matched or not filters:
                payload = _make_payload(
                    "feedback.category_match",
                    extra={"matched_categories": matched},
                )
                payload["webhook_id"] = wh.id
                celery_app.send_task(
                    "src.tasks.webhook_delivery.deliver_webhook",
                    args=[wh.id, payload],
                )


def _handle_failure(
    webhook: WebhookEndpoint,
    attempt: int,
    webhook_id: int,
    payload_dict: Dict[str, Any],
) -> None:
    """
    Increment consecutive_failures, optionally schedule a retry, and
    auto-disable the webhook after _AUTO_DISABLE_THRESHOLD failures.
    """
    webhook.consecutive_failures = (webhook.consecutive_failures or 0) + 1

    if webhook.consecutive_failures >= _AUTO_DISABLE_THRESHOLD:
        webhook.is_active = False
        logger.warning(
            "deliver_webhook: webhook %s auto-disabled after %s consecutive failures",
            webhook_id,
            webhook.consecutive_failures,
        )
        return  # no point retrying a disabled webhook

    # Schedule retry only for exponential_backoff mode
    if webhook.retry_mode == "exponential_backoff" and attempt <= _MAX_RETRIES:
        countdown = _RETRY_COUNTDOWNS[attempt - 1]  # 1→60s, 2→300s, 3→1800s
        logger.info(
            "deliver_webhook: scheduling retry %s for webhook %s in %ss",
            attempt + 1, webhook_id, countdown,
        )
        try:
            celery_app.send_task(
                "src.tasks.webhook_delivery.deliver_webhook",
                args=[webhook_id, payload_dict],
                kwargs={"attempt": attempt + 1},
                countdown=countdown,
            )
        except Exception as exc:
            logger.error(
                "deliver_webhook: failed to schedule retry for webhook %s: %s",
                webhook_id, exc,
            )
