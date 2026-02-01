"""
Webhook endpoints for receiving events from external sources (Slack, Discord, generic webhooks).
These endpoints handle signature verification and queue events for async processing.
"""

import hashlib
import hmac
import json
import logging
import os
import time
import uuid
from typing import Optional

from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.orm import Session

from src.database.session import get_db
from src.models import FeedbackSource, FeedbackSourceEvent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/webhooks", tags=["webhooks"])

# Environment variables
SLACK_SIGNING_SECRET = os.environ.get("SLACK_SIGNING_SECRET", "")


def verify_slack_signature(body: str, timestamp: str, signature: str, secret: str) -> bool:
    """
    Verify Slack request signature.

    Args:
        body: Raw request body as string
        timestamp: X-Slack-Request-Timestamp header
        signature: X-Slack-Signature header
        secret: Slack signing secret

    Returns:
        True if signature is valid
    """
    if not secret:
        logger.warning("SLACK_SIGNING_SECRET not configured, skipping signature verification")
        return True

    # Check timestamp (prevent replay attacks - 5 minute window)
    try:
        if abs(time.time() - int(timestamp)) > 300:
            logger.warning("Slack request timestamp too old")
            return False
    except (ValueError, TypeError):
        logger.warning("Invalid Slack request timestamp")
        return False

    # Compute signature
    sig_basestring = f"v0:{timestamp}:{body}"
    my_signature = "v0=" + hmac.new(
        secret.encode(),
        sig_basestring.encode(),
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(my_signature, signature)


def queue_source_event(
    source_type: str,
    external_event_id: str,
    event_type: str,
    event_data: dict,
    provider_context: dict,
) -> str:
    """
    Queue a source event for async processing via Celery.

    Returns:
        Task ID
    """
    from src.background import get_celery_app

    app = get_celery_app()

    try:
        result = app.send_task(
            "src.tasks.source_events.process_source_event",
            args=[source_type, external_event_id, event_type, event_data, provider_context],
        )
        logger.info(f"Queued {source_type} event {external_event_id}: task {result.id}")
        return result.id
    except Exception as e:
        logger.error(f"Failed to queue {source_type} event: {e}")
        raise


@router.post("/slack/events")
async def handle_slack_webhook(request: Request, db: Session = Depends(get_db)):
    """
    Handle incoming Slack Events API webhook.

    This endpoint handles:
    1. URL verification challenge (required by Slack)
    2. Event signature verification
    3. Event queueing for async processing
    """
    body = await request.body()
    body_str = body.decode('utf-8')

    # Verify Slack signature
    timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
    signature = request.headers.get("X-Slack-Signature", "")

    if not verify_slack_signature(body_str, timestamp, signature, SLACK_SIGNING_SECRET):
        raise HTTPException(status_code=401, detail="Invalid signature")

    # Parse payload
    try:
        payload = json.loads(body_str)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # Handle URL verification challenge
    if payload.get("type") == "url_verification":
        challenge = payload.get("challenge")
        logger.info("Slack URL verification challenge received")
        return {"challenge": challenge}

    # Handle event callbacks
    if payload.get("type") == "event_callback":
        event = payload.get("event", {})
        team_id = payload.get("team_id")
        event_id = payload.get("event_id")
        event_type = event.get("type", "unknown")

        if not event_id or not team_id:
            logger.warning("Missing event_id or team_id in Slack event")
            return {"status": "ignored", "reason": "missing_required_fields"}

        # Quick deduplication check (full dedup in worker)
        existing = db.query(FeedbackSourceEvent).filter(
            FeedbackSourceEvent.external_event_id == event_id
        ).first()

        if existing:
            logger.info(f"Duplicate Slack event {event_id}")
            return {"status": "duplicate"}

        # Queue for async processing
        try:
            task_id = queue_source_event(
                source_type="slack",
                external_event_id=event_id,
                event_type=event_type,
                event_data=event,
                provider_context={"team_id": team_id},
            )
            return {"status": "queued", "task_id": task_id}
        except Exception as e:
            logger.error(f"Failed to queue Slack event: {e}")
            raise HTTPException(status_code=500, detail="Failed to process event")

    return {"status": "ignored", "reason": "unknown_payload_type"}


@router.post("/inbound/{webhook_id}")
async def handle_generic_webhook(
    webhook_id: str,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Handle generic inbound webhook.

    Users create a FeedbackSource of type 'webhook' and receive a unique webhook_id.
    This endpoint validates the webhook and queues the data for processing.
    """
    # Find the feedback source by webhook_id
    source = db.query(FeedbackSource).filter(
        FeedbackSource.source_type == "webhook",
        FeedbackSource.is_active == True,
    ).all()

    # Find matching source by webhook_id in provider_config
    matching_source = None
    for s in source:
        config = s.provider_config or {}
        if config.get("webhook_id") == webhook_id:
            matching_source = s
            break

    if not matching_source:
        raise HTTPException(status_code=404, detail="Webhook not found")

    # Parse request body
    body = await request.body()
    body_str = body.decode('utf-8')

    # Verify secret if configured
    config = matching_source.provider_config or {}
    secret_token = config.get("secret_token")
    if secret_token:
        provided_token = request.headers.get("X-Webhook-Secret")
        if not provided_token or not hmac.compare_digest(secret_token, provided_token):
            raise HTTPException(status_code=401, detail="Invalid webhook secret")

    # Parse JSON
    try:
        payload = json.loads(body_str) if body_str else {}
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # Generate event ID for deduplication
    event_id = str(uuid.uuid4())

    # Quick deduplication by content hash (optional)
    content_hash = hashlib.md5(body_str.encode()).hexdigest()

    # Queue for async processing
    try:
        task_id = queue_source_event(
            source_type="webhook",
            external_event_id=event_id,
            event_type="webhook",
            event_data={
                "payload": payload,
                "content_hash": content_hash,
                "headers": dict(request.headers),
            },
            provider_context={
                "webhook_id": webhook_id,
                "source_id": matching_source.id,
            },
        )
        return {"status": "queued", "event_id": event_id, "task_id": task_id}
    except Exception as e:
        logger.error(f"Failed to queue webhook event: {e}")
        raise HTTPException(status_code=500, detail="Failed to process webhook")
