"""
Response Sender Service.

Handles sending a response through various integration channels:
  - Slack: thread reply via chat.postMessage
  - Intercom: admin reply to conversation
  - Linear: comment via GraphQL commentCreate
  - Email: send via Resend to customer_email

Each function returns {"success": bool, "error": str | None}.
"""

import logging
import os
from typing import Optional

import httpx

from src.models.feedback import FeedbackItem
from src.models.organization import Organization

logger = logging.getLogger(__name__)


async def send_via_slack(
    response_text: str,
    feedback: FeedbackItem,
    org: Organization,
    access_token: str,
) -> dict:
    """Post a thread reply in Slack using chat.postMessage."""
    source_meta = feedback.source_metadata or {}
    channel_id = source_meta.get("channel_id")
    thread_ts = source_meta.get("thread_ts") or source_meta.get("message_ts")

    if not channel_id:
        return {"success": False, "error": "Missing channel_id in source_metadata"}

    payload = {
        "channel": channel_id,
        "text": response_text,
    }
    if thread_ts:
        payload["thread_ts"] = thread_ts

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                "https://slack.com/api/chat.postMessage",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            if not data.get("ok"):
                error = data.get("error", "Slack API error")
                logger.warning(f"Slack send failed for org {org.id}: {error}")
                return {"success": False, "error": error}
            return {"success": True, "error": None}
    except Exception as exc:
        logger.error(f"Slack send exception for org {org.id}: {exc}")
        return {"success": False, "error": str(exc)}


async def send_via_intercom(
    response_text: str,
    feedback: FeedbackItem,
    org: Organization,
    access_token: str,
) -> dict:
    """Post an admin reply to an Intercom conversation."""
    source_meta = feedback.source_metadata or {}
    conversation_id = source_meta.get("conversation_id")

    if not conversation_id:
        return {"success": False, "error": "Missing conversation_id in source_metadata"}

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"https://api.intercom.io/conversations/{conversation_id}/reply",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                json={
                    "type": "admin",
                    "message_type": "comment",
                    "body": response_text,
                },
            )
            resp.raise_for_status()
            return {"success": True, "error": None}
    except httpx.HTTPStatusError as exc:
        error = f"Intercom API error {exc.response.status_code}"
        logger.warning(f"Intercom send failed for org {org.id}: {error}")
        return {"success": False, "error": error}
    except Exception as exc:
        logger.error(f"Intercom send exception for org {org.id}: {exc}")
        return {"success": False, "error": str(exc)}


async def send_via_linear(
    response_text: str,
    feedback: FeedbackItem,
    org: Organization,
    access_token: str,
) -> dict:
    """Post a comment on a Linear issue via GraphQL commentCreate mutation."""
    source_meta = feedback.source_metadata or {}
    issue_id = source_meta.get("issue_id")

    if not issue_id:
        return {"success": False, "error": "Missing issue_id in source_metadata"}

    mutation = """
    mutation CommentCreate($issueId: String!, $body: String!) {
      commentCreate(input: { issueId: $issueId, body: $body }) {
        success
        comment {
          id
        }
      }
    }
    """

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                "https://api.linear.app/graphql",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                json={
                    "query": mutation,
                    "variables": {"issueId": issue_id, "body": response_text},
                },
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("errors"):
                error = data["errors"][0].get("message", "Linear GraphQL error")
                logger.warning(f"Linear send failed for org {org.id}: {error}")
                return {"success": False, "error": error}
            success = data.get("data", {}).get("commentCreate", {}).get("success", False)
            if not success:
                return {"success": False, "error": "Linear commentCreate returned success=false"}
            return {"success": True, "error": None}
    except Exception as exc:
        logger.error(f"Linear send exception for org {org.id}: {exc}")
        return {"success": False, "error": str(exc)}


async def send_via_email(
    response_text: str,
    feedback: FeedbackItem,
    org: Organization,
    customer_email: str,
) -> dict:
    """Send the response as a plain-text email via Resend."""
    resend_api_key = os.environ.get("RESEND_API_KEY", "")
    if not resend_api_key:
        return {"success": False, "error": "RESEND_API_KEY not configured"}

    from_email = (
        org.support_email_display
        or f"noreply@rereflect.ca"
    )
    product_name = org.product_name_display or "Rereflect"
    source_meta = feedback.source_metadata or {}
    original_subject = source_meta.get("subject")
    subject = f"Re: {original_subject}" if original_subject else f"Response from {product_name}"

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {resend_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "from": from_email,
                    "to": [customer_email],
                    "subject": subject,
                    "text": response_text,
                },
            )
            resp.raise_for_status()
            return {"success": True, "error": None}
    except httpx.HTTPStatusError as exc:
        error = f"Resend API error {exc.response.status_code}"
        logger.warning(f"Email send failed for org {org.id}: {error}")
        return {"success": False, "error": error}
    except Exception as exc:
        logger.error(f"Email send exception for org {org.id}: {exc}")
        return {"success": False, "error": str(exc)}
