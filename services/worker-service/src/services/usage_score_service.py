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
from typing import List, Optional, Tuple

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


# ---------------------------------------------------------------------------
# Trend core (trend-detection-and-health aspect) — pure, no I/O.
#
# ``classify_usage_trend`` compares a customer's current active_days_14d
# against a baseline snapshot from ~14 days back (the baseline lookup itself
# is I/O and lives in the worker's recompute_usage_scores task; only the
# already-resolved baseline value + its age in days are passed in here, so
# every guard below is unit-testable without a DB). ``apply_trend_penalty``
# is applied ONLY to the health-score usage COMPONENT
# (health_score_service._compute_usage_component) — never to the stored
# customer_usage.usage_score, which segment_service.py's power_user rule
# reads directly (see aspect spec "Out of scope").
# ---------------------------------------------------------------------------

# Lookback band: "nearest to TARGET, among snapshots aged [MIN, MAX] days".
# Never widened, never relaxed to "oldest available" — see spec guards.
TREND_LOOKBACK_TARGET_DAYS: int = 14
TREND_LOOKBACK_MIN_DAYS: int = 12
TREND_LOOKBACK_MAX_DAYS: int = 16

# Baseline floor: below this, a small-number swing (e.g. 2 -> 1 active days)
# would read as a dramatic percentage decline that isn't a genuine signal.
TREND_MIN_BASELINE_ACTIVE_DAYS: int = 5

# State thresholds on usage_trend_pct (signed percent; negative = decline).
TREND_DECLINING_PCT: float = -30.0
TREND_SHARP_DECLINE_PCT: float = -60.0

# Health-component penalty per state. TREND_PENALTY_MAX is the hard cap
# asserted by the bounded-penalty property test (AC 5) — it must equal the
# largest of the two penalties below, or the bound would be violated.
TREND_PENALTY_DECLINING: int = 8
TREND_PENALTY_SHARP_DECLINE: int = 15
TREND_PENALTY_MAX: int = 15

# Trend-state slugs
TREND_STATE_INSUFFICIENT_HISTORY: str = "insufficient_history"
TREND_STATE_STABLE: str = "stable"
TREND_STATE_DECLINING: str = "declining"
TREND_STATE_SHARP_DECLINE: str = "sharp_decline"


def select_nearest_in_band_snapshot(
    snapshots: List[Tuple[int, Optional[int]]],
) -> Tuple[Optional[int], Optional[int]]:
    """
    Pick the trend baseline from a customer's candidate history snapshots.

    Args:
        snapshots: list of ``(age_days, active_days_14d)`` pairs — one entry
            per ``customer_usage_history`` row for this customer, where
            ``age_days`` is the (already computed) whole number of calendar
            days between "today" and that row's ``snapshot_date``.

    Returns:
        ``(baseline_active_days_14d, baseline_age_days)`` for the candidate
        nearest to ``TREND_LOOKBACK_TARGET_DAYS`` among those whose age falls
        in the closed band ``[TREND_LOOKBACK_MIN_DAYS, TREND_LOOKBACK_MAX_DAYS]``,
        or ``(None, None)`` when no candidate is in band. Never widens the
        band and never falls back to the oldest available snapshot.

    Tie-break (AC 2): when two candidates are equidistant from the target
    (e.g. ages 12 and 16 are both 2 days from 14), the OLDER snapshot (the
    larger ``age_days``) wins. This is arbitrary but must be deterministic —
    a non-deterministic pick would make the daily pass's idempotency (AC 13)
    flaky rather than simply failing.
    """
    in_band = [
        (age, value) for age, value in snapshots
        if TREND_LOOKBACK_MIN_DAYS <= age <= TREND_LOOKBACK_MAX_DAYS
    ]
    if not in_band:
        return (None, None)

    def _sort_key(item: Tuple[int, Optional[int]]) -> Tuple[int, int]:
        age, _ = item
        distance = abs(age - TREND_LOOKBACK_TARGET_DAYS)
        # Negate age so that, for equal distance, the larger age (older
        # snapshot) sorts first.
        return (distance, -age)

    best_age, best_value = min(in_band, key=_sort_key)
    return (best_value, best_age)


def classify_usage_trend(
    current_active_days_14d: Optional[int],
    baseline_active_days_14d: Optional[int],
    baseline_age_days: Optional[int],
) -> Tuple[str, Optional[float]]:
    """
    Classify a customer's usage direction from their current active_days_14d
    against a resolved baseline (see ``select_nearest_in_band_snapshot``).

    Guards — all return ``(insufficient_history, None)``, no division ever
    attempted:
      - ``baseline_age_days`` is None (caller found no in-band snapshot).
      - ``baseline_active_days_14d`` is None.
      - ``baseline_active_days_14d < TREND_MIN_BASELINE_ACTIVE_DAYS`` (also
        catches ``baseline_active_days_14d == 0``, the division-by-zero case).
      - ``current_active_days_14d`` is None.

    Otherwise returns ``(state, pct)`` where ``pct`` is the signed percent
    change ``(current - baseline) / baseline * 100``, rounded to 2 dp.
    Increases (and no change) always classify ``stable``.
    """
    if (
        baseline_age_days is None
        or baseline_active_days_14d is None
        or baseline_active_days_14d < TREND_MIN_BASELINE_ACTIVE_DAYS
        or current_active_days_14d is None
    ):
        return (TREND_STATE_INSUFFICIENT_HISTORY, None)

    pct = round(
        (current_active_days_14d - baseline_active_days_14d)
        / baseline_active_days_14d
        * 100,
        2,
    )

    if pct <= TREND_SHARP_DECLINE_PCT:
        state = TREND_STATE_SHARP_DECLINE
    elif pct <= TREND_DECLINING_PCT:
        state = TREND_STATE_DECLINING
    else:
        state = TREND_STATE_STABLE

    return (state, pct)


def apply_trend_penalty(usage_component: int, trend_state: str) -> int:
    """
    Apply the bounded trend penalty to a health-score usage COMPONENT value.

    ``stable`` and ``insufficient_history`` are free (penalty 0) — a
    customer still warming up their history must never look like decline
    (AC 7). ``declining`` / ``sharp_decline`` subtract a fixed, named
    penalty, clamped to ``[0, 100]``.

    Bound (AC 5): for every ``usage_component`` in 0-100 and every state,
    ``apply_trend_penalty(c, s) >= c - TREND_PENALTY_MAX``. This holds
    because every named penalty above is <= TREND_PENALTY_MAX by
    construction, and clamping only ever raises the result (via the
    ``max(0, ...)`` floor), never lowers it further.

    Double-count bound (AC 6): a customer whose recency AND frequency bands
    have already stepped down (docked ~10 + ~6 blended points via
    WEIGHT_RECENCY/WEIGHT_FREQUENCY before this function ever runs) and who
    is additionally classified ``declining`` or ``sharp_decline`` must keep
    a usage component >= 55 when their pre-decline component was >= 75.
    Since the largest penalty here is TREND_PENALTY_MAX (15),
    75 - 15 = 60 >= 55 — the arithmetic holds with headroom regardless of
    which of the two decline states applies.
    """
    if trend_state == TREND_STATE_SHARP_DECLINE:
        penalty = TREND_PENALTY_SHARP_DECLINE
    elif trend_state == TREND_STATE_DECLINING:
        penalty = TREND_PENALTY_DECLINING
    else:
        penalty = 0

    return max(0, min(100, usage_component - penalty))
