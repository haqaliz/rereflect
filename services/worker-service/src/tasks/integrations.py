"""
Integration sync tasks for pulling data from 3rd party APIs.
"""

import logging
from datetime import datetime
from typing import Optional

from celery import shared_task

from src.database import get_db_session

logger = logging.getLogger(__name__)


@shared_task
def sync_all_integrations() -> dict:
    """
    Periodic task: Sync all active integrations.
    Runs daily at 2 AM via Celery Beat.

    Returns:
        dict with sync results
    """
    from src.models import Integration

    with get_db_session() as db:
        integrations = db.query(Integration).filter(
            Integration.is_active == True,
            Integration.type.in_(["intercom", "zendesk"]),
        ).all()

        if not integrations:
            return {"status": "no_integrations", "synced": 0}

        # Queue individual sync tasks
        for integration in integrations:
            sync_integration.delay(integration.id)

        return {
            "status": "queued",
            "integrations": len(integrations),
        }


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=300,  # 5 minutes
)
def sync_integration(self, integration_id: int) -> dict:
    """
    Sync a single integration.

    Args:
        integration_id: Integration ID to sync

    Returns:
        dict with sync results
    """
    from src.models import Integration, FeedbackItem
    from src.tasks.analysis import analyze_feedback_batch

    with get_db_session() as db:
        integration = db.query(Integration).filter(
            Integration.id == integration_id
        ).first()

        if not integration:
            return {"status": "not_found", "integration_id": integration_id}

        if not integration.is_active:
            return {"status": "inactive", "integration_id": integration_id}

        try:
            # Get connector based on type
            connector = _get_connector(integration.type, integration.config)

            if connector is None:
                return {"status": "unsupported_type", "type": integration.type}

            # Fetch new items since last sync
            since = integration.last_synced_at
            new_items = connector.fetch_new_items(since=since)

            if not new_items:
                integration.last_synced_at = datetime.utcnow()
                db.commit()
                return {"status": "no_new_items", "integration_id": integration_id}

            # Create feedback items
            feedback_ids = []
            for item in new_items:
                feedback = FeedbackItem(
                    organization_id=integration.organization_id,
                    text=item["text"],
                    source=integration.type,
                    source_id=item.get("id"),
                    created_at=item.get("created_at", datetime.utcnow()),
                )
                db.add(feedback)
                db.flush()  # Get ID
                feedback_ids.append(feedback.id)

            # Update last synced timestamp
            integration.last_synced_at = datetime.utcnow()
            db.commit()

            # Invalidate dashboard/analytics cache for this org
            from src.cache import cache_invalidate
            cache_invalidate(f"dashboard:{integration.organization_id}:*")
            cache_invalidate(f"analytics:{integration.organization_id}:*")

            # Queue analysis for new items
            if feedback_ids:
                analyze_feedback_batch.delay(
                    org_id=integration.organization_id,
                    feedback_ids=feedback_ids,
                )

            logger.info(f"Synced {len(new_items)} items from {integration.type}")

            return {
                "status": "success",
                "integration_id": integration_id,
                "items_synced": len(new_items),
            }

        except Exception as e:
            logger.error(f"Integration sync failed for {integration_id}: {e}")
            raise self.retry(exc=e)


def _get_connector(integration_type: str, config: dict):
    """
    Get the appropriate connector for an integration type.

    Args:
        integration_type: Type of integration (intercom, zendesk, etc.)
        config: Integration configuration

    Returns:
        Connector instance or None if unsupported
    """
    # TODO: Implement actual connectors in Month 2
    # These are placeholder implementations

    if integration_type == "intercom":
        return IntercomConnector(config)
    elif integration_type == "zendesk":
        return ZendeskConnector(config)
    else:
        return None


class BaseConnector:
    """Base class for integration connectors."""

    def __init__(self, config: dict):
        self.config = config

    def fetch_new_items(self, since: Optional[datetime] = None) -> list:
        """Fetch new items since the given timestamp."""
        raise NotImplementedError


class IntercomConnector(BaseConnector):
    """Intercom API connector (placeholder)."""

    def fetch_new_items(self, since: Optional[datetime] = None) -> list:
        """
        Fetch conversations from Intercom.
        TODO: Implement actual Intercom API integration in Month 2.
        """
        # Placeholder - returns empty list
        logger.info("IntercomConnector.fetch_new_items called (not implemented)")
        return []


class ZendeskConnector(BaseConnector):
    """Zendesk API connector (placeholder)."""

    def fetch_new_items(self, since: Optional[datetime] = None) -> list:
        """
        Fetch tickets from Zendesk.
        TODO: Implement actual Zendesk API integration in Month 2.
        """
        # Placeholder - returns empty list
        logger.info("ZendeskConnector.fetch_new_items called (not implemented)")
        return []
