"""
Notification dispatch service.
Routes alerts to the correct channels (in-app, Slack, email digest)
based on per-user alert preferences.
"""

import logging
import os
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from urllib.parse import quote

from src.database import get_db_session

logger = logging.getLogger(__name__)

# Redis dedup key template
HEALTH_ALERT_COOLDOWN_KEY = "health_alert_cooldown:{org_id}:{customer_email}"
HEALTH_ALERT_COOLDOWN_TTL = 86400  # 24 hours

# Risk level ordering: higher = worse
RISK_LEVEL_ORDER = {"healthy": 0, "moderate": 1, "at_risk": 2, "critical": 3}


def _get_redis_client():
    """Get Redis client for alert deduplication (DB 2 = application cache)."""
    import redis
    from src.config import get_redis_url
    return redis.from_url(get_redis_url(2))


def _check_org_plan(org_id: int, db) -> bool:
    """Check if org has customer_health_scores feature (Pro+)."""
    from src.models import Organization

    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        return False

    plan_features = {
        "free": [],
        "pro": ["customer_health_scores"],
        "business": ["customer_health_scores"],
        "enterprise": ["customer_health_scores"],
    }
    features = plan_features.get(org.plan, [])
    return "customer_health_scores" in features


def _queue_llm_analysis(org_id: int, customer_email: str) -> None:
    """Queue generate_churn_insights Celery task for a specific customer."""
    try:
        from src.tasks.insights import generate_churn_insights_for_customer
        generate_churn_insights_for_customer.delay(org_id, customer_email)
    except Exception as e:
        logger.warning(f"Failed to queue LLM analysis for {customer_email}: {e}")


def _dispatch_slack_health_alert(
    org_id: int,
    blocks: List[Dict],
    text: str,
) -> None:
    """Send Slack health alert using org's active Slack integrations."""
    from src.models import Integration
    from src.tasks.alerts import send_slack_message_oauth, send_slack_message_webhook

    with get_db_session() as db:
        integrations = db.query(Integration).filter(
            Integration.organization_id == org_id,
            Integration.type == "slack",
            Integration.is_active == True,
        ).all()

        for integration in integrations:
            try:
                config = integration.config or {}
                integration_type = config.get("integration_type", "webhook")
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
            except Exception as e:
                logger.error(f"Failed to send Slack health alert for integration {integration.id}: {e}")

        db.commit()


def build_health_alert_blocks(
    customer_email: str,
    customer_name: Optional[str],
    old_score: int,
    new_score: int,
    old_risk_level: str,
    new_risk_level: str,
    components: Dict[str, int],
    is_recovery: bool = False,
) -> List[Dict]:
    """Build Slack Block Kit blocks for a health drop or recovery alert."""
    app_url = os.getenv("APP_URL", "https://app.rereflect.com")
    encoded_email = quote(customer_email, safe="")
    customer_url = f"{app_url}/customers/{encoded_email}"

    score_delta = new_score - old_score
    delta_str = f"+{score_delta}" if score_delta >= 0 else str(score_delta)

    if is_recovery:
        header_text = "✅ Customer Health Improved"
        risk_emoji = "🟢"
    else:
        header_text = "⚠️ Customer Health Drop"
        risk_emoji = "🔴" if new_risk_level in ("at_risk", "critical") else "🟡"

    # Top risk drivers: components with highest (worst = lowest score) values
    # Lower component score = worse. Sort ascending.
    sorted_components = sorted(components.items(), key=lambda x: x[0])
    # For risk drivers: highest component score means LOWEST risk (inverted)
    # Risk drivers = components with lowest scores (most problematic)
    risk_drivers = sorted(components.items(), key=lambda x: x[1])
    top_drivers = risk_drivers[:2]
    drivers_text = ", ".join(
        f"{k.replace('_', ' ').title()} ({v})" for k, v in top_drivers
    )

    display_name = customer_name or customer_email

    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": header_text,
                "emoji": True,
            },
        },
        {
            "type": "section",
            "fields": [
                {
                    "type": "mrkdwn",
                    "text": f"*Customer:*\n{display_name} ({customer_email})",
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Risk Level:*\n{risk_emoji} {new_risk_level}",
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Score Change:*\n{old_score} → {new_score} ({delta_str})",
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Top Risk Drivers:*\n{drivers_text}",
                },
            ],
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "View Customer Profile",
                    },
                    "url": customer_url,
                    "style": "primary",
                }
            ],
        },
    ]

    return blocks


def dispatch_health_drop_alert(
    org_id: int,
    customer_email: str,
    customer_name: Optional[str],
    old_score: int,
    new_score: int,
    old_risk_level: str,
    new_risk_level: str,
    components: Dict[str, int],
    is_recovery: bool = False,
    db=None,
) -> Dict[str, int]:
    """
    Dispatch a customer health drop (or recovery) alert to org users.

    Flow:
    1. Check plan gate (Pro+ required for customer_health_scores)
    2. Check Redis dedup (skip if cooldown active, unless risk level changed or score dropped further)
    3. Fetch user preferences for 'customer_health_drop' alert type
    4. For each enabled user: create in-app notification, dispatch Slack, flag email
    5. Set Redis cooldown key
    6. Auto-trigger LLM analysis if stale (drop alerts only)

    Returns dict with counts: {inapp, slack, email}
    """
    from src.models import User, UserAlertPreference, CustomerHealth

    counts = {"inapp": 0, "slack": 0, "email": 0}

    # Determine if risk level changed (for dedup bypass)
    old_order = RISK_LEVEL_ORDER.get(old_risk_level, 0)
    new_order = RISK_LEVEL_ORDER.get(new_risk_level, 0)
    is_risk_change = new_order != old_order

    def _do_dispatch(session):
        nonlocal counts

        # 1. Plan gate check
        if not _check_org_plan(org_id, session):
            return

        # 2. Redis dedup check (skip for risk level changes and recovery)
        redis_client = _get_redis_client()
        cooldown_key = HEALTH_ALERT_COOLDOWN_KEY.format(
            org_id=org_id, customer_email=customer_email
        )

        if not is_risk_change and not is_recovery:
            try:
                last_alerted_raw = redis_client.get(cooldown_key)
                if last_alerted_raw is not None:
                    last_alerted_score = int(last_alerted_raw)
                    if new_score >= last_alerted_score:
                        # Score hasn't dropped further — skip
                        return
            except Exception as e:
                logger.warning(f"Redis dedup check failed for {customer_email}: {e}")
                # Graceful fallback: proceed with dispatch

        # 3. Fetch org users and their preferences
        users = session.query(User).filter(User.organization_id == org_id).all()
        if not users:
            return

        user_ids = [u.id for u in users]
        prefs = session.query(UserAlertPreference).filter(
            UserAlertPreference.user_id.in_(user_ids),
            UserAlertPreference.alert_type == "customer_health_drop",
        ).all()
        pref_by_user = {p.user_id: p for p in prefs}

        customer_link = f"/customers/{quote(customer_email, safe='')}"

        if is_recovery:
            title = f"Customer health improved: {customer_email}"
            message = (
                f"Health score recovered from {old_score} to {new_score} "
                f"({old_risk_level} → {new_risk_level})."
            )
        else:
            # Compute top risk drivers (lowest component scores = most problematic)
            sorted_drivers = sorted(components.items(), key=lambda x: x[1])
            top_drivers = [k for k, _ in sorted_drivers[:2]]
            drivers_text = ", ".join(d.replace("_", " ").title() for d in top_drivers)
            title = f"Customer health drop: {customer_email}"
            message = (
                f"Health score dropped from {old_score} to {new_score} "
                f"({old_risk_level} → {new_risk_level}). "
                f"Top risk drivers: {drivers_text}."
            )

        notification_metadata = {
            "customer_email": customer_email,
            "customer_name": customer_name,
            "old_score": old_score,
            "new_score": new_score,
            "old_risk_level": old_risk_level,
            "new_risk_level": new_risk_level,
            "is_recovery": is_recovery,
            "components": components,
        }

        any_slack = False
        for user in users:
            pref = pref_by_user.get(user.id)

            is_enabled = pref.is_enabled if pref else True
            if not is_enabled:
                continue

            channel_inapp = pref.channel_inapp if pref else True
            channel_slack = pref.channel_slack if pref else True
            channel_email = pref.channel_email if pref else False

            if channel_inapp:
                retention_days = pref.retention_days if pref else 30
                create_notification(
                    db=session,
                    user_id=user.id,
                    org_id=org_id,
                    alert_type="customer_health_drop",
                    title=title,
                    message=message,
                    link=customer_link,
                    metadata=notification_metadata,
                )
                counts["inapp"] += 1

            if channel_slack:
                counts["slack"] += 1
                any_slack = True

            if channel_email:
                counts["email"] += 1

        session.commit()

        # 4. Send Slack alert once per org
        if any_slack:
            blocks = build_health_alert_blocks(
                customer_email=customer_email,
                customer_name=customer_name,
                old_score=old_score,
                new_score=new_score,
                old_risk_level=old_risk_level,
                new_risk_level=new_risk_level,
                components=components,
                is_recovery=is_recovery,
            )
            fallback_text = title
            _dispatch_slack_health_alert(org_id, blocks, fallback_text)

        # 5. Set Redis cooldown key
        if not is_recovery:
            try:
                redis_client.setex(cooldown_key, HEALTH_ALERT_COOLDOWN_TTL, str(new_score))
            except Exception as e:
                logger.warning(f"Failed to set Redis cooldown for {customer_email}: {e}")

        # 6. Auto-trigger LLM analysis for drop alerts
        if not is_recovery:
            try:
                ch = session.query(CustomerHealth).filter(
                    CustomerHealth.organization_id == org_id,
                    CustomerHealth.customer_email == customer_email,
                ).first()
                if ch is not None:
                    needs_llm = (
                        ch.llm_analyzed_at is None
                        or (datetime.utcnow() - ch.llm_analyzed_at) > timedelta(hours=24)
                    )
                    if needs_llm:
                        _queue_llm_analysis(org_id=org_id, customer_email=customer_email)
            except Exception as e:
                logger.warning(f"Failed to check LLM analysis status for {customer_email}: {e}")

    if db is not None:
        _do_dispatch(db)
    else:
        with get_db_session() as session:
            _do_dispatch(session)

    return counts


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
