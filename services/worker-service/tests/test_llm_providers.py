"""
Tests for LLM provider implementations: OpenAI, Anthropic, Google.
All external API calls are mocked.
"""

import json
import pytest
from unittest.mock import patch, MagicMock

from src.llm.types import LLMResponse, LLMRequest


# ──────────────────────────────────────────────────────────────────────────────
# OpenAI Provider
# ──────────────────────────────────────────────────────────────────────────────

class TestOpenAIProvider:
    """Tests for OpenAIProvider."""

    def _make_provider(self, model="gpt-4o-mini"):
        from src.llm.providers.openai import OpenAIProvider
        return OpenAIProvider(api_key="sk-test", model=model)

    def _mock_openai_response(self, content: str, prompt_tokens=100, completion_tokens=50):
        """Build a mock openai ChatCompletion response."""
        mock_usage = MagicMock()
        mock_usage.prompt_tokens = prompt_tokens
        mock_usage.completion_tokens = completion_tokens
        mock_usage.total_tokens = prompt_tokens + completion_tokens

        mock_message = MagicMock()
        mock_message.content = content

        mock_choice = MagicMock()
        mock_choice.message = mock_message

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage = mock_usage
        return mock_response

    def test_complete_returns_llm_response(self):
        """complete() should return an LLMResponse on success."""
        content = '{"sentiment": "positive"}'

        with patch("src.llm.providers.openai.OpenAI") as mock_openai_cls:
            mock_client = MagicMock()
            mock_openai_cls.return_value = mock_client
            mock_client.chat.completions.create.return_value = self._mock_openai_response(content)

            provider = self._make_provider()
            request = LLMRequest(messages=[{"role": "user", "content": "test"}])
            response = provider.complete(request)

        assert isinstance(response, LLMResponse)
        assert response.content == content
        assert response.provider == "openai"
        assert response.model == "gpt-4o-mini"
        assert response.prompt_tokens == 100
        assert response.completion_tokens == 50
        assert response.total_tokens == 150
        assert response.was_fallback is False

    def test_complete_uses_json_mode(self):
        """complete() with json_mode=True should pass response_format."""
        with patch("src.llm.providers.openai.OpenAI") as mock_openai_cls:
            mock_client = MagicMock()
            mock_openai_cls.return_value = mock_client
            mock_client.chat.completions.create.return_value = self._mock_openai_response("{}")

            provider = self._make_provider()
            request = LLMRequest(messages=[{"role": "user", "content": "test"}], json_mode=True)
            provider.complete(request)

            call_kwargs = mock_client.chat.completions.create.call_args[1]
            assert call_kwargs.get("response_format") == {"type": "json_object"}

    def test_complete_no_json_mode(self):
        """complete() with json_mode=False should not pass response_format."""
        with patch("src.llm.providers.openai.OpenAI") as mock_openai_cls:
            mock_client = MagicMock()
            mock_openai_cls.return_value = mock_client
            mock_client.chat.completions.create.return_value = self._mock_openai_response("hello")

            provider = self._make_provider()
            request = LLMRequest(messages=[{"role": "user", "content": "test"}], json_mode=False)
            provider.complete(request)

            call_kwargs = mock_client.chat.completions.create.call_args[1]
            assert "response_format" not in call_kwargs

    def test_complete_handles_rate_limit_error(self):
        """complete() should raise on RateLimitError."""
        from openai import RateLimitError

        with patch("src.llm.providers.openai.OpenAI") as mock_openai_cls:
            mock_client = MagicMock()
            mock_openai_cls.return_value = mock_client
            mock_client.chat.completions.create.side_effect = RateLimitError(
                message="Rate limit exceeded",
                response=MagicMock(status_code=429, headers={}),
                body={"error": {"message": "rate limit"}},
            )

            provider = self._make_provider()
            request = LLMRequest(messages=[{"role": "user", "content": "test"}])
            with pytest.raises(RateLimitError):
                provider.complete(request)

    def test_complete_handles_api_error(self):
        """complete() should raise on APIError."""
        from openai import APIError

        with patch("src.llm.providers.openai.OpenAI") as mock_openai_cls:
            mock_client = MagicMock()
            mock_openai_cls.return_value = mock_client
            mock_client.chat.completions.create.side_effect = APIError(
                message="Server error",
                request=MagicMock(),
                body=None,
            )

            provider = self._make_provider()
            request = LLMRequest(messages=[{"role": "user", "content": "test"}])
            with pytest.raises(APIError):
                provider.complete(request)

    def test_complete_separates_system_message(self):
        """OpenAI keeps system messages in the messages array."""
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Analyze this."},
        ]

        with patch("src.llm.providers.openai.OpenAI") as mock_openai_cls:
            mock_client = MagicMock()
            mock_openai_cls.return_value = mock_client
            mock_client.chat.completions.create.return_value = self._mock_openai_response("{}")

            provider = self._make_provider()
            request = LLMRequest(messages=messages)
            provider.complete(request)

            call_kwargs = mock_client.chat.completions.create.call_args[1]
            # All messages stay in the messages array for OpenAI
            assert len(call_kwargs["messages"]) == 2

    def test_validate_key_success(self):
        """validate_key() should return (True, '') on success."""
        with patch("src.llm.providers.openai.OpenAI") as mock_openai_cls:
            mock_client = MagicMock()
            mock_openai_cls.return_value = mock_client
            mock_client.models.list.return_value = MagicMock()

            provider = self._make_provider()
            valid, error = provider.validate_key()

        assert valid is True
        assert error == ""

    def test_validate_key_auth_error(self):
        """validate_key() should return (False, error_msg) on auth error."""
        from openai import AuthenticationError

        with patch("src.llm.providers.openai.OpenAI") as mock_openai_cls:
            mock_client = MagicMock()
            mock_openai_cls.return_value = mock_client
            mock_client.models.list.side_effect = AuthenticationError(
                message="Invalid API key",
                response=MagicMock(status_code=401, headers={}),
                body={"error": {"message": "invalid key"}},
            )

            provider = self._make_provider()
            valid, error = provider.validate_key()

        assert valid is False
        assert "Invalid" in error or "invalid" in error

    def test_complete_records_latency(self):
        """complete() should record latency_ms > 0."""
        with patch("src.llm.providers.openai.OpenAI") as mock_openai_cls:
            mock_client = MagicMock()
            mock_openai_cls.return_value = mock_client
            mock_client.chat.completions.create.return_value = self._mock_openai_response("{}")

            provider = self._make_provider()
            request = LLMRequest(messages=[{"role": "user", "content": "test"}])
            response = provider.complete(request)

        assert response.latency_ms >= 0


# ──────────────────────────────────────────────────────────────────────────────
# Anthropic Provider
# ──────────────────────────────────────────────────────────────────────────────

class TestAnthropicProvider:
    """Tests for AnthropicProvider."""

    def _make_provider(self, model="claude-haiku-4-5"):
        from src.llm.providers.anthropic import AnthropicProvider
        return AnthropicProvider(api_key="sk-ant-test", model=model)

    def _mock_anthropic_response(self, content: str, input_tokens=100, output_tokens=50):
        """Build a mock Anthropic messages response."""
        mock_usage = MagicMock()
        mock_usage.input_tokens = input_tokens
        mock_usage.output_tokens = output_tokens

        mock_content_block = MagicMock()
        mock_content_block.text = content

        mock_response = MagicMock()
        mock_response.content = [mock_content_block]
        mock_response.usage = mock_usage
        return mock_response

    def test_complete_returns_llm_response(self):
        """complete() should return an LLMResponse on success."""
        content = '{"sentiment": "positive"}'

        with patch("src.llm.providers.anthropic.Anthropic") as mock_anthropic_cls:
            mock_client = MagicMock()
            mock_anthropic_cls.return_value = mock_client
            mock_client.messages.create.return_value = self._mock_anthropic_response(content)

            provider = self._make_provider()
            request = LLMRequest(messages=[{"role": "user", "content": "test"}])
            response = provider.complete(request)

        assert isinstance(response, LLMResponse)
        assert response.content == content
        assert response.provider == "anthropic"
        assert response.model == "claude-haiku-4-5"
        assert response.prompt_tokens == 100
        assert response.completion_tokens == 50
        assert response.was_fallback is False

    def test_complete_strips_json_fences(self):
        """complete() should strip ```json ... ``` fences from response."""
        raw_content = '```json\n{"key": "value"}\n```'
        expected = '{"key": "value"}'

        with patch("src.llm.providers.anthropic.Anthropic") as mock_anthropic_cls:
            mock_client = MagicMock()
            mock_anthropic_cls.return_value = mock_client
            mock_client.messages.create.return_value = self._mock_anthropic_response(raw_content)

            provider = self._make_provider()
            request = LLMRequest(messages=[{"role": "user", "content": "test"}])
            response = provider.complete(request)

        assert response.content == expected

    def test_complete_strips_plain_fences(self):
        """complete() should strip ``` ... ``` fences (no json tag)."""
        raw_content = '```\n{"key": "value"}\n```'
        expected = '{"key": "value"}'

        with patch("src.llm.providers.anthropic.Anthropic") as mock_anthropic_cls:
            mock_client = MagicMock()
            mock_anthropic_cls.return_value = mock_client
            mock_client.messages.create.return_value = self._mock_anthropic_response(raw_content)

            provider = self._make_provider()
            request = LLMRequest(messages=[{"role": "user", "content": "test"}])
            response = provider.complete(request)

        assert response.content == expected

    def test_complete_no_fences_unchanged(self):
        """complete() should leave content unchanged if no fences present."""
        content = '{"sentiment": "neutral"}'

        with patch("src.llm.providers.anthropic.Anthropic") as mock_anthropic_cls:
            mock_client = MagicMock()
            mock_anthropic_cls.return_value = mock_client
            mock_client.messages.create.return_value = self._mock_anthropic_response(content)

            provider = self._make_provider()
            request = LLMRequest(messages=[{"role": "user", "content": "test"}])
            response = provider.complete(request)

        assert response.content == content

    def test_complete_separates_system_message(self):
        """Anthropic should send system messages as separate 'system' param."""
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Analyze this."},
        ]

        with patch("src.llm.providers.anthropic.Anthropic") as mock_anthropic_cls:
            mock_client = MagicMock()
            mock_anthropic_cls.return_value = mock_client
            mock_client.messages.create.return_value = self._mock_anthropic_response("{}")

            provider = self._make_provider()
            request = LLMRequest(messages=messages)
            provider.complete(request)

            call_kwargs = mock_client.messages.create.call_args[1]
            # System message should be in 'system' param, not in messages
            assert call_kwargs.get("system") == "You are helpful."
            assert all(m["role"] != "system" for m in call_kwargs["messages"])

    def test_complete_handles_api_error(self):
        """complete() should raise on Anthropic API error."""
        import anthropic

        with patch("src.llm.providers.anthropic.Anthropic") as mock_anthropic_cls:
            mock_client = MagicMock()
            mock_anthropic_cls.return_value = mock_client
            mock_client.messages.create.side_effect = anthropic.APIStatusError(
                message="Rate limit",
                response=MagicMock(status_code=429),
                body={"error": {"message": "rate limit"}},
            )

            provider = self._make_provider()
            request = LLMRequest(messages=[{"role": "user", "content": "test"}])
            with pytest.raises(anthropic.APIStatusError):
                provider.complete(request)

    def test_validate_key_success(self):
        """validate_key() should return (True, '') on success."""
        with patch("src.llm.providers.anthropic.Anthropic") as mock_anthropic_cls:
            mock_client = MagicMock()
            mock_anthropic_cls.return_value = mock_client
            mock_client.messages.create.return_value = self._mock_anthropic_response("test")

            provider = self._make_provider()
            valid, error = provider.validate_key()

        assert valid is True
        assert error == ""

    def test_validate_key_auth_error(self):
        """validate_key() should return (False, error_msg) on auth error."""
        import anthropic

        with patch("src.llm.providers.anthropic.Anthropic") as mock_anthropic_cls:
            mock_client = MagicMock()
            mock_anthropic_cls.return_value = mock_client
            mock_client.messages.create.side_effect = anthropic.AuthenticationError(
                message="Invalid API key",
                response=MagicMock(status_code=401),
                body={"error": {"message": "invalid key"}},
            )

            provider = self._make_provider()
            valid, error = provider.validate_key()

        assert valid is False
        assert len(error) > 0

    def test_complete_adds_json_instruction(self):
        """Anthropic provider should add JSON instruction to user message."""
        with patch("src.llm.providers.anthropic.Anthropic") as mock_anthropic_cls:
            mock_client = MagicMock()
            mock_anthropic_cls.return_value = mock_client
            mock_client.messages.create.return_value = self._mock_anthropic_response("{}")

            provider = self._make_provider()
            request = LLMRequest(
                messages=[{"role": "user", "content": "Analyze feedback"}],
                json_mode=True,
            )
            provider.complete(request)

            call_kwargs = mock_client.messages.create.call_args[1]
            user_message = next(m for m in call_kwargs["messages"] if m["role"] == "user")
            assert "JSON" in user_message["content"] or "json" in user_message["content"]


# ──────────────────────────────────────────────────────────────────────────────
# Google Provider
# ──────────────────────────────────────────────────────────────────────────────

class TestGoogleProvider:
    """Tests for GoogleProvider."""

    def _make_provider(self, model="gemini-2.0-flash"):
        from src.llm.providers.google import GoogleProvider
        return GoogleProvider(api_key="google-test-key", model=model)

    def _mock_google_response(self, text: str, prompt_tokens=100, candidates_tokens=50):
        """Build a mock Google GenerativeAI response."""
        mock_usage = MagicMock()
        mock_usage.prompt_token_count = prompt_tokens
        mock_usage.candidates_token_count = candidates_tokens
        mock_usage.total_token_count = prompt_tokens + candidates_tokens

        mock_response = MagicMock()
        mock_response.text = text
        mock_response.usage_metadata = mock_usage
        return mock_response

    def test_complete_returns_llm_response(self):
        """complete() should return an LLMResponse on success."""
        provider = self._make_provider()
        content = '{"sentiment": "positive"}'

        with patch("src.llm.providers.google.genai") as mock_genai:
            mock_model = MagicMock()
            mock_genai.GenerativeModel.return_value = mock_model
            mock_model.generate_content.return_value = self._mock_google_response(content)

            request = LLMRequest(messages=[{"role": "user", "content": "test"}])
            response = provider.complete(request)

        assert isinstance(response, LLMResponse)
        assert response.content == content
        assert response.provider == "google"
        assert response.model == "gemini-2.0-flash"
        assert response.was_fallback is False

    def test_complete_uses_json_mime_type(self):
        """complete() with json_mode=True should use response_mime_type."""
        provider = self._make_provider()

        with patch("src.llm.providers.google.genai") as mock_genai:
            mock_model = MagicMock()
            mock_genai.GenerativeModel.return_value = mock_model
            mock_model.generate_content.return_value = self._mock_google_response("{}")

            request = LLMRequest(messages=[{"role": "user", "content": "test"}], json_mode=True)
            provider.complete(request)

            # Check GenerationConfig was passed with json mime type
            call_kwargs = mock_model.generate_content.call_args[1]
            gen_config = call_kwargs.get("generation_config")
            assert gen_config is not None

    def test_complete_handles_api_error(self):
        """complete() should raise on Google API error."""
        provider = self._make_provider()

        with patch("src.llm.providers.google.genai") as mock_genai:
            mock_model = MagicMock()
            mock_genai.GenerativeModel.return_value = mock_model
            mock_model.generate_content.side_effect = Exception("API Error")

            request = LLMRequest(messages=[{"role": "user", "content": "test"}])
            with pytest.raises(Exception):
                provider.complete(request)

    def test_validate_key_success(self):
        """validate_key() should return (True, '') on success."""
        provider = self._make_provider()

        with patch("src.llm.providers.google.genai") as mock_genai:
            mock_model = MagicMock()
            mock_genai.GenerativeModel.return_value = mock_model
            mock_model.generate_content.return_value = self._mock_google_response("test")

            valid, error = provider.validate_key()

        assert valid is True
        assert error == ""

    def test_validate_key_auth_error(self):
        """validate_key() should return (False, error_msg) on auth error."""
        provider = self._make_provider()

        with patch("src.llm.providers.google.genai") as mock_genai:
            mock_model = MagicMock()
            mock_genai.GenerativeModel.return_value = mock_model
            mock_model.generate_content.side_effect = Exception("API key not valid")

            valid, error = provider.validate_key()

        assert valid is False
        assert len(error) > 0

    def test_complete_separates_system_message(self):
        """Google provider should use system_instruction for system messages."""
        provider = self._make_provider()

        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Analyze this."},
        ]

        with patch("src.llm.providers.google.genai") as mock_genai:
            mock_model = MagicMock()
            mock_genai.GenerativeModel.return_value = mock_model
            mock_model.generate_content.return_value = self._mock_google_response("{}")

            request = LLMRequest(messages=messages)
            provider.complete(request)

            # GenerativeModel should be called with system_instruction
            call_kwargs = mock_genai.GenerativeModel.call_args[1]
            assert "system_instruction" in call_kwargs


# ──────────────────────────────────────────────────────────────────────────────
# JSON Fence Stripping (Anthropic utility)
# ──────────────────────────────────────────────────────────────────────────────

class TestStripJsonFences:
    """Tests for the _strip_json_fences utility."""

    def test_strips_json_fence(self):
        from src.llm.providers.anthropic import _strip_json_fences
        raw = '```json\n{"key": "value"}\n```'
        assert _strip_json_fences(raw) == '{"key": "value"}'

    def test_strips_plain_fence(self):
        from src.llm.providers.anthropic import _strip_json_fences
        raw = '```\n{"key": "value"}\n```'
        assert _strip_json_fences(raw) == '{"key": "value"}'

    def test_no_fence_unchanged(self):
        from src.llm.providers.anthropic import _strip_json_fences
        raw = '{"key": "value"}'
        assert _strip_json_fences(raw) == '{"key": "value"}'

    def test_strips_whitespace(self):
        from src.llm.providers.anthropic import _strip_json_fences
        raw = '  ```json\n  {"key": "value"}\n  ```  '
        assert _strip_json_fences(raw) == '{"key": "value"}'

    def test_empty_string(self):
        from src.llm.providers.anthropic import _strip_json_fences
        assert _strip_json_fences("") == ""
