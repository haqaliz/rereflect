"""
Abstract base class for LLM providers.
"""

from abc import ABC, abstractmethod
from typing import AsyncIterator, Tuple

from src.llm.types import LLMRequest, LLMResponse


class LLMProvider(ABC):
    """Abstract LLM provider interface."""

    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model

    @abstractmethod
    def complete(self, request: LLMRequest) -> LLMResponse:
        """Synchronous completion. Returns structured response."""
        ...

    async def stream(
        self,
        request: LLMRequest,
    ) -> AsyncIterator[str]:
        """Streaming completion. M2.2 implementation."""
        raise NotImplementedError("Streaming not yet implemented")

    @abstractmethod
    def validate_key(self) -> Tuple[bool, str]:
        """Validate API key. Returns (success, error_message)."""
        ...
