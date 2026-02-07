"""
Notification dispatch service.
Routes alerts to the correct channels (in-app, Slack, email digest)
based on per-user alert preferences.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from src.database import get_db_session

logger = logging.getLogger(__name__)


def create_notification(
    db,
    user_id: int,
    org_id: int,
    alert_type: str,
    title: str,
    message: str,
    link: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """Create a single in-app notification with correct expiry based on per-type retention setting."""
    from src.models import Notification, User, UserAlertPreference

    # Look up per-type retention first, fall back to user-level default
    pref = db.query(UserAlertPreference).filter(
        UserAlertPreference.user_id == user_id,
        UserAlertPreference.alert_type == alert_type,
    ).first()

    if pref and pref.retention_days:
        retention_days = pref.retention_days
    else:
        user = db.query(User).filter(User.id == user_id).first()
        retention_days = user.notification_retention_days if user else 30

    notification = Notification(
        user_id=user_id,
        organization_id=org_id,
        type=alert_type,
        title=title,
        message=message,
        link=link,
        metadata_=metadata,
        created_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(days=retention_days),
    )
    db.add(notification)


def dispatch_alert(
    org_id: int,
    alert_type: str,
    title: str,
    message: str,
    link: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, int]:
    """
    Dispatch an alert to all users in an organization based on their preferences.

    For each user:
    - If alert type is enabled and channel_inapp is on → create Notification record
    - If alert type is enabled and channel_slack is on → queue Slack alert
    - If alert type is enabled and channel_email is on → flag for daily digest (not sent immediately)

    Args:
        org_id: Organization ID
        alert_type: One of "urgent_feedback", "sentiment_spike", "churn_risk", "volume_spike"
        title: Notification title
        message: Notification message body
        link: Optional link to relevant page (e.g., "/feedbacks/123")
        metadata: Optional metadata dict

    Returns:
        dict with counts: {inapp, slack, email}
    """
    from src.models import User, UserAlertPreference

    counts = {"inapp": 0, "slack": 0, "email": 0}

    with get_db_session() as db:
        users = db.query(User).filter(User.organization_id == org_id).all()

        if not users:
            return counts

        user_ids = [u.id for u in users]

        # Fetch all preferences for this alert type in one query
        prefs = db.query(UserAlertPreference).filter(
            UserAlertPreference.user_id.in_(user_ids),
            UserAlertPreference.alert_type == alert_type,
        ).all()

        pref_by_user = {p.user_id: p for p in prefs}

        for user in users:
            pref = pref_by_user.get(user.id)

            # If no preference exists, use defaults (enabled, inapp+slack on, email off)
            is_enabled = pref.is_enabled if pref else True
            if not is_enabled:
                continue

            channel_inapp = pref.channel_inapp if pref else True
            channel_slack = pref.channel_slack if pref else True
            channel_email = pref.channel_email if pref else False

            # In-app notification
            if channel_inapp:
                create_notification(
                    db=db,
                    user_id=user.id,
                    org_id=org_id,
                    alert_type=alert_type,
                    title=title,
                    message=message,
                    link=link,
                    metadata=metadata,
                )
                counts["inapp"] += 1

            # Slack alert (queued per-org, not per-user)
            if channel_slack:
                counts["slack"] += 1

            # Email (flagged for daily digest, not sent immediately)
            if channel_email:
                counts["email"] += 1

        db.commit()

        # Send Slack alert once per org if any user wants it
        if counts["slack"] > 0:
            _dispatch_slack_alert(org_id, alert_type, title, message, link)

    return counts


def _dispatch_slack_alert(
    org_id: int,
    alert_type: str,
    title: str,
    message: str,
    link: Optional[str] = None,
) -> None:
    """Send a Slack alert for the organization using available integrations."""
    from src.models import Integration
    from src.tasks.alerts import send_slack_message_oauth, send_slack_message_webhook
    import os

    app_url = os.getenv("APP_URL", "http://localhost:3000")

    with get_db_session() as db:
        integrations = db.query(Integration).filter(
            Integration.organization_id == org_id,
            Integration.type == "slack",
            Integration.is_active == True,
        ).all()

        if not integrations:
            return

        # Build simple text message with link
        emoji_map = {
            "urgent_feedback": "\U0001f6a8",
            "sentiment_spike": "\U0001f4c9",
            "churn_risk": "\u26a0\ufe0f",
            "volume_spike": "\U0001f4ca",
        }
        emoji = emoji_map.get(alert_type, "\U0001f514")
        full_link = f"{app_url}{link}" if link else app_url

        text = f"{emoji} *{title}*\n{message}\nView: {full_link}"

        blocks = [
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": text},
            }
        ]

        for integration in integrations:
            try:
                config = integration.config or {}
                integration_type = config.get("integration_type", "webhook")

                # Determine channel: use alert_channel_id override if set
                channel_id = integration.alert_channel_id or config.get("channel_id")

                if integration_type == "oauth" and integration.oauth_access_token and channel_id:
                    send_slack_message_oauth(
                        access_token=integration.oauth_access_token,
                        channel_id=channel_id,
                        blocks=blocks,
                        text=text,
                    )
                elif config.get("webhook_url"):
                    send_slack_message_webhook(
                        webhook_url=config["webhook_url"],
                        blocks=blocks,
                        text=text,
                    )

                integration.last_used_at = datetime.utcnow()
                integration.error_count = 0
                integration.last_error = None

            except Exception as e:
                logger.error(f"Failed to send Slack alert for integration {integration.id}: {e}")
                integration.error_count = (integration.error_count or 0) + 1
                integration.last_error = str(e)

        db.commit()
