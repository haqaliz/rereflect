# DUPLICATED: keep in sync with the worker-service copy at
# services/worker-service/src/services/usage_score_service.py. See TRACKING.md.
"""
Usage score computation service.

``compute_usage_score(rollup, now) -> int`` blends three dimensions:
  - Recency   (weight 0.50): time since last_active_at
  - Frequency (weight 0.30): active_days_30d
  - Breadth   (weight 0.20): distinct_feature_count

Returns an integer 0-100 (higher = more engaged).

Neutral fallback of 50 is returned when:
  - ``rollup`` is None (no row in the customer_usage table), OR
  - all three measured dimensions are None (no data at all).

This module is pure Python with no I/O — it is designed to be importable
by both the backend-api read API and the worker-service Celery task.
"""

from datetime import datetime
from typing import Optional

# ---------------------------------------------------------------------------
# Named thresholds — NO magic numbers in the function bodies below
# ---------------------------------------------------------------------------

# Recency thresholds (calendar days since last_active_at)
RECENCY_VERY_RECENT_DAYS: int = 2    # ≤2 d
RECENCY_RECENT_DAYS: int = 7         # ≤7 d
RECENCY_MODERATE_DAYS: int = 14      # ≤14 d
RECENCY_AGING_DAYS: int = 30         # ≤30 d
RECENCY_STALE_DAYS: int = 60         # ≤60 d
# > RECENCY_STALE_DAYS → inactive

# Recency component scores (0-100 per-band)
RECENCY_SCORE_VERY_RECENT: int = 100
RECENCY_SCORE_RECENT: int = 80
RECENCY_SCORE_MODERATE: int = 60
RECENCY_SCORE_AGING: int = 40
RECENCY_SCORE_STALE: int = 20
RECENCY_SCORE_INACTIVE: int = 5
RECENCY_SCORE_UNKNOWN: int = 50   # neutral when last_active_at is None

# Frequency thresholds (active calendar days within last 30 days)
FREQUENCY_HIGH_DAYS: int = 20        # ≥20 active days → max
FREQUENCY_MOD_HIGH_DAYS: int = 15    # ≥15
FREQUENCY_MODERATE_DAYS: int = 10    # ≥10
FREQUENCY_LOW_MOD_DAYS: int = 5      # ≥5
FREQUENCY_LOW_DAYS: int = 2          # ≥2
# < FREQUENCY_LOW_DAYS (0 or 1) → inactive

# Frequency component scores
FREQUENCY_SCORE_HIGH: int = 100
FREQUENCY_SCORE_MOD_HIGH: int = 80
FREQUENCY_SCORE_MODERATE: int = 60
FREQUENCY_SCORE_LOW_MOD: int = 40
FREQUENCY_SCORE_LOW: int = 20
FREQUENCY_SCORE_INACTIVE: int = 5
FREQUENCY_SCORE_UNKNOWN: int = 50    # neutral when active_days_30d is None

# Breadth thresholds (count of distinct feature names)
BREADTH_HIGH: int = 5       # ≥5 features → max
BREADTH_MOD_HIGH: int = 4   # ≥4
BREADTH_MODERATE: int = 3   # ≥3
BREADTH_LOW_MOD: int = 2    # ≥2
BREADTH_LOW: int = 1        # ≥1
# < BREADTH_LOW (0) → none

# Breadth component scores
BREADTH_SCORE_HIGH: int = 100
BREADTH_SCORE_MOD_HIGH: int = 80
BREADTH_SCORE_MODERATE: int = 60
BREADTH_SCORE_LOW_MOD: int = 40
BREADTH_SCORE_LOW: int = 20
BREADTH_SCORE_NONE: int = 5
BREADTH_SCORE_UNKNOWN: int = 50  # neutral when distinct_feature_count is None

# Blend weights (must sum to 1.0)
WEIGHT_RECENCY: float = 0.50
WEIGHT_FREQUENCY: float = 0.30
WEIGHT_BREADTH: float = 0.20

# Neutral / fallback score
SCORE_NEUTRAL: int = 50


# ---------------------------------------------------------------------------
# Internal component helpers
# ---------------------------------------------------------------------------


def _recency_component(last_active_at: Optional[datetime], now: datetime) -> int:
    """Return the 0-100 recency score from the age of last_active_at."""
    if last_active_at is None:
        return RECENCY_SCORE_UNKNOWN

    # Strip timezone for safe subtraction if needed
    laa = last_active_at.replace(tzinfo=None) if last_active_at.tzinfo else last_active_at
    n = now.replace(tzinfo=None) if now.tzinfo else now

    delta_days = max(0, (n - laa).days)

    if delta_days <= RECENCY_VERY_RECENT_DAYS:
        return RECENCY_SCORE_VERY_RECENT
    if delta_days <= RECENCY_RECENT_DAYS:
        return RECENCY_SCORE_RECENT
    if delta_days <= RECENCY_MODERATE_DAYS:
        return RECENCY_SCORE_MODERATE
    if delta_days <= RECENCY_AGING_DAYS:
        return RECENCY_SCORE_AGING
    if delta_days <= RECENCY_STALE_DAYS:
        return RECENCY_SCORE_STALE
    return RECENCY_SCORE_INACTIVE


def _frequency_component(active_days_30d: Optional[int]) -> int:
    """Return the 0-100 frequency score from active_days_30d."""
    if active_days_30d is None:
        return FREQUENCY_SCORE_UNKNOWN

    f = active_days_30d
    if f >= FREQUENCY_HIGH_DAYS:
        return FREQUENCY_SCORE_HIGH
    if f >= FREQUENCY_MOD_HIGH_DAYS:
        return FREQUENCY_SCORE_MOD_HIGH
    if f >= FREQUENCY_MODERATE_DAYS:
        return FREQUENCY_SCORE_MODERATE
    if f >= FREQUENCY_LOW_MOD_DAYS:
        return FREQUENCY_SCORE_LOW_MOD
    if f >= FREQUENCY_LOW_DAYS:
        return FREQUENCY_SCORE_LOW
    return FREQUENCY_SCORE_INACTIVE


def _breadth_component(distinct_feature_count: Optional[int]) -> int:
    """Return the 0-100 breadth score from the count of distinct features."""
    if distinct_feature_count is None:
        return BREADTH_SCORE_UNKNOWN

    b = distinct_feature_count
    if b >= BREADTH_HIGH:
        return BREADTH_SCORE_HIGH
    if b >= BREADTH_MOD_HIGH:
        return BREADTH_SCORE_MOD_HIGH
    if b >= BREADTH_MODERATE:
        return BREADTH_SCORE_MODERATE
    if b >= BREADTH_LOW_MOD:
        return BREADTH_SCORE_LOW_MOD
    if b >= BREADTH_LOW:
        return BREADTH_SCORE_LOW
    return BREADTH_SCORE_NONE


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def compute_usage_score(rollup, now: Optional[datetime] = None) -> int:
    """
    Compute a 0-100 product-usage engagement score for a single customer.

    Args:
        rollup: A ``CustomerUsage`` ORM instance (or any object with
                ``last_active_at``, ``active_days_30d``, and
                ``distinct_feature_count`` attributes).  Pass ``None`` to
                get the neutral default.
        now:    Reference timestamp for recency computation.  Defaults to
                ``datetime.utcnow()`` when omitted.

    Returns:
        Integer score in [0, 100].  Returns 50 when ``rollup`` is None or
        when all three key fields are None (no data available).
    """
    if rollup is None:
        return SCORE_NEUTRAL

    if now is None:
        now = datetime.utcnow()

    last_active_at = getattr(rollup, "last_active_at", None)
    active_days_30d = getattr(rollup, "active_days_30d", None)
    distinct_feature_count = getattr(rollup, "distinct_feature_count", None)

    # All three dimensions unknown → neutral (blend would also yield 50, but
    # be explicit for clarity and to avoid surprise if weights change).
    if last_active_at is None and active_days_30d is None and distinct_feature_count is None:
        return SCORE_NEUTRAL

    recency = _recency_component(last_active_at, now)
    frequency = _frequency_component(active_days_30d)
    breadth = _breadth_component(distinct_feature_count)

    raw = (
        recency * WEIGHT_RECENCY
        + frequency * WEIGHT_FREQUENCY
        + breadth * WEIGHT_BREADTH
    )
    return max(0, min(100, round(raw)))
