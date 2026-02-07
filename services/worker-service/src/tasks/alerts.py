"""
Alert tasks for urgent feedback notifications.
Supports configurable triggers and customizable message templates.
"""

import logging
import re
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any

from celery import shared_task

from src.database import get_db_session

logger = logging.getLogger(__name__)

# Default message template
DEFAULT_MESSAGE_TEMPLATE = """*{{sentiment_emoji}} New Feedback Alert*

> {{text}}

*Sentiment:* {{sentiment}} ({{sentiment_score}})
{{#pain_point_category}}*Pain Point:* {{pain_point_category}} ({{pain_point_severity}}){{/pain_point_category}}
{{#feature_request_category}}*Feature Request:* {{feature_request_category}} ({{feature_request_priority}}){{/feature_request_category}}
{{#urgent_category}}*Urgent:* {{urgent_category}} - Response: {{urgent_response_time}}{{/urgent_category}}
*Source:* {{source}} | *Created:* {{created_at}}"""


def get_sentiment_emoji(sentiment_label: Optional[str]) -> str:
    """Get emoji for sentiment label."""
    emoji_map = {
        "positive": "😊",
        "neutral": "😐",
        "negative": "😟",
    }
    return emoji_map.get(sentiment_label or "", "📝")


def render_template(template: str, feedback_item: Any) -> str:
    """
    Render a message template with feedback item values.

    Supports:
    - {{variable}} - simple variable replacement
    - {{#variable}}content{{/variable}} - conditional blocks (only shown if variable has value)

    Args:
        template: The message template string
        feedback_item: FeedbackItem object with values

    Returns:
        Rendered message string
    """
    # Build context with all available variables
    context = {
        "text": feedback_item.text[:500] if feedback_item.text else "",
        "sentiment": feedback_item.sentiment_label or "unknown",
        "sentiment_score": f"{feedback_item.sentiment_score:.2f}" if feedback_item.sentiment_score is not None else "N/A",
        "sentiment_emoji": get_sentiment_emoji(feedback_item.sentiment_label),
        "pain_point_category": feedback_item.pain_point_category or "",
        "pain_point_severity": feedback_item.pain_point_severity or "",
        "feature_request_category": feedback_item.feature_request_category or "",
        "feature_request_priority": feedback_item.feature_request_priority or "",
        "urgent_category": feedback_item.urgent_category or "",
        "urgent_response_time": feedback_item.urgent_response_time or "",
        "source": feedback_item.source or "unknown",
        "created_at": feedback_item.created_at.strftime("%Y-%m-%d %H:%M") if feedback_item.created_at else "",
        "feedback_id": str(feedback_item.id),
    }

    result = template

    # Process conditional blocks first: {{#var}}content{{/var}}
    # These blocks are only shown if the variable has a truthy value
    conditional_pattern = r'\{\{#(\w+)\}\}(.*?)\{\{/\1\}\}'
    for match in re.finditer(conditional_pattern, result, re.DOTALL):
        var_name = match.group(1)
        content = match.group(2)
        full_match = match.group(0)

        if context.get(var_name):
            # Replace the conditional block with its content
            # Then replace any variables within the content
            rendered_content = content
            for key, value in context.items():
                rendered_content = rendered_content.replace(f"{{{{{key}}}}}", str(value))
            result = result.replace(full_match, rendered_content)
        else:
            # Remove the entire conditional block
            result = result.replace(full_match, "")

    # Process simple variable replacements: {{var}}
    for key, value in context.items():
        result = result.replace(f"{{{{{key}}}}}", str(value))

    # Clean up extra blank lines
    result = re.sub(r'\n\s*\n\s*\n', '\n\n', result)
    result = result.strip()

    return result


def build_slack_blocks_from_template(
    feedback_items: List[Any],
    message_template: Optional[str],
    alert_type: str
) -> List[Dict]:
    """
    Build Slack Block Kit blocks using a message template.

    Args:
        feedback_items: List of FeedbackItem objects
        message_template: Custom message template or None for default
        alert_type: Type of alert (urgent, negative, all, digest)

    Returns:
        List of Slack Block Kit blocks
    """
    template = message_template or DEFAULT_MESSAGE_TEMPLATE

    # Header based on alert type
    emoji_map = {
        "urgent": "🚨",
        "negative": "😟",
        "all": "📬",
        "daily_digest": "📊",
        "weekly_digest": "📈",
    }
    emoji = emoji_map.get(alert_type, "📬")

    title_map = {
        "urgent": "Urgent Feedback Alert",
        "negative": "Negative Feedback Alert",
        "all": "New Feedback",
        "daily_digest": "Daily Feedback Digest",
        "weekly_digest": "Weekly Feedback Digest",
    }
    title = title_map.get(alert_type, "Feedback Alert")

    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"{emoji} {len(feedback_items)} {title}",
                "emoji": True,
            }
        },
        {"type": "divider"},
    ]

    # Render each feedback item using the template
    for item in feedback_items[:5]:  # Limit to 5 items per message
        rendered = render_template(template, item)
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": rendered
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

    # Add timestamp
    blocks.append({
        "type": "context",
        "elements": [{
            "type": "mrkdwn",
            "text": f"🕐 Sent at {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC"
        }]
    })

    return blocks


def log_alert(
    db,
    integration_id: int,
    feedback_id: Optional[int],
    alert_type: str,
    status: str,
    slack_response: Optional[Dict] = None,
    error_message: Optional[str] = None
):
    """Log an alert to the slack_alert_logs table."""
    from src.models import SlackAlertLog

    log_entry = SlackAlertLog(
        integration_id=integration_id,
        feedback_id=feedback_id,
        alert_type=alert_type,
        status=status,
        slack_response=slack_response,
        error_message=error_message,
        sent_at=datetime.utcnow(),
    )
    db.add(log_entry)


def send_slack_message_webhook(webhook_url: str, blocks: list, text: str) -> Dict:
    """Send a message to Slack via webhook."""
    import httpx

    with httpx.Client(timeout=10) as client:
        response = client.post(
            webhook_url,
            json={"text": text, "blocks": blocks},
        )
        response.raise_for_status()
        return {"success": True, "status_code": response.status_code}


def send_slack_message_oauth(access_token: str, channel_id: str, blocks: list, text: str) -> Dict:
    """Send a message to Slack via OAuth token (Bot API)."""
    import httpx

    with httpx.Client(timeout=10) as client:
        response = client.post(
            "https://slack.com/api/chat.postMessage",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            json={
                "channel": channel_id,
                "text": text,
                "blocks": blocks,
            }
        )
        response.raise_for_status()
        data = response.json()

        if data.get("ok"):
            return {"success": True, "response": data}
        else:
            raise Exception(data.get("error", "Unknown Slack API error"))


@shared_task
def check_urgent_alerts() -> dict:
    """
    Periodic task: Check for urgent feedback and send alerts via dispatch system.
    Runs every 5 minutes via Celery Beat.

    Dispatches to in-app, Slack, and email channels based on user preferences.

    Returns:
        dict with alert results
    """
    from sqlalchemy import inspect
    from src.models import FeedbackItem, Organization
    from src.database import engine
    from src.notification_dispatch import dispatch_alert

    # Check if integrations table exists
    inspector = inspect(engine)
    if "integrations" not in inspector.get_table_names():
        logger.debug("Integrations table not yet created, skipping alert check")
        return {"status": "skipped", "reason": "integrations_table_not_exists"}

    with get_db_session() as db:
        organizations = db.query(Organization).all()

        if not organizations:
            return {"status": "no_organizations", "alerts_sent": 0}

        total_alerts = 0

        for org in organizations:
            try:
                # Find urgent feedback from last 5 minutes (since last check)
                since = datetime.utcnow() - timedelta(minutes=6)

                urgent_items = db.query(FeedbackItem).filter(
                    FeedbackItem.organization_id == org.id,
                    FeedbackItem.is_urgent == True,
                    FeedbackItem.created_at >= since,
                ).all()

                if not urgent_items:
                    continue

                for item in urgent_items:
                    text_preview = (item.text[:100] + "...") if len(item.text) > 100 else item.text
                    dispatch_alert(
                        org_id=org.id,
                        alert_type="urgent_feedback",
                        title=f"Urgent Feedback: \"{text_preview}\"",
                        message=f"Churn risk detected. Source: {item.source or 'unknown'}",
                        link=f"/feedbacks?search={item.id}",
                        metadata={"feedback_id": item.id},
                    )
                    total_alerts += 1

                # Also send legacy Slack Block Kit alerts for integrations that have custom templates
                _send_legacy_slack_alerts(db, org.id, urgent_items)

            except Exception as e:
                logger.error(f"Failed to check urgent alerts for org {org.id}: {e}")

        return {
            "status": "complete",
            "orgs_checked": len(organizations),
            "alerts_dispatched": total_alerts,
        }


def _send_legacy_slack_alerts(db, org_id: int, feedback_items: list) -> None:
    """Send legacy Slack Block Kit alerts for integrations with custom templates."""
    from src.models import Integration

    integrations = db.query(Integration).filter(
        Integration.organization_id == org_id,
        Integration.type == "slack",
        Integration.is_active == True,
        Integration.message_template.isnot(None),
    ).all()

    for integration in integrations:
        try:
            config = integration.config or {}
            integration_type = config.get("integration_type", "webhook")

            can_send = False
            if integration_type == "oauth":
                can_send = bool(integration.oauth_access_token and config.get("channel_id"))
            else:
                can_send = bool(config.get("webhook_url"))

            if can_send:
                send_slack_alert.delay(
                    integration_id=integration.id,
                    feedback_ids=[item.id for item in feedback_items],
                    org_id=org_id,
                    alert_type="urgent",
                    message_template=integration.message_template,
                )
        except Exception as e:
            logger.error(f"Failed to queue legacy alert for integration {integration.id}: {e}")


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=30,
)
def send_slack_alert(
    self,
    integration_id: int,
    feedback_ids: List[int],
    org_id: int,
    alert_type: str = "urgent",
    message_template: Optional[str] = None,
) -> dict:
    """
    Send a Slack alert for feedback items using the configured template.

    Args:
        integration_id: Integration ID for logging
        feedback_ids: List of feedback IDs
        org_id: Organization ID
        alert_type: Type of alert (urgent, negative, all, digest)
        message_template: Custom message template or None for default

    Returns:
        dict with send status
    """
    import httpx

    from src.models import FeedbackItem, Integration

    with get_db_session() as db:
        # Get the integration
        integration = db.query(Integration).filter(
            Integration.id == integration_id,
            Integration.organization_id == org_id,
        ).first()

        if not integration:
            return {"status": "integration_not_found"}

        config = integration.config or {}
        integration_type = config.get("integration_type", "webhook")

        # Validate integration can send
        if integration_type == "oauth":
            if not integration.oauth_access_token:
                return {"status": "no_oauth_token"}
            if not config.get("channel_id"):
                return {"status": "no_channel_id"}
        else:
            if not config.get("webhook_url"):
                return {"status": "no_webhook_url"}

        # Use integration's template if not provided
        template = message_template or integration.message_template

        # Get feedback items
        feedback_items = db.query(FeedbackItem).filter(
            FeedbackItem.id.in_(feedback_ids),
            FeedbackItem.organization_id == org_id,
        ).all()

        if not feedback_items:
            return {"status": "no_items"}

        # Build Slack message using template
        blocks = build_slack_blocks_from_template(feedback_items, template, alert_type)
        fallback_text = f"Rereflect: {len(feedback_items)} {alert_type} feedback alert(s)"

        # Send to Slack via webhook or OAuth
        try:
            if integration_type == "oauth":
                result = send_slack_message_oauth(
                    access_token=integration.oauth_access_token,
                    channel_id=config.get("channel_id"),
                    blocks=blocks,
                    text=fallback_text,
                )
            else:
                result = send_slack_message_webhook(
                    webhook_url=config.get("webhook_url"),
                    blocks=blocks,
                    text=fallback_text,
                )

            # Update integration status
            integration.last_used_at = datetime.utcnow()
            integration.error_count = 0
            integration.last_error = None

            # Log successful alerts
            for item in feedback_items:
                log_alert(
                    db,
                    integration_id=integration.id,
                    feedback_id=item.id,
                    alert_type=alert_type,
                    status="sent",
                    slack_response=result,
                )

            db.commit()
            return {"status": "sent", "items": len(feedback_items)}

        except Exception as e:
            logger.error(f"Slack message failed: {e}")

            # Update error tracking
            integration.error_count = (integration.error_count or 0) + 1
            integration.last_error = str(e)

            # Disable integration after 5 consecutive failures
            if integration.error_count >= 5:
                integration.is_active = False
                logger.warning(f"Disabled integration {integration.id} after 5 failures")

            # Log failed alert
            log_alert(
                db,
                integration_id=integration.id,
                feedback_id=feedback_ids[0] if feedback_ids else None,
                alert_type=alert_type,
                status="failed",
                error_message=str(e),
            )

            db.commit()
            raise self.retry(exc=e)


@shared_task(name="src.tasks.alerts.send_weekly_digests")
def send_weekly_digests() -> dict:
    """
    Periodic task: Send weekly email digests to eligible users.
    Runs every hour at :05 via Celery Beat. Filters users by preferred day+hour.

    Workflow:
    1. Determine current UTC day-of-week and hour
    2. Query users whose weekly_digest_day and weekly_digest_hour match now
    3. For each user's org, count feedback from the past 7 days
    4. Skip if 0 feedback, otherwise calculate stats and send digest
    """
    from sqlalchemy import func, case
    from src.models import Organization, User, FeedbackItem, WeeklyInsight
    from src.email import send_weekly_digest_email

    now = datetime.utcnow()
    current_day = now.weekday()  # 0=Mon, 6=Sun
    current_hour = now.hour

    with get_db_session() as db:
        # Only fetch users whose preferred day+hour match the current run
        users = db.query(User).filter(
            User.weekly_digest_enabled == True,
            User.weekly_digest_day == current_day,
            User.weekly_digest_hour == current_hour,
        ).all()

        if not users:
            return {"status": "no_matching_users", "sent": 0}

        total_sent = 0
        total_skipped = 0
        errors = 0

        end_date = now
        start_date = end_date - timedelta(days=7)
        week_date = f"{start_date.strftime('%b %d')} - {end_date.strftime('%b %d, %Y')}"

        # Group users by org to avoid duplicate stats queries
        org_users: Dict[int, list] = {}
        for user in users:
            org_users.setdefault(user.organization_id, []).append(user)

        for org_id, org_user_list in org_users.items():
            try:
                org = db.query(Organization).filter(Organization.id == org_id).first()
                if not org:
                    continue

                # Count total feedback for this org in the past week
                total_feedback = db.query(FeedbackItem).filter(
                    FeedbackItem.organization_id == org_id,
                    FeedbackItem.created_at >= start_date,
                    FeedbackItem.created_at <= end_date,
                ).count()

                if total_feedback == 0:
                    total_skipped += 1
                    continue

                # Sentiment breakdown
                sentiment_stats = db.query(
                    func.sum(case((FeedbackItem.sentiment_label == "positive", 1), else_=0)).label("positive"),
                    func.sum(case((FeedbackItem.sentiment_label == "neutral", 1), else_=0)).label("neutral"),
                    func.sum(case((FeedbackItem.sentiment_label == "negative", 1), else_=0)).label("negative"),
                ).filter(
                    FeedbackItem.organization_id == org_id,
                    FeedbackItem.created_at >= start_date,
                    FeedbackItem.created_at <= end_date,
                ).first()

                positive = int(sentiment_stats.positive or 0)
                neutral = int(sentiment_stats.neutral or 0)
                negative = int(sentiment_stats.negative or 0)

                positive_pct = round((positive / total_feedback) * 100) if total_feedback > 0 else 0
                neutral_pct = round((neutral / total_feedback) * 100) if total_feedback > 0 else 0
                negative_pct = 100 - positive_pct - neutral_pct

                # Pain points count
                pain_points = db.query(FeedbackItem).filter(
                    FeedbackItem.organization_id == org_id,
                    FeedbackItem.created_at >= start_date,
                    FeedbackItem.created_at <= end_date,
                    FeedbackItem.pain_point_category.isnot(None),
                ).count()

                # Feature requests count
                feature_requests = db.query(FeedbackItem).filter(
                    FeedbackItem.organization_id == org_id,
                    FeedbackItem.created_at >= start_date,
                    FeedbackItem.created_at <= end_date,
                    FeedbackItem.feature_request_category.isnot(None),
                ).count()

                # Urgent count
                urgent_count = db.query(FeedbackItem).filter(
                    FeedbackItem.organization_id == org_id,
                    FeedbackItem.created_at >= start_date,
                    FeedbackItem.created_at <= end_date,
                    FeedbackItem.is_urgent == True,
                ).count()

                # Fetch latest weekly insight for this org
                latest_insight = db.query(WeeklyInsight).filter(
                    WeeklyInsight.organization_id == org_id,
                ).order_by(WeeklyInsight.generated_at.desc()).first()

                # Format insights for email
                insights_html = ""
                if latest_insight and latest_insight.insights:
                    insight_items = latest_insight.insights
                    if isinstance(insight_items, list) and len(insight_items) > 0:
                        lines = []
                        for ins in insight_items[:5]:
                            title = ins.get("title", "")
                            desc = ins.get("description", "")
                            lines.append(f"<li><strong>{title}</strong>: {desc}</li>")
                        insights_html = "<ul>" + "".join(lines) + "</ul>"

                for user in org_user_list:
                    try:
                        success = send_weekly_digest_email(
                            to_email=user.email,
                            organization_name=org.name,
                            week_date=week_date,
                            total_feedback=total_feedback,
                            pain_points=pain_points,
                            feature_requests=feature_requests,
                            positive_percent=positive_pct,
                            neutral_percent=neutral_pct,
                            negative_percent=negative_pct,
                            urgent_count=urgent_count,
                            insights_html=insights_html,
                        )
                        if success:
                            total_sent += 1
                        else:
                            errors += 1
                    except Exception as e:
                        logger.error(f"Failed to send digest to {user.email}: {e}")
                        errors += 1

            except Exception as e:
                logger.error(f"Error processing org {org_id}: {e}")
                errors += 1

        logger.info(f"Weekly digest complete: sent={total_sent}, skipped={total_skipped}, errors={errors}")

        return {
            "status": "complete",
            "sent": total_sent,
            "skipped": total_skipped,
            "errors": errors,
        }


@shared_task(name="src.tasks.alerts.check_volume_spikes")
def check_volume_spikes() -> dict:
    """
    Periodic task: Detect feedback volume spikes per organization.
    Runs every hour via Celery Beat.

    Algorithm:
    - For each org, compare last 24h feedback count to 30-day daily average
    - For each user, check their volume_spike threshold multiplier
    - If exceeded, dispatch alert

    Returns:
        dict with detection results
    """
    from sqlalchemy import func
    from src.models import Organization, FeedbackItem, UserAlertPreference, User
    from src.notification_dispatch import dispatch_alert

    with get_db_session() as db:
        organizations = db.query(Organization).all()

        if not organizations:
            return {"status": "no_organizations", "alerts_sent": 0}

        total_alerts = 0
        now = datetime.utcnow()
        last_24h = now - timedelta(hours=24)
        last_30d = now - timedelta(days=30)

        for org in organizations:
            try:
                # Count last 24h feedback
                recent_count = db.query(func.count(FeedbackItem.id)).filter(
                    FeedbackItem.organization_id == org.id,
                    FeedbackItem.created_at >= last_24h,
                ).scalar() or 0

                if recent_count < 5:
                    continue

                # Calculate 30-day daily average
                total_30d = db.query(func.count(FeedbackItem.id)).filter(
                    FeedbackItem.organization_id == org.id,
                    FeedbackItem.created_at >= last_30d,
                ).scalar() or 0

                daily_avg = total_30d / 30.0 if total_30d > 0 else 0

                if daily_avg < 1:
                    continue

                multiplier = recent_count / daily_avg

                # Default threshold is 2.0x — check if any user in org has a custom threshold
                # Use the lowest threshold among org users for the org-wide check
                users = db.query(User).filter(User.organization_id == org.id).all()
                user_ids = [u.id for u in users]

                prefs = db.query(UserAlertPreference).filter(
                    UserAlertPreference.user_id.in_(user_ids),
                    UserAlertPreference.alert_type == "volume_spike",
                    UserAlertPreference.is_enabled == True,
                ).all()

                if not prefs:
                    # No users have volume spike alerts enabled, use default
                    min_threshold = 2.0
                else:
                    min_threshold = min(p.threshold_value or 2.0 for p in prefs)

                if multiplier < min_threshold:
                    continue

                dispatch_alert(
                    org_id=org.id,
                    alert_type="volume_spike",
                    title=f"Feedback Volume Spike: {multiplier:.1f}x daily average",
                    message=f"{recent_count} items in last 24h vs {daily_avg:.0f} daily average",
                    link="/feedbacks",
                    metadata={
                        "recent_count": recent_count,
                        "daily_average": round(daily_avg, 1),
                        "multiplier": round(multiplier, 1),
                    },
                )
                total_alerts += 1

            except Exception as e:
                logger.error(f"Error checking volume spikes for org {org.id}: {e}")

        return {
            "status": "complete",
            "orgs_checked": len(organizations),
            "alerts_sent": total_alerts,
        }


@shared_task(name="src.tasks.alerts.send_daily_alert_digests")
def send_daily_alert_digests() -> dict:
    """
    Periodic task: Send daily alert digest emails.
    Runs every hour at :00 via Celery Beat. Filters users by preferred hour.

    For each user with daily_digest_enabled whose daily_digest_hour matches:
    - Query notifications created in last 24 hours
    - Check which alert types have channel_email enabled
    - If any alerts exist, send digest email

    Returns:
        dict with send results
    """
    from src.models import User, Notification, UserAlertPreference
    from src.email import _send_with_template
    import os

    TEMPLATE_DAILY_DIGEST = os.getenv("RESEND_TEMPLATE_DAILY_ALERT_DIGEST")
    APP_URL = os.getenv("APP_URL", "http://localhost:3000")

    current_hour = datetime.utcnow().hour

    with get_db_session() as db:
        users = db.query(User).filter(
            User.daily_digest_enabled == True,
            User.daily_digest_hour == current_hour,
        ).all()

        if not users:
            return {"status": "no_users", "sent": 0}

        total_sent = 0
        errors = 0
        now = datetime.utcnow()
        last_24h = now - timedelta(hours=24)

        for user in users:
            try:
                # Get alert types where user has email enabled
                email_prefs = db.query(UserAlertPreference).filter(
                    UserAlertPreference.user_id == user.id,
                    UserAlertPreference.is_enabled == True,
                    UserAlertPreference.channel_email == True,
                ).all()

                if not email_prefs:
                    continue

                email_alert_types = [p.alert_type for p in email_prefs]

                # Get notifications from last 24h matching those types
                notifications = db.query(Notification).filter(
                    Notification.user_id == user.id,
                    Notification.type.in_(email_alert_types),
                    Notification.created_at >= last_24h,
                ).order_by(Notification.created_at.desc()).all()

                if not notifications:
                    continue

                # Build HTML summary of alerts
                alerts_html_lines = []
                for n in notifications[:20]:
                    link = f"{APP_URL}{n.link}" if n.link else APP_URL
                    alerts_html_lines.append(
                        f'<li><strong>{n.title}</strong><br/>'
                        f'<span style="color:#666">{n.message or ""}</span><br/>'
                        f'<a href="{link}">View details</a></li>'
                    )
                alerts_html = "<ul>" + "".join(alerts_html_lines) + "</ul>"

                # Get org name
                from src.models import Organization
                org = db.query(Organization).filter(Organization.id == user.organization_id).first()
                org_name = org.name if org else "Your Organization"

                success = _send_with_template(
                    to=user.email,
                    template_id=TEMPLATE_DAILY_DIGEST,
                    variables={
                        "ORGANIZATION_NAME": org_name,
                        "DATE": now.strftime("%B %d, %Y"),
                        "ALERT_COUNT": str(len(notifications)),
                        "ALERTS_HTML": alerts_html,
                        "DASHBOARD_URL": f"{APP_URL}/dashboard",
                        "UNSUBSCRIBE_URL": f"{APP_URL}/settings/notifications",
                    },
                )

                if success:
                    total_sent += 1
                else:
                    errors += 1

            except Exception as e:
                logger.error(f"Failed to send daily digest to {user.email}: {e}")
                errors += 1

        logger.info(f"Daily digest complete: sent={total_sent}, errors={errors}")

        return {
            "status": "complete",
            "sent": total_sent,
            "errors": errors,
        }


@shared_task(name="src.tasks.alerts.cleanup_expired_notifications")
def cleanup_expired_notifications() -> dict:
    """
    Periodic task: Delete expired notifications.
    Runs daily at 3 AM UTC via Celery Beat.

    Returns:
        dict with cleanup results
    """
    from src.models import Notification

    with get_db_session() as db:
        now = datetime.utcnow()

        deleted = db.query(Notification).filter(
            Notification.expires_at.isnot(None),
            Notification.expires_at < now,
        ).delete(synchronize_session=False)

        db.commit()

        logger.info(f"Cleaned up {deleted} expired notifications")

        return {
            "status": "complete",
            "deleted": deleted,
        }
