"""
Intercom adapter for handling Intercom webhook events.
"""

import re
import logging
from typing import Optional, Dict, Any, Tuple

import httpx

from .base import BaseSourceAdapter

logger = logging.getLogger(__name__)


def strip_html(text: str) -> str:
    """Strip HTML tags from text."""
    return re.sub(r"<[^>]+>", "", text).strip()


class IntercomAdapter(BaseSourceAdapter):
    """
    Adapter for Intercom webhook events.

    Handles event types:
    - conversation.user.created: New conversation started
    - conversation.user.replied: Customer replied
    - conversation.rating.added: Customer gave rating
    """

    CONVERSATION_EVENTS = {
        "conversation.user.created",
        "conversation.user.replied",
        "conversation.rating.added",
    }

    def check_triggers(
        self,
        event_type: str,
        event_data: Dict[str, Any],
        triggers: Dict[str, Any],
    ) -> Optional[str]:
        # 1. All conversations trigger
        if triggers.get("all_conversations") and event_type in self.CONVERSATION_EVENTS:
            return "all_conversations"

        # 2. New conversations only
        if triggers.get("new_conversations") and event_type == "conversation.user.created":
            return "new_conversations"

        # 3. Replies only
        if triggers.get("replies") and event_type == "conversation.user.replied":
            return "replies"

        # 4. Ratings only
        if triggers.get("ratings") and event_type == "conversation.rating.added":
            return "ratings"

        # 5. Keyword trigger
        keywords = triggers.get("keywords", [])
        if keywords:
            body = self._get_body_text(event_type, event_data)
            if body:
                body_lower = body.lower()
                for keyword in keywords:
                    if keyword.lower() in body_lower:
                        return f"keyword:{keyword}"

        return None

    def _get_body_text(self, event_type: str, event_data: Dict[str, Any]) -> str:
        """Extract raw body text from event data for keyword matching."""
        item = event_data.get("data", {}).get("item", {})
        if event_type == "conversation.user.created":
            msg = item.get("conversation_message", {})
            return strip_html(msg.get("body", ""))
        elif event_type == "conversation.user.replied":
            return strip_html(item.get("body", ""))
        elif event_type == "conversation.rating.added":
            return item.get("remark", "")
        return ""

    def extract_content(
        self,
        event_data: Dict[str, Any],
        field_mapping: Dict[str, Any],
    ) -> Dict[str, Any]:
        topic = event_data.get("topic", "")
        item = event_data.get("data", {}).get("item", {})

        if "rating" in topic:
            return self._extract_rating(item)
        elif "replied" in topic:
            return self._extract_reply(item)
        else:
            return self._extract_new_conversation(item)

    def _extract_new_conversation(self, item: Dict[str, Any]) -> Dict[str, Any]:
        msg = item.get("conversation_message", {})
        body = strip_html(msg.get("body", ""))
        author = msg.get("author", {})
        return {
            "text": body,
            "metadata": {
                "conversation_id": item.get("id"),
                "author_id": author.get("id"),
                "author_name": author.get("name"),
                "author_email": author.get("email"),
            },
        }

    def _extract_reply(self, item: Dict[str, Any]) -> Dict[str, Any]:
        body = strip_html(item.get("body", ""))
        author = item.get("author", {})
        return {
            "text": body,
            "metadata": {
                "conversation_id": item.get("conversation_id"),
                "part_id": item.get("id"),
                "author_id": author.get("id"),
                "author_name": author.get("name"),
                "author_email": author.get("email"),
            },
        }

    def _extract_rating(self, item: Dict[str, Any]) -> Dict[str, Any]:
        rating = item.get("rating")
        remark = item.get("remark", "")
        contact = item.get("contact", {})
        text = f"Rating: {rating}/5"
        if remark:
            text = f"{text} - {remark}"
        return {
            "text": text,
            "metadata": {
                "conversation_id": item.get("conversation_id"),
                "rating": rating,
                "author_id": contact.get("id"),
                "author_name": contact.get("name"),
            },
        }

    def get_external_ids(
        self,
        event_data: Dict[str, Any],
    ) -> Tuple[str, Optional[str]]:
        topic = event_data.get("topic", "")
        item = event_data.get("data", {}).get("item", {})

        if "replied" in topic:
            conv_id = item.get("conversation_id", "")
            part_id = item.get("id", "")
            return f"{conv_id}:{part_id}", conv_id
        elif "rating" in topic:
            conv_id = item.get("conversation_id", "")
            return f"{conv_id}:rating", conv_id
        else:
            conv_id = item.get("id", "")
            return conv_id, conv_id

    def fetch_context(
        self,
        event_data: Dict[str, Any],
        access_token: Optional[str],
        field_mapping: Dict[str, Any],
    ) -> Dict[str, Any]:
        if not access_token:
            return {}

        context = {}
        item = event_data.get("data", {}).get("item", {})
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }

        # Get conversation ID
        topic = event_data.get("topic", "")
        if "replied" in topic or "rating" in topic:
            conv_id = item.get("conversation_id")
        else:
            conv_id = item.get("id")

        # Get contact ID
        if "rating" in topic:
            contact_id = item.get("contact", {}).get("id")
        else:
            msg = item.get("conversation_message", {}) if "created" in topic else item
            contact_id = msg.get("author", {}).get("id")

        try:
            with httpx.Client(timeout=10) as client:
                # Fetch conversation history
                if conv_id:
                    resp = client.get(
                        f"https://api.intercom.io/conversations/{conv_id}",
                        headers=headers,
                    )
                    data = resp.json()
                    parts = data.get("conversation_parts", {}).get("conversation_parts", [])
                    context["previous_messages"] = [
                        {
                            "text": strip_html(p.get("body", "") or ""),
                            "author": p.get("author", {}).get("name"),
                        }
                        for p in parts
                    ]
                    context["conversation_url"] = f"https://app.intercom.com/a/apps/_/inbox/conversation/{conv_id}"

                # Fetch contact details
                if contact_id:
                    resp = client.get(
                        f"https://api.intercom.io/contacts/{contact_id}",
                        headers=headers,
                    )
                    contact_data = resp.json()
                    context["contact_name"] = contact_data.get("name")
                    context["contact_email"] = contact_data.get("email")

        except Exception as e:
            logger.error(f"Failed to fetch Intercom context: {e}")

        return context
