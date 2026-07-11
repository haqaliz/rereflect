"""
Org-scoped corrections-classifier mode resolver — M5.2 predict-seam-resolver.

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
  - classifier_type selects which OrgAIConfig column is read
    (MODE_COLUMN_BY_CLASSIFIER_TYPE) — sentiment and category are
    independently configurable; an unrecognized classifier_type degrades to
    None (off), same as an unrecognized mode value.

References:
  - services/backend-api/src/services/sentiment_resolver.py (shape mirrored)
  - services/worker-service/src/services/classifier_resolver.py (independent
    mirror — no cross-service import; reads the worker's own OrgAIConfig)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

VALID_CLASSIFIER_MODES: frozenset = frozenset({"shadow", "auto"})

# Per-classifier_type OrgAIConfig column holding the off/shadow/auto mode.
# Each type is independently controllable (PRD "Independent control" success
# metric) — enabling category never reads/writes the sentiment column and
# vice versa. Unknown classifier_type -> resolve_classifier degrades to None
# (same contract as an unrecognized mode value).
MODE_COLUMN_BY_CLASSIFIER_TYPE: dict = {
    "sentiment": "classifier_mode",
    "category": "category_classifier_mode",
}


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
        from src.models.org_ai_config import OrgAIConfig

        config = db.query(OrgAIConfig).filter_by(organization_id=org_id).first()
        if config is None:
            logger.debug(
                "resolve_classifier: no OrgAIConfig for org=%s classifier_type=%s",
                org_id, classifier_type,
            )
            return None

        mode_column = MODE_COLUMN_BY_CLASSIFIER_TYPE.get(classifier_type)
        if mode_column is None:
            logger.warning(
                "resolve_classifier: unrecognized classifier_type=%r for "
                "org=%s — degrading to off",
                classifier_type, org_id,
            )
            return None

        # getattr with default so this resolver never breaks against a DB
        # that hasn't run this aspect's migration yet (mirrors
        # resolve_sentiment_provider's precedent).
        mode: Optional[str] = getattr(config, mode_column, None)

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
