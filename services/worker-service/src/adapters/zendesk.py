"""
Zendesk adapter for handling Zendesk ticket events (pull + webhook).

Shared ingestion core consumed by both the ingestion-pull and ingestion-webhook
aspects. See docs/planning/zendesk-integration/ingestion-core/plan_20260705.md
for the locked contracts this adapter implements.
"""

import logging
from typing import Optional, Dict, Any, Tuple

import httpx

from .base import BaseSourceAdapter
from .intercom import strip_html

logger = logging.getLogger(__name__)


class ZendeskAdapter(BaseSourceAdapter):
    """
    Adapter for Zendesk ticket events.

    Handles the "ticket.created" event type (new tickets only, per PRD scope).
    Dedup key is the ticket id — one feedback item per ticket.
    """

    TICKET_CREATED = "ticket.created"

    def check_triggers(
        self,
        event_type: str,
        event_data: Dict[str, Any],
        triggers: Dict[str, Any],
    ) -> Optional[str]:
        # 1. New ticket trigger
        if triggers.get("new_ticket") and event_type == self.TICKET_CREATED:
            return "new_ticket"

        # 2. Keyword trigger
        keywords = triggers.get("keywords", [])
        if keywords:
            body = self._get_body_text(event_data)
            if body:
                body_lower = body.lower()
                for keyword in keywords:
                    if keyword.lower() in body_lower:
                        return f"keyword:{keyword}"

        return None

    def _get_body_text(self, event_data: Dict[str, Any]) -> str:
        """Extract raw subject+description text for keyword matching."""
        ticket = event_data.get("ticket", {})
        subject = strip_html(ticket.get("subject") or "")
        description = strip_html(ticket.get("description") or "")
        return f"{subject} {description}".strip()

    def extract_content(
        self,
        event_data: Dict[str, Any],
        field_mapping: Dict[str, Any],
    ) -> Dict[str, Any]:
        ticket = event_data.get("ticket", {})
        subdomain = event_data.get("subdomain")
        subject = strip_html(ticket.get("subject") or "")
        description = strip_html(ticket.get("description") or "")
        text = f"{subject}\n\n{description}" if description else subject
        requester_email = ticket.get("requester_email")

        return {
            "text": text,
            "metadata": {
                "subdomain": subdomain,
                "ticket_id": ticket.get("id"),
                "status": ticket.get("status"),
                "requester_email": requester_email,
                "tags": ticket.get("tags") or [],
            },
            "customer_email": requester_email,
        }

    def get_external_ids(
        self,
        event_data: Dict[str, Any],
    ) -> Tuple[str, Optional[str]]:
        ticket_id = str(event_data.get("ticket", {}).get("id"))
        return ticket_id, ticket_id

    def fetch_context(
        self,
        event_data: Dict[str, Any],
        access_token: Optional[str],
        field_mapping: Dict[str, Any],
    ) -> Dict[str, Any]:
        if not access_token or ":" not in access_token:
            return {}

        email, api_token = access_token.split(":", 1)
        ticket = event_data.get("ticket", {})
        subdomain = event_data.get("subdomain")
        ticket_id = ticket.get("id")

        context = {}
        try:
            with httpx.Client(timeout=10, auth=(f"{email}/token", api_token)) as client:
                resp = client.get(f"https://{subdomain}.zendesk.com/api/v2/tickets/{ticket_id}")
                ticket_data = resp.json().get("ticket", {})
                context["ticket_url"] = f"https://{subdomain}.zendesk.com/agent/tickets/{ticket_id}"

                requester_id = ticket_data.get("requester_id")
                if requester_id:
                    resp2 = client.get(f"https://{subdomain}.zendesk.com/api/v2/users/{requester_id}")
                    user_data = resp2.json().get("user", {})
                    context["requester_name"] = user_data.get("name")
                    context["requester_email"] = user_data.get("email")
        except Exception as e:
            logger.error(f"Failed to fetch Zendesk context: {e}")

        return context
