"""
Inbound email webhook endpoint for Resend.

Receives forwarded emails, looks up the org by inbound address,
applies rate limiting and deduplication, parses the body, and
queues the feedback for async analysis.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.database.session import get_db
from src.models import FeedbackSource
from src.services.email_parser import parse_email_body

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/webhooks/email", tags=["email-webhooks"])

# Rate limiting constants
EMAIL_RATE_LIMIT = 100  # per org per hour
EMAIL_RATE_WINDOW = 3600  # 1 hour in seconds
EMAIL_DEDUP_TTL = 86400  # 24 hours in seconds

RESEND_INBOUND_WEBHOOK_SECRET = os.environ.get("RESEND_INBOUND_WEBHOOK_SECRET")


def _verify_webhook_signature(body: bytes, headers: dict) -> bool:
    """Verify Resend webhook signature using svix."""
    if not RESEND_INBOUND_WEBHOOK_SECRET:
        logger.warning("RESEND_INBOUND_WEBHOOK_SECRET not configured, skipping verification")
        return True

    try:
        from svix.webhooks import Webhook

        wh = Webhook(RESEND_INBOUND_WEBHOOK_SECRET)
        wh.verify(body, headers)
        return True
    except Exception as e:
        logger.error(f"Webhook signature verification failed: {e}")
        return False


def _get_redis():
    """Get a Redis connection for rate limiting and dedup."""
    import redis
    host = os.environ.get("REDIS_HOST", "localhost")
    port = int(os.environ.get("REDIS_PORT", "6379"))
    password = os.environ.get("REDIS_PASSWORD", "")
    if password:
        return redis.from_url(f"redis://:{password}@{host}:{port}/0")
    return redis.from_url(f"redis://{host}:{port}/0")


def queue_source_event(
    source_type: str,
    external_event_id: str,
    event_type: str,
    event_data: dict,
    provider_context: dict,
) -> str:
    """Queue a source event for async processing via Celery."""
    from src.background import get_celery_app

    app = get_celery_app()
    result = app.send_task(
        "src.tasks.source_events.process_source_event",
        args=[source_type, external_event_id, event_type, event_data, provider_context],
    )
    logger.info(f"Queued email event {external_event_id}: task {result.id}")
    return result.id


@router.post("/inbound")
async def handle_email_inbound(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Handle inbound email from Resend webhook.

    Flow:
    1. Extract recipient address from payload
    2. Look up FeedbackSource by inbound_address
    3. Dedup check via Message-ID in Redis
    4. Rate limit check via Redis
    5. Parse email body
    6. Queue for async processing
    """
    # Read raw body for signature verification, then parse JSON
    try:
        body = await request.body()
    except Exception:
        raise HTTPException(status_code=400, detail="Failed to read request body")

    # Verify webhook signature
    svix_headers = {
        "svix-id": request.headers.get("svix-id", ""),
        "svix-timestamp": request.headers.get("svix-timestamp", ""),
        "svix-signature": request.headers.get("svix-signature", ""),
    }
    if not _verify_webhook_signature(body, svix_headers):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    try:
        payload = json.loads(body)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    # Resend wraps inbound email data in a "data" object
    email_data = payload.get("data", payload)

    # Extract required fields
    to_address = email_data.get("to")
    if not to_address:
        raise HTTPException(status_code=400, detail="Missing recipient address")

    # Normalize: Resend sends 'to' as a list of strings
    if isinstance(to_address, list):
        to_address = to_address[0] if to_address else None
    if not to_address:
        raise HTTPException(status_code=400, detail="Missing recipient address")

    message_id = email_data.get("message_id", "")
    subject = email_data.get("subject", "")
    html_body = email_data.get("html")
    text_body = email_data.get("text")

    # Look up the feedback source by inbound address
    source = db.query(FeedbackSource).filter(
        FeedbackSource.source_type == "email",
    ).all()

    matching_source = None
    for s in source:
        config = s.provider_config or {}
        if config.get("inbound_address") == to_address:
            matching_source = s
            break

    if not matching_source:
        raise HTTPException(status_code=400, detail="Unknown recipient address")

    if not matching_source.is_active:
        raise HTTPException(status_code=400, detail="Email source is inactive")

    org_id = matching_source.organization_id

    # Redis checks
    r = _get_redis()

    # Dedup check via Message-ID
    if message_id:
        dedup_key = f"email_dedup:{hashlib.md5(message_id.encode()).hexdigest()}"
        if r.get(dedup_key):
            logger.info(f"Duplicate email Message-ID: {message_id}")
            return {"status": "duplicate", "message_id": message_id}

    # Rate limit check
    rate_key = f"email_rate:{org_id}"
    current_count = r.incr(rate_key)
    if current_count == 1:
        r.expire(rate_key, EMAIL_RATE_WINDOW)

    if current_count > EMAIL_RATE_LIMIT:
        logger.warning(f"Email rate limit exceeded for org {org_id}: {current_count}")
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    # Mark Message-ID as seen (24hr TTL)
    if message_id:
        dedup_key = f"email_dedup:{hashlib.md5(message_id.encode()).hexdigest()}"
        r.setex(dedup_key, EMAIL_DEDUP_TTL, "1")

    # Quick empty-body check before queuing
    parsed_body = parse_email_body(html_body, text_body)

    if not parsed_body:
        logger.info(f"Empty email body from {to_address}, skipping")
        return {"status": "skipped", "reason": "empty_body"}

    # Queue for async processing — pass raw html/text so the adapter can parse
    try:
        task_id = queue_source_event(
            source_type="email",
            external_event_id=message_id or hashlib.md5(parsed_body.encode()).hexdigest(),
            event_type="email.inbound",
            event_data={
                "subject": subject,
                "html": html_body,
                "text": text_body,
                "from": email_data.get("from", ""),
                "to": to_address,
                "message_id": message_id,
            },
            provider_context={
                "source_id": matching_source.id,
                "organization_id": org_id,
                "inbound_address": to_address,
            },
        )
        return {"status": "queued", "task_id": task_id}
    except Exception as e:
        logger.error(f"Failed to queue email event: {e}")
        raise HTTPException(status_code=500, detail="Failed to process email")
