"""
TDD tests for classify_segment() — customer-segments Phase 1 (segment-engine).

RED -> GREEN workflow: these tests were written BEFORE the implementation in
src/services/segment_service.py.

Pure classifier — no DB. `usage` is either None or a UsageSignals instance.

Priority order (first match wins):
  1. at_risk
  2. silent_churner   (usage-gated)
  3. dormant          (usage-gated first arm; usage-less second arm)
  4. power_user       (usage-gated)
  5. happy_advocate
  6. new
  7. unsegmented
"""
from datetime import datetime, timedelta

import pytest

from src.services.segment_service import (
    SEGMENT_SLUGS,
    SEGMENT_AT_RISK,
    SEGMENT_SILENT_CHURNER,
    SEGMENT_DORMANT,
    SEGMENT_POWER_USER,
    SEGMENT_HAPPY_ADVOCATE,
    SEGMENT_NEW,
    SEGMENT_UNSEGMENTED,
    SILENT_CHURNER_FEEDBACK_STALE_DAYS,
    UsageSignals,
    classify_segment,
)
from src.services.usage_score_service import FREQUENCY_LOW_MOD_DAYS, RECENCY_AGING_DAYS

NOW = datetime(2026, 7, 8, 12, 0, 0)


def _usage(
    last_active_at=None,
    active_days_30d=None,
    distinct_feature_count=None,
    usage_score=None,
    first_seen_at=None,
):
    return UsageSignals(
        last_active_at=last_active_at,
        active_days_30d=active_days_30d,
        distinct_feature_count=distinct_feature_count,
        usage_score=usage_score,
        first_seen_at=first_seen_at,
    )


def _classify(
    health_score=50,
    risk_level="healthy",
    churn_probability=None,
    feedback_count=10,
    last_feedback_at=None,
    created_at=None,
    usage=None,
    sentiment_direction="stable",
    now=NOW,
):
    return classify_segment(
        health_score=health_score,
        risk_level=risk_level,
        churn_probability=churn_probability,
        feedback_count=feedback_count,
        last_feedback_at=last_feedback_at,
        created_at=created_at,
        usage=usage,
        sentiment_direction=sentiment_direction,
        now=now,
    )


# ---------------------------------------------------------------------------
# SEGMENT_SLUGS export
# ---------------------------------------------------------------------------


class TestSegmentSlugsExport:
    def test_priority_order_and_membership(self):
        assert SEGMENT_SLUGS == [
            SEGMENT_AT_RISK,
            SEGMENT_SILENT_CHURNER,
            SEGMENT_DORMANT,
            SEGMENT_POWER_USER,
            SEGMENT_HAPPY_ADVOCATE,
            SEGMENT_NEW,
            SEGMENT_UNSEGMENTED,
        ]

    def test_all_slugs_are_unique_strings(self):
        assert len(SEGMENT_SLUGS) == len(set(SEGMENT_SLUGS))
        assert all(isinstance(s, str) for s in SEGMENT_SLUGS)


# ---------------------------------------------------------------------------
# One row matching each of the 6 segments exactly (+ unsegmented fallback)
# ---------------------------------------------------------------------------


class TestOneRowPerSegment:
    def test_at_risk_via_risk_level(self):
        result = _classify(risk_level="at_risk", health_score=50, sentiment_direction="stable")
        assert result == SEGMENT_AT_RISK

    def test_at_risk_via_critical_risk_level(self):
        result = _classify(risk_level="critical", health_score=80, sentiment_direction="improving")
        assert result == SEGMENT_AT_RISK

    def test_at_risk_via_churn_probability(self):
        result = _classify(risk_level="healthy", churn_probability=0.5, health_score=80)
        assert result == SEGMENT_AT_RISK

    def test_silent_churner(self):
        usage = _usage(active_days_30d=2)
        result = _classify(
            risk_level="healthy",
            churn_probability=0.1,
            usage=usage,
            sentiment_direction="declining",
            last_feedback_at=NOW - timedelta(days=45),
            health_score=50,
        )
        assert result == SEGMENT_SILENT_CHURNER

    def test_silent_churner_no_feedback_at_all(self):
        usage = _usage(active_days_30d=1)
        result = _classify(
            risk_level="healthy",
            churn_probability=None,
            usage=usage,
            sentiment_direction="declining",
            last_feedback_at=None,
            health_score=50,
        )
        assert result == SEGMENT_SILENT_CHURNER

    def test_dormant_via_usage_recency(self):
        usage = _usage(last_active_at=NOW - timedelta(days=40))
        result = _classify(
            risk_level="healthy",
            churn_probability=None,
            usage=usage,
            sentiment_direction="stable",
            health_score=50,
        )
        assert result == SEGMENT_DORMANT

    def test_dormant_via_no_usage_stale_feedback(self):
        result = _classify(
            risk_level="healthy",
            churn_probability=None,
            usage=None,
            sentiment_direction="stable",
            last_feedback_at=NOW - timedelta(days=61),
            health_score=50,
        )
        assert result == SEGMENT_DORMANT

    def test_power_user(self):
        usage = _usage(usage_score=80, active_days_30d=20)
        result = _classify(
            risk_level="healthy",
            churn_probability=None,
            usage=usage,
            sentiment_direction="stable",
            health_score=50,
        )
        assert result == SEGMENT_POWER_USER

    def test_happy_advocate(self):
        result = _classify(
            risk_level="healthy",
            churn_probability=None,
            usage=None,
            sentiment_direction="improving",
            health_score=80,
        )
        assert result == SEGMENT_HAPPY_ADVOCATE

    def test_happy_advocate_stable_sentiment(self):
        result = _classify(
            risk_level="healthy",
            churn_probability=None,
            usage=None,
            sentiment_direction="stable",
            health_score=75,
        )
        assert result == SEGMENT_HAPPY_ADVOCATE

    def test_new(self):
        result = _classify(
            risk_level="healthy",
            churn_probability=None,
            usage=None,
            sentiment_direction="stable",
            health_score=50,
            created_at=NOW - timedelta(days=5),
            feedback_count=1,
        )
        assert result == SEGMENT_NEW

    def test_unsegmented_fallback(self):
        result = _classify(
            risk_level="healthy",
            churn_probability=None,
            usage=None,
            sentiment_direction="stable",
            health_score=50,
            created_at=NOW - timedelta(days=100),
            feedback_count=10,
        )
        assert result == SEGMENT_UNSEGMENTED


# ---------------------------------------------------------------------------
# Priority tiebreaks
# ---------------------------------------------------------------------------


class TestPriorityTiebreaks:
    def test_power_user_shaped_row_but_critical_risk_is_at_risk(self):
        usage = _usage(usage_score=90, active_days_30d=25)
        result = _classify(
            risk_level="critical",
            churn_probability=None,
            usage=usage,
            sentiment_direction="stable",
            health_score=90,
        )
        assert result == SEGMENT_AT_RISK

    def test_advocate_shaped_row_but_stale_usage_is_dormant(self):
        usage = _usage(last_active_at=NOW - timedelta(days=40))
        result = _classify(
            risk_level="healthy",
            churn_probability=None,
            usage=usage,
            sentiment_direction="improving",
            health_score=80,
        )
        assert result == SEGMENT_DORMANT

    def test_silent_churner_beats_dormant_when_both_arms_present(self):
        # active_days_30d < 5 AND declining AND stale feedback triggers silent_churner
        # (rule 2) which must win over dormant (rule 3) since it's checked first,
        # even though last_active_at is also stale enough for dormant.
        usage = _usage(active_days_30d=2, last_active_at=NOW - timedelta(days=40))
        result = _classify(
            risk_level="healthy",
            churn_probability=None,
            usage=usage,
            sentiment_direction="declining",
            last_feedback_at=NOW - timedelta(days=45),
            health_score=50,
        )
        assert result == SEGMENT_SILENT_CHURNER

    def test_new_shaped_row_but_at_risk_wins(self):
        result = _classify(
            risk_level="at_risk",
            churn_probability=None,
            usage=None,
            sentiment_direction="stable",
            health_score=50,
            created_at=NOW - timedelta(days=2),
            feedback_count=1,
        )
        assert result == SEGMENT_AT_RISK


# ---------------------------------------------------------------------------
# No-usage path — usage-gated rules must never fire when usage is None
# ---------------------------------------------------------------------------


class TestNoUsagePath:
    def test_usage_none_power_user_shaped_other_fields_not_power_user(self):
        # No usage row at all — even though health/sentiment look great, without
        # usage the power_user rule cannot fire.
        result = _classify(
            risk_level="healthy",
            churn_probability=None,
            usage=None,
            sentiment_direction="stable",
            health_score=50,
        )
        assert result != SEGMENT_POWER_USER

    def test_usage_none_recent_feedback_not_dormant(self):
        result = _classify(
            risk_level="healthy",
            churn_probability=None,
            usage=None,
            sentiment_direction="stable",
            last_feedback_at=NOW - timedelta(days=5),
            health_score=50,
        )
        assert result != SEGMENT_DORMANT

    def test_usage_none_declining_sentiment_not_silent_churner(self):
        result = _classify(
            risk_level="healthy",
            churn_probability=None,
            usage=None,
            sentiment_direction="declining",
            last_feedback_at=NOW - timedelta(days=45),
            health_score=50,
        )
        assert result != SEGMENT_SILENT_CHURNER

    def test_usage_none_can_still_be_at_risk(self):
        result = _classify(
            risk_level="critical",
            churn_probability=None,
            usage=None,
            sentiment_direction="stable",
            health_score=50,
        )
        assert result == SEGMENT_AT_RISK

    def test_usage_none_can_still_be_happy_advocate(self):
        result = _classify(
            risk_level="healthy",
            churn_probability=None,
            usage=None,
            sentiment_direction="improving",
            health_score=90,
        )
        assert result == SEGMENT_HAPPY_ADVOCATE

    def test_usage_none_can_still_be_new(self):
        result = _classify(
            risk_level="healthy",
            churn_probability=None,
            usage=None,
            sentiment_direction="stable",
            health_score=50,
            created_at=NOW - timedelta(days=1),
            feedback_count=0,
        )
        assert result == SEGMENT_NEW

    def test_usage_none_can_still_be_unsegmented(self):
        result = _classify(
            risk_level="healthy",
            churn_probability=None,
            usage=None,
            sentiment_direction="stable",
            health_score=50,
            created_at=NOW - timedelta(days=100),
            feedback_count=10,
        )
        assert result == SEGMENT_UNSEGMENTED


# ---------------------------------------------------------------------------
# Boundary values at each threshold
# ---------------------------------------------------------------------------


class TestBoundaryValues:
    def test_churn_probability_exactly_half_is_at_risk(self):
        result = _classify(risk_level="healthy", churn_probability=0.5, health_score=50)
        assert result == SEGMENT_AT_RISK

    def test_churn_probability_just_below_half_is_not_at_risk_alone(self):
        result = _classify(risk_level="healthy", churn_probability=0.49, health_score=50)
        assert result != SEGMENT_AT_RISK

    def test_silent_churner_active_days_boundary_below_5_qualifies(self):
        usage = _usage(active_days_30d=4)
        result = _classify(
            risk_level="healthy",
            usage=usage,
            sentiment_direction="declining",
            last_feedback_at=NOW - timedelta(days=31),
            health_score=50,
        )
        assert result == SEGMENT_SILENT_CHURNER

    def test_silent_churner_active_days_boundary_at_5_disqualifies(self):
        usage = _usage(active_days_30d=5)
        result = _classify(
            risk_level="healthy",
            usage=usage,
            sentiment_direction="declining",
            last_feedback_at=NOW - timedelta(days=31),
            health_score=50,
        )
        assert result != SEGMENT_SILENT_CHURNER

    def test_silent_churner_last_feedback_boundary_exactly_30_days_disqualifies(self):
        usage = _usage(active_days_30d=2)
        result = _classify(
            risk_level="healthy",
            usage=usage,
            sentiment_direction="declining",
            last_feedback_at=NOW - timedelta(days=30),
            health_score=50,
        )
        assert result != SEGMENT_SILENT_CHURNER

    def test_silent_churner_last_feedback_boundary_just_over_30_days_qualifies(self):
        usage = _usage(active_days_30d=2)
        result = _classify(
            risk_level="healthy",
            usage=usage,
            sentiment_direction="declining",
            last_feedback_at=NOW - timedelta(days=31),
            health_score=50,
        )
        assert result == SEGMENT_SILENT_CHURNER

    def test_dormant_recency_boundary_exactly_30_days_disqualifies(self):
        usage = _usage(last_active_at=NOW - timedelta(days=30))
        result = _classify(risk_level="healthy", usage=usage, health_score=50)
        assert result != SEGMENT_DORMANT

    def test_dormant_recency_boundary_31_days_qualifies(self):
        usage = _usage(last_active_at=NOW - timedelta(days=31))
        result = _classify(risk_level="healthy", usage=usage, health_score=50)
        assert result == SEGMENT_DORMANT

    def test_dormant_no_usage_feedback_boundary_exactly_60_days_disqualifies(self):
        result = _classify(
            risk_level="healthy",
            usage=None,
            last_feedback_at=NOW - timedelta(days=60),
            health_score=50,
        )
        assert result != SEGMENT_DORMANT

    def test_dormant_no_usage_feedback_boundary_61_days_qualifies(self):
        result = _classify(
            risk_level="healthy",
            usage=None,
            last_feedback_at=NOW - timedelta(days=61),
            health_score=50,
        )
        assert result == SEGMENT_DORMANT

    def test_power_user_active_days_boundary_exactly_15_qualifies(self):
        usage = _usage(usage_score=75, active_days_30d=15)
        result = _classify(risk_level="healthy", usage=usage, health_score=50)
        assert result == SEGMENT_POWER_USER

    def test_power_user_active_days_boundary_14_disqualifies(self):
        usage = _usage(usage_score=75, active_days_30d=14)
        result = _classify(risk_level="healthy", usage=usage, health_score=50)
        assert result != SEGMENT_POWER_USER

    def test_power_user_usage_score_boundary_exactly_75_qualifies(self):
        usage = _usage(usage_score=75, active_days_30d=20)
        result = _classify(risk_level="healthy", usage=usage, health_score=50)
        assert result == SEGMENT_POWER_USER

    def test_power_user_usage_score_boundary_74_disqualifies(self):
        usage = _usage(usage_score=74, active_days_30d=20)
        result = _classify(risk_level="healthy", usage=usage, health_score=50)
        assert result != SEGMENT_POWER_USER

    def test_happy_advocate_health_score_boundary_exactly_75_qualifies(self):
        result = _classify(
            risk_level="healthy", usage=None, sentiment_direction="stable", health_score=75
        )
        assert result == SEGMENT_HAPPY_ADVOCATE

    def test_happy_advocate_health_score_boundary_74_disqualifies(self):
        result = _classify(
            risk_level="healthy", usage=None, sentiment_direction="stable", health_score=74
        )
        assert result != SEGMENT_HAPPY_ADVOCATE

    def test_new_created_at_boundary_exactly_14_days_qualifies(self):
        result = _classify(
            risk_level="healthy",
            usage=None,
            health_score=50,
            created_at=NOW - timedelta(days=14),
            feedback_count=0,
        )
        assert result == SEGMENT_NEW

    def test_new_created_at_boundary_15_days_disqualifies(self):
        result = _classify(
            risk_level="healthy",
            usage=None,
            health_score=50,
            created_at=NOW - timedelta(days=15),
            feedback_count=0,
        )
        assert result != SEGMENT_NEW

    def test_new_feedback_count_boundary_exactly_3_disqualifies(self):
        result = _classify(
            risk_level="healthy",
            usage=None,
            health_score=50,
            created_at=NOW - timedelta(days=1),
            feedback_count=3,
        )
        assert result != SEGMENT_NEW

    def test_new_feedback_count_boundary_2_qualifies(self):
        result = _classify(
            risk_level="healthy",
            usage=None,
            health_score=50,
            created_at=NOW - timedelta(days=1),
            feedback_count=2,
        )
        assert result == SEGMENT_NEW


# ---------------------------------------------------------------------------
# silent_churner reachability after rolling-window re-derivation
# (usage-trend-churn-signal / rollup-rewindow-fix, Phase E)
#
# Before that fix, `active_days_30d` froze at its last-event value for a
# customer who stopped sending usage events entirely — the rolling window
# never decayed toward zero on its own. Because the silent_churner rule is
# gated on `active_days_30d < FREQUENCY_LOW_MOD_DAYS`, a customer who had
# gone completely silent could still show a stale, high `active_days_30d`
# and would never trip the gate built specifically to catch them. The daily
# re-derivation (`recompute_usage_scores` -> `_rederive_windows`) now decays
# `active_days_30d` toward 0 when there are no recent events, making the
# segment reachable.
# ---------------------------------------------------------------------------


class TestSilentChurnerReachableAfterRewindow:
    # Same customer, same declining sentiment, same stale feedback — only
    # `active_days_30d` differs between the frozen (pre-fix) and re-derived
    # (post-fix) rollup state.
    _STALE_LAST_ACTIVE_AT = NOW - timedelta(days=RECENCY_AGING_DAYS + 15)
    _STALE_LAST_FEEDBACK_AT = NOW - timedelta(days=SILENT_CHURNER_FEEDBACK_STALE_DAYS + 15)

    def test_frozen_active_days_30d_classifies_as_dormant_not_silent_churner(self):
        # Pre-fix: active_days_30d is frozen at its last-event high-water mark
        # (>= FREQUENCY_LOW_MOD_DAYS), so the silent_churner gate never opens.
        # The customer falls through to the dormant rule instead, via the
        # equally-stale last_active_at.
        usage = _usage(
            active_days_30d=FREQUENCY_LOW_MOD_DAYS + 20,
            last_active_at=self._STALE_LAST_ACTIVE_AT,
        )
        result = _classify(
            risk_level="healthy",
            churn_probability=None,
            usage=usage,
            sentiment_direction="declining",
            last_feedback_at=self._STALE_LAST_FEEDBACK_AT,
            health_score=50,
        )
        assert result == SEGMENT_DORMANT

    def test_rederived_active_days_30d_classifies_as_silent_churner(self):
        # Post-fix: the daily recompute has decayed active_days_30d to 0
        # since there are no usage events in the window. Every other signal
        # is unchanged. The silent_churner gate now opens, and rule 2 fires
        # before the dormant check (rule 3) is ever reached.
        usage = _usage(
            active_days_30d=0,
            last_active_at=self._STALE_LAST_ACTIVE_AT,
        )
        result = _classify(
            risk_level="healthy",
            churn_probability=None,
            usage=usage,
            sentiment_direction="declining",
            last_feedback_at=self._STALE_LAST_FEEDBACK_AT,
            health_score=50,
        )
        assert result == SEGMENT_SILENT_CHURNER


class TestAtRiskPrecedesSilentChurner:
    """
    Guards against the fix accidentally reshuffling segment precedence:
    at_risk (rule 1) must still win over silent_churner (rule 2) even when
    a customer satisfies every silent_churner condition too.
    """

    def test_at_risk_via_risk_level_wins_over_silent_churner_shaped_row(self):
        usage = _usage(active_days_30d=0, last_active_at=NOW - timedelta(days=45))
        result = _classify(
            risk_level="at_risk",
            churn_probability=None,
            usage=usage,
            sentiment_direction="declining",
            last_feedback_at=NOW - timedelta(days=45),
            health_score=50,
        )
        assert result == SEGMENT_AT_RISK

    def test_at_risk_via_churn_probability_wins_over_silent_churner_shaped_row(self):
        usage = _usage(active_days_30d=0, last_active_at=NOW - timedelta(days=45))
        result = _classify(
            risk_level="healthy",
            churn_probability=0.9,
            usage=usage,
            sentiment_direction="declining",
            last_feedback_at=NOW - timedelta(days=45),
            health_score=50,
        )
        assert result == SEGMENT_AT_RISK
