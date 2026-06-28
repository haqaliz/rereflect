"""
Org-scoped embedding provider resolver.

Single entry point for all consumers (template-matching-local, copilot-llm-local):

    embedder = resolve_embedding_provider(org_id, db)
    if embedder is None:
        # degrade: no embedding support configured for this org
        return fallback_response()
    vector = embedder.embedder.embed(text)

Design:
  - Reads OrgAIConfig for the org (default_provider, base_url, optional model_embeddings).
  - Local providers (ollama, openai_compatible): keyless, require base_url
    (ollama falls back to localhost:11434/v1 if not set).
  - Cloud providers (openai, google): require a valid BYOK key via resolve_org_byok_key.
  - Returns None in every unconfigured case; never raises to the caller.
  - Multi-tenant: always scoped by org_id.

References:
  - services/backend-api/src/utils/byok.py (resolve_org_byok_key, no env fallback)
  - services/worker-service/src/llm/factory.py (_LOCAL_PROVIDERS pattern, mirrored here)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from src.services.embeddings.base import EmbeddingProvider
from src.services.embeddings.factory import EmbeddingProviderFactory
from src.utils.byok import resolve_org_byok_key

logger = logging.getLogger(__name__)

# Providers that are keyless and require a base_url instead of a BYOK key.
# Mirrors the worker-service _LOCAL_PROVIDERS constant (no cross-import).
_LOCAL_PROVIDERS: frozenset[str] = frozenset({"ollama", "openai_compatible"})


@dataclass
class ResolvedEmbedder:
    """
    The result of a successful embedding provider resolution.

    Attributes:
        provider:       Provider name string (e.g. "openai", "ollama").
        embedder:       Ready-to-use EmbeddingProvider instance.
        dimension_hint: Expected embedding dimension from the provider.
                        For local providers this is 0 until embed() is called
                        (dimension is model-dependent and unknown pre-call).
                        For OpenAI text-embedding-3-small this is 1536.
                        Consumers should call embedder.embed() and then read
                        embedder.dimension for a definitive value.
    """

    provider: str
    embedder: EmbeddingProvider
    dimension_hint: int


def resolve_embedding_provider(
    org_id: int,
    db,
) -> Optional[ResolvedEmbedder]:
    """
    Resolve a ready embedder for the given organization.

    This is the single call all consumers make.  It handles the full
    lookup chain:
      1. Load OrgAIConfig for org_id.
      2. Pick provider, base_url, optional model_embeddings.
      3. For local providers: require base_url (Ollama defaults to localhost).
      4. For cloud providers: BYOK key lookup; None key → return None.
      5. Build via EmbeddingProviderFactory; wrap errors → return None.
      6. Return ResolvedEmbedder or None.

    Args:
        org_id: Organization ID (multi-tenant scoping).
        db:     SQLAlchemy session.

    Returns:
        ResolvedEmbedder if the org has a working embedding configuration,
        None otherwise (no config row, missing BYOK key, missing base_url,
        or construction error).
    """
    try:
        from src.models.org_ai_config import OrgAIConfig

        config = db.query(OrgAIConfig).filter_by(
            organization_id=org_id
        ).first()

        if config is None:
            logger.debug(
                "resolve_embedding_provider: no OrgAIConfig for org=%s", org_id
            )
            return None

        provider: str = config.default_provider
        base_url: Optional[str] = config.base_url
        # model_embeddings column does not exist yet (added in template-matching-local S1).
        # Use getattr with None default so this aspect doesn't depend on the migration.
        model: Optional[str] = getattr(config, "model_embeddings", None)

        if provider in _LOCAL_PROVIDERS:
            # Local / keyless path — no BYOK lookup needed.
            # For ollama: factory applies the localhost:11434/v1 default when base_url is None.
            # For openai_compatible: base_url is required; factory raises ValueError if absent.
            if provider == "openai_compatible" and not base_url:
                logger.debug(
                    "resolve_embedding_provider: openai_compatible configured but "
                    "no base_url for org=%s — cannot resolve",
                    org_id,
                )
                return None

            embedder = EmbeddingProviderFactory.create(
                provider,
                api_key=None,
                base_url=base_url,
                model=model,
            )

        else:
            # Cloud path — BYOK key is required.
            api_key: Optional[str] = resolve_org_byok_key(provider, org_id, db)
            if api_key is None:
                logger.debug(
                    "resolve_embedding_provider: no BYOK key for provider=%s org=%s",
                    provider,
                    org_id,
                )
                return None

            embedder = EmbeddingProviderFactory.create(
                provider,
                api_key=api_key,
                base_url=base_url,
                model=model,
            )

        return ResolvedEmbedder(
            provider=provider,
            embedder=embedder,
            dimension_hint=embedder.dimension,
        )

    except Exception as exc:
        logger.warning(
            "resolve_embedding_provider: failed for org=%s: %s",
            org_id,
            exc,
            exc_info=True,
        )
        return None
