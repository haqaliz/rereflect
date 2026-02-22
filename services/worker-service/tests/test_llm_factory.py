"""
Tests for LLMProviderFactory.
"""

import pytest
from unittest.mock import patch


class TestLLMProviderFactory:
    """Tests for LLMProviderFactory.create()."""

    def test_creates_openai_provider(self):
        """Should create an OpenAIProvider for 'openai'."""
        from src.llm.factory import LLMProviderFactory
        from src.llm.providers.openai import OpenAIProvider

        with patch("src.llm.providers.openai.OpenAI"):
            provider = LLMProviderFactory.create("openai", "sk-test", "gpt-4o-mini")

        assert isinstance(provider, OpenAIProvider)

    def test_creates_anthropic_provider(self):
        """Should create an AnthropicProvider for 'anthropic'."""
        from src.llm.factory import LLMProviderFactory
        from src.llm.providers.anthropic import AnthropicProvider

        with patch("src.llm.providers.anthropic.Anthropic"):
            provider = LLMProviderFactory.create("anthropic", "sk-ant-test", "claude-haiku-4-5")

        assert isinstance(provider, AnthropicProvider)

    def test_creates_google_provider(self):
        """Should create a GoogleProvider for 'google'."""
        from src.llm.factory import LLMProviderFactory
        from src.llm.providers.google import GoogleProvider

        with patch("src.llm.providers.google.genai"):
            provider = LLMProviderFactory.create("google", "google-test", "gemini-2.0-flash")

        assert isinstance(provider, GoogleProvider)

    def test_raises_on_unknown_provider(self):
        """Should raise ValueError for unknown provider."""
        from src.llm.factory import LLMProviderFactory

        with pytest.raises(ValueError, match="Unknown provider"):
            LLMProviderFactory.create("unknown_provider", "key", "model")

    def test_raises_on_empty_provider(self):
        """Should raise ValueError for empty provider string."""
        from src.llm.factory import LLMProviderFactory

        with pytest.raises(ValueError):
            LLMProviderFactory.create("", "key", "model")

    def test_provider_has_correct_model(self):
        """Created provider should use the specified model."""
        from src.llm.factory import LLMProviderFactory

        with patch("src.llm.providers.openai.OpenAI"):
            provider = LLMProviderFactory.create("openai", "sk-test", "gpt-4o")

        assert provider.model == "gpt-4o"

    def test_provider_has_correct_api_key(self):
        """Created provider should store the api_key."""
        from src.llm.factory import LLMProviderFactory

        with patch("src.llm.providers.openai.OpenAI"):
            provider = LLMProviderFactory.create("openai", "sk-custom-key", "gpt-4o-mini")

        assert provider.api_key == "sk-custom-key"
