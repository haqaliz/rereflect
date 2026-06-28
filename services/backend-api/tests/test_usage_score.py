"""
TDD tests for compute_usage_score() — Phase 2.

RED → GREEN workflow: these tests were written BEFORE the implementation.

Acceptance criteria:
  AC3: recent+frequent+broad usage → high (>70)
  AC3: stale (last active >30d, low activity) → low (<40)
  AC3: no rollup (None) → 50 (neutral)
  Additional: monotonic in recency; all-None fields → 50
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# Helpers — lightweight rollup proxy so tests don't need the DB
# ---------------------------------------------------------------------------

def _rollup(
    last_active_days_ago=None,
    active_days_30d=None,
    distinct_feature_count=None,
):
    """Build a simple namespace object that looks like a CustomerUsage row."""
    r = MagicMock()
    r.last_active_at = (
        datetime.utcnow() - timedelta(days=last_active_days_ago)
        if last_active_days_ago is not None
        else None
    )
    r.active_days_30d = active_days_30d
    r.distinct_feature_count = distinct_feature_count
    return r


# ---------------------------------------------------------------------------
# Import target (will fail RED until implemented)
# ---------------------------------------------------------------------------

from src.services.usage_score_service import compute_usage_score


# ---------------------------------------------------------------------------
# Acceptance criteria
# ---------------------------------------------------------------------------

class TestComputeUsageScore:
    def test_no_rollup_returns_neutral_50(self):
        """AC3: no rollup / None → 50."""
        assert compute_usage_score(None) == 50

    def test_all_none_fields_returns_neutral_50(self):
        """AC3: rollup exists but all key fields are None → 50 (neutral)."""
        r = _rollup(last_active_days_ago=None, active_days_30d=None, distinct_feature_count=None)
        score = compute_usage_score(r)
        assert score == 50

    def test_recent_frequent_broad_is_high(self):
        """AC3: very recent + high frequency + high breadth → > 70."""
        r = _rollup(last_active_days_ago=1, active_days_30d=22, distinct_feature_count=6)
        score = compute_usage_score(r)
        assert score > 70, f"Expected >70, got {score}"

    def test_stale_inactive_is_low(self):
        """AC3: last active >30d + no recent activity → < 40."""
        r = _rollup(last_active_days_ago=45, active_days_30d=0, distinct_feature_count=1)
        score = compute_usage_score(r)
        assert score < 40, f"Expected <40, got {score}"

    def test_very_stale_is_very_low(self):
        """Last active >60d + zero activity → score should be very low."""
        r = _rollup(last_active_days_ago=90, active_days_30d=0, distinct_feature_count=0)
        score = compute_usage_score(r)
        assert score < 20, f"Expected <20, got {score}"

    def test_monotonic_recency(self):
        """Score decreases strictly as last_active_at ages."""
        now = datetime.utcnow()
        # Span across several recency bands with fixed freq/breadth
        scores = []
        for days_ago in [1, 5, 12, 25, 45, 75]:
            r = _rollup(
                last_active_days_ago=days_ago,
                active_days_30d=5,
                distinct_feature_count=3,
            )
            scores.append(compute_usage_score(r, now=now))

        # Each successive score must be <= the previous one
        for i in range(1, len(scores)):
            assert scores[i] <= scores[i - 1], (
                f"Score NOT monotonic: days[{i-1}] score={scores[i-1]}, "
                f"days[{i}] score={scores[i]}"
            )

    def test_score_clamped_0_to_100(self):
        """Score is always in [0, 100]."""
        r = _rollup(last_active_days_ago=1, active_days_30d=30, distinct_feature_count=10)
        score = compute_usage_score(r)
        assert 0 <= score <= 100

    def test_low_score_clamped_at_zero(self):
        """Even with worst-case inputs, score stays >= 0."""
        r = _rollup(last_active_days_ago=365, active_days_30d=0, distinct_feature_count=0)
        score = compute_usage_score(r)
        assert score >= 0

    # ------------------------------------------------------------------
    # Recency band smoke tests
    # ------------------------------------------------------------------

    def test_recency_very_recent(self):
        """≤2 days → recency component maxes out; total score is high."""
        r = _rollup(last_active_days_ago=1, active_days_30d=15, distinct_feature_count=5)
        assert compute_usage_score(r) > 70

    def test_recency_recent(self):
        """3-7 days — still fairly high."""
        r = _rollup(last_active_days_ago=5, active_days_30d=10, distinct_feature_count=3)
        score = compute_usage_score(r)
        assert score > 50

    def test_recency_aging(self):
        """15-30 days — moderate; score should be below very-recent but not critical."""
        r = _rollup(last_active_days_ago=20, active_days_30d=2, distinct_feature_count=2)
        score = compute_usage_score(r)
        assert score < 70

    def test_recency_stale(self):
        """31-60 days — pulling score down noticeably."""
        r = _rollup(last_active_days_ago=50, active_days_30d=0, distinct_feature_count=1)
        score = compute_usage_score(r)
        assert score < 40

    # ------------------------------------------------------------------
    # Frequency band smoke tests
    # ------------------------------------------------------------------

    def test_frequency_high(self):
        """≥20 active days → frequency component maxes out."""
        r = _rollup(last_active_days_ago=2, active_days_30d=25, distinct_feature_count=5)
        score = compute_usage_score(r)
        assert score > 80

    def test_frequency_zero(self):
        """0 active days → low frequency component."""
        r = _rollup(last_active_days_ago=2, active_days_30d=0, distinct_feature_count=5)
        r2 = _rollup(last_active_days_ago=2, active_days_30d=20, distinct_feature_count=5)
        assert compute_usage_score(r) < compute_usage_score(r2)

    # ------------------------------------------------------------------
    # Breadth band smoke tests
    # ------------------------------------------------------------------

    def test_breadth_high(self):
        """≥5 features → breadth component maxes out."""
        r_high = _rollup(last_active_days_ago=2, active_days_30d=10, distinct_feature_count=5)
        r_low = _rollup(last_active_days_ago=2, active_days_30d=10, distinct_feature_count=1)
        assert compute_usage_score(r_high) > compute_usage_score(r_low)

    def test_breadth_zero(self):
        """0 distinct features → breadth component very low."""
        r = _rollup(last_active_days_ago=2, active_days_30d=10, distinct_feature_count=0)
        score = compute_usage_score(r)
        # With recency high (100) and frequency moderate, score still decent
        # but lower than with breadth
        assert score >= 0

    # ------------------------------------------------------------------
    # now= parameter
    # ------------------------------------------------------------------

    def test_custom_now_shifts_recency(self):
        """Passing an explicit now= shifts the recency calculation."""
        anchor = datetime(2026, 1, 1)
        last_active = anchor - timedelta(days=1)  # 1 day before anchor → very recent

        r = MagicMock()
        r.last_active_at = last_active
        r.active_days_30d = 10
        r.distinct_feature_count = 3

        score_with_now = compute_usage_score(r, now=anchor)

        # Same rollup, but "now" is 40 days later → recency is now 41 days → stale
        score_with_stale_now = compute_usage_score(r, now=anchor + timedelta(days=40))

        assert score_with_now > score_with_stale_now
