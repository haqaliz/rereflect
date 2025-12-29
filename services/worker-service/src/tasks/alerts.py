"""
Alert tasks for urgent feedback notifications.
"""

import logging
from datetime import datetime
from typing import List, Optional

from celery import shared_task

from src.database import get_db_session

logger = logging.getLogger(__name__)


@shared_task
def check_urgent_alerts() -> dict:
    """
    Periodic task: Check for urgent feedback and send alerts.
    Runs every 5 minutes via Celery Beat.

    Returns:
        dict with alert results
    """
    from sqlalchemy import inspect
    from src.models import FeedbackItem
    from src.database import engine

    # Check if integrations table exists (feature not yet implemented)
    inspector = inspect(engine)
    if "integrations" not in inspector.get_table_names():
        logger.debug("Integrations table not yet created, skipping alert check")
        return {"status": "skipped", "reason": "integrations_table_not_exists"}

    from src.models import Integration

    with get_db_session() as db:
        # Get all active Slack integrations
        integrations = db.query(Integration).filter(
            Integration.type == "slack",
            Integration.is_active == True,
        ).all()

        if not integrations:
            return {"status": "no_integrations", "alerts_sent": 0}

        total_alerts = 0

        for integration in integrations:
            # Get urgent feedback not yet alerted
            urgent_items = db.query(FeedbackItem).filter(
                FeedbackItem.organization_id == integration.organization_id,
                FeedbackItem.is_urgent == True,
            ).all()

            if not urgent_items:
                continue

            # Send Slack alert
            try:
                send_slack_alert.delay(
                    webhook_url=integration.config.get("webhook_url"),
                    feedback_ids=[item.id for item in urgent_items],
                    org_id=integration.organization_id,
                )

                total_alerts += len(urgent_items)

            except Exception as e:
                logger.error(f"Failed to queue alert for org {integration.organization_id}: {e}")

        db.commit()

        return {
            "status": "complete",
            "integrations_checked": len(integrations),
            "alerts_sent": total_alerts,
        }


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=30,
)
def send_slack_alert(
    self,
    webhook_url: str,
    feedback_ids: List[int],
    org_id: int,
) -> dict:
    """
    Send a Slack alert for urgent feedback.

    Args:
        webhook_url: Slack webhook URL
        feedback_ids: List of urgent feedback IDs
        org_id: Organization ID

    Returns:
        dict with send status
    """
    import httpx

    from src.models import FeedbackItem

    with get_db_session() as db:
        feedback_items = db.query(FeedbackItem).filter(
            FeedbackItem.id.in_(feedback_ids),
            FeedbackItem.organization_id == org_id,
        ).all()

        if not feedback_items:
            return {"status": "no_items"}

        # Build Slack message
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"🚨 {len(feedback_items)} Urgent Feedback Alert(s)",
                    "emoji": True,
                }
            },
            {"type": "divider"},
        ]

        for item in feedback_items[:5]:  # Limit to 5 items per message
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Category:* {item.urgent_category or 'Unknown'}\n"
                            f"*Severity:* {item.pain_point_severity or 'Unknown'}\n"
                            f"*Text:* {item.text[:200]}{'...' if len(item.text) > 200 else ''}"
                }
            })

        if len(feedback_items) > 5:
            blocks.append({
                "type": "context",
                "elements": [{
                    "type": "mrkdwn",
                    "text": f"_...and {len(feedback_items) - 5} more items_"
                }]
            })

        # Send to Slack
        try:
            with httpx.Client(timeout=10) as client:
                response = client.post(
                    webhook_url,
                    json={"blocks": blocks},
                )
                response.raise_for_status()

            return {"status": "sent", "items": len(feedback_items)}

        except httpx.HTTPError as e:
            logger.error(f"Slack webhook failed: {e}")
            raise self.retry(exc=e)


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def send_email_digest(
    self,
    org_id: int,
    recipient_emails: List[str],
    digest_type: str = "daily",
) -> dict:
    """
    Send email digest of feedback summary.

    Args:
        org_id: Organization ID
        recipient_emails: List of email addresses
        digest_type: "daily" or "weekly"

    Returns:
        dict with send status
    """
    # TODO: Implement email sending (SendGrid/AWS SES)
    # This is a placeholder for Month 3
    logger.info(f"Email digest task for org {org_id}: {digest_type}")

    return {
        "status": "not_implemented",
        "org_id": org_id,
        "digest_type": digest_type,
    }
