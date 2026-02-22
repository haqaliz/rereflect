"""
Shared dataclasses for the LLM abstraction layer.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class LLMRequest:
    """Input to an LLM provider."""
    messages: list[dict]
    temperature: float = 0.1
    max_tokens: int = 500
    json_mode: bool = True


@dataclass
class LLMResponse:
    """Standardized response from any LLM provider."""
    content: str                        # Raw text response
    provider: str                       # "openai" | "anthropic" | "google"
    model: str                          # "gpt-4o-mini", "claude-haiku-4-5", etc.
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    estimated_cost_cents: float         # Calculated from pricing table
    latency_ms: int                     # Wall clock time in milliseconds
    was_fallback: bool                  # True if this was a fallback call
    fallback_reason: Optional[str]      # "rate_limit", "server_error", "timeout"
