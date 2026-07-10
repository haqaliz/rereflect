"""
Org-scoped corrections-classifier mode resolver — worker-service mirror
(M5.2 predict-seam-resolver).

Independent mirror of services/backend-api/src/services/classifier_resolver.py.
No cross-service import: this reads the worker's own OrgAIConfig ORM mirror
(src/models/__init__.py), consistent with sentiment_resolver.py's precedent.

Single entry point for both classifier call sites:

    resolved = resolve_classifier(org_id, "sentiment", db)
    if resolved is None:
        ...  # off / unconfigured — no-op, keep incumbent analyzer output
    elif resolved.mode == "shadow":
        ...  # compute + log challenger, never mutate stored values
    elif resolved.mode == "auto":
        ...  # (worker only) override stored values with challenger

Design:
  - Reads OrgAIConfig.classifier_mode for the org via getattr-defensive access
    so this resolver is safe to call even against a DB that hasn't run the
    data-layer migration yet (missing column -> None, never raises).
  - Returns None for 'off' (the default), no OrgAIConfig row, a NULL/unset
    column, or an unrecognized value.
  - Never raises to the caller.
  - Multi-tenant: always scoped by org_id.
  - classifier_type is accepted (and passed through in log messages) for
    forward-compat with a future non-sentiment classifier type; v1 only has
    OrgAIConfig.classifier_mode (a single per-org mode, not per-type).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

VALID_CLASSIFIER_MODES: frozenset = frozenset({"shadow", "auto"})


@dataclass
class ResolvedClassifier:
    """Result of a successful classifier-mode resolution.

    Attributes:
        mode: Validated mode, one of VALID_CLASSIFIER_MODES ('shadow' or 'auto').
    """
    mode: str


def resolve_classifier(org_id: int, classifier_type: str, db) -> Optional[ResolvedClassifier]:
    """
    Resolve the org's configured corrections-classifier mode.

    Returns:
        ResolvedClassifier(mode=...) if the org has an explicit 'shadow' or
        'auto' classifier_mode set.
        None if there is no OrgAIConfig row, the column is NULL/unset/'off',
        the column doesn't exist (un-migrated DB), the value is unrecognized,
        or any error occurs reading it. Callers treat None as "off" — this
        function never raises.
    """
    try:
        from src.models import OrgAIConfig

        config = db.query(OrgAIConfig).filter_by(organization_id=org_id).first()
        if config is None:
            logger.debug(
                "resolve_classifier: no OrgAIConfig for org=%s classifier_type=%s",
                org_id, classifier_type,
            )
            return None

        # getattr with default so this resolver never breaks against a DB
        # that hasn't run this aspect's migration yet (mirrors
        # resolve_sentiment_provider's precedent).
        mode: Optional[str] = getattr(config, "classifier_mode", None)

        if not mode or mode == "off":
            return None

        if mode not in VALID_CLASSIFIER_MODES:
            logger.warning(
                "resolve_classifier: unrecognized classifier_mode=%r for "
                "org=%s classifier_type=%s — degrading to off",
                mode, org_id, classifier_type,
            )
            return None

        return ResolvedClassifier(mode=mode)

    except Exception as exc:
        logger.warning(
            "resolve_classifier: failed for org=%s classifier_type=%s: %s",
            org_id, classifier_type, exc, exc_info=True,
        )
        return None
