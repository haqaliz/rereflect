"""Frozen churn feature vector builder (M5.3 churn-classifier-core).

The FROZEN field set (fixed by the gate study, aspect 2, and locked here — see
tests/churn_classifier/test_features.py): per customer at label time,

- 6 health components + health_score + risk_level (ordinal-encoded int:
  unknown=0 < healthy=1 < moderate=2 < at_risk=3 < critical=4);
- usage: active_days_7d/14d/30d, login_count_30d, usage_score,
  usage_trend_pct + usage_trend_state one-hot (stable/declining/sharp_decline;
  the insufficient_history reference state is all-zero);
- feedback aggregates: count_30d, avg_sentiment, sentiment_trend, urgent_share,
  avg_churn_risk;
- segment one-hot (dormant/silent_churner/at_risk/new/power_user; the
  happy_advocate + unsegmented reference is all-zero — the study's dummy-trap
  convention);
- renewal_proximity_days (absent = -1, per the frozen set).

`build_feature_vector` NEVER raises on missing fields: missing keys and None
values take `missing_snapshot_defaults` (documented R3 reconstruction defaults,
matching the gate study's missing-snapshot semantics). Pure stdlib.
"""
from __future__ import annotations

from typing import Any

HEALTH_COMPONENTS: tuple[str, ...] = (
    "churn_risk_component",
    "sentiment_component",
    "resolution_component",
    "frequency_component",
    "usage_component",
    "crm_component",
)

RISK_LEVEL_ORDER: dict[str, float] = {
    "unknown": 0.0,
    "healthy": 1.0,
    "moderate": 2.0,
    "at_risk": 3.0,
    "critical": 4.0,
}

TREND_STATES: tuple[str, ...] = ("stable", "declining", "sharp_decline")

SEGMENTS: tuple[str, ...] = (
    "dormant",
    "silent_churner",
    "at_risk",
    "new",
    "power_user",
)

FEATURE_NAMES: list[str] = [
    *HEALTH_COMPONENTS,
    "health_score",
    "risk_level",
    "active_days_7d",
    "active_days_14d",
    "active_days_30d",
    "login_count_30d",
    "usage_score",
    "usage_trend_pct",
    *(f"usage_trend_state_{s}" for s in TREND_STATES),
    "count_30d",
    "avg_sentiment",
    "sentiment_trend",
    "urgent_share",
    "avg_churn_risk",
    *(f"segment_{s}" for s in SEGMENTS),
    "renewal_proximity_days",
]

# Documented reconstruction defaults for rows with no snapshots at label time
# (PRD R3). Row-keyed (the keys `build_feature_vector` reads from the row dict):
# components/health_score/usage_score -> neutral 50, counts -> 0, trend pct -> 0,
# trend state -> reference (all-zero one-hot), segment -> reference (all-zero
# one-hot), feedback aggregates -> 0 ("no signal"), renewal proximity -> -1
# (absent). Mirrors the gate study's _MISSING_DEFAULTS where they overlap.
missing_snapshot_defaults: dict[str, Any] = {
    **{component: 50.0 for component in HEALTH_COMPONENTS},
    "health_score": 50.0,
    "risk_level": "unknown",
    "active_days_7d": 0.0,
    "active_days_14d": 0.0,
    "active_days_30d": 0.0,
    "login_count_30d": 0.0,
    "usage_score": 50.0,
    "usage_trend_pct": 0.0,
    "usage_trend_state": "insufficient_history",
    "count_30d": 0.0,
    "avg_sentiment": 0.0,
    "sentiment_trend": 0.0,
    "urgent_share": 0.0,
    "avg_churn_risk": 0.0,
    "segment": "unsegmented",
    "renewal_proximity_days": -1.0,
}


def _value(row: dict, key: str) -> Any:
    """Row value for `key`, with None treated as missing (documented default)."""
    value = row.get(key)
    if value is None:
        return missing_snapshot_defaults[key]
    return value


def build_feature_vector(row: dict) -> list[float]:
    """Fixed-order feature vector (length == len(FEATURE_NAMES)) for one customer.

    Missing fields never raise — they take the documented defaults. Deterministic:
    identical rows produce identical vectors.
    """
    vec: list[float] = []

    for component in HEALTH_COMPONENTS:
        vec.append(float(_value(row, component)))
    vec.append(float(_value(row, "health_score")))

    risk_level = str(_value(row, "risk_level"))
    vec.append(RISK_LEVEL_ORDER.get(risk_level, RISK_LEVEL_ORDER["unknown"]))

    for usage_field in (
        "active_days_7d",
        "active_days_14d",
        "active_days_30d",
        "login_count_30d",
        "usage_score",
        "usage_trend_pct",
    ):
        vec.append(float(_value(row, usage_field)))

    trend_state = str(_value(row, "usage_trend_state"))
    vec.extend(1.0 if trend_state == state else 0.0 for state in TREND_STATES)

    for aggregate in ("count_30d", "avg_sentiment", "sentiment_trend", "urgent_share", "avg_churn_risk"):
        vec.append(float(_value(row, aggregate)))

    segment = str(_value(row, "segment"))
    vec.extend(1.0 if segment == slug else 0.0 for slug in SEGMENTS)

    vec.append(float(_value(row, "renewal_proximity_days")))

    return vec
