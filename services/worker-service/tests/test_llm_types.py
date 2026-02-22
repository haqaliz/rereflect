"""
Tests for LLM types and dataclasses.
"""

from src.llm.types import LLMResponse, LLMRequest


class TestLLMResponse:
    """Tests for LLMResponse dataclass."""

    def test_create_basic_response(self):
        """Should create a basic LLMResponse with all required fields."""
        response = LLMResponse(
            content='{"sentiment": "positive"}',
            provider="openai",
            model="gpt-4o-mini",
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
            estimated_cost_cents=0.01,
            latency_ms=500,
            was_fallback=False,
            fallback_reason=None,
        )
        assert response.content == '{"sentiment": "positive"}'
        assert response.provider == "openai"
        assert response.model == "gpt-4o-mini"
        assert response.prompt_tokens == 100
        assert response.completion_tokens == 50
        assert response.total_tokens == 150
        assert response.estimated_cost_cents == 0.01
        assert response.latency_ms == 500
        assert response.was_fallback is False
        assert response.fallback_reason is None

    def test_create_fallback_response(self):
        """Should create a fallback LLMResponse with reason."""
        response = LLMResponse(
            content='{"result": "ok"}',
            provider="openai",
            model="gpt-4o-mini",
            prompt_tokens=80,
            completion_tokens=40,
            total_tokens=120,
            estimated_cost_cents=0.005,
            latency_ms=800,
            was_fallback=True,
            fallback_reason="rate_limit",
        )
        assert response.was_fallback is True
        assert response.fallback_reason == "rate_limit"

    def test_response_is_dataclass(self):
        """LLMResponse should be a dataclass with proper equality."""
        r1 = LLMResponse(
            content="test",
            provider="openai",
            model="gpt-4o-mini",
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
            estimated_cost_cents=0.001,
            latency_ms=100,
            was_fallback=False,
            fallback_reason=None,
        )
        r2 = LLMResponse(
            content="test",
            provider="openai",
            model="gpt-4o-mini",
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
            estimated_cost_cents=0.001,
            latency_ms=100,
            was_fallback=False,
            fallback_reason=None,
        )
        assert r1 == r2


class TestLLMRequest:
    """Tests for LLMRequest dataclass."""

    def test_create_basic_request(self):
        """Should create a basic LLMRequest."""
        request = LLMRequest(
            messages=[{"role": "user", "content": "analyze this"}],
            temperature=0.1,
            max_tokens=500,
            json_mode=True,
        )
        assert len(request.messages) == 1
        assert request.temperature == 0.1
        assert request.max_tokens == 500
        assert request.json_mode is True

    def test_create_request_with_defaults(self):
        """Should create request with default values."""
        request = LLMRequest(messages=[{"role": "user", "content": "hi"}])
        assert request.temperature == 0.1
        assert request.max_tokens == 500
        assert request.json_mode is True
