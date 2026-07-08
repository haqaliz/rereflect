# DUPLICATED: keep in sync with the worker-service copy at
# services/worker-service/src/services/segment_service.py. See TRACKING.md.
"""
Customer segment classifier.

``classify_segment(...) -> str`` is a PURE, no-DB rule engine that assigns a
single segment slug to a customer, given already-computed health/usage/
sentiment signals. Callers (``health_score_service.resolve_segment`` on
ingest, the worker's nightly ``recompute_segments`` task) build the inputs
from ORM rows and pass primitives in — the core here never touches the DB.

Rules are evaluated top-down; the FIRST matching rule wins. See
``docs/planning/customer-segments/segment-engine/spec.md`` and
``plan_20260708.md`` (Phase 1) for the authoritative rule table.

Thresholds are reused from ``usage_score_service`` (do not redefine magic
numbers here).
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from src.services.usage_score_service import (
    FREQUENCY_MOD_HIGH_DAYS,
    FREQUENCY_LOW_MOD_DAYS,
    RECENCY_AGING_DAYS,
    RECENCY_STALE_DAYS,
)

# ---------------------------------------------------------------------------
# Segment slugs — canonical set, priority order
# ---------------------------------------------------------------------------

SEGMENT_AT_RISK = "at_risk"
SEGMENT_SILENT_CHURNER = "silent_churner"
SEGMENT_DORMANT = "dormant"
SEGMENT_POWER_USER = "power_user"
SEGMENT_HAPPY_ADVOCATE = "happy_advocate"
SEGMENT_NEW = "new"
SEGMENT_UNSEGMENTED = "unsegmented"

# Exported in PRIORITY ORDER — later aspects (segment-api, segment-ui) import
# this list. Keep it stable.
SEGMENT_SLUGS = [
    SEGMENT_AT_RISK,
    SEGMENT_SILENT_CHURNER,
    SEGMENT_DORMANT,
    SEGMENT_POWER_USER,
    SEGMENT_HAPPY_ADVOCATE,
    SEGMENT_NEW,
    SEGMENT_UNSEGMENTED,
]

# Thresholds specific to segment rules (not owned by usage_score_service)
AT_RISK_CHURN_PROBABILITY_THRESHOLD: float = 0.5
SILENT_CHURNER_FEEDBACK_STALE_DAYS: int = 30
DORMANT_NO_USAGE_FEEDBACK_STALE_DAYS: int = RECENCY_STALE_DAYS  # 60
POWER_USER_USAGE_SCORE_THRESHOLD: int = 75
HAPPY_ADVOCATE_HEALTH_SCORE_THRESHOLD: int = 75
NEW_CUSTOMER_AGE_DAYS: int = 14
NEW_CUSTOMER_MAX_FEEDBACK_COUNT: int = 3

AT_RISK_RISK_LEVELS = {"at_risk", "critical"}
HAPPY_ADVOCATE_SENTIMENT_DIRECTIONS = {"improving", "stable"}


@dataclass(frozen=True)
class UsageSignals:
    """
    Lightweight, pure carrier for product-usage signals used by the
    classifier. Mirrors the fields on ``CustomerUsage`` (see
    ``models/customer_usage.py``) that segment rules need. Callers build
    this from the ORM row (or pass ``None`` when no ``CustomerUsage`` row
    exists for the customer) — the classifier itself never touches the DB.
    """

    last_active_at: Optional[datetime] = None
    active_days_30d: Optional[int] = None
    distinct_feature_count: Optional[int] = None
    usage_score: Optional[int] = None
    first_seen_at: Optional[datetime] = None


def _days_ago(now: datetime, dt: Optional[datetime]) -> Optional[int]:
    """Return the (non-negative) number of whole days between ``dt`` and ``now``, or None."""
    if dt is None:
        return None
    n = now.replace(tzinfo=None) if now.tzinfo else now
    d = dt.replace(tzinfo=None) if dt.tzinfo else dt
    return max(0, (n - d).days)


def classify_segment(
    *,
    health_score: float,
    risk_level: Optional[str],
    churn_probability: Optional[float],
    feedback_count: int,
    last_feedback_at: Optional[datetime],
    created_at: Optional[datetime],
    usage: Optional[UsageSignals],
    sentiment_direction: Optional[str],
    now: datetime,
) -> str:
    """
    Classify a customer into exactly one segment slug.

    Pure function — no DB access. Evaluates rules top-down; first match wins.
    See module docstring / spec.md for the rule table.
    """

    # 1. at_risk
    if (risk_level in AT_RISK_RISK_LEVELS) or (
        churn_probability is not None
        and churn_probability >= AT_RISK_CHURN_PROBABILITY_THRESHOLD
    ):
        return SEGMENT_AT_RISK

    # 2. silent_churner — usage-gated
    if (
        usage is not None
        and usage.active_days_30d is not None
        and usage.active_days_30d < FREQUENCY_LOW_MOD_DAYS
        and sentiment_direction == "declining"
        and (
            last_feedback_at is None
            or (_days_ago(now, last_feedback_at) or 0) > SILENT_CHURNER_FEEDBACK_STALE_DAYS
        )
    ):
        return SEGMENT_SILENT_CHURNER

    # 3. dormant — usage-gated recency arm OR usage-less feedback-recency arm
    usage_dormant = (
        usage is not None
        and usage.last_active_at is not None
        and (_days_ago(now, usage.last_active_at) or 0) > RECENCY_AGING_DAYS
    )
    no_usage_dormant = (
        usage is None
        and last_feedback_at is not None
        and (_days_ago(now, last_feedback_at) or 0) > DORMANT_NO_USAGE_FEEDBACK_STALE_DAYS
    )
    if usage_dormant or no_usage_dormant:
        return SEGMENT_DORMANT

    # 4. power_user — usage-gated
    if (
        usage is not None
        and usage.usage_score is not None
        and usage.usage_score >= POWER_USER_USAGE_SCORE_THRESHOLD
        and usage.active_days_30d is not None
        and usage.active_days_30d >= FREQUENCY_MOD_HIGH_DAYS
    ):
        return SEGMENT_POWER_USER

    # 5. happy_advocate
    if (
        health_score >= HAPPY_ADVOCATE_HEALTH_SCORE_THRESHOLD
        and sentiment_direction in HAPPY_ADVOCATE_SENTIMENT_DIRECTIONS
    ):
        return SEGMENT_HAPPY_ADVOCATE

    # 6. new
    if (
        created_at is not None
        and (_days_ago(now, created_at) or 0) <= NEW_CUSTOMER_AGE_DAYS
        and feedback_count < NEW_CUSTOMER_MAX_FEEDBACK_COUNT
    ):
        return SEGMENT_NEW

    # 7. else
    return SEGMENT_UNSEGMENTED
