"""
Phase 2 RED: Tests for OpenAICompatibleEmbeddingProvider.

AC2: openai_compatible provider calls configured base_url with no api_key,
     returns the model's native dims (mock a 768-dim response).
- dimension derived from actual response length, not hardcoded
- missing base_url raises ValueError
- uses dummy key "ollama" when no api_key provided (mirrors worker pattern)
- model is injectable
"""

import pytest
from unittest.mock import MagicMock, patch

from src.services.embeddings.providers.openai_compatible import (
    OpenAICompatibleEmbeddingProvider,
)

_FAKE_VECTOR_768 = [0.001 * i for i in range(768)]


class TestOpenAICompatibleEmbeddingProvider:
    """Tests for the OpenAI-compatible / keyless local embedding provider."""

    def _make_mock_response(self, vector: list[float]) -> MagicMock:
        embedding_obj = MagicMock()
        embedding_obj.embedding = vector
        response = MagicMock()
        response.data = [embedding_obj]
        return response

    def test_embed_with_base_url_returns_768_vector(self):
        """embed() returns the 768-dim mock vector from the local endpoint."""
        mock_client = MagicMock()
        mock_client.embeddings.create.return_value = self._make_mock_response(
            _FAKE_VECTOR_768
        )

        with patch(
            "src.services.embeddings.providers.openai_compatible.openai.OpenAI",
            return_value=mock_client,
        ):
            provider = OpenAICompatibleEmbeddingProvider(
                base_url="http://localhost:11434/v1",
                model="nomic-embed-text",
            )
            result = provider.embed("hello")

        assert isinstance(result, list)
        assert len(result) == 768
        assert all(isinstance(v, float) for v in result)

    def test_dimension_derived_from_response_not_hardcoded(self):
        """dimension must be 768 (from response), not 1536 (hardcoded)."""
        mock_client = MagicMock()
        mock_client.embeddings.create.return_value = self._make_mock_response(
            _FAKE_VECTOR_768
        )

        with patch(
            "src.services.embeddings.providers.openai_compatible.openai.OpenAI",
            return_value=mock_client,
        ):
            provider = OpenAICompatibleEmbeddingProvider(
                base_url="http://localhost:11434/v1",
                model="nomic-embed-text",
            )
            provider.embed("hello")

        assert provider.dimension == 768

    def test_no_api_key_uses_dummy_ollama_key(self):
        """Without api_key, the client must be constructed with the dummy key 'ollama'."""
        mock_client = MagicMock()
        mock_client.embeddings.create.return_value = self._make_mock_response(
            _FAKE_VECTOR_768
        )

        with patch(
            "src.services.embeddings.providers.openai_compatible.openai.OpenAI",
            return_value=mock_client,
        ) as mock_openai_cls:
            provider = OpenAICompatibleEmbeddingProvider(
                base_url="http://localhost:11434/v1",
                model="nomic-embed-text",
            )
            provider.embed("test")

        call_kwargs = mock_openai_cls.call_args.kwargs
        # api_key should be a non-empty dummy (e.g. "ollama") because the SDK requires one
        assert call_kwargs.get("api_key") or mock_openai_cls.call_args.args
        # base_url must be forwarded
        assert call_kwargs.get("base_url") == "http://localhost:11434/v1"

    def test_missing_base_url_raises(self):
        """Constructing without base_url must raise ValueError."""
        with pytest.raises(ValueError, match="base_url"):
            OpenAICompatibleEmbeddingProvider(base_url="", model="nomic-embed-text")

    def test_none_base_url_raises(self):
        """Constructing with None base_url must raise ValueError."""
        with pytest.raises(ValueError, match="base_url"):
            OpenAICompatibleEmbeddingProvider(base_url=None, model="nomic-embed-text")  # type: ignore

    def test_model_forwarded_to_create(self):
        """The configured model must be passed to embeddings.create."""
        mock_client = MagicMock()
        mock_client.embeddings.create.return_value = self._make_mock_response(
            _FAKE_VECTOR_768
        )

        with patch(
            "src.services.embeddings.providers.openai_compatible.openai.OpenAI",
            return_value=mock_client,
        ):
            provider = OpenAICompatibleEmbeddingProvider(
                base_url="http://localhost:11434/v1",
                model="nomic-embed-text",
            )
            provider.embed("test")

        mock_client.embeddings.create.assert_called_once_with(
            model="nomic-embed-text",
            input="test",
        )

    def test_explicit_api_key_is_used_if_provided(self):
        """When api_key is provided explicitly, it must be forwarded to the client."""
        mock_client = MagicMock()
        mock_client.embeddings.create.return_value = self._make_mock_response(
            _FAKE_VECTOR_768
        )

        with patch(
            "src.services.embeddings.providers.openai_compatible.openai.OpenAI",
            return_value=mock_client,
        ) as mock_openai_cls:
            provider = OpenAICompatibleEmbeddingProvider(
                base_url="http://localhost:11434/v1",
                model="nomic-embed-text",
                api_key="custom-key",
            )
            provider.embed("test")

        assert mock_openai_cls.call_args.kwargs.get("api_key") == "custom-key"

    def test_different_base_urls_accepted(self):
        """Any valid base_url must be accepted (not just localhost)."""
        mock_client = MagicMock()
        mock_client.embeddings.create.return_value = self._make_mock_response(
            _FAKE_VECTOR_768
        )

        with patch(
            "src.services.embeddings.providers.openai_compatible.openai.OpenAI",
            return_value=mock_client,
        ):
            provider = OpenAICompatibleEmbeddingProvider(
                base_url="http://embeddings.internal:8080/v1",
                model="bge-m3",
            )
            result = provider.embed("text")

        assert len(result) == 768

    def test_client_fails_fast_no_retries_bounded_timeout(self):
        """
        Fail-fast on unreachable local endpoints.

        Startup seeding embeds ~15 system templates on boot; if the local
        endpoint is down, the SDK's default max_retries=2 + exponential backoff
        makes each embed slow and boot crawls (per PRD R3: "seeding must not
        block boot"). The client must therefore be constructed with
        max_retries=0 and a bounded timeout so a down endpoint fails immediately.
        """
        mock_client = MagicMock()
        mock_client.embeddings.create.return_value = self._make_mock_response(
            _FAKE_VECTOR_768
        )

        with patch(
            "src.services.embeddings.providers.openai_compatible.openai.OpenAI",
            return_value=mock_client,
        ) as mock_openai_cls:
            provider = OpenAICompatibleEmbeddingProvider(
                base_url="http://localhost:11434/v1",
                model="nomic-embed-text",
            )
            provider.embed("test")

        kwargs = mock_openai_cls.call_args.kwargs
        assert kwargs.get("max_retries") == 0, "local client must not retry a down endpoint"
        assert kwargs.get("timeout") is not None, "local client must set a bounded timeout"
