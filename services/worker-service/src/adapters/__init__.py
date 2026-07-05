"""
Source adapters for handling provider-specific event processing.
"""

from .base import BaseSourceAdapter
from .email import EmailAdapter
from .intercom import IntercomAdapter
from .slack import SlackAdapter
from .webhook import WebhookAdapter
from .zendesk import ZendeskAdapter

__all__ = [
    "BaseSourceAdapter",
    "EmailAdapter",
    "IntercomAdapter",
    "SlackAdapter",
    "WebhookAdapter",
    "ZendeskAdapter",
]


def get_adapter(source_type: str) -> BaseSourceAdapter:
    """
    Get the appropriate adapter for a source type.

    Args:
        source_type: The source type (slack, webhook, email, etc.)

    Returns:
        An instance of the appropriate adapter

    Raises:
        ValueError: If source type is not supported
    """
    adapters = {
        "email": EmailAdapter,
        "intercom": IntercomAdapter,
        "slack": SlackAdapter,
        "webhook": WebhookAdapter,
        "zendesk": ZendeskAdapter,
    }

    adapter_class = adapters.get(source_type)
    if not adapter_class:
        raise ValueError(f"Unsupported source type: {source_type}")

    return adapter_class()
