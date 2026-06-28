"""
Inbound product-usage event receiver.

POST /api/v1/webhooks/usage

Accepts a Segment-compatible normalized batch of usage events from self-hosted
operators.  Authentication uses the existing API-key scheme (ingest scope).
Writes accepted events to the ``usage_events`` raw-log table and enqueues them
for rollup/scoring by the ``usage_metrics`` Celery task.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import sqlalchemy.exc

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from src.api.public.auth import ApiKeyAuth, require_scope, verify_api_key
from src.api.schemas.usage import (
    UsageBatchIn,
    UsageIngestResponse,
    guard_properties,
    resolve_email,
)
from src.database.session import get_db
from src.models.usage_event import UsageEvent

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/webhooks/usage",
    tags=["usage-webhooks"],
)

_TASK_NAME = "src.tasks.usage_metrics.process_usage_event"


@router.post(
    "",
    response_model=UsageIngestResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_scope("ingest"))],
)
def ingest_usage_events(
    body: UsageBatchIn,
    auth: ApiKeyAuth = Depends(verify_api_key),
    db: Session = Depends(get_db),
) -> UsageIngestResponse:
    """
    Receive a batch of usage events (max 1000) and enqueue them for processing.

    Auth: API key with the ``ingest`` scope.  The organization is taken from
    the resolved API key — the request body MUST NOT be trusted for org identity.

    Returns 202 with accepted/skipped counts regardless of partial failures.
    """
    org_id: int = auth.organization_id
    events = body.events

    # AC3: Reject oversized batch before touching the DB
    if len(events) > 1000:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Batch exceeds the 1000-event limit; nothing written.",
        )

    accepted = 0
    skipped = 0
    skipped_reasons: dict[str, int] = {}

    received_at = datetime.now(timezone.utc)

    for event in events:
        # ── Email resolution ──────────────────────────────────────────────────
        customer_email = resolve_email(event)
        if customer_email is None:
            skipped += 1
            skipped_reasons["no_email"] = skipped_reasons.get("no_email", 0) + 1
            continue

        # ── messageId required ────────────────────────────────────────────────
        if not event.messageId:
            skipped += 1
            skipped_reasons["no_message_id"] = (
                skipped_reasons.get("no_message_id", 0) + 1
            )
            continue

        external_event_id = event.messageId

        # ── Quick dedup check ─────────────────────────────────────────────────
        exists = (
            db.query(UsageEvent.id)
            .filter(
                UsageEvent.organization_id == org_id,
                UsageEvent.external_event_id == external_event_id,
            )
            .first()
        )
        if exists is not None:
            skipped += 1
            skipped_reasons["duplicate"] = skipped_reasons.get("duplicate", 0) + 1
            continue

        # ── Timestamp handling ────────────────────────────────────────────────
        occurred_at: datetime | None = None
        if event.timestamp is not None:
            occurred_at = event.timestamp
            # Ensure timezone-aware for ISO serialization
            if occurred_at.tzinfo is None:
                occurred_at = occurred_at.replace(tzinfo=timezone.utc)

        occurred_at_iso: str = (
            occurred_at.isoformat() if occurred_at is not None
            else received_at.isoformat()
        )

        # ── Properties size guard ─────────────────────────────────────────────
        props, _truncated = guard_properties(event.properties)

        # ── Determine event name ──────────────────────────────────────────────
        # Prefer event.event (track), fall back to event.name, else None
        event_name: str | None = event.event or event.name

        # ── Persist raw event ─────────────────────────────────────────────────
        row = UsageEvent(
            organization_id=org_id,
            customer_email=customer_email,
            event_type=event.type,
            event_name=event_name,
            external_event_id=external_event_id,
            occurred_at=occurred_at,
            received_at=received_at,
            properties=props,
        )
        # Isolate each insert in a SAVEPOINT so that a race-condition
        # UniqueViolation on this event does not roll back previously
        # accepted rows in the same batch.
        sp = db.begin_nested()
        db.add(row)
        try:
            sp.commit()  # flushes the row within the savepoint
        except sqlalchemy.exc.IntegrityError:
            sp.rollback()  # only THIS event is undone; prior accepted rows survive
            skipped += 1
            skipped_reasons["duplicate"] = skipped_reasons.get("duplicate", 0) + 1
            continue

        # ── Enqueue Celery task ───────────────────────────────────────────────
        try:
            from src.background.celery_client import get_celery_app

            get_celery_app().send_task(
                _TASK_NAME,
                args=[
                    org_id,
                    customer_email,
                    event.type,
                    event_name,
                    occurred_at_iso,
                    external_event_id,
                    props,
                ],
            )
        except Exception as exc:
            logger.warning(
                "Failed to enqueue usage event %s for org %s: %s",
                external_event_id,
                org_id,
                exc,
            )
            # Still count as accepted — the row is persisted; worker can retry

        accepted += 1

    db.commit()

    return UsageIngestResponse(
        accepted=accepted,
        skipped=skipped,
        skipped_reasons=skipped_reasons,
    )
