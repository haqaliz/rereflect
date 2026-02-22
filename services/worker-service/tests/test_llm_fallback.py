"""
Tests for FallbackChain — retry + fallback logic.
All LLM calls are mocked. No real API calls.
"""

import pytest
from unittest.mock import patch, MagicMock, call
from dataclasses import dataclass

from src.llm.types import LLMResponse, LLMRequest


def _make_llm_response(provider="openai", was_fallback=False, fallback_reason=None):
    """Helper to build a successful LLMResponse."""
    return LLMResponse(
        content='{"ok": true}',
        provider=provider,
        model="gpt-4o-mini",
        prompt_tokens=100,
        completion_tokens=50,
        total_tokens=150,
        estimated_cost_cents=0.01,
        latency_ms=500,
        was_fallback=was_fallback,
        fallback_reason=fallback_reason,
    )


class TestFallbackChainSuccess:
    """Tests for the happy path — primary succeeds."""

    def test_primary_success_returns_response(self):
        """When primary provider succeeds, return its response directly."""
        from src.llm.fallback import FallbackChain

        mock_primary = MagicMock()
        mock_primary.complete.return_value = _make_llm_response("openai")

        chain = FallbackChain(primary_provider=mock_primary, system_provider=None)
        request = LLMRequest(messages=[{"role": "user", "content": "test"}])
        response = chain.complete(request)

        assert response.provider == "openai"
        assert response.was_fallback is False
        mock_primary.complete.assert_called_once()

    def test_primary_success_no_fallback_called(self):
        """When primary succeeds, fallback provider should never be called."""
        from src.llm.fallback import FallbackChain

        mock_primary = MagicMock()
        mock_primary.complete.return_value = _make_llm_response("anthropic")

        mock_system = MagicMock()

        chain = FallbackChain(primary_provider=mock_primary, system_provider=mock_system)
        request = LLMRequest(messages=[{"role": "user", "content": "test"}])
        chain.complete(request)

        mock_system.complete.assert_not_called()


class TestFallbackChainRetry:
    """Tests for retry logic on transient errors."""

    def test_rate_limit_triggers_retry(self):
        """429 RateLimitError should trigger exactly one retry."""
        from src.llm.fallback import FallbackChain
        from openai import RateLimitError

        rate_limit_error = RateLimitError(
            message="Rate limit exceeded",
            response=MagicMock(status_code=429, headers={}),
            body={"error": {"message": "rate limit"}},
        )
        success_response = _make_llm_response("openai")

        mock_primary = MagicMock()
        mock_primary.complete.side_effect = [rate_limit_error, success_response]

        chain = FallbackChain(primary_provider=mock_primary, system_provider=None)
        request = LLMRequest(messages=[{"role": "user", "content": "test"}])

        with patch("time.sleep"):  # Skip actual sleep
            response = chain.complete(request)

        assert response.provider == "openai"
        assert mock_primary.complete.call_count == 2

    def test_retry_succeeds_on_second_attempt(self):
        """After one failure, the second attempt should succeed."""
        from src.llm.fallback import FallbackChain
        from openai import APIError

        api_error = APIError(message="Server error", request=MagicMock(), body=None)
        success_response = _make_llm_response("openai")

        mock_primary = MagicMock()
        mock_primary.complete.side_effect = [api_error, success_response]

        chain = FallbackChain(primary_provider=mock_primary, system_provider=None)
        request = LLMRequest(messages=[{"role": "user", "content": "test"}])

        with patch("time.sleep"):
            response = chain.complete(request)

        assert response is success_response

    def test_retry_uses_backoff_sleep(self):
        """Retry should sleep with 2s backoff before retrying."""
        from src.llm.fallback import FallbackChain
        from openai import RateLimitError

        rate_limit_error = RateLimitError(
            message="Rate limit exceeded",
            response=MagicMock(status_code=429, headers={}),
            body={"error": {"message": "rate limit"}},
        )
        success_response = _make_llm_response("openai")

        mock_primary = MagicMock()
        mock_primary.complete.side_effect = [rate_limit_error, success_response]

        chain = FallbackChain(primary_provider=mock_primary, system_provider=None)
        request = LLMRequest(messages=[{"role": "user", "content": "test"}])

        with patch("time.sleep") as mock_sleep:
            chain.complete(request)

        mock_sleep.assert_called_once_with(2)


class TestFallbackChainFallback:
    """Tests for fallback to system OpenAI provider."""

    def test_retry_exhausted_falls_back_to_system(self):
        """After both attempts fail, should fall back to system OpenAI."""
        from src.llm.fallback import FallbackChain
        from openai import RateLimitError

        rate_limit_error = RateLimitError(
            message="Rate limit exceeded",
            response=MagicMock(status_code=429, headers={}),
            body={"error": {"message": "rate limit"}},
        )

        mock_primary = MagicMock()
        mock_primary.complete.side_effect = [rate_limit_error, rate_limit_error]

        fallback_response = _make_llm_response("openai", was_fallback=True, fallback_reason="rate_limit")
        mock_system = MagicMock()
        mock_system.complete.return_value = fallback_response

        chain = FallbackChain(primary_provider=mock_primary, system_provider=mock_system)
        request = LLMRequest(messages=[{"role": "user", "content": "test"}])

        with patch("time.sleep"):
            response = chain.complete(request)

        assert response.was_fallback is True
        mock_system.complete.assert_called_once()

    def test_fallback_response_has_was_fallback_true(self):
        """Fallback response should have was_fallback=True."""
        from src.llm.fallback import FallbackChain
        from openai import RateLimitError

        rate_limit_error = RateLimitError(
            message="Rate limit exceeded",
            response=MagicMock(status_code=429, headers={}),
            body={"error": {"message": "rate limit"}},
        )

        mock_primary = MagicMock()
        mock_primary.complete.side_effect = [rate_limit_error, rate_limit_error]

        system_response = _make_llm_response("openai", was_fallback=False)
        mock_system = MagicMock()
        mock_system.complete.return_value = system_response

        chain = FallbackChain(primary_provider=mock_primary, system_provider=mock_system)
        request = LLMRequest(messages=[{"role": "user", "content": "test"}])

        with patch("time.sleep"):
            response = chain.complete(request)

        # FallbackChain should mark the response as a fallback
        assert response.was_fallback is True

    def test_fallback_reason_set_to_rate_limit(self):
        """Fallback due to rate limit should have fallback_reason='rate_limit'."""
        from src.llm.fallback import FallbackChain
        from openai import RateLimitError

        rate_limit_error = RateLimitError(
            message="Rate limit exceeded",
            response=MagicMock(status_code=429, headers={}),
            body={"error": {"message": "rate limit"}},
        )

        mock_primary = MagicMock()
        mock_primary.complete.side_effect = [rate_limit_error, rate_limit_error]

        mock_system = MagicMock()
        mock_system.complete.return_value = _make_llm_response("openai")

        chain = FallbackChain(primary_provider=mock_primary, system_provider=mock_system)
        request = LLMRequest(messages=[{"role": "user", "content": "test"}])

        with patch("time.sleep"):
            response = chain.complete(request)

        assert response.fallback_reason == "rate_limit"

    def test_system_key_org_no_further_fallback(self):
        """When primary IS system key and it fails, there's no further fallback."""
        from src.llm.fallback import FallbackChain
        from openai import RateLimitError

        rate_limit_error = RateLimitError(
            message="Rate limit exceeded",
            response=MagicMock(status_code=429, headers={}),
            body={"error": {"message": "rate limit"}},
        )

        mock_primary = MagicMock()
        mock_primary.complete.side_effect = [rate_limit_error, rate_limit_error]

        # No system provider (primary IS the system provider)
        chain = FallbackChain(primary_provider=mock_primary, system_provider=None)
        request = LLMRequest(messages=[{"role": "user", "content": "test"}])

        with patch("time.sleep"):
            response = chain.complete(request)

        # Should return None when no fallback is possible
        assert response is None


class TestFallbackChainAuthError:
    """Tests for auth error handling — no retry, no fallback."""

    def test_auth_error_not_retried(self):
        """401/403 auth errors should fail immediately without retry."""
        from src.llm.fallback import FallbackChain
        from openai import AuthenticationError

        auth_error = AuthenticationError(
            message="Invalid API key",
            response=MagicMock(status_code=401, headers={}),
            body={"error": {"message": "invalid key"}},
        )

        mock_primary = MagicMock()
        mock_primary.complete.side_effect = auth_error

        mock_system = MagicMock()
        chain = FallbackChain(primary_provider=mock_primary, system_provider=mock_system)
        request = LLMRequest(messages=[{"role": "user", "content": "test"}])

        with patch("time.sleep"):
            response = chain.complete(request)

        # Auth errors: fail immediately, no fallback
        mock_primary.complete.assert_called_once()
        mock_system.complete.assert_not_called()
        assert response is None

    def test_anthropic_auth_error_not_retried(self):
        """Anthropic auth errors should also fail immediately."""
        import anthropic
        from src.llm.fallback import FallbackChain

        auth_error = anthropic.AuthenticationError(
            message="Invalid API key",
            response=MagicMock(status_code=401),
            body={"error": {"message": "invalid key"}},
        )

        mock_primary = MagicMock()
        mock_primary.complete.side_effect = auth_error

        mock_system = MagicMock()
        chain = FallbackChain(primary_provider=mock_primary, system_provider=mock_system)
        request = LLMRequest(messages=[{"role": "user", "content": "test"}])

        with patch("time.sleep"):
            response = chain.complete(request)

        mock_primary.complete.assert_called_once()
        mock_system.complete.assert_not_called()
        assert response is None


class TestFallbackChainTimeout:
    """Tests for timeout handling."""

    def test_timeout_triggers_retry_then_fallback(self):
        """Timeout should trigger retry, then fall back to system."""
        from src.llm.fallback import FallbackChain
        from openai import APITimeoutError

        timeout_error = APITimeoutError(request=MagicMock())

        mock_primary = MagicMock()
        mock_primary.complete.side_effect = [timeout_error, timeout_error]

        fallback_response = _make_llm_response("openai", was_fallback=True, fallback_reason="timeout")
        mock_system = MagicMock()
        mock_system.complete.return_value = fallback_response

        chain = FallbackChain(primary_provider=mock_primary, system_provider=mock_system)
        request = LLMRequest(messages=[{"role": "user", "content": "test"}])

        with patch("time.sleep"):
            response = chain.complete(request)

        assert response.was_fallback is True
        mock_system.complete.assert_called_once()

    def test_timeout_fallback_reason(self):
        """Timeout fallback should have fallback_reason='timeout'."""
        from src.llm.fallback import FallbackChain
        from openai import APITimeoutError

        timeout_error = APITimeoutError(request=MagicMock())

        mock_primary = MagicMock()
        mock_primary.complete.side_effect = [timeout_error, timeout_error]

        mock_system = MagicMock()
        mock_system.complete.return_value = _make_llm_response("openai")

        chain = FallbackChain(primary_provider=mock_primary, system_provider=mock_system)
        request = LLMRequest(messages=[{"role": "user", "content": "test"}])

        with patch("time.sleep"):
            response = chain.complete(request)

        assert response.fallback_reason == "timeout"
