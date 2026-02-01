"""
Base adapter class for source-specific event handling.
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, Tuple


class BaseSourceAdapter(ABC):
    """
    Abstract base class for provider-specific event handling.

    Each adapter implements provider-specific logic for:
    - Trigger matching
    - Content extraction
    - Event deduplication
    - Context fetching
    """

    @abstractmethod
    def check_triggers(
        self,
        event_type: str,
        event_data: Dict[str, Any],
        triggers: Dict[str, Any],
    ) -> Optional[str]:
        """
        Check if an event matches any configured triggers.

        Args:
            event_type: The type of event (message, reaction, mention, etc.)
            event_data: The raw event data from the provider
            triggers: The trigger configuration from FeedbackSource

        Returns:
            The name of the matched trigger (e.g., "all_messages", "reaction:memo"),
            or None if no trigger matched.
        """
        pass

    @abstractmethod
    def extract_content(
        self,
        event_data: Dict[str, Any],
        field_mapping: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Extract feedback content from an event.

        Args:
            event_data: The raw event data from the provider
            field_mapping: The field mapping configuration from FeedbackSource

        Returns:
            A dictionary with:
            - text: The extracted feedback text
            - metadata: Source metadata (author, channel, etc.)
        """
        pass

    @abstractmethod
    def get_external_ids(
        self,
        event_data: Dict[str, Any],
    ) -> Tuple[str, Optional[str]]:
        """
        Get unique identifiers for deduplication.

        Args:
            event_data: The raw event data from the provider

        Returns:
            A tuple of (event_id, message_id) where:
            - event_id: Unique identifier for this event
            - message_id: Identifier for the underlying message (for dedup across events)
        """
        pass

    def fetch_context(
        self,
        event_data: Dict[str, Any],
        access_token: Optional[str],
        field_mapping: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Fetch additional context for the event (optional).

        Override this method to fetch thread messages, user info, etc.

        Args:
            event_data: The raw event data
            access_token: OAuth access token for API calls
            field_mapping: Field mapping configuration

        Returns:
            Additional context data to merge with extracted content
        """
        return {}
