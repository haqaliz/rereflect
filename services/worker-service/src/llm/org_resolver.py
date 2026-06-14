"""
Resolves per-org LLM configuration: provider, model, API key.

Strictly BYOK (bring-your-own-key): reads OrgApiKey from the database.
If no valid BYOK key exists for an org, AI is disabled for that org and
returns (None, False) — no system/env key fallback ever.

Handles usage logging (org sees its own usage). Budget-cap machinery removed.
is_byok column dropped (OSS pivot B4): all AI calls are BYOK-only by definition;
the column carried no information and is no longer written.
"""

import logging
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from src.llm.types import LLMRequest, LLMResponse
from src.llm.factory import LLMProviderFactory
from src.llm.fallback import FallbackChain
from src.llm.base import LLMProvider

logger = logging.getLogger(__name__)

# Encryption key for decrypting BYOK keys
import os
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


def log_usage(
    org_id: int,
    response: LLMResponse,
    task_type: str,
    db: Session,
) -> None:
    """
    Write an LLMUsageLog entry for a completed LLM call.
    Org usage is always logged so operators can see their own spend.
    Budget-update logic removed (no system key → no owner budget to track).
    is_byok column dropped (OSS pivot B4): all calls are BYOK by definition.
    """
    from src.models import LLMUsageLog

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
        )
        db.add(log)
        db.flush()
    except Exception as e:
        logger.error(f"Failed to log LLM usage for org {org_id}: {e}")


def build_fallback_chain(
    org_id: int,
    provider: str,
    model: str,
    db: Session,
) -> Tuple[Optional[FallbackChain], bool]:
    """
    Build a FallbackChain for the given org/provider/model.

    BYOK-only: if the org has no valid encrypted key for the requested provider,
    returns (None, False) — AI is disabled for this org. No system/env key is
    ever used as a fallback.

    Returns:
        Tuple of (FallbackChain, is_byok)
        is_byok is True when the org's own API key is being used.
        Returns (None, False) when no valid BYOK key is available.
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

    if not byok_key:
        logger.warning(
            f"No valid BYOK key for provider '{provider}' (org {org_id}) — AI disabled for this org"
        )
        return None, False

    primary = LLMProviderFactory.create(provider, byok_key, model)
    # No system fallback: FallbackChain only does primary + one retry.
    chain = FallbackChain(primary_provider=primary, system_provider=None)
    return chain, True


def call_llm_for_org(
    org_id: int,
    task_type: str,
    request: LLMRequest,
    provider: str,
    model: str,
    db: Session,
) -> Optional[LLMResponse]:
    """
    Full LLM call with org resolution, fallback, and usage logging.

    Args:
        org_id: Organization ID
        task_type: "categorization", "analysis", "insights", or "churn_analysis"
        request: LLMRequest to send
        provider: Provider name (from OrgAIConfig)
        model: Model ID (from OrgAIConfig)
        db: Database session

    Returns:
        LLMResponse on success, None if no BYOK key or all providers fail.
    """
    chain, _is_byok = build_fallback_chain(org_id, provider, model, db)
    if chain is None:
        return None

    response = chain.complete(request)
    if response is None:
        return None

    log_usage(org_id, response, task_type, db)
    return response
