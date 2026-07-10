"""
Org-scoped sentiment provider resolver — worker-service mirror.

Independent mirror of services/backend-api/src/services/sentiment_resolver.py.
No cross-service import: this reads the worker's own OrgAIConfig ORM mirror
(src/models/__init__.py), consistent with worker-service/src/llm/org_resolver.py
and the existing OrgAIConfig/OrgApiKey model mirrors.

Single entry point for both sentiment call sites:

    resolved = resolve_sentiment_provider(org_id, db)
    provider_name = resolved.provider if resolved else "vader"
    analyzer = get_sentiment_analyzer(provider_name)

Design:
  - Reads OrgAIConfig.sentiment_provider for the org.
  - Returns None whenever the org isn't explicitly, validly configured (no
    OrgAIConfig row, NULL column, or an unrecognized value) — the caller's own
    "vader" fallback then applies.
  - Never raises to the caller.
  - Multi-tenant: always scoped by org_id.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

VALID_SENTIMENT_PROVIDERS: frozenset = frozenset({"vader", "transformer"})


@dataclass
class ResolvedSentiment:
    """Result of a successful sentiment provider resolution.

    Attributes:
        provider: Validated provider name, one of VALID_SENTIMENT_PROVIDERS.
    """
    provider: str


def resolve_sentiment_provider(org_id: int, db) -> Optional[ResolvedSentiment]:
    """
    Resolve the org's configured sentiment provider.

    Returns:
        ResolvedSentiment(provider=...) if the org has an explicit, valid
        sentiment_provider set ('vader' or 'transformer').
        None if there is no OrgAIConfig row, the column is NULL/unset, the
        value is unrecognized, or any error occurs reading it. Callers treat
        None as "use VADER" — this function never raises.
    """
    try:
        from src.models import OrgAIConfig

        config = db.query(OrgAIConfig).filter_by(organization_id=org_id).first()
        if config is None:
            logger.debug(
                "resolve_sentiment_provider: no OrgAIConfig for org=%s", org_id
            )
            return None

        # getattr with default so this resolver never breaks against a DB that
        # hasn't run this aspect's migration yet (mirrors model_embeddings
        # precedent).
        provider: Optional[str] = getattr(config, "sentiment_provider", None)

        if not provider:
            return None

        if provider not in VALID_SENTIMENT_PROVIDERS:
            logger.warning(
                "resolve_sentiment_provider: unrecognized sentiment_provider=%r "
                "for org=%s — degrading to vader",
                provider, org_id,
            )
            return None

        return ResolvedSentiment(provider=provider)

    except Exception as exc:
        logger.warning(
            "resolve_sentiment_provider: failed for org=%s: %s",
            org_id, exc, exc_info=True,
        )
        return None
