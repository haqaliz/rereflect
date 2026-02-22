"""
LLM abstraction layer for the worker service.

Provides a provider-agnostic interface for calling OpenAI, Anthropic, and Google models,
with automatic retry and fallback chain support.

Usage:
    from src.llm import LLMProviderFactory, FallbackChain, LLMRequest

    provider = LLMProviderFactory.create("openai", api_key="sk-...", model="gpt-4o-mini")
    chain = FallbackChain(primary_provider=provider, system_provider=None)
    response = chain.complete(LLMRequest(messages=[{"role": "user", "content": "..."}]))
"""

from src.llm.types import LLMRequest, LLMResponse
from src.llm.base import LLMProvider
from src.llm.factory import LLMProviderFactory
from src.llm.fallback import FallbackChain
from src.llm.pricing import estimate_cost_cents, PRICING_TABLE

__all__ = [
    "LLMRequest",
    "LLMResponse",
    "LLMProvider",
    "LLMProviderFactory",
    "FallbackChain",
    "estimate_cost_cents",
    "PRICING_TABLE",
]
