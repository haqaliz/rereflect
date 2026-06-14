"""
FallbackChain — orchestrates retry logic for LLM calls.

Strategy:
1. Try primary provider (org's BYOK key)
2. On transient failure (429, 5xx, timeout): retry once with 2s backoff
3. If retry also fails: return None — no system/env fallback ever
4. Auth errors (401, 403) are NOT retried — config problem

BYOK-only pivot: the system-provider fallback (Attempt 3) has been removed.
Orgs with no configured key simply don't get AI; they fall back to VADER.
"""

import logging
import time
from typing import Optional

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
    Orchestrates retry logic for LLM calls (BYOK-only).

    Args:
        primary_provider: The org's chosen LLM provider (BYOK key).
        system_provider: Accepted for compatibility but ignored. Must always
                         be None in BYOK-only mode.
    """

    def __init__(
        self,
        primary_provider: LLMProvider,
        system_provider: Optional[LLMProvider],
    ):
        self._primary = primary_provider
        # system_provider is intentionally ignored — no system key in BYOK-only mode.
        self._system = None

    def complete(self, request: LLMRequest) -> Optional[LLMResponse]:
        """
        Attempt completion with retry logic.

        Returns:
            LLMResponse on success, None if both attempts fail.
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
            logger.warning(
                f"Primary LLM failed ({fallback_reason}), retrying in {_RETRY_BACKOFF_SECONDS}s: {exc}"
            )

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

        # Both attempts failed, no system fallback available
        logger.error(
            f"LLM call failed after 2 attempts ({fallback_reason}). "
            "No system fallback — org must configure a valid BYOK key."
        )
        return None
