"""
Tests for LLM pricing / cost estimation utilities.
"""

import pytest
from src.llm.pricing import estimate_cost_cents, PRICING_TABLE


class TestEstimateCostCents:
    """Tests for estimate_cost_cents()."""

    def test_gpt4o_mini_cost(self):
        """Should compute correct cost for gpt-4o-mini."""
        # gpt-4o-mini: $0.15/1M input, $0.60/1M output
        cost = estimate_cost_cents(
            provider="openai",
            model="gpt-4o-mini",
            prompt_tokens=1_000_000,
            completion_tokens=1_000_000,
        )
        # $0.15 input + $0.60 output = $0.75 = 75 cents
        assert abs(cost - 75.0) < 0.01

    def test_gpt4o_cost(self):
        """Should compute correct cost for gpt-4o."""
        # gpt-4o: $2.50/1M input, $10.00/1M output
        cost = estimate_cost_cents(
            provider="openai",
            model="gpt-4o",
            prompt_tokens=1_000_000,
            completion_tokens=1_000_000,
        )
        # $2.50 + $10.00 = $12.50 = 1250 cents
        assert abs(cost - 1250.0) < 0.01

    def test_claude_haiku_cost(self):
        """Should compute correct cost for claude-haiku-4-5."""
        # claude-haiku-4-5: $0.80/1M input, $4.00/1M output
        cost = estimate_cost_cents(
            provider="anthropic",
            model="claude-haiku-4-5",
            prompt_tokens=1_000_000,
            completion_tokens=1_000_000,
        )
        # $0.80 + $4.00 = $4.80 = 480 cents
        assert abs(cost - 480.0) < 0.01

    def test_gemini_flash_cost(self):
        """Should compute correct cost for gemini-2.0-flash."""
        # gemini-2.0-flash: $0.075/1M input, $0.30/1M output
        cost = estimate_cost_cents(
            provider="google",
            model="gemini-2.0-flash",
            prompt_tokens=1_000_000,
            completion_tokens=1_000_000,
        )
        # $0.075 + $0.30 = $0.375 = 37.5 cents
        assert abs(cost - 37.5) < 0.01

    def test_small_token_count(self):
        """Should compute correct cost for small token counts."""
        # gpt-4o-mini: $0.15/1M input, $0.60/1M output
        # 100 prompt + 50 completion
        cost = estimate_cost_cents(
            provider="openai",
            model="gpt-4o-mini",
            prompt_tokens=100,
            completion_tokens=50,
        )
        # 100/1M * 0.15 * 100 + 50/1M * 0.60 * 100
        # = 0.0000015 + 0.000003 = 0.0000045 dollars = 0.00045 cents
        assert cost > 0
        assert cost < 0.01

    def test_unknown_model_returns_zero(self):
        """Unknown model should return 0 cost."""
        cost = estimate_cost_cents(
            provider="openai",
            model="unknown-model-xyz",
            prompt_tokens=1000,
            completion_tokens=500,
        )
        assert cost == 0.0

    def test_unknown_provider_returns_zero(self):
        """Unknown provider should return 0 cost."""
        cost = estimate_cost_cents(
            provider="unknown_provider",
            model="gpt-4o-mini",
            prompt_tokens=1000,
            completion_tokens=500,
        )
        assert cost == 0.0

    def test_zero_tokens_returns_zero(self):
        """Zero tokens should return 0 cost."""
        cost = estimate_cost_cents(
            provider="openai",
            model="gpt-4o-mini",
            prompt_tokens=0,
            completion_tokens=0,
        )
        assert cost == 0.0

    def test_pricing_table_has_all_models(self):
        """Pricing table should include all 8 models from PRD."""
        expected_models = [
            ("openai", "gpt-4o-mini"),
            ("openai", "gpt-4o"),
            ("openai", "gpt-4-turbo"),
            ("anthropic", "claude-haiku-4-5"),
            ("anthropic", "claude-sonnet-4-6"),
            ("anthropic", "claude-opus-4-6"),
            ("google", "gemini-2.0-flash"),
            ("google", "gemini-2.0-pro"),
        ]
        for provider, model in expected_models:
            assert provider in PRICING_TABLE
            assert model in PRICING_TABLE[provider], f"Missing model: {provider}/{model}"


class TestPricingTable:
    """Tests for PRICING_TABLE structure."""

    def test_each_model_has_input_and_output_price(self):
        """Each model entry should have input_price and output_price."""
        for provider, models in PRICING_TABLE.items():
            for model_id, prices in models.items():
                assert "input_price_per_1m" in prices, f"{provider}/{model_id} missing input_price_per_1m"
                assert "output_price_per_1m" in prices, f"{provider}/{model_id} missing output_price_per_1m"

    def test_prices_are_positive(self):
        """All prices should be positive numbers."""
        for provider, models in PRICING_TABLE.items():
            for model_id, prices in models.items():
                assert prices["input_price_per_1m"] >= 0
                assert prices["output_price_per_1m"] >= 0
