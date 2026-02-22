"""
High-level LLM service — wraps factory + fallback chain for task callers.

Reads org AI config, resolves BYOK/system keys, creates providers,
calls LLM via fallback chain, logs usage, and returns results.
"""

import json
import logging
import os
from typing import Optional

from src.llm.types import LLMRequest, LLMResponse
from src.llm.factory import LLMProviderFactory
from src.llm.fallback import FallbackChain
from src.llm.pricing import estimate_cost_cents

logger = logging.getLogger(__name__)

# System API keys from env vars
_SYSTEM_KEYS = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "google": "GOOGLE_AI_API_KEY",
}


def _get_system_key(provider: str) -> Optional[str]:
    """Get system API key for a provider from env."""
    env_var = _SYSTEM_KEYS.get(provider)
    return os.environ.get(env_var, "") if env_var else ""


def _get_org_config(org_id: int, db) -> dict:
    """
    Read org AI config from DB. Returns dict with provider, models, BYOK keys.

    Returns:
        {
            "provider": "openai",
            "model_categorization": "gpt-4o-mini",
            "model_analysis": "gpt-4o-mini",
            "model_insights": "gpt-4o-mini",
            "byok_keys": {"openai": "sk-...", "anthropic": None, ...},
            "budget_exceeded": False,
        }
    """
    from src.models import OrgAIConfig, OrgApiKey

    config = db.query(OrgAIConfig).filter_by(organization_id=org_id).first()

    byok_keys = {}
    for key_row in db.query(OrgApiKey).filter_by(organization_id=org_id, is_valid=True).all():
        try:
            from cryptography.fernet import Fernet
            enc_key = os.environ.get("LLM_ENCRYPTION_KEY", "")
            if enc_key:
                fernet = Fernet(enc_key.encode())
                byok_keys[key_row.provider] = fernet.decrypt(key_row.encrypted_key.encode()).decode()
            else:
                byok_keys[key_row.provider] = key_row.encrypted_key
        except Exception:
            byok_keys[key_row.provider] = key_row.encrypted_key

    if config:
        budget_exceeded = False
        if config.monthly_budget_cents and config.budget_used_cents:
            budget_exceeded = config.budget_used_cents >= config.monthly_budget_cents

        return {
            "provider": config.default_provider or "openai",
            "model_categorization": config.model_categorization or "gpt-4o-mini",
            "model_analysis": config.model_analysis or "gpt-4o-mini",
            "model_insights": config.model_insights or "gpt-4o-mini",
            "byok_keys": byok_keys,
            "budget_exceeded": budget_exceeded,
        }

    return {
        "provider": "openai",
        "model_categorization": "gpt-4o-mini",
        "model_analysis": "gpt-4o-mini",
        "model_insights": "gpt-4o-mini",
        "byok_keys": byok_keys,
        "budget_exceeded": False,
    }


def _resolve_api_key(provider: str, byok_keys: dict) -> tuple[str, bool]:
    """
    Resolve API key for a provider: BYOK first, then system.
    Returns (api_key, is_byok).
    """
    byok = byok_keys.get(provider)
    if byok:
        return byok, True
    system_key = _get_system_key(provider)
    if system_key:
        return system_key, False
    return "", False


def _build_chain(provider: str, model: str, byok_keys: dict) -> tuple[Optional[FallbackChain], bool]:
    """
    Build a FallbackChain for the given provider/model.
    Returns (chain, is_byok).
    """
    api_key, is_byok = _resolve_api_key(provider, byok_keys)
    if not api_key:
        return None, False

    primary = LLMProviderFactory.create(provider, api_key, model)

    # System fallback (only if primary is BYOK)
    system_provider = None
    if is_byok:
        system_key = _get_system_key("openai")
        if system_key:
            system_provider = LLMProviderFactory.create("openai", system_key, "gpt-4o-mini")

    chain = FallbackChain(primary_provider=primary, system_provider=system_provider)
    return chain, is_byok


def _log_usage(
    org_id: int,
    response: LLMResponse,
    task_type: str,
    is_byok: bool,
    db,
) -> None:
    """Log LLM usage to the llm_usage_logs table and update budget."""
    from src.models import LLMUsageLog, OrgAIConfig

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

    # Update budget (only for system key usage)
    if not is_byok:
        config = db.query(OrgAIConfig).filter_by(organization_id=org_id).first()
        if config:
            config.budget_used_cents = (config.budget_used_cents or 0) + int(response.estimated_cost_cents + 0.5)

    db.flush()


def call_llm(
    org_id: int,
    task_type: str,
    messages: list[dict],
    db,
    temperature: float = 0.1,
    max_tokens: int = 500,
    json_mode: bool = True,
) -> Optional[tuple[str, str, str]]:
    """
    High-level LLM call for worker tasks.

    Args:
        org_id: Organization ID
        task_type: "categorization", "analysis", or "insights"
        messages: Chat messages list
        db: SQLAlchemy session
        temperature: LLM temperature
        max_tokens: Max output tokens
        json_mode: Whether to request JSON output

    Returns:
        Tuple of (content, provider, model) on success, None on failure.
    """
    org_config = _get_org_config(org_id, db)

    if org_config["budget_exceeded"]:
        logger.warning(f"Budget exceeded for org {org_id}, skipping LLM call")
        return None

    provider = org_config["provider"]
    model_key = f"model_{task_type}"
    model = org_config.get(model_key, "gpt-4o-mini")

    chain, is_byok = _build_chain(provider, model, org_config["byok_keys"])
    if chain is None:
        logger.warning(f"No API key available for provider '{provider}' (org {org_id})")
        return None

    request = LLMRequest(
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        json_mode=json_mode,
    )

    response = chain.complete(request)
    if response is None:
        logger.error(f"LLM call failed for org {org_id}, task {task_type}")
        return None

    # Log usage
    try:
        _log_usage(org_id, response, task_type, is_byok, db)
    except Exception as e:
        logger.warning(f"Failed to log LLM usage: {e}")

    return response.content, response.provider, response.model
