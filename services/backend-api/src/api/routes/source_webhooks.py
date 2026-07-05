"""
Webhook endpoints for receiving events from external sources (Slack, Intercom, generic webhooks).
These endpoints handle signature verification and queue events for async processing.
"""

import base64
import hashlib
import hmac
import json
import logging
import os
import time
import uuid
from typing import Mapping, Optional
from urllib.parse import urlparse

from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.orm import Session

from src.database.session import get_db
from src.models import FeedbackSource, FeedbackSourceEvent
from src.models.zendesk_integration import ZendeskIntegration
from src.utils.encryption import decrypt_api_key

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/webhooks", tags=["webhooks"])

# Environment variables
SLACK_SIGNING_SECRET = os.environ.get("SLACK_SIGNING_SECRET", "")
INTERCOM_CLIENT_SECRET = os.environ.get("INTERCOM_CLIENT_SECRET", "")


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


# ============================================================================
# Intercom Webhook
# ============================================================================

INTERCOM_HANDLED_TOPICS = {
    "conversation.user.created",
    "conversation.user.replied",
    "conversation.rating.added",
}


def verify_intercom_signature(body: bytes, signature: str, secret: str) -> bool:
    """
    Verify Intercom webhook HMAC-SHA1 signature.

    Args:
        body: Raw request body bytes
        signature: X-Hub-Signature header value (e.g. "sha1=abc123...")
        secret: Intercom client secret used as HMAC key

    Returns:
        True if signature is valid
    """
    if not secret:
        logger.warning("INTERCOM_CLIENT_SECRET not configured, skipping signature verification")
        return True

    expected = "sha1=" + hmac.new(secret.encode(), body, hashlib.sha1).hexdigest()
    return hmac.compare_digest(expected, signature)


@router.post("/intercom/events")
async def handle_intercom_webhook(request: Request):
    """
    Handle incoming Intercom webhook events.

    Verifies HMAC-SHA1 signature, parses the event topic,
    and queues supported conversation events for async processing.
    """
    body = await request.body()

    # Verify Intercom signature
    signature = request.headers.get("X-Hub-Signature", "")
    if not verify_intercom_signature(body, signature, INTERCOM_CLIENT_SECRET):
        raise HTTPException(status_code=401, detail="Invalid signature")

    # Parse payload
    try:
        payload = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    topic = payload.get("topic", "")

    # Only handle supported conversation topics
    if topic not in INTERCOM_HANDLED_TOPICS:
        logger.info(f"Ignoring Intercom topic: {topic}")
        return {"status": "ignored", "reason": f"unsupported_topic:{topic}"}

    # Extract conversation ID as external event ID
    conversation_id = payload.get("data", {}).get("item", {}).get("id")
    if not conversation_id:
        logger.warning("Missing conversation ID in Intercom event")
        return {"status": "ignored", "reason": "missing_conversation_id"}

    # Extract workspace_id (app_id) for source matching
    workspace_id = payload.get("app_id")

    # Queue for async processing
    try:
        task_id = queue_source_event(
            source_type="intercom",
            external_event_id=conversation_id,
            event_type=topic,
            event_data=payload.get("data", {}),
            provider_context={
                "conversation_id": conversation_id,
                "workspace_id": workspace_id,
            },
        )
        return {"status": "queued", "task_id": task_id}
    except Exception as e:
        logger.error(f"Failed to queue Intercom event: {e}")
        raise HTTPException(status_code=500, detail="Failed to process event")


# ============================================================================
# Zendesk Webhook
# ============================================================================


def _resolve_zendesk_subdomain(payload: dict, headers: Mapping) -> Optional[str]:
    """
    Resolve the Zendesk account subdomain for an inbound webhook payload.

    Resolution order (first match wins):
    1. Top-level `subdomain` field in the payload (simplest for the operator
       to hardcode literally in the Zendesk trigger's JSON body).
    2. The host label parsed from `payload["ticket"]["url"]`
       (`https://{subdomain}.zendesk.com/...`).
    3. The `X-Zendesk-Subdomain` request header.

    Returns the normalized (lower-cased) subdomain, or None if none of the
    three are resolvable.
    """
    subdomain = payload.get("subdomain")
    if subdomain:
        return str(subdomain).lower()

    ticket = payload.get("ticket") or {}
    url = ticket.get("url")
    if url:
        try:
            host = urlparse(url).hostname
        except (ValueError, AttributeError):
            host = None
        if host and host.endswith(".zendesk.com"):
            label = host[: -len(".zendesk.com")]
            if label:
                return label.lower()

    header_subdomain = headers.get("X-Zendesk-Subdomain")
    if header_subdomain:
        return str(header_subdomain).lower()

    return None


def _verify_zendesk_signature(body: bytes, timestamp: str, signature: str, secret: Optional[str]) -> bool:
    """
    Verify a Zendesk webhook HMAC-SHA256 signature.

    `X-Zendesk-Webhook-Signature` = base64(HMAC-SHA256(webhook_secret,
    `X-Zendesk-Webhook-Signature-Timestamp` + raw_body)), verified over the
    raw request body.

    Fails closed: an empty/None secret returns False (Zendesk's per-org
    webhook_secret is a required value once the webhook path is opted into,
    not an optional global env var like Intercom's INTERCOM_CLIENT_SECRET).
    """
    if not secret:
        return False
    if not signature or not timestamp:
        return False

    expected = base64.b64encode(
        hmac.new(secret.encode(), timestamp.encode() + body, hashlib.sha256).digest()
    ).decode()
    return hmac.compare_digest(expected, signature)


def _ignore(reason: str) -> dict:
    """
    Build the 200 no-op response body shared by every "logged, nothing
    created" branch (missing_subdomain / unknown_subdomain / no_active_source
    / missing_ticket_id). Callers still log a distinct message per reason
    before calling this -- this only dedupes the return shape.
    """
    return {"status": "ignored", "reason": reason}


@router.post("/zendesk/events")
async def handle_zendesk_webhook(request: Request, db: Session = Depends(get_db)):
    """
    Handle incoming Zendesk webhook events (new-ticket trigger).

    Flow: read raw body -> parse JSON -> resolve subdomain -> look up the
    org's ZendeskIntegration by subdomain (secret lookup happens per-org, not
    via a global env var) -> verify HMAC signature -> look up the org's
    active zendesk FeedbackSource -> quick dedup pre-check -> queue.
    """
    # Read raw body FIRST -- both JSON parsing and signature verification
    # must operate on the exact same bytes Zendesk sent (re-serializing the
    # parsed dict is not guaranteed to round-trip byte-for-byte).
    body = await request.body()

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid JSON")

    subdomain = _resolve_zendesk_subdomain(payload, request.headers)
    if not subdomain:
        logger.info("Zendesk webhook: no subdomain resolvable from payload/headers")
        return _ignore("missing_subdomain")

    integration = (
        db.query(ZendeskIntegration)
        .filter(
            ZendeskIntegration.subdomain == subdomain,
            ZendeskIntegration.is_active.is_(True),
        )
        .first()
    )
    if not integration:
        logger.info(f"Zendesk webhook: unknown/inactive subdomain '{subdomain}'")
        return _ignore("unknown_subdomain")

    # Fail-closed: a matched integration with no webhook_secret has not
    # opted into the real-time webhook. This is deliberately a 401 (not the
    # 200 "unknown_subdomain"/"no_active_source" no-op shape) -- silently
    # accepting unsigned payloads for an org that never configured a secret
    # would let anyone who guesses/enumerates a subdomain inject fake
    # tickets.
    if not integration.webhook_secret:
        logger.warning(f"Zendesk webhook: no webhook_secret configured for subdomain '{subdomain}'")
        raise HTTPException(status_code=401, detail="Webhook not configured for this account")

    try:
        secret = decrypt_api_key(integration.webhook_secret)
    except Exception:
        logger.error(f"Zendesk webhook: failed to decrypt webhook_secret for subdomain '{subdomain}'")
        raise HTTPException(status_code=401, detail="Invalid webhook configuration")

    timestamp = request.headers.get("X-Zendesk-Webhook-Signature-Timestamp", "")
    signature = request.headers.get("X-Zendesk-Webhook-Signature", "")
    if not signature or not timestamp or not _verify_zendesk_signature(body, timestamp, signature, secret):
        raise HTTPException(status_code=401, detail="Invalid signature")

    source = (
        db.query(FeedbackSource)
        .filter(
            FeedbackSource.organization_id == integration.organization_id,
            FeedbackSource.source_type == "zendesk",
            FeedbackSource.is_active.is_(True),
        )
        .first()
    )
    if not source:
        # Should not normally happen -- backend-connection auto-provisions
        # the source on connect. Its absence here means the source was
        # later deactivated or the auto-provision step regressed.
        logger.warning(
            f"Zendesk webhook: no active zendesk FeedbackSource for org {integration.organization_id} "
            f"(subdomain '{subdomain}')"
        )
        return _ignore("no_active_source")

    ticket = payload.get("ticket") or {}
    ticket_id = ticket.get("id")
    if not ticket_id:
        logger.warning(f"Zendesk webhook: missing ticket id for subdomain '{subdomain}'")
        return _ignore("missing_ticket_id")

    # Quick synchronous dedup pre-check (fast-path optimization on top of,
    # not a replacement for, the ingestion-core's own FeedbackSourceEvent
    # dedup -- the authoritative dedup lives downstream via the unique
    # constraint uq_source_event(source_id, external_event_id)).
    existing = (
        db.query(FeedbackSourceEvent)
        .filter(
            FeedbackSourceEvent.source_id == source.id,
            FeedbackSourceEvent.external_event_id == str(ticket_id),
        )
        .first()
    )
    if existing:
        logger.info(f"Duplicate Zendesk ticket {ticket_id} for subdomain '{subdomain}'")
        return {"status": "duplicate"}

    provider_context = {"subdomain": subdomain}
    try:
        task_id = queue_source_event(
            source_type="zendesk",
            external_event_id=str(ticket_id),
            event_type="ticket.created",
            event_data={"ticket": ticket, "subdomain": subdomain},
            provider_context=provider_context,
        )
        return {"status": "queued", "task_id": task_id}
    except Exception as e:
        logger.error(f"Failed to queue Zendesk event: {e}")
        raise HTTPException(status_code=500, detail="Failed to process event")
