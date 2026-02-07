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
    Periodic task: Check for urgent feedback and send alerts.
    Runs every 5 minutes via Celery Beat.

    Returns:
        dict with alert results
    """
    from sqlalchemy import inspect
    from src.models import FeedbackItem
    from src.database import engine

    # Check if integrations table exists
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
            triggers = integration.triggers or ["urgent"]

            # Build query based on triggers
            query = db.query(FeedbackItem).filter(
                FeedbackItem.organization_id == integration.organization_id,
            )

            # Filter based on trigger type
            if "all" in triggers:
                pass  # No additional filter
            elif "urgent" in triggers and "negative" in triggers:
                query = query.filter(
                    (FeedbackItem.is_urgent == True) |
                    (FeedbackItem.sentiment_label == "negative")
                )
            elif "urgent" in triggers:
                query = query.filter(FeedbackItem.is_urgent == True)
            elif "negative" in triggers:
                query = query.filter(FeedbackItem.sentiment_label == "negative")
            else:
                continue

            feedback_items = query.limit(20).all()

            if not feedback_items:
                continue

            # Determine alert type
            if "urgent" in triggers and any(item.is_urgent for item in feedback_items):
                alert_type = "urgent"
            elif "negative" in triggers:
                alert_type = "negative"
            else:
                alert_type = "all"

            # Send Slack alert
            try:
                config = integration.config or {}
                integration_type = config.get("integration_type", "webhook")

                # Check if integration can send messages
                can_send = False
                if integration_type == "oauth":
                    can_send = bool(integration.oauth_access_token and config.get("channel_id"))
                else:
                    can_send = bool(config.get("webhook_url"))

                if can_send:
                    send_slack_alert.delay(
                        integration_id=integration.id,
                        feedback_ids=[item.id for item in feedback_items],
                        org_id=integration.organization_id,
                        alert_type=alert_type,
                        message_template=integration.message_template,
                    )
                    total_alerts += len(feedback_items)

            except Exception as e:
                logger.error(f"Failed to queue alert for org {integration.organization_id}: {e}")

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
    Periodic task: Send weekly email digests to all eligible organizations.
    Runs every Monday at 9 AM UTC via Celery Beat.

    Workflow:
    1. Query all organizations
    2. For each org, count feedback from the past 7 days
    3. Skip orgs with 0 feedback
    4. Calculate stats and send digest to opted-in users
    """
    from sqlalchemy import func, case
    from src.models import Organization, User, FeedbackItem, WeeklyInsight
    from src.email import send_weekly_digest_email

    with get_db_session() as db:
        organizations = db.query(Organization).all()

        if not organizations:
            return {"status": "no_organizations", "sent": 0}

        total_sent = 0
        total_skipped = 0
        errors = 0

        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=7)
        week_date = f"{start_date.strftime('%b %d')} - {end_date.strftime('%b %d, %Y')}"

        for org in organizations:
            try:
                # Count total feedback for this org in the past week
                total_feedback = db.query(FeedbackItem).filter(
                    FeedbackItem.organization_id == org.id,
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
                    FeedbackItem.organization_id == org.id,
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
                    FeedbackItem.organization_id == org.id,
                    FeedbackItem.created_at >= start_date,
                    FeedbackItem.created_at <= end_date,
                    FeedbackItem.pain_point_category.isnot(None),
                ).count()

                # Feature requests count
                feature_requests = db.query(FeedbackItem).filter(
                    FeedbackItem.organization_id == org.id,
                    FeedbackItem.created_at >= start_date,
                    FeedbackItem.created_at <= end_date,
                    FeedbackItem.feature_request_category.isnot(None),
                ).count()

                # Urgent count
                urgent_count = db.query(FeedbackItem).filter(
                    FeedbackItem.organization_id == org.id,
                    FeedbackItem.created_at >= start_date,
                    FeedbackItem.created_at <= end_date,
                    FeedbackItem.is_urgent == True,
                ).count()

                # Fetch latest weekly insight for this org (generated at 8:30 AM)
                latest_insight = db.query(WeeklyInsight).filter(
                    WeeklyInsight.organization_id == org.id,
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

                # Get opted-in users
                users = db.query(User).filter(
                    User.organization_id == org.id,
                    User.weekly_digest_enabled == True,
                ).all()

                for user in users:
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
                logger.error(f"Error processing org {org.id}: {e}")
                errors += 1

        logger.info(f"Weekly digest complete: sent={total_sent}, skipped={total_skipped}, errors={errors}")

        return {
            "status": "complete",
            "sent": total_sent,
            "skipped": total_skipped,
            "errors": errors,
        }
