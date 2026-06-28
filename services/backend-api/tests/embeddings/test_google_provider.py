"""
Phase 3 RED: Tests for GoogleEmbeddingProvider.

AC3: google provider normalizes its response to list[float].
- Mock google.generativeai client; assert embed() returns list[float]
- dimension matches the response length (768 for text-embedding-004)
- api_key is configurable (injectable)
- model is injectable (defaults to text-embedding-004)
- Tests pass without the Google SDK actually installed (mock is at module level)
"""

import pytest
from unittest.mock import MagicMock, patch

from src.services.embeddings.providers.google import GoogleEmbeddingProvider

_FAKE_VECTOR_768 = [0.001 * i for i in range(768)]


class TestGoogleEmbeddingProvider:
    """Tests for the Google (Gemini) embedding provider."""

    def test_embed_returns_list_of_floats(self):
        """embed() must return list[float] normalized from the SDK response."""
        mock_genai = MagicMock()
        mock_genai.embed_content.return_value = {"embedding": _FAKE_VECTOR_768}

        with patch(
            "src.services.embeddings.providers.google.genai",
            mock_genai,
        ):
            provider = GoogleEmbeddingProvider(
                api_key="AIza-test", model="models/text-embedding-004"
            )
            result = provider.embed("test text")

        assert isinstance(result, list)
        assert len(result) == 768
        assert all(isinstance(v, float) for v in result)

    def test_dimension_derived_from_response(self):
        """dimension must equal len(response embedding), not a hardcoded value."""
        mock_genai = MagicMock()
        mock_genai.embed_content.return_value = {"embedding": _FAKE_VECTOR_768}

        with patch(
            "src.services.embeddings.providers.google.genai",
            mock_genai,
        ):
            provider = GoogleEmbeddingProvider(
                api_key="AIza-test", model="models/text-embedding-004"
            )
            provider.embed("hi")

        assert provider.dimension == 768

    def test_api_key_is_configured(self):
        """genai must be configured with the provided api_key."""
        mock_genai = MagicMock()
        mock_genai.embed_content.return_value = {"embedding": _FAKE_VECTOR_768}

        with patch(
            "src.services.embeddings.providers.google.genai",
            mock_genai,
        ):
            provider = GoogleEmbeddingProvider(
                api_key="AIza-secret", model="models/text-embedding-004"
            )
            provider.embed("hello")

        mock_genai.configure.assert_called_once_with(api_key="AIza-secret")

    def test_model_forwarded_to_embed_content(self):
        """The configured model must be passed to genai.embed_content."""
        mock_genai = MagicMock()
        mock_genai.embed_content.return_value = {"embedding": _FAKE_VECTOR_768}

        with patch(
            "src.services.embeddings.providers.google.genai",
            mock_genai,
        ):
            provider = GoogleEmbeddingProvider(
                api_key="AIza-test", model="models/text-embedding-004"
            )
            provider.embed("some text")

        call_kwargs = mock_genai.embed_content.call_args
        assert call_kwargs is not None
        # model and content must be in the call
        assert "models/text-embedding-004" in str(call_kwargs)
        assert "some text" in str(call_kwargs)

    def test_default_model_constant(self):
        """DEFAULT_MODEL must be text-embedding-004."""
        assert GoogleEmbeddingProvider.DEFAULT_MODEL == "models/text-embedding-004"

    def test_different_vector_sizes_respected(self):
        """If mock returns a 1024-dim vector, dimension must be 1024."""
        vector_1024 = [0.0] * 1024
        mock_genai = MagicMock()
        mock_genai.embed_content.return_value = {"embedding": vector_1024}

        with patch(
            "src.services.embeddings.providers.google.genai",
            mock_genai,
        ):
            provider = GoogleEmbeddingProvider(
                api_key="AIza-test", model="models/text-embedding-004"
            )
            result = provider.embed("text")

        assert len(result) == 1024
        assert provider.dimension == 1024

    def test_empty_api_key_raises(self):
        """Empty api_key must raise a ValueError."""
        with pytest.raises(ValueError):
            GoogleEmbeddingProvider(api_key="", model="models/text-embedding-004")

    def test_response_normalized_to_python_floats(self):
        """Even if response contains non-float values, output must be list[float]."""
        # Some SDK versions may return numpy floats or other types
        int_vector = [i for i in range(768)]  # plain ints
        mock_genai = MagicMock()
        mock_genai.embed_content.return_value = {"embedding": int_vector}

        with patch(
            "src.services.embeddings.providers.google.genai",
            mock_genai,
        ):
            provider = GoogleEmbeddingProvider(
                api_key="AIza-test", model="models/text-embedding-004"
            )
            result = provider.embed("text")

        assert all(isinstance(v, float) for v in result)
