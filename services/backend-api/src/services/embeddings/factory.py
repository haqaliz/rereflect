"""
EmbeddingProviderFactory — creates embedding provider instances by name.

Mirrors the shape of services/worker-service/src/llm/factory.py (LLMProviderFactory)
for consistency. Cross-service import is prohibited; this is a backend-api–local copy
of the factory pattern.

Supported providers:
  "openai"            — OpenAI Embeddings API (BYOK key required)
  "openai_compatible" — Any OpenAI-API-compatible local/remote server (keyless)
  "ollama"            — Alias for openai_compatible with localhost:11434/v1 default
  "google"            — Google Generative AI Embeddings (BYOK key required)

Explicitly unsupported:
  "anthropic"         — Anthropic has no first-party embeddings API; raises ValueError.

Unknown providers raise ValueError.
"""

from __future__ import annotations

from typing import Optional

from src.services.embeddings.base import EmbeddingProvider

# Default Ollama base URL — same constant as worker-service factory
_OLLAMA_DEFAULT_BASE_URL = "http://localhost:11434/v1"


class EmbeddingProviderFactory:
    """Factory for creating EmbeddingProvider instances by provider name."""

    @staticmethod
    def create(
        provider: str,
        *,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ) -> EmbeddingProvider:
        """
        Create an EmbeddingProvider for the given provider name.

        Lazy imports per branch so that a missing optional SDK does not break
        the other providers (mirrors the worker factory pattern).

        Args:
            provider:  One of "openai", "openai_compatible", "ollama", "google".
                       "anthropic" raises a clear error (no embeddings API).
                       Empty or unknown strings raise ValueError.
            api_key:   API key for cloud providers (openai, google).
                       Ignored for keyless local providers (ollama, openai_compatible).
            base_url:  Base URL for local/compatible endpoints.
                       Optional for "ollama" (defaults to localhost:11434/v1).
                       Required for "openai_compatible".
            model:     Model ID. If None, provider-specific defaults apply:
                         openai            → text-embedding-3-small
                         ollama/compat     → caller must supply (no default)
                         google            → models/text-embedding-004

        Returns:
            Configured EmbeddingProvider instance.

        Raises:
            ValueError: If provider is empty, unknown, or is "anthropic".
        """
        if not provider:
            raise ValueError(
                f"Unknown embedding provider: {provider!r}. "
                f"Supported: openai, openai_compatible, ollama, google."
            )

        if provider == "openai":
            from src.services.embeddings.providers.openai import OpenAIEmbeddingProvider
            return OpenAIEmbeddingProvider(
                api_key=api_key or "",
                model=model or OpenAIEmbeddingProvider.DEFAULT_MODEL,
            )

        elif provider == "ollama":
            from src.services.embeddings.providers.openai_compatible import (
                OpenAICompatibleEmbeddingProvider,
            )
            effective_url = base_url or _OLLAMA_DEFAULT_BASE_URL
            return OpenAICompatibleEmbeddingProvider(
                base_url=effective_url,
                model=model or "nomic-embed-text",
                api_key=api_key or None,
            )

        elif provider == "openai_compatible":
            from src.services.embeddings.providers.openai_compatible import (
                OpenAICompatibleEmbeddingProvider,
            )
            return OpenAICompatibleEmbeddingProvider(
                base_url=base_url or "",
                model=model or "",
                api_key=api_key or None,
            )

        elif provider == "google":
            from src.services.embeddings.providers.google import GoogleEmbeddingProvider
            return GoogleEmbeddingProvider(
                api_key=api_key or "",
                model=model or GoogleEmbeddingProvider.DEFAULT_MODEL,
            )

        elif provider == "anthropic":
            raise ValueError(
                "Anthropic has no first-party embeddings API. "
                "Use 'openai', 'openai_compatible', 'ollama', or 'google' instead."
            )

        else:
            raise ValueError(
                f"Unknown embedding provider: {provider!r}. "
                f"Supported: openai, openai_compatible, ollama, google."
            )
