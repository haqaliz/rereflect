"""
LLM pricing table and cost estimation utilities.

Prices are in USD per 1M tokens (input/output).
Cost is returned in cents.
"""

# Pricing table: provider -> model_id -> {input_price_per_1m, output_price_per_1m}
# Prices in USD per 1M tokens (from PRD seed data, approximate)
PRICING_TABLE: dict[str, dict[str, dict[str, float]]] = {
    "openai": {
        "gpt-4o-mini": {
            "input_price_per_1m": 0.15,
            "output_price_per_1m": 0.60,
        },
        "gpt-4o": {
            "input_price_per_1m": 2.50,
            "output_price_per_1m": 10.00,
        },
        "gpt-4-turbo": {
            "input_price_per_1m": 10.00,
            "output_price_per_1m": 30.00,
        },
    },
    "anthropic": {
        "claude-haiku-4-5": {
            "input_price_per_1m": 0.80,
            "output_price_per_1m": 4.00,
        },
        "claude-sonnet-4-6": {
            "input_price_per_1m": 3.00,
            "output_price_per_1m": 15.00,
        },
        "claude-opus-4-6": {
            "input_price_per_1m": 15.00,
            "output_price_per_1m": 75.00,
        },
    },
    "google": {
        "gemini-2.0-flash": {
            "input_price_per_1m": 0.075,
            "output_price_per_1m": 0.30,
        },
        "gemini-2.0-pro": {
            "input_price_per_1m": 1.25,
            "output_price_per_1m": 5.00,
        },
    },
}


def estimate_cost_cents(
    provider: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> float:
    """
    Estimate cost in cents for a given LLM call.

    Args:
        provider: "openai", "anthropic", or "google"
        model: Model ID (e.g., "gpt-4o-mini")
        prompt_tokens: Number of input tokens used
        completion_tokens: Number of output tokens used

    Returns:
        Estimated cost in cents (float). Returns 0.0 for unknown models.
    """
    provider_prices = PRICING_TABLE.get(provider)
    if not provider_prices:
        return 0.0

    model_prices = provider_prices.get(model)
    if not model_prices:
        return 0.0

    input_price = model_prices["input_price_per_1m"]
    output_price = model_prices["output_price_per_1m"]

    # Convert from USD per 1M tokens to dollars for actual token count
    input_cost_usd = (prompt_tokens / 1_000_000) * input_price
    output_cost_usd = (completion_tokens / 1_000_000) * output_price
    total_cost_usd = input_cost_usd + output_cost_usd

    # Convert to cents
    return total_cost_usd * 100
