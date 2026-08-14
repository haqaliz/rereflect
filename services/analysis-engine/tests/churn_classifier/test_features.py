"""Tests for churn_classifier.features (M5.3 churn-classifier-core).

Pins the FROZEN feature vector — the field set fixed by the gate study
(aspect 2) and locked here: 6 health components + health_score + risk_level,
usage (active_days_7d/14d/30d, login_count_30d, usage_score, usage_trend_pct
+ trend-state one-hot), feedback aggregates (count_30d, avg_sentiment,
sentiment_trend, urgent_share, avg_churn_risk), segment one-hot, and
renewal_proximity_days (absent = -1). Any change to the vector is a change to
the frozen contract and must be a deliberate, documented change.
"""
from __future__ import annotations

import pytest

from src.analyzer.churn_classifier.features import (
    FEATURE_NAMES,
    build_feature_vector,
    missing_snapshot_defaults,
)


def test_feature_names_are_frozen_and_fixed_order():
    assert FEATURE_NAMES == [
        # 6 health components + health_score + risk_level
        "churn_risk_component",
        "sentiment_component",
        "resolution_component",
        "frequency_component",
        "usage_component",
        "crm_component",
        "health_score",
        "risk_level",
        # usage
        "active_days_7d",
        "active_days_14d",
        "active_days_30d",
        "login_count_30d",
        "usage_score",
        "usage_trend_pct",
        "usage_trend_state_stable",
        "usage_trend_state_declining",
        "usage_trend_state_sharp_decline",
        # feedback aggregates
        "count_30d",
        "avg_sentiment",
        "sentiment_trend",
        "urgent_share",
        "avg_churn_risk",
        # segment one-hot (happy_advocate/unsegmented = reference, all-zero)
        "segment_dormant",
        "segment_silent_churner",
        "segment_at_risk",
        "segment_new",
        "segment_power_user",
        # renewal proximity (absent = -1)
        "renewal_proximity_days",
    ]
    assert len(FEATURE_NAMES) == 28


def _full_row():
    return {
        "churn_risk_component": 72,
        "sentiment_component": 61,
        "resolution_component": 55,
        "frequency_component": 48,
        "usage_component": 30,
        "crm_component": 40.0,
        "health_score": 52,
        "risk_level": "at_risk",
        "active_days_7d": 3,
        "active_days_14d": 6,
        "active_days_30d": 14,
        "login_count_30d": 22,
        "usage_score": 44,
        "usage_trend_pct": -35.5,
        "usage_trend_state": "declining",
        "count_30d": 5,
        "avg_sentiment": -0.42,
        "sentiment_trend": -0.18,
        "urgent_share": 0.2,
        "avg_churn_risk": 68.5,
        "segment": "at_risk",
        "renewal_proximity_days": 21,
    }


def test_full_row_produces_expected_vector():
    vec = build_feature_vector(_full_row())
    assert vec == [
        72.0, 61.0, 55.0, 48.0, 30.0, 40.0,  # 6 health components
        52.0,                                # health_score
        3.0,                                 # risk_level ordinal (at_risk)
        3.0, 6.0, 14.0, 22.0, 44.0, -35.5,   # usage numerics
        0.0, 1.0, 0.0,                       # trend one-hot (declining)
        5.0, -0.42, -0.18, 0.2, 68.5,        # feedback aggregates
        0.0, 0.0, 1.0, 0.0, 0.0,             # segment one-hot (at_risk)
        21.0,                                # renewal proximity
    ]


def test_vector_length_matches_feature_names():
    assert len(build_feature_vector(_full_row())) == len(FEATURE_NAMES)


def test_all_missing_row_returns_documented_defaults_without_raising():
    vec = build_feature_vector({})
    assert vec == [
        # components neutral 50, health_score 50, risk_level unknown(0)
        50.0, 50.0, 50.0, 50.0, 50.0, 50.0, 50.0, 0.0,
        # usage counts 0, usage_score 50, trend pct 0, trend state reference (zeros)
        0.0, 0.0, 0.0, 0.0, 50.0, 0.0, 0.0, 0.0, 0.0,
        # feedback aggregates all zero
        0.0, 0.0, 0.0, 0.0, 0.0,
        # segment reference (all zeros)
        0.0, 0.0, 0.0, 0.0, 0.0,
        # renewal proximity absent -> -1
        -1.0,
    ]


def test_none_values_are_treated_as_missing():
    row = {name: None for name in FEATURE_NAMES}
    row["segment"] = None
    row["usage_trend_state"] = None
    row["risk_level"] = None
    assert build_feature_vector(row) == build_feature_vector({})


def test_identical_rows_produce_identical_vectors():
    a = build_feature_vector(_full_row())
    b = build_feature_vector(dict(_full_row()))
    assert a == b


def test_deterministic_across_calls():
    assert build_feature_vector(_full_row()) == build_feature_vector(_full_row())


def test_risk_level_ordinal_encoding():
    for level, expected in [
        ("unknown", 0.0),
        ("healthy", 1.0),
        ("moderate", 2.0),
        ("at_risk", 3.0),
        ("critical", 4.0),
    ]:
        assert build_feature_vector({"risk_level": level})[FEATURE_NAMES.index("risk_level")] == expected


def test_unknown_risk_level_value_falls_back_to_unknown():
    idx = FEATURE_NAMES.index("risk_level")
    assert build_feature_vector({"risk_level": "nonsense"})[idx] == 0.0


def test_segment_one_hot_mapping():
    segment_idx = {name: FEATURE_NAMES.index(name) for name in
                   ("segment_dormant", "segment_silent_churner", "segment_at_risk",
                    "segment_new", "segment_power_user")}
    assert build_feature_vector({"segment": "dormant"})[segment_idx["segment_dormant"]] == 1.0
    assert build_feature_vector({"segment": "power_user"})[segment_idx["segment_power_user"]] == 1.0
    assert build_feature_vector({"segment": "at_risk"})[segment_idx["segment_at_risk"]] == 1.0
    assert build_feature_vector({"segment": "silent_churner"})[segment_idx["segment_silent_churner"]] == 1.0
    assert build_feature_vector({"segment": "new"})[segment_idx["segment_new"]] == 1.0


def test_segment_reference_values_map_to_all_zero_one_hot():
    for segment in ("happy_advocate", "unsegmented", "something_unknown"):
        vec = build_feature_vector({"segment": segment})
        for name in ("segment_dormant", "segment_silent_churner", "segment_at_risk",
                     "segment_new", "segment_power_user"):
            assert vec[FEATURE_NAMES.index(name)] == 0.0


def test_usage_trend_state_one_hot_mapping():
    states = {name: FEATURE_NAMES.index(name) for name in
              ("usage_trend_state_stable", "usage_trend_state_declining",
               "usage_trend_state_sharp_decline")}
    assert build_feature_vector({"usage_trend_state": "stable"})[states["usage_trend_state_stable"]] == 1.0
    assert build_feature_vector({"usage_trend_state": "declining"})[states["usage_trend_state_declining"]] == 1.0
    assert build_feature_vector({"usage_trend_state": "sharp_decline"})[states["usage_trend_state_sharp_decline"]] == 1.0


def test_usage_trend_reference_and_unknown_map_to_all_zero():
    for state in ("insufficient_history", None, "nonsense_state"):
        vec = build_feature_vector({"usage_trend_state": state})
        for name in ("usage_trend_state_stable", "usage_trend_state_declining",
                     "usage_trend_state_sharp_decline"):
            assert vec[FEATURE_NAMES.index(name)] == 0.0


def test_renewal_proximity_absent_is_minus_one_and_present_is_value():
    assert build_feature_vector({})[FEATURE_NAMES.index("renewal_proximity_days")] == -1.0
    assert build_feature_vector({"renewal_proximity_days": 0})[FEATURE_NAMES.index("renewal_proximity_days")] == 0.0
    assert build_feature_vector({"renewal_proximity_days": 120})[FEATURE_NAMES.index("renewal_proximity_days")] == 120.0


def test_missing_snapshot_defaults_are_documented_per_field():
    assert missing_snapshot_defaults["churn_risk_component"] == 50.0
    assert missing_snapshot_defaults["health_score"] == 50.0
    assert missing_snapshot_defaults["usage_score"] == 50.0
    assert missing_snapshot_defaults["active_days_30d"] == 0.0
    assert missing_snapshot_defaults["usage_trend_pct"] == 0.0
    assert missing_snapshot_defaults["count_30d"] == 0.0
    assert missing_snapshot_defaults["avg_sentiment"] == 0.0
    assert missing_snapshot_defaults["urgent_share"] == 0.0
    assert missing_snapshot_defaults["segment"] == "unsegmented"
    assert missing_snapshot_defaults["usage_trend_state"] == "insufficient_history"
    assert missing_snapshot_defaults["risk_level"] == "unknown"
    assert missing_snapshot_defaults["renewal_proximity_days"] == -1.0


def test_partial_row_keeps_present_values_and_defaults_rest():
    row = {"health_score": 90, "active_days_30d": 25, "segment": "power_user"}
    vec = build_feature_vector(row)
    assert vec[FEATURE_NAMES.index("health_score")] == 90.0
    assert vec[FEATURE_NAMES.index("active_days_30d")] == 25.0
    assert vec[FEATURE_NAMES.index("segment_power_user")] == 1.0
    assert vec[FEATURE_NAMES.index("churn_risk_component")] == 50.0  # defaulted
    assert vec[FEATURE_NAMES.index("renewal_proximity_days")] == -1.0  # defaulted
