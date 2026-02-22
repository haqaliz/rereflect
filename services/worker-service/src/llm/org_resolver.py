"""
Resolves per-org LLM configuration: provider, model, API key.

Reads OrgAIConfig and OrgApiKey from the database to determine which
LLM provider to use for a given task type.

Also handles budget checking and usage logging.
"""

import logging
import os
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from src.llm.types import LLMRequest, LLMResponse
from src.llm.factory import LLMProviderFactory
from src.llm.fallback import FallbackChain
from src.llm.base import LLMProvider

logger = logging.getLogger(__name__)

# System API keys from environment variables
_SYSTEM_OPENAI_KEY = os.environ.get("OPENAI_API_KEY", "")
_SYSTEM_ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
_SYSTEM_GOOGLE_KEY = os.environ.get("GOOGLE_AI_API_KEY", "")

# Encryption key for decrypting BYOK keys
_ENCRYPTION_KEY = os.environ.get("LLM_ENCRYPTION_KEY", "")

_DEFAULT_PROVIDER = "openai"
_DEFAULT_MODEL = "gpt-4o-mini"


def _decrypt_api_key(encrypted_key: str) -> str:
    """Decrypt a Fernet-encrypted API key."""
    if not _ENCRYPTION_KEY:
        logger.warning("LLM_ENCRYPTION_KEY not set, cannot decrypt BYOK key")
        return ""
    try:
        from cryptography.fernet import Fernet
        fernet = Fernet(_ENCRYPTION_KEY.encode())
        return fernet.decrypt(encrypted_key.encode()).decode()
    except Exception as e:
        logger.error(f"Failed to decrypt API key: {e}")
        return ""


def _get_system_key_for_provider(provider: str) -> str:
    """Get the system API key for the given provider."""
    if provider == "openai":
        return _SYSTEM_OPENAI_KEY
    elif provider == "anthropic":
        return _SYSTEM_ANTHROPIC_KEY
    elif provider == "google":
        return _SYSTEM_GOOGLE_KEY
    return ""


def check_budget(org_id: int, estimated_cost_cents: float, db: Session) -> bool:
    """
    Check if org has remaining AI budget for system key usage.

    Args:
        org_id: Organization ID
        estimated_cost_cents: Estimated cost of the upcoming LLM call
        db: Database session

    Returns:
        True if call is allowed, False if budget exceeded.
    """
    from src.models import OrgAIConfig

    config = db.query(OrgAIConfig).filter_by(organization_id=org_id).first()
    if not config or not config.monthly_budget_cents:
        return True  # No limit configured

    if config.budget_used_cents >= config.monthly_budget_cents:
        logger.warning(
            f"Org {org_id} budget exceeded: "
            f"{config.budget_used_cents}/{config.monthly_budget_cents} cents"
        )
        return False
    return True


def log_usage(
    org_id: int,
    response: LLMResponse,
    task_type: str,
    is_byok: bool,
    db: Session,
) -> None:
    """
    Write an LLMUsageLog entry for a completed LLM call.
    Also updates budget_used_cents if using system key.
    """
    from src.models import LLMUsageLog, OrgAIConfig

    try:
        log = LLMUsageLog(
            organization_id=org_id,
            provider=response.provider,
            model=response.model,
            task_type=task_type,
            prompt_tokens=response.prompt_tokens,
            completion_tokens=response.completion_tokens,
            total_tokens=response.total_tokens,
            estimated_cost_cents=response.estimated_cost_cents,
            latency_ms=response.latency_ms,
            was_fallback=response.was_fallback,
            fallback_reason=response.fallback_reason,
            is_byok=is_byok,
        )
        db.add(log)

        # Update budget if using system key
        if not is_byok:
            config = db.query(OrgAIConfig).filter_by(organization_id=org_id).first()
            if config:
                config.budget_used_cents = (config.budget_used_cents or 0) + response.estimated_cost_cents

        db.flush()
    except Exception as e:
        logger.error(f"Failed to log LLM usage for org {org_id}: {e}")


def build_fallback_chain(
    org_id: int,
    provider: str,
    model: str,
    db: Session,
) -> Tuple[FallbackChain, bool]:
    """
    Build a FallbackChain for the given org/provider/model.

    Returns:
        Tuple of (FallbackChain, is_byok)
        is_byok is True if the org's own API key is being used.
    """
    from src.models import OrgApiKey

    # Look up org's BYOK key for this provider
    org_api_key_record = db.query(OrgApiKey).filter_by(
        organization_id=org_id,
        provider=provider,
        is_valid=True,
    ).first()

    byok_key = None
    if org_api_key_record:
        byok_key = _decrypt_api_key(org_api_key_record.encrypted_key)

    is_byok = bool(byok_key)
    api_key = byok_key or _get_system_key_for_provider(provider)

    if not api_key:
        logger.warning(f"No API key available for provider '{provider}' (org {org_id})")
        return None, False

    primary = LLMProviderFactory.create(provider, api_key, model)

    # System fallback: only if primary is not already using system OpenAI
    system_provider = None
    if is_byok or provider != "openai":
        system_key = _SYSTEM_OPENAI_KEY
        if system_key:
            system_provider = LLMProviderFactory.create("openai", system_key, _DEFAULT_MODEL)

    chain = FallbackChain(primary_provider=primary, system_provider=system_provider)
    return chain, is_byok


def call_llm_for_org(
    org_id: int,
    task_type: str,
    request: LLMRequest,
    provider: str,
    model: str,
    db: Session,
) -> Optional[LLMResponse]:
    """
    Full LLM call with org resolution, budget check, fallback, and usage logging.

    Args:
        org_id: Organization ID
        task_type: "categorization", "analysis", "insights", or "churn_analysis"
        request: LLMRequest to send
        provider: Provider name (from OrgAIConfig)
        model: Model ID (from OrgAIConfig)
        db: Database session

    Returns:
        LLMResponse on success, None if budget exceeded or all providers fail.
    """
    chain, is_byok = build_fallback_chain(org_id, provider, model, db)
    if chain is None:
        return None

    # Budget check for system key usage
    if not is_byok:
        # Rough estimate: 1000 tokens at cheapest rate
        rough_estimate = 0.05  # ~5 cents, very conservative
        if not check_budget(org_id, rough_estimate, db):
            return None

    response = chain.complete(request)
    if response is None:
        return None

    log_usage(org_id, response, task_type, is_byok, db)
    return response
