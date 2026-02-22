"""
Anthropic LLM provider implementation.

Uses messages.create API.
System messages are extracted into the separate 'system' parameter.
JSON mode is handled via prompt instruction + stripping markdown fences.
"""

import logging
import time
from typing import Tuple

import anthropic
from anthropic import Anthropic, AuthenticationError, APIStatusError

from src.llm.base import LLMProvider
from src.llm.types import LLMRequest, LLMResponse
from src.llm.pricing import estimate_cost_cents

logger = logging.getLogger(__name__)

_JSON_INSTRUCTION = "\n\nReturn ONLY valid JSON with no additional text or markdown."


def _strip_json_fences(content: str) -> str:
    """Remove ```json ... ``` or ``` ... ``` wrapping if present."""
    content = content.strip()
    if content.startswith("```json"):
        content = content[7:]
    elif content.startswith("```"):
        content = content[3:]
    if content.endswith("```"):
        content = content[:-3]
    return content.strip()


class AnthropicProvider(LLMProvider):
    """Anthropic messages provider."""

    def __init__(self, api_key: str, model: str):
        super().__init__(api_key=api_key, model=model)
        self._client = None  # Lazy init

    def _get_client(self) -> "Anthropic":
        if self._client is None:
            self._client = Anthropic(api_key=self.api_key)
        return self._client

    def complete(self, request: LLMRequest) -> LLMResponse:
        """
        Call Anthropic messages.create.

        System messages are extracted to the 'system' kwarg.
        JSON mode appends an instruction to the last user message.

        Args:
            request: LLMRequest with messages, temperature, max_tokens, json_mode

        Returns:
            LLMResponse with content (fences stripped), token counts, cost, latency.

        Raises:
            anthropic.APIStatusError and related exceptions on failures.
        """
        # Extract system message if present
        system_content = None
        user_messages = []
        for msg in request.messages:
            if msg["role"] == "system":
                system_content = msg["content"]
            else:
                user_messages.append(dict(msg))

        # Append JSON instruction to last user message if json_mode
        if request.json_mode and user_messages:
            last_msg = user_messages[-1]
            if last_msg["role"] == "user":
                user_messages[-1] = {
                    "role": "user",
                    "content": last_msg["content"] + _JSON_INSTRUCTION,
                }

        kwargs = {
            "model": self.model,
            "messages": user_messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }

        if system_content:
            kwargs["system"] = system_content

        start_time = time.monotonic()
        response = self._get_client().messages.create(**kwargs)
        latency_ms = int((time.monotonic() - start_time) * 1000)

        raw_content = response.content[0].text if response.content else ""

        # Strip markdown JSON fences from response
        content = _strip_json_fences(raw_content) if request.json_mode else raw_content

        usage = response.usage
        prompt_tokens = usage.input_tokens if usage else 0
        completion_tokens = usage.output_tokens if usage else 0
        total_tokens = prompt_tokens + completion_tokens

        cost = estimate_cost_cents(
            provider="anthropic",
            model=self.model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )

        return LLMResponse(
            content=content,
            provider="anthropic",
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
        Validate the API key by making a minimal test call.

        Returns:
            (True, "") on success, (False, error_message) on failure.
        """
        try:
            self._get_client().messages.create(
                model=self.model,
                messages=[{"role": "user", "content": "Hi"}],
                max_tokens=5,
            )
            return True, ""
        except AuthenticationError as e:
            return False, str(e)
        except Exception as e:
            return False, str(e)
