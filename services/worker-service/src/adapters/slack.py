"""
Slack adapter for handling Slack Events API events.
"""

import logging
from typing import Optional, Dict, Any, Tuple, List

import httpx

from .base import BaseSourceAdapter

logger = logging.getLogger(__name__)


class SlackAdapter(BaseSourceAdapter):
    """
    Adapter for Slack Events API.

    Handles event types:
    - message: Regular channel messages
    - app_mention: Bot @mentions
    - reaction_added: Emoji reactions on messages
    """

    def check_triggers(
        self,
        event_type: str,
        event_data: Dict[str, Any],
        triggers: Dict[str, Any],
    ) -> Optional[str]:
        """
        Check if a Slack event matches any configured triggers.

        Trigger types supported:
        - all_messages: Capture all messages (excluding bot/system messages)
        - reactions: Capture messages that receive specific emoji reactions
        - mentions.bot: Capture @bot mentions
        - mentions.users: Capture @user mentions for specific users
        - keywords: Capture messages containing specific keywords
        """
        # Skip bot messages and message edits
        if event_type == "message":
            subtype = event_data.get("subtype")
            if subtype in ["bot_message", "message_changed", "message_deleted"]:
                return None

        # 1. All messages trigger
        if triggers.get("all_messages") and event_type == "message":
            return "all_messages"

        # 2. Emoji reaction trigger
        reactions = triggers.get("reactions", [])
        if reactions and event_type == "reaction_added":
            reaction = event_data.get("reaction", "")
            # Remove skin tone modifiers for comparison
            base_reaction = reaction.split("::")[0]
            if base_reaction in reactions or reaction in reactions:
                return f"reaction:{reaction}"

        # 3. Bot mention trigger
        mentions = triggers.get("mentions", {})
        if mentions.get("bot") and event_type == "app_mention":
            return "mention:bot"

        # 4. User mention trigger
        mentioned_users = mentions.get("users", [])
        if mentioned_users and event_type == "message":
            text = event_data.get("text", "")
            for user_id in mentioned_users:
                if f"<@{user_id}>" in text:
                    return f"mention:{user_id}"

        # 5. Keyword trigger
        keywords = triggers.get("keywords", [])
        if keywords and event_type == "message":
            text = event_data.get("text", "").lower()
            for keyword in keywords:
                if keyword.lower() in text:
                    return f"keyword:{keyword}"

        return None

    def extract_content(
        self,
        event_data: Dict[str, Any],
        field_mapping: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Extract feedback content from a Slack event.
        """
        text = event_data.get("text", "")

        # Clean up Slack mentions in text
        # <@U123> -> @user, <#C123|channel> -> #channel
        import re
        text = re.sub(r'<@[A-Z0-9]+>', '@user', text)
        text = re.sub(r'<#[A-Z0-9]+\|([^>]+)>', r'#\1', text)
        text = re.sub(r'<(https?://[^|>]+)\|([^>]+)>', r'\2', text)  # Links
        text = re.sub(r'<(https?://[^>]+)>', r'\1', text)  # Bare links

        metadata = {
            "author_id": event_data.get("user"),
            "channel_id": event_data.get("channel"),
            "message_id": event_data.get("ts"),
            "thread_id": event_data.get("thread_ts"),
        }

        # Handle reaction events (the event is on reaction, not message)
        if event_data.get("type") == "reaction_added":
            item = event_data.get("item", {})
            metadata["message_id"] = item.get("ts")
            metadata["channel_id"] = item.get("channel")
            metadata["reaction"] = event_data.get("reaction")
            metadata["reactor_id"] = event_data.get("user")

        return {
            "text": text.strip(),
            "metadata": metadata,
        }

    def get_external_ids(
        self,
        event_data: Dict[str, Any],
    ) -> Tuple[str, Optional[str]]:
        """
        Get Slack event identifiers.

        For messages: event_id is the event callback ID, message_id is the ts
        For reactions: we use the item ts as message_id
        """
        # The event_id is typically passed from the outer event callback
        # For message events, ts is the message timestamp (unique per channel)
        message_ts = event_data.get("ts")

        # For reaction events, get the message ts from the item
        if event_data.get("type") == "reaction_added":
            item = event_data.get("item", {})
            message_ts = item.get("ts")

        # We don't have the event_id here (it's at the callback level)
        # So we use a combination of channel + ts + type
        channel = event_data.get("channel") or event_data.get("item", {}).get("channel", "")
        event_type = event_data.get("type", "message")

        # Generate a pseudo event_id based on available data
        event_id = f"{channel}:{message_ts}:{event_type}"

        return event_id, message_ts

    def fetch_context(
        self,
        event_data: Dict[str, Any],
        access_token: Optional[str],
        field_mapping: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Fetch additional context from Slack API.

        Can fetch:
        - Thread messages for context
        - User profile information
        - Original message for reaction events
        """
        if not access_token:
            return {}

        context = {}
        include_context = field_mapping.get("include_context", False)
        include_author = field_mapping.get("include_author", True)

        channel_id = event_data.get("channel") or event_data.get("item", {}).get("channel")

        # Fetch original message for reaction events
        if event_data.get("type") == "reaction_added":
            item = event_data.get("item", {})
            message_ts = item.get("ts")
            if channel_id and message_ts:
                original_message = self._fetch_message(access_token, channel_id, message_ts)
                if original_message:
                    context["original_text"] = original_message.get("text", "")
                    context["original_author"] = original_message.get("user")

        # Fetch thread context
        thread_ts = event_data.get("thread_ts")
        if include_context and thread_ts and channel_id:
            max_messages = field_mapping.get("max_context_messages", 5)
            thread_messages = self._fetch_thread(access_token, channel_id, thread_ts, max_messages)
            if thread_messages:
                context["thread_messages"] = [
                    {"text": m.get("text", ""), "user": m.get("user")}
                    for m in thread_messages
                ]

        # Fetch user info
        user_id = event_data.get("user")
        if include_author and user_id:
            user_info = self._fetch_user_info(access_token, user_id)
            if user_info:
                context["author_name"] = user_info.get("real_name") or user_info.get("name")
                context["author_email"] = user_info.get("email")

        return context

    def _fetch_message(
        self,
        access_token: str,
        channel_id: str,
        message_ts: str,
    ) -> Optional[Dict]:
        """Fetch a specific message from Slack."""
        try:
            with httpx.Client(timeout=10) as client:
                response = client.get(
                    "https://slack.com/api/conversations.history",
                    headers={"Authorization": f"Bearer {access_token}"},
                    params={
                        "channel": channel_id,
                        "latest": message_ts,
                        "limit": 1,
                        "inclusive": True,
                    }
                )
                data = response.json()
                if data.get("ok") and data.get("messages"):
                    return data["messages"][0]
        except Exception as e:
            logger.error(f"Failed to fetch Slack message: {e}")
        return None

    def _fetch_thread(
        self,
        access_token: str,
        channel_id: str,
        thread_ts: str,
        limit: int = 5,
    ) -> List[Dict]:
        """Fetch messages in a thread."""
        try:
            with httpx.Client(timeout=10) as client:
                response = client.get(
                    "https://slack.com/api/conversations.replies",
                    headers={"Authorization": f"Bearer {access_token}"},
                    params={
                        "channel": channel_id,
                        "ts": thread_ts,
                        "limit": limit,
                    }
                )
                data = response.json()
                if data.get("ok"):
                    return data.get("messages", [])
        except Exception as e:
            logger.error(f"Failed to fetch Slack thread: {e}")
        return []

    def _fetch_user_info(
        self,
        access_token: str,
        user_id: str,
    ) -> Optional[Dict]:
        """Fetch user profile information."""
        try:
            with httpx.Client(timeout=10) as client:
                response = client.get(
                    "https://slack.com/api/users.info",
                    headers={"Authorization": f"Bearer {access_token}"},
                    params={"user": user_id}
                )
                data = response.json()
                if data.get("ok"):
                    return data.get("user", {}).get("profile", {})
        except Exception as e:
            logger.error(f"Failed to fetch Slack user info: {e}")
        return None
