"""
Phase A — RED: pure trend core (no I/O).

Covers the two pure functions plus the lookback-selection helper added to
usage_score_service.py for the trend-detection-and-health aspect:

  - select_nearest_in_band_snapshot(snapshots) -> (baseline_value, baseline_age)
  - classify_usage_trend(current, baseline, baseline_age) -> (state, pct)
  - apply_trend_penalty(usage_component, trend_state) -> int

This file is intentionally byte-identical between backend-api/tests/ and
worker-service/tests/ (AC 15 — "core tested in BOTH") since both services
import the same module path (src.services.usage_score_service).

AC references are to docs/planning/usage-trend-churn-signal/
trend-detection-and-health/spec.md.
"""
import pytest

from src.services.usage_score_service import (
    TREND_LOOKBACK_MAX_DAYS,
    TREND_LOOKBACK_MIN_DAYS,
    TREND_LOOKBACK_TARGET_DAYS,
    TREND_MIN_BASELINE_ACTIVE_DAYS,
    TREND_PENALTY_DECLINING,
    TREND_PENALTY_MAX,
    TREND_PENALTY_SHARP_DECLINE,
    TREND_STATE_DECLINING,
    TREND_STATE_INSUFFICIENT_HISTORY,
    TREND_STATE_SHARP_DECLINE,
    TREND_STATE_STABLE,
    apply_trend_penalty,
    classify_usage_trend,
    select_nearest_in_band_snapshot,
)


# ---------------------------------------------------------------------------
# AC 1, 2 — select_nearest_in_band_snapshot
# ---------------------------------------------------------------------------


class TestSelectNearestInBandSnapshot:
    def test_picks_nearest_in_band_among_three(self):
        """AC 1: snapshots at 10, 13, 20 days back -> the 13-day one is used."""
        value, age = select_nearest_in_band_snapshot(
            [(10, 999), (13, 7), (20, 999)]
        )
        assert (value, age) == (7, 13)

    def test_none_in_band_yields_insufficient_history_marker(self):
        """AC 1: only 10 and 20 days back (neither in [12, 16]) -> (None, None)."""
        value, age = select_nearest_in_band_snapshot([(10, 5), (20, 5)])
        assert (value, age) == (None, None)

    def test_nearer_wins_inside_band(self):
        """AC 2: 12 and 15 days back -> 15 wins (distance 1 vs distance 2)."""
        value, age = select_nearest_in_band_snapshot([(12, 3), (15, 9)])
        assert (value, age) == (9, 15)

    def test_tie_at_12_vs_16_breaks_deterministically_to_older(self):
        """AC 2: 12 and 16 are equidistant from target=14 -> the OLDER
        snapshot (age=16) wins, per the stated tie-break rule."""
        value, age = select_nearest_in_band_snapshot([(12, 100), (16, 200)])
        assert (value, age) == (200, 16)

    def test_tie_break_is_order_independent(self):
        """The deterministic tie-break must not depend on input ordering."""
        a = select_nearest_in_band_snapshot([(16, 200), (12, 100)])
        b = select_nearest_in_band_snapshot([(12, 100), (16, 200)])
        assert a == b == (200, 16)

    def test_empty_snapshots_yields_none(self):
        assert select_nearest_in_band_snapshot([]) == (None, None)

    def test_band_boundaries_are_inclusive(self):
        """Ages exactly at TREND_LOOKBACK_MIN_DAYS / MAX_DAYS count as in-band."""
        value, age = select_nearest_in_band_snapshot(
            [(TREND_LOOKBACK_MIN_DAYS, 1)]
        )
        assert (value, age) == (1, TREND_LOOKBACK_MIN_DAYS)

        value, age = select_nearest_in_band_snapshot(
            [(TREND_LOOKBACK_MAX_DAYS, 2)]
        )
        assert (value, age) == (2, TREND_LOOKBACK_MAX_DAYS)

    def test_one_day_outside_each_boundary_is_excluded(self):
        assert select_nearest_in_band_snapshot(
            [(TREND_LOOKBACK_MIN_DAYS - 1, 1)]
        ) == (None, None)
        assert select_nearest_in_band_snapshot(
            [(TREND_LOOKBACK_MAX_DAYS + 1, 1)]
        ) == (None, None)


# ---------------------------------------------------------------------------
# AC 3 — small-number guard (incl. baseline 0 / None, no div-by-zero)
# ---------------------------------------------------------------------------


class TestClassifyUsageTrendSmallNumberGuard:
    def test_baseline_2_current_1_is_insufficient_history_not_declining(self):
        """A 2 -> 1 drop is -50% arithmetically, but the baseline floor
        (TREND_MIN_BASELINE_ACTIVE_DAYS=5) must catch this as noise, not
        signal."""
        state, pct = classify_usage_trend(1, 2, baseline_age_days=14)
        assert state == TREND_STATE_INSUFFICIENT_HISTORY
        assert pct is None

    def test_baseline_zero_never_divides(self):
        state, pct = classify_usage_trend(3, 0, baseline_age_days=14)
        assert state == TREND_STATE_INSUFFICIENT_HISTORY
        assert pct is None

    def test_baseline_none(self):
        state, pct = classify_usage_trend(3, None, baseline_age_days=14)
        assert state == TREND_STATE_INSUFFICIENT_HISTORY
        assert pct is None

    def test_baseline_age_none_no_in_band_snapshot(self):
        """No in-band snapshot is signalled by baseline_age_days=None,
        regardless of what baseline value happens to be passed."""
        state, pct = classify_usage_trend(10, 10, baseline_age_days=None)
        assert state == TREND_STATE_INSUFFICIENT_HISTORY
        assert pct is None

    def test_current_none(self):
        state, pct = classify_usage_trend(None, 10, baseline_age_days=14)
        assert state == TREND_STATE_INSUFFICIENT_HISTORY
        assert pct is None

    def test_baseline_exactly_at_floor_is_not_insufficient(self):
        """baseline == TREND_MIN_BASELINE_ACTIVE_DAYS (the floor itself) is
        NOT insufficient — only strictly below it is."""
        state, pct = classify_usage_trend(
            TREND_MIN_BASELINE_ACTIVE_DAYS,
            TREND_MIN_BASELINE_ACTIVE_DAYS,
            baseline_age_days=14,
        )
        assert state == TREND_STATE_STABLE
        assert pct == 0.0

    def test_baseline_one_below_floor_is_insufficient(self):
        state, pct = classify_usage_trend(
            TREND_MIN_BASELINE_ACTIVE_DAYS - 1,
            TREND_MIN_BASELINE_ACTIVE_DAYS - 1,
            baseline_age_days=14,
        )
        assert state == TREND_STATE_INSUFFICIENT_HISTORY
        assert pct is None


# ---------------------------------------------------------------------------
# AC 4 — state thresholds & pct values
# ---------------------------------------------------------------------------


class TestClassifyUsageTrendStateThresholds:
    def test_no_change_is_stable_pct_zero(self):
        state, pct = classify_usage_trend(10, 10, baseline_age_days=14)
        assert (state, pct) == (TREND_STATE_STABLE, 0.0)

    def test_increase_is_stable_positive_pct(self):
        state, pct = classify_usage_trend(12, 10, baseline_age_days=14)
        assert (state, pct) == (TREND_STATE_STABLE, 20.0)

    def test_moderate_decline_is_declining(self):
        state, pct = classify_usage_trend(6, 10, baseline_age_days=14)
        assert (state, pct) == (TREND_STATE_DECLINING, -40.0)

    def test_sharp_decline(self):
        state, pct = classify_usage_trend(3, 10, baseline_age_days=14)
        assert (state, pct) == (TREND_STATE_SHARP_DECLINE, -70.0)

    def test_all_four_states_reachable_and_mutually_exclusive(self):
        seen = set()
        for current, baseline in [
            (None, 10),   # insufficient_history (current None)
            (10, 10),     # stable
            (6, 10),      # declining
            (3, 10),      # sharp_decline
        ]:
            state, _ = classify_usage_trend(current, baseline, baseline_age_days=14)
            seen.add(state)
        assert seen == {
            TREND_STATE_INSUFFICIENT_HISTORY,
            TREND_STATE_STABLE,
            TREND_STATE_DECLINING,
            TREND_STATE_SHARP_DECLINE,
        }

    def test_pct_rounded_to_two_dp(self):
        # 14 vs 6 -> (14-6)/6*100 = 133.333...
        state, pct = classify_usage_trend(14, 6, baseline_age_days=14)
        assert pct == 133.33
        assert state == TREND_STATE_STABLE


# ---------------------------------------------------------------------------
# AC 5 — bounded penalty (property-style, full 0-100 range)
# ---------------------------------------------------------------------------


class TestApplyTrendPenaltyBounded:
    ALL_STATES = [
        TREND_STATE_INSUFFICIENT_HISTORY,
        TREND_STATE_STABLE,
        TREND_STATE_DECLINING,
        TREND_STATE_SHARP_DECLINE,
    ]

    def test_bound_holds_for_every_component_and_state(self):
        for c in range(0, 101):
            for state in self.ALL_STATES:
                result = apply_trend_penalty(c, state)
                assert result >= c - TREND_PENALTY_MAX, (c, state, result)
                assert 0 <= result <= 100, (c, state, result)

    def test_cannot_regress_below_hard_cap_even_if_constants_change(self):
        """Explicit guard that TREND_PENALTY_MAX is truly the max of the
        named per-state penalties — if a future edit raised
        TREND_PENALTY_SHARP_DECLINE above TREND_PENALTY_MAX without updating
        the cap, this test (not just the property test above) would catch it."""
        assert TREND_PENALTY_MAX >= TREND_PENALTY_DECLINING
        assert TREND_PENALTY_MAX >= TREND_PENALTY_SHARP_DECLINE


# ---------------------------------------------------------------------------
# AC 6 — double-counting bound (explicit, arithmetic stated)
# ---------------------------------------------------------------------------


class TestApplyTrendPenaltyDoubleCountBound:
    def test_pre_decline_75_stays_above_55_when_declining(self):
        """A customer already docked ~10 blended pts on recency and ~6 on
        frequency (WEIGHT_RECENCY=0.50, WEIGHT_FREQUENCY=0.30 — see
        usage_score_service module docstring) whose pre-decline usage
        component was 75, additionally classified `declining`:
        75 - TREND_PENALTY_DECLINING(8) = 67 >= 55.
        """
        result = apply_trend_penalty(75, TREND_STATE_DECLINING)
        assert result == 67
        assert result >= 55

    def test_pre_decline_75_stays_above_55_when_sharp_decline(self):
        """Worst case: 75 - TREND_PENALTY_MAX(15) = 60 >= 55 — holds with
        5 points of headroom even at the maximum penalty."""
        result = apply_trend_penalty(75, TREND_STATE_SHARP_DECLINE)
        assert result == 60
        assert result >= 55


# ---------------------------------------------------------------------------
# AC 7 — stable / insufficient_history are free
# ---------------------------------------------------------------------------


class TestApplyTrendPenaltyFreeStates:
    def test_stable_never_changes_component(self):
        for c in range(0, 101):
            assert apply_trend_penalty(c, TREND_STATE_STABLE) == c

    def test_insufficient_history_never_changes_component(self):
        for c in range(0, 101):
            assert apply_trend_penalty(c, TREND_STATE_INSUFFICIENT_HISTORY) == c


# ---------------------------------------------------------------------------
# AC 14 — trend-distribution sanity bound
# ---------------------------------------------------------------------------


class TestTrendDistributionSanity:
    def test_at_least_50_flat_customers_are_overwhelmingly_stable(self):
        """
        >=50 customers with FLAT usage (baseline == current, or differing by
        <=1) and valid in-band snapshots must classify >=95% `stable` and
        ZERO `sharp_decline`. This is the only AC that fails for the right
        reason if the thresholds are miscalibrated (too loose) — every other
        test above would still pass green under degenerate thresholds.
        """
        baselines = list(range(5, 65))  # 60 customers, baseline 5..64
        results = []
        for i, baseline in enumerate(baselines):
            # Alternate: exact match, +1, -1 (all "flat" per the AC's own definition)
            drift = [0, 1, -1][i % 3]
            current = baseline + drift
            state, _ = classify_usage_trend(current, baseline, baseline_age_days=14)
            results.append(state)

        assert len(results) >= 50
        stable_count = sum(1 for s in results if s == TREND_STATE_STABLE)
        sharp_count = sum(1 for s in results if s == TREND_STATE_SHARP_DECLINE)

        assert sharp_count == 0, f"flat-usage fixture produced {sharp_count} sharp_decline (expected 0)"
        assert stable_count / len(results) >= 0.95, (
            f"only {stable_count}/{len(results)} flat-usage customers classified stable "
            f"(expected >=95%) — thresholds may be degenerate"
        )
