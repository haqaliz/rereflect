"""
Source event processing tasks.
Handles events from all source types (Slack, webhooks, etc.) using the adapter pattern.
"""

import logging
from datetime import datetime
from typing import Dict, Any, Optional, List

from celery import shared_task

from src.database import get_db_session
from src.adapters import get_adapter

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=30,
)
def process_source_event(
    self,
    source_type: str,
    external_event_id: str,
    event_type: str,
    event_data: Dict[str, Any],
    provider_context: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Process an event from a feedback source.

    This task:
    1. Finds matching FeedbackSource configurations
    2. Uses the appropriate adapter to check triggers
    3. Extracts content using field mapping
    4. Creates FeedbackItem or PendingFeedback based on auto_import setting
    5. Logs the event for deduplication and debugging

    Args:
        source_type: The source type (slack, webhook, discord, etc.)
        external_event_id: The provider's event ID
        event_type: Normalized event type (message, reaction, mention, webhook)
        event_data: Raw event data from the provider
        provider_context: Provider-specific context (team_id, source_id, etc.)

    Returns:
        dict with processing results
    """
    from src.models import (
        FeedbackSource, FeedbackSourceEvent, FeedbackItem,
        PendingFeedback, Integration
    )

    logger.info(f"Processing {source_type} event: {external_event_id}")

    with get_db_session() as db:
        try:
            # Find matching feedback sources
            sources = _find_matching_sources(db, source_type, provider_context)

            if not sources:
                logger.info(f"No matching sources for {source_type} event")
                return {"status": "no_sources", "event_id": external_event_id}

            # Get the adapter for this source type
            try:
                adapter = get_adapter(source_type)
            except ValueError as e:
                logger.error(f"Unsupported source type: {source_type}")
                return {"status": "unsupported_source_type", "error": str(e)}

            results = []

            for source in sources:
                result = _process_event_for_source(
                    db=db,
                    source=source,
                    adapter=adapter,
                    external_event_id=external_event_id,
                    event_type=event_type,
                    event_data=event_data,
                )
                results.append(result)

            db.commit()
            return {"status": "processed", "results": results}

        except Exception as e:
            logger.error(f"Error processing {source_type} event {external_event_id}: {e}")
            db.rollback()
            raise self.retry(exc=e)


def _find_matching_sources(
    db,
    source_type: str,
    provider_context: Dict[str, Any],
) -> List:
    """Find FeedbackSource configurations that match the event."""
    from src.models import FeedbackSource, Integration

    query = db.query(FeedbackSource).filter(
        FeedbackSource.source_type == source_type,
        FeedbackSource.is_active == True,
    )

    # For Slack events, match by team_id via the integration
    if source_type == "slack":
        team_id = provider_context.get("team_id")
        if team_id:
            # Find integrations with this team_id
            integrations = db.query(Integration).filter(
                Integration.type == "slack",
                Integration.is_active == True,
            ).all()

            # Filter to those with matching team_id in config
            matching_integration_ids = []
            for integration in integrations:
                config = integration.config or {}
                if config.get("team_id") == team_id:
                    matching_integration_ids.append(integration.id)

            if matching_integration_ids:
                query = query.filter(
                    FeedbackSource.integration_id.in_(matching_integration_ids)
                )
            else:
                return []

    # For webhook events, match by source_id directly
    elif source_type == "webhook":
        source_id = provider_context.get("source_id")
        if source_id:
            query = query.filter(FeedbackSource.id == source_id)

    # Check channel match for Slack (if event has channel info)
    event_channel = provider_context.get("channel_id")
    if source_type == "slack" and event_channel:
        # Filter by sources configured for this channel
        # (handled in trigger matching, but we could pre-filter here)
        pass

    return query.all()


def _process_event_for_source(
    db,
    source,
    adapter,
    external_event_id: str,
    event_type: str,
    event_data: Dict[str, Any],
) -> Dict[str, Any]:
    """Process a single event against a specific source configuration."""
    from src.models import FeedbackSourceEvent, FeedbackItem, PendingFeedback, Integration

    source_id = source.id
    org_id = source.organization_id

    # Check for channel match (for Slack)
    if source.source_type == "slack":
        config_channel = (source.provider_config or {}).get("channel_id")
        event_channel = event_data.get("channel") or event_data.get("item", {}).get("channel")
        if config_channel and event_channel and config_channel != event_channel:
            return {"source_id": source_id, "status": "channel_mismatch"}

    # Check triggers
    triggers = source.triggers or {}
    trigger_matched = adapter.check_triggers(event_type, event_data, triggers)

    if not trigger_matched:
        # Log as ignored (optional - could skip logging for ignored events)
        _log_event(
            db, source_id, org_id, external_event_id, event_type,
            event_data, "ignored", None
        )
        return {"source_id": source_id, "status": "no_trigger_match"}

    # Get external IDs for deduplication
    adapter_event_id, message_id = adapter.get_external_ids(event_data)

    # Check for duplicates (same source + same message)
    existing = db.query(FeedbackSourceEvent).filter(
        FeedbackSourceEvent.source_id == source_id,
        FeedbackSourceEvent.external_message_id == message_id,
        FeedbackSourceEvent.status.in_(["processed", "pending"]),
    ).first()

    if existing:
        return {"source_id": source_id, "status": "duplicate"}

    # Extract content
    field_mapping = source.field_mapping or {}
    content = adapter.extract_content(event_data, field_mapping)

    # Fetch additional context if needed
    access_token = None
    if source.integration_id:
        integration = db.query(Integration).filter(
            Integration.id == source.integration_id
        ).first()
        if integration:
            access_token = integration.oauth_access_token

    if field_mapping.get("include_context") or field_mapping.get("include_author"):
        context = adapter.fetch_context(event_data, access_token, field_mapping)
        content["metadata"].update(context)

        # If we got original text for reactions, use it
        if "original_text" in context:
            content["text"] = context["original_text"]

    # Validate we have text
    text = content.get("text", "").strip()
    if not text or len(text) < 3:
        _log_event(
            db, source_id, org_id, external_event_id, event_type,
            event_data, "ignored", trigger_matched
        )
        return {"source_id": source_id, "status": "empty_text"}

    # Create FeedbackItem or PendingFeedback
    if source.auto_import:
        # Create feedback directly
        feedback = FeedbackItem(
            organization_id=org_id,
            text=text,
            source=source.source_type,
            source_id=source_id,
            source_external_id=message_id,
            source_metadata=content.get("metadata"),
        )
        db.add(feedback)
        db.flush()  # Get feedback.id

        # Log the event
        event_log = _log_event(
            db, source_id, org_id, external_event_id, event_type,
            event_data, "processed", trigger_matched, feedback_id=feedback.id
        )

        # Update source stats
        source.last_event_at = datetime.utcnow()
        source.events_processed = (source.events_processed or 0) + 1

        # Queue for analysis
        from src.tasks.analysis import analyze_single_feedback
        analyze_single_feedback.delay(feedback.id)

        return {
            "source_id": source_id,
            "status": "feedback_created",
            "feedback_id": feedback.id,
            "trigger": trigger_matched,
        }

    else:
        # Create pending feedback for manual review
        event_log = _log_event(
            db, source_id, org_id, external_event_id, event_type,
            event_data, "pending", trigger_matched
        )

        pending = PendingFeedback(
            source_id=source_id,
            organization_id=org_id,
            event_id=event_log.id,
            text=text,
            source_metadata=content.get("metadata"),
            trigger_type=trigger_matched,
        )
        db.add(pending)
        db.flush()

        # Update event log with pending ID
        event_log.pending_feedback_id = pending.id

        # Update source stats
        source.last_event_at = datetime.utcnow()

        return {
            "source_id": source_id,
            "status": "pending_created",
            "pending_id": pending.id,
            "trigger": trigger_matched,
        }


def _log_event(
    db,
    source_id: int,
    org_id: int,
    external_event_id: str,
    event_type: str,
    event_data: Dict[str, Any],
    status: str,
    trigger_matched: Optional[str],
    feedback_id: Optional[int] = None,
):
    """Create an event log entry."""
    from src.models import FeedbackSourceEvent

    # Get message_id for the log
    from src.adapters import get_adapter
    try:
        # We need to determine source_type from the context
        # For now, try to infer or use a default
        source = db.query(FeedbackSourceEvent.source_id).filter(
            FeedbackSourceEvent.source_id == source_id
        ).first()
    except:
        pass

    # Use a simple approach to get message_id
    message_id = (
        event_data.get("ts") or
        event_data.get("item", {}).get("ts") or
        event_data.get("content_hash")
    )

    event_log = FeedbackSourceEvent(
        source_id=source_id,
        organization_id=org_id,
        external_event_id=external_event_id,
        external_message_id=message_id,
        event_type=event_type,
        status=status,
        trigger_matched=trigger_matched,
        feedback_id=feedback_id,
        event_data=event_data,
        received_at=datetime.utcnow(),
        processed_at=datetime.utcnow() if status in ["processed", "ignored"] else None,
    )

    db.add(event_log)
    db.flush()

    return event_log
