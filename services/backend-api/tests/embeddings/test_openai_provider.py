"""
Phase 2 RED: Tests for OpenAIEmbeddingProvider.

AC1: openai provider returns a 1536-dim vector (mocked client) for given text.
- Mock openai.OpenAI client
- Assert embed("hi") returns a list of 1536 floats
- Assert .dimension == 1536 (derived from response, not hardcoded)
- Assert empty api_key raises a clear ValueError
- Assert model is injectable (no hardcoded model in calls)
"""

import pytest
from unittest.mock import MagicMock, patch

from src.services.embeddings.providers.openai import OpenAIEmbeddingProvider

_FAKE_VECTOR_1536 = [0.001 * i for i in range(1536)]


class TestOpenAIEmbeddingProvider:
    """Tests for the OpenAI embedding provider."""

    def _make_mock_response(self, vector: list[float]) -> MagicMock:
        """Build the minimal openai response object shape."""
        embedding_obj = MagicMock()
        embedding_obj.embedding = vector
        response = MagicMock()
        response.data = [embedding_obj]
        return response

    def test_embed_returns_1536_float_list(self):
        """embed() must return the 1536-dim vector from the mocked client."""
        mock_client = MagicMock()
        mock_client.embeddings.create.return_value = self._make_mock_response(
            _FAKE_VECTOR_1536
        )

        with patch(
            "src.services.embeddings.providers.openai.openai.OpenAI",
            return_value=mock_client,
        ):
            provider = OpenAIEmbeddingProvider(
                api_key="sk-test", model="text-embedding-3-small"
            )
            result = provider.embed("hi")

        assert isinstance(result, list)
        assert len(result) == 1536
        assert all(isinstance(v, float) for v in result)

    def test_dimension_derived_from_response(self):
        """dimension must equal len(actual embedding), not a hardcoded constant."""
        mock_client = MagicMock()
        mock_client.embeddings.create.return_value = self._make_mock_response(
            _FAKE_VECTOR_1536
        )

        with patch(
            "src.services.embeddings.providers.openai.openai.OpenAI",
            return_value=mock_client,
        ):
            provider = OpenAIEmbeddingProvider(
                api_key="sk-test", model="text-embedding-3-small"
            )
            provider.embed("hi")  # prime the cached dimension

        assert provider.dimension == 1536

    def test_model_is_passed_to_api_call(self):
        """The configured model must be forwarded to embeddings.create."""
        mock_client = MagicMock()
        mock_client.embeddings.create.return_value = self._make_mock_response(
            _FAKE_VECTOR_1536
        )

        with patch(
            "src.services.embeddings.providers.openai.openai.OpenAI",
            return_value=mock_client,
        ):
            provider = OpenAIEmbeddingProvider(
                api_key="sk-test", model="text-embedding-3-small"
            )
            provider.embed("test text")

        mock_client.embeddings.create.assert_called_once_with(
            model="text-embedding-3-small",
            input="test text",
        )

    def test_empty_api_key_raises_value_error(self):
        """Empty api_key must raise ValueError with a clear message."""
        with pytest.raises((ValueError, RuntimeError)):
            provider = OpenAIEmbeddingProvider(api_key="", model="text-embedding-3-small")
            provider.embed("hi")

    def test_none_api_key_raises(self):
        """None api_key must raise ValueError or RuntimeError."""
        with pytest.raises((ValueError, RuntimeError, TypeError)):
            provider = OpenAIEmbeddingProvider(api_key=None, model="text-embedding-3-small")  # type: ignore
            provider.embed("hi")

    def test_default_model_constant_is_text_embedding_3_small(self):
        """The default model must be text-embedding-3-small."""
        assert OpenAIEmbeddingProvider.DEFAULT_MODEL == "text-embedding-3-small"

    def test_dimension_returns_response_length_not_hardcoded(self):
        """If model returns 768 dims, dimension must be 768, not 1536."""
        vector_768 = [0.0] * 768
        mock_client = MagicMock()
        mock_client.embeddings.create.return_value = self._make_mock_response(vector_768)

        with patch(
            "src.services.embeddings.providers.openai.openai.OpenAI",
            return_value=mock_client,
        ):
            provider = OpenAIEmbeddingProvider(
                api_key="sk-test", model="text-embedding-3-large"
            )
            result = provider.embed("test")

        assert len(result) == 768
        assert provider.dimension == 768
