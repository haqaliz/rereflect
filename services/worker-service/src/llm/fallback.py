"""
FallbackChain — orchestrates retry + provider fallback for LLM calls.

Strategy:
1. Try primary provider
2. On transient failure (429, 5xx, timeout): retry once with 2s backoff
3. If retry fails: fall back to system OpenAI provider (if available)
4. Auth errors (401, 403) are NOT retried or fallen back — config problem

Returns None if all attempts fail and no fallback is available.
"""

import logging
import time
from dataclasses import replace
from typing import Optional, Tuple

from src.llm.base import LLMProvider
from src.llm.types import LLMRequest, LLMResponse

logger = logging.getLogger(__name__)

_RETRY_BACKOFF_SECONDS = 2


def _is_auth_error(exc: Exception) -> bool:
    """Return True if the exception is an authentication error (401/403)."""
    try:
        from openai import AuthenticationError as OpenAIAuthError
        if isinstance(exc, OpenAIAuthError):
            return True
    except ImportError:
        pass

    try:
        import anthropic
        if isinstance(exc, anthropic.AuthenticationError):
            return True
    except ImportError:
        pass

    return False


def _get_fallback_reason(exc: Exception) -> str:
    """Map exception to a fallback_reason string."""
    try:
        from openai import RateLimitError, APITimeoutError
        if isinstance(exc, RateLimitError):
            return "rate_limit"
        if isinstance(exc, APITimeoutError):
            return "timeout"
    except ImportError:
        pass

    try:
        import anthropic
        if isinstance(exc, anthropic.APIStatusError):
            if exc.status_code == 429:
                return "rate_limit"
    except ImportError:
        pass

    # Check for timeout-like messages
    msg = str(exc).lower()
    if "timeout" in msg:
        return "timeout"
    if "rate" in msg or "429" in msg:
        return "rate_limit"

    return "server_error"


class FallbackChain:
    """
    Orchestrates retry + provider fallback for LLM calls.

    Args:
        primary_provider: The org's chosen LLM provider.
        system_provider: System OpenAI fallback (None if primary IS system key).
    """

    def __init__(
        self,
        primary_provider: LLMProvider,
        system_provider: Optional[LLMProvider],
    ):
        self._primary = primary_provider
        self._system = system_provider

    def complete(self, request: LLMRequest) -> Optional[LLMResponse]:
        """
        Attempt completion with retry and fallback logic.

        Returns:
            LLMResponse on success, None if all attempts fail.
        """
        last_error = None
        fallback_reason = None

        # Attempt 1: primary
        try:
            return self._primary.complete(request)
        except Exception as exc:
            if _is_auth_error(exc):
                logger.error(f"Auth error on primary provider — not retrying: {exc}")
                return None
            last_error = exc
            fallback_reason = _get_fallback_reason(exc)
            logger.warning(f"Primary LLM failed ({fallback_reason}), retrying in {_RETRY_BACKOFF_SECONDS}s: {exc}")

        # Attempt 2: retry primary with backoff
        time.sleep(_RETRY_BACKOFF_SECONDS)
        try:
            return self._primary.complete(request)
        except Exception as exc:
            if _is_auth_error(exc):
                logger.error(f"Auth error on primary retry — not falling back: {exc}")
                return None
            last_error = exc
            fallback_reason = _get_fallback_reason(exc)
            logger.warning(f"Primary LLM retry failed ({fallback_reason}): {exc}")

        # Attempt 3: fallback to system provider
        if self._system is None:
            logger.error("No system fallback available, giving up")
            return None

        try:
            logger.info(f"Falling back to system provider (reason: {fallback_reason})")
            response = self._system.complete(request)
            # Mark the response as a fallback
            return replace(response, was_fallback=True, fallback_reason=fallback_reason)
        except Exception as exc:
            logger.error(f"System fallback also failed: {exc}")
            return None
