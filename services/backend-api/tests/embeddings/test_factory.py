"""
Phase 4 RED: Tests for EmbeddingProviderFactory.

- create("openai", api_key="k", model=None) → OpenAIEmbeddingProvider
- create("openai_compatible", base_url=..., model="nomic-embed-text") → OpenAICompatibleEmbeddingProvider
- create("ollama", ...) → OpenAICompatibleEmbeddingProvider with default base_url localhost:11434/v1
- create("google", ...) → GoogleEmbeddingProvider
- create("local", ...) → LocalEmbeddingProvider (Aspect 2 / Task 2, local-embedding-quality)
- create("anthropic", ...) raises ValueError("no first-party embeddings API")
- create("", ...) raises ValueError
- create("unknown_xyz", ...) raises ValueError

LocalEmbeddingProvider construction is safe to call directly (no mocking
needed): __init__ never loads the model (see providers/local.py), so these
tests stay offline/fast without patching sentence_transformers.
"""

import pytest

from src.services.embeddings.factory import EmbeddingProviderFactory
from src.services.embeddings.providers.openai import OpenAIEmbeddingProvider
from src.services.embeddings.providers.openai_compatible import (
    OpenAICompatibleEmbeddingProvider,
)
from src.services.embeddings.providers.google import GoogleEmbeddingProvider
from src.services.embeddings.providers.local import LocalEmbeddingProvider


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

    def test_create_local_returns_local_provider(self):
        """create('local') → LocalEmbeddingProvider (Aspect 2 / Task 2)."""
        provider = EmbeddingProviderFactory.create("local")
        assert isinstance(provider, LocalEmbeddingProvider)

    def test_create_local_default_model_is_bge_small(self):
        """Without model, local provider must default to LocalEmbeddingProvider.DEFAULT_MODEL."""
        provider = EmbeddingProviderFactory.create("local")
        assert provider._model == LocalEmbeddingProvider.DEFAULT_MODEL
        assert provider._model == "BAAI/bge-small-en-v1.5"

    def test_create_local_with_custom_model(self):
        """create('local', model='x') must respect the override."""
        provider = EmbeddingProviderFactory.create("local", model="x")
        assert provider._model == "x"

    def test_create_local_ignores_api_key_and_base_url(self):
        """local is keyless — api_key/base_url must be accepted but ignored."""
        provider = EmbeddingProviderFactory.create(
            "local", api_key="unused-key", base_url="http://unused/v1"
        )
        assert isinstance(provider, LocalEmbeddingProvider)

    def test_create_anthropic_raises_value_error(self):
        """Anthropic has no embeddings API; factory must raise clear ValueError."""
        with pytest.raises(ValueError) as exc_info:
            EmbeddingProviderFactory.create("anthropic", api_key="sk-ant-test")
        assert "embeddings" in str(exc_info.value).lower()

    def test_create_unknown_provider_raises_value_error(self):
        """Unknown provider name must raise ValueError."""
        with pytest.raises(ValueError):
            EmbeddingProviderFactory.create("cohere", api_key="key")

    def test_unknown_provider_error_lists_local_as_supported(self):
        """The 'Supported: ...' error message must list 'local' (Task 2 wiring)."""
        with pytest.raises(ValueError) as exc_info:
            EmbeddingProviderFactory.create("cohere", api_key="key")
        assert "local" in str(exc_info.value)

    def test_create_empty_provider_raises_value_error(self):
        """Empty provider string must raise ValueError."""
        with pytest.raises(ValueError):
            EmbeddingProviderFactory.create("", api_key="key")

    def test_factory_create_is_static_method(self):
        """create must be callable without instantiating the factory."""
        provider = EmbeddingProviderFactory.create("openai", api_key="sk-test")
        assert provider is not None
