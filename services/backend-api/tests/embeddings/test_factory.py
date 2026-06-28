"""
Phase 4 RED: Tests for EmbeddingProviderFactory.

- create("openai", api_key="k", model=None) → OpenAIEmbeddingProvider
- create("openai_compatible", base_url=..., model="nomic-embed-text") → OpenAICompatibleEmbeddingProvider
- create("ollama", ...) → OpenAICompatibleEmbeddingProvider with default base_url localhost:11434/v1
- create("google", ...) → GoogleEmbeddingProvider
- create("anthropic", ...) raises ValueError("no first-party embeddings API")
- create("", ...) raises ValueError
- create("unknown_xyz", ...) raises ValueError
"""

import pytest

from src.services.embeddings.factory import EmbeddingProviderFactory
from src.services.embeddings.providers.openai import OpenAIEmbeddingProvider
from src.services.embeddings.providers.openai_compatible import (
    OpenAICompatibleEmbeddingProvider,
)
from src.services.embeddings.providers.google import GoogleEmbeddingProvider


class TestEmbeddingProviderFactory:
    """Tests for EmbeddingProviderFactory.create."""

    def test_create_openai_returns_openai_provider(self):
        """create('openai', api_key=...) must return OpenAIEmbeddingProvider."""
        provider = EmbeddingProviderFactory.create("openai", api_key="sk-test")
        assert isinstance(provider, OpenAIEmbeddingProvider)

    def test_create_openai_with_custom_model(self):
        """create('openai', model=...) must use the supplied model."""
        provider = EmbeddingProviderFactory.create(
            "openai", api_key="sk-test", model="text-embedding-3-large"
        )
        assert isinstance(provider, OpenAIEmbeddingProvider)
        assert provider._model == "text-embedding-3-large"

    def test_create_openai_default_model_is_text_embedding_3_small(self):
        """Without model, OpenAI provider must default to text-embedding-3-small."""
        provider = EmbeddingProviderFactory.create("openai", api_key="sk-test")
        assert provider._model == "text-embedding-3-small"

    def test_create_openai_compatible_returns_compatible_provider(self):
        """create('openai_compatible', base_url=...) → OpenAICompatibleEmbeddingProvider."""
        provider = EmbeddingProviderFactory.create(
            "openai_compatible",
            base_url="http://localhost:11434/v1",
            model="nomic-embed-text",
        )
        assert isinstance(provider, OpenAICompatibleEmbeddingProvider)

    def test_create_openai_compatible_uses_supplied_model(self):
        """The model must be forwarded to OpenAICompatibleEmbeddingProvider."""
        provider = EmbeddingProviderFactory.create(
            "openai_compatible",
            base_url="http://localhost:11434/v1",
            model="nomic-embed-text",
        )
        assert provider._model == "nomic-embed-text"

    def test_create_ollama_returns_openai_compatible_provider(self):
        """create('ollama', ...) → OpenAICompatibleEmbeddingProvider (alias)."""
        provider = EmbeddingProviderFactory.create(
            "ollama", model="nomic-embed-text"
        )
        assert isinstance(provider, OpenAICompatibleEmbeddingProvider)

    def test_create_ollama_uses_default_localhost_base_url(self):
        """When no base_url supplied, ollama must default to localhost:11434/v1."""
        provider = EmbeddingProviderFactory.create(
            "ollama", model="nomic-embed-text"
        )
        assert "localhost:11434" in provider._base_url
        assert provider._base_url.endswith("/v1")

    def test_create_ollama_with_custom_base_url(self):
        """Custom base_url overrides the ollama default."""
        provider = EmbeddingProviderFactory.create(
            "ollama",
            model="nomic-embed-text",
            base_url="http://gpu-box:11434/v1",
        )
        assert provider._base_url == "http://gpu-box:11434/v1"

    def test_create_google_returns_google_provider(self):
        """create('google', api_key=...) → GoogleEmbeddingProvider."""
        provider = EmbeddingProviderFactory.create("google", api_key="AIza-test")
        assert isinstance(provider, GoogleEmbeddingProvider)

    def test_create_google_default_model(self):
        """Without model, Google provider must default to models/text-embedding-004."""
        provider = EmbeddingProviderFactory.create("google", api_key="AIza-test")
        assert provider._model == "models/text-embedding-004"

    def test_create_google_with_custom_model(self):
        """Custom Google model must be forwarded."""
        provider = EmbeddingProviderFactory.create(
            "google", api_key="AIza-test", model="models/text-multilingual-embedding-002"
        )
        assert provider._model == "models/text-multilingual-embedding-002"

    def test_create_anthropic_raises_value_error(self):
        """Anthropic has no embeddings API; factory must raise clear ValueError."""
        with pytest.raises(ValueError) as exc_info:
            EmbeddingProviderFactory.create("anthropic", api_key="sk-ant-test")
        assert "embeddings" in str(exc_info.value).lower()

    def test_create_unknown_provider_raises_value_error(self):
        """Unknown provider name must raise ValueError."""
        with pytest.raises(ValueError):
            EmbeddingProviderFactory.create("cohere", api_key="key")

    def test_create_empty_provider_raises_value_error(self):
        """Empty provider string must raise ValueError."""
        with pytest.raises(ValueError):
            EmbeddingProviderFactory.create("", api_key="key")

    def test_factory_create_is_static_method(self):
        """create must be callable without instantiating the factory."""
        provider = EmbeddingProviderFactory.create("openai", api_key="sk-test")
        assert provider is not None
