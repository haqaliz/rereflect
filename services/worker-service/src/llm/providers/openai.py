"""
OpenAI LLM provider implementation.

Uses chat.completions.create with json_object response format for JSON mode.
System messages are kept in the messages array (OpenAI's native format).
"""

import logging
import time
from typing import Optional, Tuple

from openai import OpenAI, RateLimitError, APIError, APITimeoutError, AuthenticationError

from src.llm.base import LLMProvider
from src.llm.types import LLMRequest, LLMResponse
from src.llm.pricing import estimate_cost_cents

logger = logging.getLogger(__name__)


class OpenAIProvider(LLMProvider):
    """OpenAI chat completions provider."""

    def __init__(self, api_key: str, model: str):
        super().__init__(api_key=api_key, model=model)
        self._client = None  # Lazy init

    def _get_client(self) -> "OpenAI":
        if self._client is None:
            self._client = OpenAI(api_key=self.api_key)
        return self._client

    def complete(self, request: LLMRequest) -> LLMResponse:
        """
        Call OpenAI chat.completions.create.

        Args:
            request: LLMRequest with messages, temperature, max_tokens, json_mode

        Returns:
            LLMResponse with content, token counts, cost, latency.

        Raises:
            RateLimitError, APIError, APITimeoutError on failures.
        """
        kwargs = {
            "model": self.model,
            "messages": request.messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }

        if request.json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        start_time = time.monotonic()
        response = self._get_client().chat.completions.create(**kwargs)
        latency_ms = int((time.monotonic() - start_time) * 1000)

        content = response.choices[0].message.content or ""
        usage = response.usage

        prompt_tokens = usage.prompt_tokens if usage else 0
        completion_tokens = usage.completion_tokens if usage else 0
        total_tokens = usage.total_tokens if usage else 0

        cost = estimate_cost_cents(
            provider="openai",
            model=self.model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )

        return LLMResponse(
            content=content,
            provider="openai",
            model=self.model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            estimated_cost_cents=cost,
            latency_ms=latency_ms,
            was_fallback=False,
            fallback_reason=None,
        )

    def validate_key(self) -> Tuple[bool, str]:
        """
        Validate the API key by listing models.

        Returns:
            (True, "") on success, (False, error_message) on failure.
        """
        try:
            self._get_client().models.list()
            return True, ""
        except AuthenticationError as e:
            return False, str(e)
        except Exception as e:
            return False, str(e)
