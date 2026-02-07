"""
Email service using Resend for sending transactional emails.
Fetches templates from Resend, renders variables locally, then sends.
"""
import os
import re
import logging
import requests
from typing import Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)

# Configuration
RESEND_API_KEY = os.getenv("RESEND_API_KEY")
FROM_EMAIL = os.getenv("FROM_EMAIL", "noreply@rereflect.ca")
FROM_NAME = os.getenv("FROM_NAME", "Rereflect")
APP_URL = os.getenv("APP_URL", "http://localhost:3000")

# Template IDs from Resend
TEMPLATE_TEAM_INVITE = os.getenv("RESEND_TEMPLATE_TEAM_INVITE")
TEMPLATE_WELCOME = os.getenv("RESEND_TEMPLATE_WELCOME")
TEMPLATE_PASSWORD_RESET = os.getenv("RESEND_TEMPLATE_PASSWORD_RESET")
TEMPLATE_WEEKLY_DIGEST = os.getenv("RESEND_TEMPLATE_WEEKLY_DIGEST")
TEMPLATE_ROLE_CHANGE = os.getenv("RESEND_TEMPLATE_ROLE_CHANGE")
TEMPLATE_MEMBER_REMOVED = os.getenv("RESEND_TEMPLATE_MEMBER_REMOVED")
TEMPLATE_DAILY_ALERT_DIGEST = os.getenv("RESEND_TEMPLATE_DAILY_ALERT_DIGEST")

# Resend API endpoints
RESEND_API_BASE = "https://api.resend.com"

# Template cache (template_id -> (html, subject))
_template_cache: Dict[str, Tuple[str, str]] = {}


def _is_email_enabled() -> bool:
    """Check if email sending is enabled."""
    return bool(RESEND_API_KEY)


def _get_template(template_id: str) -> Optional[Tuple[str, str]]:
    """
    Fetch template from Resend API. Returns (html, subject) or None if failed.
    Caches templates to avoid repeated API calls.
    """
    if template_id in _template_cache:
        return _template_cache[template_id]

    try:
        response = requests.get(
            f"{RESEND_API_BASE}/templates/{template_id}",
            headers={
                "Authorization": f"Bearer {RESEND_API_KEY}",
            },
            timeout=30,
        )

        if response.status_code == 200:
            data = response.json().get("data", response.json())
            html = data.get("html", "")
            subject = data.get("subject", "")
            _template_cache[template_id] = (html, subject)
            logger.info(f"Fetched template {template_id}")
            return (html, subject)
        else:
            logger.error(f"Failed to fetch template {template_id}: {response.status_code} - {response.text}")
            return None

    except Exception as e:
        logger.error(f"Failed to fetch template {template_id}: {e}")
        return None


def _render_template(html: str, subject: str, variables: Dict[str, Any]) -> Tuple[str, str]:
    """
    Render template by replacing {{{VAR}}} placeholders with values.
    Returns (rendered_html, rendered_subject).
    """
    rendered_html = html
    rendered_subject = subject

    for key, value in variables.items():
        # Replace {{{KEY}}} with value (Resend template syntax)
        pattern = r'\{\{\{' + re.escape(key) + r'\}\}\}'
        rendered_html = re.sub(pattern, str(value), rendered_html)
        rendered_subject = re.sub(pattern, str(value), rendered_subject)

    return rendered_html, rendered_subject


def _send_email(to: str, subject: str, html: str) -> bool:
    """Send email with rendered HTML content."""
    if not _is_email_enabled():
        logger.warning(f"Email not sent (RESEND_API_KEY not configured): {subject} to {to}")
        return False

    try:
        response = requests.post(
            f"{RESEND_API_BASE}/emails",
            headers={
                "Authorization": f"Bearer {RESEND_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "from": f"{FROM_NAME} <{FROM_EMAIL}>",
                "to": [to],
                "subject": subject,
                "html": html,
            },
            timeout=30,
        )

        if response.status_code == 200:
            email_id = response.json().get("id", "unknown")
            logger.info(f"Email sent successfully to {to}: {email_id}")
            return True
        else:
            logger.error(f"Failed to send email to {to}: {response.status_code} - {response.text}")
            return False

    except Exception as e:
        logger.error(f"Failed to send email to {to}: {e}")
        return False


def _send_with_template(to: str, template_id: str, variables: Dict[str, Any]) -> bool:
    """Fetch template, render variables, and send email."""
    if not template_id:
        logger.warning(f"Email not sent (template_id not configured) to {to}")
        return False

    template = _get_template(template_id)
    if not template:
        logger.error(f"Email not sent (failed to fetch template {template_id}) to {to}")
        return False

    html, subject = template
    rendered_html, rendered_subject = _render_template(html, subject, variables)

    return _send_email(to, rendered_subject, rendered_html)


def send_team_invite_email(
    to_email: str,
    invite_token: str,
    organization_name: str,
    inviter_email: str,
    role: str,
) -> bool:
    """Send a team invitation email."""
    invite_url = f"{APP_URL}/invite/{invite_token}"

    return _send_with_template(
        to=to_email,
        template_id=TEMPLATE_TEAM_INVITE,
        variables={
            "ORGANIZATION_NAME": organization_name,
            "INVITER_EMAIL": inviter_email,
            "ROLE": role,
            "INVITE_URL": invite_url,
        },
    )


def send_welcome_email(
    to_email: str,
    organization_name: str,
) -> bool:
    """Send a welcome email after user signs up or accepts an invite."""
    dashboard_url = f"{APP_URL}/dashboard"

    return _send_with_template(
        to=to_email,
        template_id=TEMPLATE_WELCOME,
        variables={
            "ORGANIZATION_NAME": organization_name,
            "DASHBOARD_URL": dashboard_url,
        },
    )


def send_password_reset_email(
    to_email: str,
    reset_token: str,
) -> bool:
    """Send a password reset email."""
    reset_url = f"{APP_URL}/reset-password/{reset_token}"

    return _send_with_template(
        to=to_email,
        template_id=TEMPLATE_PASSWORD_RESET,
        variables={
            "RESET_URL": reset_url,
        },
    )


def send_weekly_digest_email(
    to_email: str,
    organization_name: str,
    week_date: str,
    total_feedback: int,
    pain_points: int,
    feature_requests: int,
    positive_percent: int,
    neutral_percent: int,
    negative_percent: int,
    urgent_count: int,
) -> bool:
    """Send a weekly feedback digest email."""
    dashboard_url = f"{APP_URL}/dashboard"
    unsubscribe_url = f"{APP_URL}/settings/notifications"

    return _send_with_template(
        to=to_email,
        template_id=TEMPLATE_WEEKLY_DIGEST,
        variables={
            "ORGANIZATION_NAME": organization_name,
            "WEEK_DATE": week_date,
            "TOTAL_FEEDBACK": total_feedback,
            "PAIN_POINTS": pain_points,
            "FEATURE_REQUESTS": feature_requests,
            "POSITIVE_PERCENT": positive_percent,
            "NEUTRAL_PERCENT": neutral_percent,
            "NEGATIVE_PERCENT": negative_percent,
            "URGENT_COUNT": urgent_count,
            "DASHBOARD_URL": dashboard_url,
            "UNSUBSCRIBE_URL": unsubscribe_url,
        },
    )


def send_role_change_email(
    to_email: str,
    organization_name: str,
    old_role: str,
    new_role: str,
    changed_by_email: str,
) -> bool:
    """Send a notification email when a user's role is changed."""
    dashboard_url = f"{APP_URL}/dashboard"

    return _send_with_template(
        to=to_email,
        template_id=TEMPLATE_ROLE_CHANGE,
        variables={
            "ORGANIZATION_NAME": organization_name,
            "OLD_ROLE": old_role.capitalize(),
            "NEW_ROLE": new_role.capitalize(),
            "CHANGED_BY_EMAIL": changed_by_email,
            "DASHBOARD_URL": dashboard_url,
        },
    )


def send_daily_alert_digest_email(
    to_email: str,
    organization_name: str,
    date: str,
    alert_count: int,
    alerts_html: str,
) -> bool:
    """Send a daily alert digest email."""
    dashboard_url = f"{APP_URL}/dashboard"
    unsubscribe_url = f"{APP_URL}/settings/notifications"

    return _send_with_template(
        to=to_email,
        template_id=TEMPLATE_DAILY_ALERT_DIGEST,
        variables={
            "ORGANIZATION_NAME": organization_name,
            "DATE": date,
            "ALERT_COUNT": alert_count,
            "ALERTS_HTML": alerts_html,
            "DASHBOARD_URL": dashboard_url,
            "UNSUBSCRIBE_URL": unsubscribe_url,
        },
    )


def send_member_removed_email(
    to_email: str,
    organization_name: str,
    removed_by_email: str,
) -> bool:
    """Send a notification email when a user is removed from an organization."""
    return _send_with_template(
        to=to_email,
        template_id=TEMPLATE_MEMBER_REMOVED,
        variables={
            "ORGANIZATION_NAME": organization_name,
            "REMOVED_BY_EMAIL": removed_by_email,
        },
    )
