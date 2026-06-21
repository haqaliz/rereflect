"""
OpenAI-compatible LLM provider.

Wraps the OpenAI client against a custom base_url, enabling local / offline
models (Ollama, LM Studio, vLLM, etc.) as drop-in replacements.

The api_key is optional: Ollama ignores it entirely; custom endpoints may
require one. We pass a dummy "ollama" string when none is provided, because
the upstream OpenAI client requires a non-empty value.

Usage:
    provider = OpenAICompatibleProvider(
        base_url="http://localhost:11434/v1",
        model="llama3",
        api_key=None,   # keyless local
    )
    response = provider.complete(request)

Note: This provider is NOT a cloud BYOK path — it requires no OrgApiKey row.
No environment API key is read here.
"""

import logging
import time
from typing import Optional, Tuple

from openai import OpenAI, RateLimitError, APIError, APITimeoutError, AuthenticationError

from src.llm.providers.openai import OpenAIProvider
from src.llm.types import LLMRequest, LLMResponse
from src.llm.pricing import estimate_cost_cents

logger = logging.getLogger(__name__)

_DUMMY_KEY = "ollama"  # non-empty placeholder required by the OpenAI SDK


class OpenAICompatibleProvider(OpenAIProvider):
    """
    Provider for any OpenAI-compatible inference server (Ollama, LM Studio, etc.).

    Subclasses OpenAIProvider to reuse complete() logic; overrides only
    client construction (adds base_url) and the provider label in LLMResponse.
    """

    def __init__(self, base_url: str, model: str, api_key: Optional[str] = None):
        # Use a dummy key when the caller passes None; Ollama ignores the value entirely.
        effective_key = api_key if api_key else _DUMMY_KEY
        super().__init__(api_key=effective_key, model=model)
        self.base_url = base_url
        self._client = None  # reset; _get_client() will use base_url

    def _get_client(self) -> "OpenAI":
        if self._client is None:
            self._client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
            )
        return self._client

    def complete(self, request: LLMRequest) -> LLMResponse:
        """
        Call the OpenAI-compatible endpoint.

        The response provider field is 'openai_compatible', not 'openai',
        so usage logs correctly attribute local vs. cloud calls.
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

        # Local models have $0 cost; estimate_cost_cents will return 0 for unknown models.
        cost = estimate_cost_cents(
            provider="openai_compatible",
            model=self.model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )

        return LLMResponse(
            content=content,
            provider="openai_compatible",
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
        Validate by listing available models on the local endpoint.
        Returns (True, "") if the endpoint responds; (False, error) otherwise.
        """
        try:
            self._get_client().models.list()
            return True, ""
        except AuthenticationError as e:
            return False, str(e)
        except Exception as e:
            return False, str(e)
