"""
LLM Provider Factory — creates provider instances by name.
"""

from src.llm.base import LLMProvider


class LLMProviderFactory:
    """Factory for creating LLM provider instances."""

    @staticmethod
    def create(provider: str, api_key: str, model: str) -> LLMProvider:
        """
        Create an LLMProvider for the given provider name.

        Args:
            provider: "openai", "anthropic", or "google"
            api_key: API key for the provider
            model: Model ID to use (e.g., "gpt-4o-mini")

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
        else:
            raise ValueError(f"Unknown provider: {provider!r}")
