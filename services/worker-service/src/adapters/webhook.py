"""
Generic webhook adapter for handling custom webhook events.
"""

import logging
from typing import Optional, Dict, Any, Tuple

from .base import BaseSourceAdapter

logger = logging.getLogger(__name__)


def _get_nested_value(data: Dict, path: str, default: Any = None) -> Any:
    """
    Get a nested value from a dictionary using dot notation.

    Example: _get_nested_value({"a": {"b": "c"}}, "a.b") -> "c"
    """
    keys = path.split(".")
    value = data
    for key in keys:
        if isinstance(value, dict):
            value = value.get(key)
        elif isinstance(value, list) and key.isdigit():
            idx = int(key)
            value = value[idx] if 0 <= idx < len(value) else None
        else:
            return default
        if value is None:
            return default
    return value


class WebhookAdapter(BaseSourceAdapter):
    """
    Adapter for generic webhooks.

    Supports configurable JSON path extraction and keyword matching.
    """

    def check_triggers(
        self,
        event_type: str,
        event_data: Dict[str, Any],
        triggers: Dict[str, Any],
    ) -> Optional[str]:
        """
        Check if a webhook event matches any configured triggers.

        Trigger types supported:
        - all_messages: Capture all webhook requests
        - keywords: Capture requests where content contains specific keywords
        - labels: Capture requests with specific field values (for structured data)
        """
        payload = event_data.get("payload", {})

        # 1. All messages trigger
        if triggers.get("all_messages"):
            return "all_messages"

        # 2. Keyword trigger (search in entire payload as string)
        keywords = triggers.get("keywords", [])
        if keywords:
            # Convert payload to string for searching
            import json
            payload_str = json.dumps(payload).lower()
            for keyword in keywords:
                if keyword.lower() in payload_str:
                    return f"keyword:{keyword}"

        # 3. Label trigger (check specific fields)
        labels = triggers.get("labels", [])
        if labels:
            # labels is a list of field paths to check
            # e.g., ["type.feedback", "status.urgent"]
            for label in labels:
                # Check if the label exists as a field path
                parts = label.split(".")
                if len(parts) == 2:
                    field, expected_value = parts
                    actual_value = _get_nested_value(payload, field)
                    if actual_value and str(actual_value).lower() == expected_value.lower():
                        return f"label:{label}"

        # 4. Custom rules (provider-specific)
        custom_rules = triggers.get("custom_rules", [])
        for rule in custom_rules:
            rule_type = rule.get("type")
            if rule_type == "json_path_match":
                path = rule.get("path")
                expected = rule.get("value")
                actual = _get_nested_value(payload, path)
                if actual is not None and str(actual) == str(expected):
                    return f"custom:{path}={expected}"

        return None

    def extract_content(
        self,
        event_data: Dict[str, Any],
        field_mapping: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Extract feedback content from a webhook payload.

        The field_mapping can specify:
        - json_path: Path to the text content (e.g., "message.text")
        - author_path: Path to author info (e.g., "user.name")
        - source_name_path: Path to source identifier (e.g., "channel.name")
        """
        payload = event_data.get("payload", {})

        # Get text from specified path or fall back to common paths
        text_source = field_mapping.get("text_source", "message")

        if text_source == "message":
            # Try common paths for message content
            text = (
                _get_nested_value(payload, "message") or
                _get_nested_value(payload, "text") or
                _get_nested_value(payload, "content") or
                _get_nested_value(payload, "body") or
                _get_nested_value(payload, "data.message") or
                _get_nested_value(payload, "data.text") or
                ""
            )
        else:
            # Use the text_source as a json path
            text = _get_nested_value(payload, text_source, "")

        # Ensure text is a string
        if not isinstance(text, str):
            import json
            text = json.dumps(text)

        # Build metadata
        metadata = {
            "content_hash": event_data.get("content_hash"),
        }

        # Extract author info
        if field_mapping.get("include_author"):
            author = (
                _get_nested_value(payload, "user.name") or
                _get_nested_value(payload, "author") or
                _get_nested_value(payload, "from") or
                _get_nested_value(payload, "sender")
            )
            if author:
                metadata["author_name"] = str(author)

        # Extract source name
        if field_mapping.get("include_source_name"):
            source_name = (
                _get_nested_value(payload, "channel") or
                _get_nested_value(payload, "source") or
                _get_nested_value(payload, "type")
            )
            if source_name:
                metadata["source_name"] = str(source_name)

        # Include any custom template processing
        custom_template = field_mapping.get("custom_template")
        if custom_template:
            try:
                # Simple template substitution
                for key, value in payload.items():
                    if isinstance(value, str):
                        custom_template = custom_template.replace(f"{{{{{key}}}}}", value)
                text = custom_template
            except Exception as e:
                logger.warning(f"Failed to apply custom template: {e}")

        return {
            "text": text.strip() if text else "",
            "metadata": metadata,
        }

    def get_external_ids(
        self,
        event_data: Dict[str, Any],
    ) -> Tuple[str, Optional[str]]:
        """
        Get webhook event identifiers.

        Uses content_hash for deduplication if available.
        """
        payload = event_data.get("payload", {})

        # Try to find a unique ID in the payload
        event_id = (
            _get_nested_value(payload, "id") or
            _get_nested_value(payload, "event_id") or
            _get_nested_value(payload, "message_id") or
            event_data.get("content_hash")
        )

        message_id = event_data.get("content_hash")

        return str(event_id) if event_id else "unknown", message_id
