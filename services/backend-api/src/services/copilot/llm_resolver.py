"""
LLM resolver for the Copilot's answer-generation path.

Mirrors the worker-service's local/keyless pattern (worker-service/src/llm/org_resolver.py)
but lives in backend-api to avoid cross-service coupling.

Resolution rules (in order of priority):
- LOCAL PROVIDER (ollama, openai_compatible) with base_url set
    → proceed keyless (api_key=None, base_url from config), is_configured=True
- LOCAL PROVIDER with no base_url
    → is_configured=False (user must set base_url in Settings → AI)
- CLOUD PROVIDER with a valid BYOK key
    → proceed with key, base_url=None, is_configured=True
- CLOUD PROVIDER with no BYOK key
    → is_configured=False (user must add key in Settings → AI → API Keys)

The caller decides what to do with an unconfigured result — typically send an
honest "configure a model in Settings → AI" WS error message, never a crash.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

# Providers that run locally/offline and do not need an OrgApiKey row.
# Mirrors the worker-service constant to stay consistent.
_LOCAL_PROVIDERS: frozenset[str] = frozenset({"ollama", "openai_compatible"})

_DEFAULT_PROVIDER = "openai"
_DEFAULT_MODEL = "gpt-4o-mini"


@dataclass
class LLMConfig:
    """Resolved LLM configuration for Copilot generation."""

    provider: str
    """LLM provider name, e.g. 'openai', 'openai_compatible', 'ollama'."""

    model: str
    """Model ID to use for generation."""

    api_key: Optional[str]
    """Decrypted BYOK API key.  None for local/keyless providers."""

    base_url: Optional[str]
    """Base URL for local/OpenAI-compatible endpoints.  None for cloud."""

    is_configured: bool
    """
    True when the org has a usable LLM (either key or local base_url).
    False when neither is available — caller should send an honest message.
    """


def resolve_generation_llm(org_id: int, db) -> LLMConfig:
    """
    Resolve the LLM configuration for Copilot answer generation.

    Args:
        org_id: Organization ID.
        db:     SQLAlchemy session (sync).

    Returns:
        LLMConfig.  When is_configured=False the caller should send the user an
        honest "configure a model in Settings → AI" message rather than crashing.
    """
    provider = _DEFAULT_PROVIDER
    model = _DEFAULT_MODEL
    base_url: Optional[str] = None

    # ── Load per-org AI settings ──────────────────────────────────────────────
    try:
        from src.models.org_ai_config import OrgAIConfig  # local import keeps this testable

        config = db.query(OrgAIConfig).filter_by(organization_id=org_id).first()
        if config:
            provider = config.default_provider or _DEFAULT_PROVIDER
            model = config.model_analysis or _DEFAULT_MODEL
            base_url = config.base_url  # None for cloud providers
    except Exception as exc:
        logger.warning(
            "resolve_generation_llm: could not load OrgAIConfig for org %s: %s",
            org_id,
            exc,
        )

    # ── Local / keyless path ──────────────────────────────────────────────────
    if provider in _LOCAL_PROVIDERS:
        if base_url:
            logger.debug(
                "resolve_generation_llm: org=%s local provider '%s' base_url=%s",
                org_id,
                provider,
                base_url,
            )
            return LLMConfig(
                provider=provider,
                model=model,
                api_key=None,    # keyless — Ollama / local endpoints ignore the key
                base_url=base_url,
                is_configured=True,
            )
        else:
            logger.warning(
                "resolve_generation_llm: org=%s provider '%s' has no base_url — "
                "Copilot generation unconfigured",
                org_id,
                provider,
            )
            return LLMConfig(
                provider=provider,
                model=model,
                api_key=None,
                base_url=None,
                is_configured=False,
            )

    # ── Cloud BYOK path ───────────────────────────────────────────────────────
    api_key: Optional[str] = None
    try:
        from src.utils.byok import resolve_org_byok_key

        api_key = resolve_org_byok_key(provider, org_id, db)
    except Exception as exc:
        logger.warning(
            "resolve_generation_llm: BYOK lookup failed for org=%s provider=%s: %s",
            org_id,
            provider,
            exc,
        )

    if api_key:
        return LLMConfig(
            provider=provider,
            model=model,
            api_key=api_key,
            base_url=None,
            is_configured=True,
        )

    logger.warning(
        "resolve_generation_llm: org=%s has no BYOK key for provider '%s' — "
        "Copilot generation unconfigured",
        org_id,
        provider,
    )
    return LLMConfig(
        provider=provider,
        model=model,
        api_key=None,
        base_url=None,
        is_configured=False,
    )
