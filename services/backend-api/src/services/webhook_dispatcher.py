"""
Webhook Dispatch Engine (M3.1 Phase 2).

dispatch_webhook_event() is the main public entry point.  It queries all
active WebhookEndpoints for an organisation that subscribe to the given event,
applies category-match filtering where required, builds the canonical JSON
payload, and hands off to _enqueue_delivery() which schedules the Celery
deliver_webhook task.

This module is intentionally side-effect-free with respect to the HTTP
delivery — all network I/O happens inside the Celery worker task so that API
response times are not affected.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from src.models.webhook_endpoint import WebhookEndpoint
from src.models.feedback import FeedbackItem

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def dispatch_webhook_event(
    db: Session,
    org_id: int,
    event_type: str,
    feedback: FeedbackItem,
    changes: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Find all active WebhookEndpoints for *org_id* subscribed to *event_type*,
    build the canonical payload, and enqueue one Celery task per endpoint.

    For ``feedback.category_match`` events the webhook's ``category_filters``
    list is intersected with ``feedback.tags``.  A webhook fires when:
      - ``category_filters`` is empty (match-all), OR
      - the intersection is non-empty.

    The ``changes`` dict is included in ``payload.data.changes`` only for
    ``feedback.status_changed`` events.

    This function never raises — any exception is caught and logged so that
    the caller's main flow is not interrupted.
    """
    try:
        webhooks = _get_matching_webhooks(db, org_id, event_type, feedback)
        for webhook in webhooks:
            matched_categories: Optional[List[str]] = None
            if event_type == "feedback.category_match":
                feedback_tags = feedback.tags or []
                filters = webhook.category_filters or []
                matched_categories = (
                    list(set(filters) & set(feedback_tags)) if filters else feedback_tags
                )
            payload = _build_payload(
                webhook=webhook,
                event_type=event_type,
                feedback=feedback,
                changes=changes,
                matched_categories=matched_categories,
            )
            _enqueue_delivery(webhook.id, payload)
    except Exception as exc:
        logger.error(
            "dispatch_webhook_event failed for org=%s event=%s: %s",
            org_id,
            event_type,
            exc,
            exc_info=True,
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_matching_webhooks(
    db: Session,
    org_id: int,
    event_type: str,
    feedback: FeedbackItem,
) -> List[WebhookEndpoint]:
    """
    Return the active webhooks for the org that are subscribed to event_type.

    For category_match events we additionally filter by tag intersection.
    The SQLAlchemy query handles the org/active/event parts; Python handles
    the JSON array intersection (easier than a portable JSON-contains query
    that works across both PostgreSQL and SQLite test fixtures).
    """
    candidates = (
        db.query(WebhookEndpoint)
        .filter(
            WebhookEndpoint.organization_id == org_id,
            WebhookEndpoint.is_active.is_(True),
        )
        .all()
    )

    matched: List[WebhookEndpoint] = []
    for wh in candidates:
        events = wh.events or []
        if event_type not in events:
            continue

        if event_type == "feedback.category_match":
            filters = wh.category_filters or []
            feedback_tags = feedback.tags or []
            if filters and not (set(filters) & set(feedback_tags)):
                # Webhook has filters and none of them match → skip
                continue

        matched.append(wh)

    return matched


def _build_payload(
    webhook: WebhookEndpoint,
    event_type: str,
    feedback: FeedbackItem,
    changes: Optional[Dict[str, Any]],
    matched_categories: Optional[List[str]],
) -> Dict[str, Any]:
    """Build the fixed JSON payload schema defined in PRD §5."""
    timestamp = datetime.now(timezone.utc).isoformat()

    # Normalise created_at to a string
    created_at = feedback.created_at
    if isinstance(created_at, datetime):
        created_at = created_at.isoformat()

    fb_data: Dict[str, Any] = {
        "id": feedback.id,
        "text": feedback.text,
        "sentiment_label": getattr(feedback, "sentiment_label", None),
        "sentiment_score": getattr(feedback, "sentiment_score", None),
        "tags": feedback.tags or [],
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

    data: Dict[str, Any] = {"feedback": fb_data}

    if event_type == "feedback.status_changed" and changes is not None:
        data["changes"] = changes

    if event_type == "feedback.category_match" and matched_categories is not None:
        data["matched_categories"] = matched_categories

    return {
        "event": event_type,
        "timestamp": timestamp,
        "webhook_id": webhook.id,
        "organization_id": webhook.organization_id,
        "data": data,
    }


def _enqueue_delivery(webhook_id: int, payload: Dict[str, Any]) -> None:
    """
    Schedule the Celery ``deliver_webhook`` task.

    The worker-service task name is ``src.tasks.webhook_delivery.deliver_webhook``.
    We use ``celery_app.send_task`` to avoid a circular import between backend-api
    and the worker (they share the same Celery broker but are separate processes).
    """
    try:
        from src.background import get_celery_app
        app = get_celery_app()
        app.send_task(
            "src.tasks.webhook_delivery.deliver_webhook",
            args=[webhook_id, payload],
        )
    except Exception as exc:
        logger.error(
            "Failed to enqueue deliver_webhook for webhook_id=%s: %s",
            webhook_id,
            exc,
            exc_info=True,
        )
