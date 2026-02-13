"""
Email adapter for handling inbound email webhook events.
"""

import logging
from typing import Optional, Dict, Any, Tuple

from .base import BaseSourceAdapter
from src.email_parser import parse_email_body

logger = logging.getLogger(__name__)


class EmailAdapter(BaseSourceAdapter):
    """
    Adapter for inbound email webhooks (via Resend).

    All emails are accepted (no trigger filtering for v1).
    Body parsing is delegated to email_parser.parse_email_body().
    """

    def check_triggers(
        self,
        event_type: str,
        event_data: Dict[str, Any],
        triggers: Dict[str, Any],
    ) -> Optional[str]:
        """
        All inbound emails are accepted as feedback (no filtering for v1).

        Returns "all_emails" for every event.
        """
        return "all_emails"

    def extract_content(
        self,
        event_data: Dict[str, Any],
        field_mapping: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Extract feedback content from an inbound email event.

        Delegates body parsing to email_parser.parse_email_body() which handles
        HTML stripping, forwarding header removal, signature stripping, and
        quote removal.
        """
        html = event_data.get("html")
        text = event_data.get("text")
        parsed_text = parse_email_body(html=html, text=text)

        metadata = {
            "subject": event_data.get("subject"),
            "from": event_data.get("from"),
        }

        return {
            "text": parsed_text,
            "metadata": metadata,
        }

    def get_external_ids(
        self,
        event_data: Dict[str, Any],
    ) -> Tuple[str, Optional[str]]:
        """
        Get email message identifiers for deduplication.

        Uses the Message-ID as both event_id and message_id.
        Checks top-level message_id first (from webhook handler),
        then falls back to headers.message-id.
        """
        message_id = event_data.get("message_id")
        if not message_id:
            headers = event_data.get("headers") or {}
            message_id = headers.get("message-id")

        if message_id:
            return message_id, message_id

        return "unknown", None
