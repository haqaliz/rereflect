"""
Email service for worker-service.
Duplicates core Resend email logic for sending weekly digests.
"""
import os
import re
import logging
import requests
from typing import Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)

RESEND_API_KEY = os.getenv("RESEND_API_KEY")
FROM_EMAIL = os.getenv("FROM_EMAIL", "noreply@rereflect.ca")
FROM_NAME = os.getenv("FROM_NAME", "Rereflect")
APP_URL = os.getenv("APP_URL", "http://localhost:3000")
TEMPLATE_WEEKLY_DIGEST = os.getenv("RESEND_TEMPLATE_WEEKLY_DIGEST")

RESEND_API_BASE = "https://api.resend.com"

_template_cache: Dict[str, Tuple[str, str]] = {}


def _is_email_enabled() -> bool:
    return bool(RESEND_API_KEY)


def _get_template(template_id: str) -> Optional[Tuple[str, str]]:
    if template_id in _template_cache:
        return _template_cache[template_id]

    try:
        response = requests.get(
            f"{RESEND_API_BASE}/templates/{template_id}",
            headers={"Authorization": f"Bearer {RESEND_API_KEY}"},
            timeout=30,
        )

        if response.status_code == 200:
            data = response.json().get("data", response.json())
            html = data.get("html", "")
            subject = data.get("subject", "")
            _template_cache[template_id] = (html, subject)
            return (html, subject)
        else:
            logger.error(f"Failed to fetch template {template_id}: {response.status_code}")
            return None
    except Exception as e:
        logger.error(f"Failed to fetch template {template_id}: {e}")
        return None


def _render_template(html: str, subject: str, variables: Dict[str, Any]) -> Tuple[str, str]:
    rendered_html = html
    rendered_subject = subject

    for key, value in variables.items():
        pattern = r'\{\{\{' + re.escape(key) + r'\}\}\}'
        rendered_html = re.sub(pattern, str(value), rendered_html)
        rendered_subject = re.sub(pattern, str(value), rendered_subject)

    return rendered_html, rendered_subject


def _send_email(to: str, subject: str, html: str) -> bool:
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
            logger.info(f"Email sent to {to}")
            return True
        else:
            logger.error(f"Failed to send email to {to}: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        logger.error(f"Failed to send email to {to}: {e}")
        return False


def _send_with_template(to: str, template_id: str, variables: Dict[str, Any]) -> bool:
    if not template_id:
        logger.warning(f"Email not sent (template_id not configured) to {to}")
        return False

    template = _get_template(template_id)
    if not template:
        return False

    html, subject = template
    rendered_html, rendered_subject = _render_template(html, subject, variables)
    return _send_email(to, rendered_subject, rendered_html)


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
    dashboard_url = f"{APP_URL}/dashboard"
    unsubscribe_url = f"{APP_URL}/settings/preferences"

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
