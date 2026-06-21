"""
LLM Provider Factory — creates provider instances by name.
"""

from typing import Optional

from src.llm.base import LLMProvider

# Default base URL for Ollama when not explicitly configured
_OLLAMA_DEFAULT_BASE_URL = "http://localhost:11434/v1"


class LLMProviderFactory:
    """Factory for creating LLM provider instances."""

    @staticmethod
    def create(
        provider: str,
        api_key: str,
        model: str,
        base_url: Optional[str] = None,
    ) -> LLMProvider:
        """
        Create an LLMProvider for the given provider name.

        Args:
            provider: "openai", "anthropic", "google", "ollama", or
                      "openai_compatible"
            api_key: API key for cloud providers; ignored for keyless locals
            model: Model ID to use (e.g., "gpt-4o-mini", "llama3")
            base_url: Base URL for local/compatible endpoints; optional for
                      "ollama" (defaults to localhost:11434/v1), required for
                      "openai_compatible"

        Returns:
            Configured LLMProvider instance.

        Raises:
            ValueError: If provider is unknown or empty.
        """
        if not provider:
            raise ValueError(f"Unknown provider: {provider!r}")

        if provider == "openai":
            from src.llm.providers.openai import OpenAIProvider
            return OpenAIProvider(api_key=api_key, model=model)
        elif provider == "anthropic":
            from src.llm.providers.anthropic import AnthropicProvider
            return AnthropicProvider(api_key=api_key, model=model)
        elif provider == "google":
            from src.llm.providers.google import GoogleProvider
            return GoogleProvider(api_key=api_key, model=model)
        elif provider == "ollama":
            from src.llm.providers.openai_compatible import OpenAICompatibleProvider
            effective_url = base_url or _OLLAMA_DEFAULT_BASE_URL
            return OpenAICompatibleProvider(
                base_url=effective_url,
                model=model,
                api_key=api_key or None,
            )
        elif provider == "openai_compatible":
            from src.llm.providers.openai_compatible import OpenAICompatibleProvider
            return OpenAICompatibleProvider(
                base_url=base_url or "",
                model=model,
                api_key=api_key or None,
            )
        else:
            raise ValueError(f"Unknown provider: {provider!r}")
