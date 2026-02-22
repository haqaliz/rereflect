"""
Google Generative AI (Gemini) LLM provider implementation.

Uses google-generativeai SDK.
JSON mode is handled via response_mime_type="application/json".
System messages are passed as system_instruction on model init.
"""

import logging
import time
from typing import Tuple

import google.generativeai as genai
from google.generativeai import GenerationConfig

from src.llm.base import LLMProvider
from src.llm.types import LLMRequest, LLMResponse
from src.llm.pricing import estimate_cost_cents

logger = logging.getLogger(__name__)


class GoogleProvider(LLMProvider):
    """Google Generative AI (Gemini) provider."""

    def __init__(self, api_key: str, model: str):
        super().__init__(api_key=api_key, model=model)
        genai.configure(api_key=api_key)

    def complete(self, request: LLMRequest) -> LLMResponse:
        """
        Call Google GenerativeModel.generate_content.

        System messages are passed as system_instruction to the model.
        JSON mode uses response_mime_type="application/json".

        Args:
            request: LLMRequest with messages, temperature, max_tokens, json_mode

        Returns:
            LLMResponse with content, token counts, cost, latency.

        Raises:
            Exception on API failures.
        """
        # Extract system message if present
        system_content = None
        user_messages = []
        for msg in request.messages:
            if msg["role"] == "system":
                system_content = msg["content"]
            else:
                user_messages.append(msg)

        # Build GenerativeModel kwargs
        model_kwargs = {"model_name": self.model}
        if system_content:
            model_kwargs["system_instruction"] = system_content

        model = genai.GenerativeModel(**model_kwargs)

        # Build GenerationConfig
        gen_config_kwargs = {
            "temperature": request.temperature,
            "max_output_tokens": request.max_tokens,
        }
        if request.json_mode:
            gen_config_kwargs["response_mime_type"] = "application/json"

        gen_config = GenerationConfig(**gen_config_kwargs)

        # Build contents from user messages (concatenate for simple case)
        contents = [msg["content"] for msg in user_messages if msg["role"] == "user"]
        prompt = "\n".join(contents)

        start_time = time.monotonic()
        response = model.generate_content(
            prompt,
            generation_config=gen_config,
        )
        latency_ms = int((time.monotonic() - start_time) * 1000)

        content = response.text or ""

        usage = getattr(response, "usage_metadata", None)
        prompt_tokens = getattr(usage, "prompt_token_count", 0) if usage else 0
        completion_tokens = getattr(usage, "candidates_token_count", 0) if usage else 0
        total_tokens = getattr(usage, "total_token_count", prompt_tokens + completion_tokens) if usage else 0

        cost = estimate_cost_cents(
            provider="google",
            model=self.model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )

        return LLMResponse(
            content=content,
            provider="google",
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
            model = genai.GenerativeModel(model_name=self.model)
            model.generate_content("test", generation_config=GenerationConfig(max_output_tokens=5))
            return True, ""
        except Exception as e:
            error_msg = str(e)
            return False, error_msg
