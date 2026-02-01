"""
Source adapters for handling provider-specific event processing.
"""

from .base import BaseSourceAdapter
from .slack import SlackAdapter
from .webhook import WebhookAdapter

__all__ = [
    "BaseSourceAdapter",
    "SlackAdapter",
    "WebhookAdapter",
]


def get_adapter(source_type: str) -> BaseSourceAdapter:
    """
    Get the appropriate adapter for a source type.

    Args:
        source_type: The source type (slack, webhook, discord, etc.)

    Returns:
        An instance of the appropriate adapter

    Raises:
        ValueError: If source type is not supported
    """
    adapters = {
        "slack": SlackAdapter,
        "webhook": WebhookAdapter,
    }

    adapter_class = adapters.get(source_type)
    if not adapter_class:
        raise ValueError(f"Unsupported source type: {source_type}")

    return adapter_class()
