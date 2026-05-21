"""
Tests for ChurnCalibrator service.
TDD — all 26 tests written before implementation.
"""

import pytest
import random

from src.services.churn_calibrator import (
    CalibrationModel,
    ChurnCalibrator,
    InsufficientLabelsError,
    Metrics,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

DEFAULT_BANDS = {"low": 0.30, "medium": 0.50, "high": 0.70, "critical": 0.85}


def _make_calibrator() -> ChurnCalibrator:
    return ChurnCalibrator()


def _large_dataset(n: int = 200, seed: int = 42) -> tuple[list[int], list[bool]]:
    """Return a balanced synthetic dataset with clear separation."""
    rng = random.Random(seed)
    scores: list[int] = []
    labels: list[bool] = []
    for _ in range(n):
        if rng.random() < 0.5:
            # churned: high scores
            scores.append(rng.randint(60, 100))
            labels.append(True)
        else:
            # retained: low scores
            scores.append(rng.randint(0, 40))
            labels.append(False)
    return scores, labels


def _small_dataset(n: int = 20, seed: int = 7) -> tuple[list[int], list[bool]]:
    """Return a small balanced dataset (exactly n labels)."""
    rng = random.Random(seed)
    scores: list[int] = []
    labels: list[bool] = []
    for i in range(n):
        scores.append(rng.randint(0, 100))
        labels.append(i % 2 == 0)
    return scores, labels


# ---------------------------------------------------------------------------
# Identity model
# ---------------------------------------------------------------------------


def test_identity_model_returns_score_over_100_as_probability():
    """identity_model() + predict(50) should return 0.5."""
    c = _make_calibrator()
    m = c.identity_model()
    assert c.predict(50, m) == pytest.approx(0.5)


def test_identity_model_clamps_score_above_100_to_one():
    """predict(150) on identity model should clamp to 1.0."""
    c = _make_calibrator()
    m = c.identity_model()
    assert c.predict(150, m) == pytest.approx(1.0)


def test_identity_model_clamps_negative_score_to_zero():
    """predict(-10) on identity model should clamp to 0.0."""
    c = _make_calibrator()
    m = c.identity_model()
    assert c.predict(-10, m) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Fit + predict
# ---------------------------------------------------------------------------


def test_fit_with_perfect_separation_yields_monotonic_model():
    """Model fitted on perfectly separated scores should be monotonic."""
    c = _make_calibrator()
    # Use 30 labels (≥ MIN_LABELS=20) with clear separation
    scores = [10, 20, 30, 80, 90, 95] * 5  # 30 labels
    labels = [False, False, False, True, True, True] * 5
    m = c.fit(scores, labels)
    p_low = c.predict(10, m)
    p_mid = c.predict(50, m)
    p_high = c.predict(95, m)
    assert p_low < p_mid < p_high


def test_fit_with_single_label_class_returns_identity_fallback():
    """All-False labels → model behaves like identity (no real signal)."""
    c = _make_calibrator()
    # 20 labels all False — no positive class seen
    scores = list(range(20))
    labels = [False] * 20
    # Should not raise but return identity-like model
    m = c.fit(scores, labels)
    # A model with no positives should behave identically to identity
    identity = c.identity_model()
    assert c.predict(50, m) == pytest.approx(c.predict(50, identity))


def test_fit_with_fewer_than_20_labels_raises():
    """Fewer than 20 labels should raise InsufficientLabelsError."""
    c = _make_calibrator()
    scores = [10, 20, 30, 80, 90]
    labels = [False, False, False, True, True]
    with pytest.raises(InsufficientLabelsError):
        c.fit(scores, labels)


def test_predict_at_breakpoint_returns_probability_value():
    """predict() at an exact breakpoint returns the stored probability."""
    c = _make_calibrator()
    scores, labels = _large_dataset(200)
    m = c.fit(scores, labels)
    # Each breakpoint should map exactly to its probability
    for bp, prob in zip(m.breakpoints, m.probabilities):
        result = c.predict(int(round(bp)), m)
        assert abs(result - prob) < 0.01  # small tolerance for rounding


def test_predict_below_minimum_breakpoint_returns_minimum_probability():
    """predict() below all breakpoints returns the minimum probability."""
    c = _make_calibrator()
    scores = [10, 20, 30, 80, 90, 95] * 5  # 30 labels
    labels = [False, False, False, True, True, True] * 5
    m = c.fit(scores, labels)
    min_bp = int(min(m.breakpoints))
    p_at_min = c.predict(min_bp, m)
    p_below = c.predict(0, m)
    # Below-min should be ≤ p at min breakpoint
    assert p_below <= p_at_min + 1e-9


def test_predict_above_maximum_breakpoint_returns_maximum_probability():
    """predict() above all breakpoints returns the maximum probability."""
    c = _make_calibrator()
    scores = [10, 20, 30, 80, 90, 95] * 5
    labels = [False, False, False, True, True, True] * 5
    m = c.fit(scores, labels)
    max_bp = int(max(m.breakpoints))
    p_at_max = c.predict(max_bp, m)
    p_above = c.predict(100, m)
    assert p_above >= p_at_max - 1e-9


# ---------------------------------------------------------------------------
# Bootstrap CI
# ---------------------------------------------------------------------------


def test_predict_with_interval_returns_three_values():
    """predict_with_interval returns (p, lower, upper) with lower ≤ p ≤ upper."""
    c = _make_calibrator()
    scores, labels = _large_dataset(200)
    m = c.fit(scores, labels)
    result = c.predict_with_interval(70, m, n_bootstrap=50, ci=0.90)
    assert len(result) == 3
    p, lower, upper = result
    assert lower <= p + 1e-9
    assert upper >= p - 1e-9


def test_bootstrap_ci_widens_with_fewer_labels():
    """A small dataset should produce wider CIs than a large one at same score."""
    c = _make_calibrator()
    big_scores, big_labels = _large_dataset(200, seed=42)
    small_scores, small_labels = _small_dataset(20, seed=7)

    m_big = c.fit(big_scores, big_labels)
    m_small = c.fit(small_scores, small_labels)

    _, lo_big, hi_big = c.predict_with_interval(50, m_big, n_bootstrap=100, ci=0.90)
    _, lo_small, hi_small = c.predict_with_interval(50, m_small, n_bootstrap=100, ci=0.90)

    ci_big = hi_big - lo_big
    ci_small = hi_small - lo_small
    assert ci_small >= ci_big


def test_bootstrap_is_deterministic_with_seed():
    """Same inputs + same seed must produce identical (lower, upper)."""
    c = _make_calibrator()
    scores, labels = _large_dataset(100, seed=99)
    m = c.fit(scores, labels)

    result1 = c.predict_with_interval(60, m, n_bootstrap=100, ci=0.90)
    result2 = c.predict_with_interval(60, m, n_bootstrap=100, ci=0.90)

    assert result1 == result2


# ---------------------------------------------------------------------------
# Risk level bands
# ---------------------------------------------------------------------------


def test_derive_risk_level_returns_critical_above_high_threshold():
    """p ≥ 0.85 → 'critical'."""
    c = _make_calibrator()
    assert c.derive_risk_level(0.90, DEFAULT_BANDS) == "critical"
    assert c.derive_risk_level(0.85, DEFAULT_BANDS) == "critical"


def test_derive_risk_level_returns_high_in_high_band():
    """0.70 ≤ p < 0.85 → 'high'."""
    c = _make_calibrator()
    assert c.derive_risk_level(0.75, DEFAULT_BANDS) == "high"
    assert c.derive_risk_level(0.70, DEFAULT_BANDS) == "high"


def test_derive_risk_level_returns_medium_in_medium_band():
    """0.50 ≤ p < 0.70 → 'medium'."""
    c = _make_calibrator()
    assert c.derive_risk_level(0.60, DEFAULT_BANDS) == "medium"
    assert c.derive_risk_level(0.50, DEFAULT_BANDS) == "medium"


def test_derive_risk_level_returns_low_below_low_threshold():
    """p < 0.30 → 'low'."""
    c = _make_calibrator()
    assert c.derive_risk_level(0.10, DEFAULT_BANDS) == "low"
    assert c.derive_risk_level(0.29, DEFAULT_BANDS) == "low"


def test_derive_risk_level_uses_provided_bands_not_defaults():
    """Custom bands override the defaults."""
    c = _make_calibrator()
    custom_bands = {"low": 0.20, "medium": 0.40, "high": 0.60, "critical": 0.80}
    # p=0.75 → high under default (0.70 threshold), but high under custom (0.60 threshold) too
    # p=0.65 → medium under default (0.50≤p<0.70), but high under custom (0.60≤p<0.80)
    assert c.derive_risk_level(0.65, custom_bands) == "high"
    # p=0.45 → medium under default but medium under custom (0.40≤p<0.60)
    assert c.derive_risk_level(0.45, custom_bands) == "medium"
    # p=0.15 → low under default, low under custom
    assert c.derive_risk_level(0.15, custom_bands) == "low"
    # p=0.85 → critical under both
    assert c.derive_risk_level(0.85, custom_bands) == "critical"


# ---------------------------------------------------------------------------
# Timeline buckets
# ---------------------------------------------------------------------------


def test_timeline_bucket_immediate_at_high_probability():
    """p=0.90, trend=0.0 → 'immediate'."""
    c = _make_calibrator()
    assert c.derive_timeline_bucket(0.90, 0.0) == "immediate"


def test_timeline_bucket_immediate_when_sentiment_collapsing():
    """p=0.72, trend=-0.5 → 'immediate' (sentiment override)."""
    c = _make_calibrator()
    assert c.derive_timeline_bucket(0.72, -0.5) == "immediate"


def test_timeline_bucket_2w_in_range_without_sentiment_override():
    """p=0.75, trend=0.0 → '2w' (not sentiment-triggered)."""
    c = _make_calibrator()
    assert c.derive_timeline_bucket(0.75, 0.0) == "2w"


def test_timeline_bucket_2_to_4w_in_range():
    """p=0.60, trend=0.0 → '2-4w'."""
    c = _make_calibrator()
    assert c.derive_timeline_bucket(0.60, 0.0) == "2-4w"


def test_timeline_bucket_1_to_3m_in_range():
    """p=0.40, trend=0.0 → '1-3m'."""
    c = _make_calibrator()
    assert c.derive_timeline_bucket(0.40, 0.0) == "1-3m"


def test_timeline_bucket_low_below_threshold():
    """p=0.10, trend=0.0 → 'low'."""
    c = _make_calibrator()
    assert c.derive_timeline_bucket(0.10, 0.0) == "low"


# ---------------------------------------------------------------------------
# Backtest metrics
# ---------------------------------------------------------------------------


def test_backtest_returns_precision_recall_f1_auc():
    """backtest() returns Metrics with plausible values on clean synthetic data."""
    c = _make_calibrator()
    scores, labels = _large_dataset(200)
    m = c.fit(scores, labels)
    metrics = c.backtest(scores, labels, m)
    assert isinstance(metrics, Metrics)
    assert 0.0 <= metrics.precision <= 1.0
    assert 0.0 <= metrics.recall <= 1.0
    assert 0.0 <= metrics.f1 <= 1.0
    assert 0.0 <= metrics.auc <= 1.0
    # On well-separated data the calibrated model should be non-trivial
    assert metrics.auc > 0.5


def test_backtest_optimal_threshold_maximizes_f1():
    """The returned optimal_threshold should beat its immediate neighbors."""
    c = _make_calibrator()
    scores, labels = _large_dataset(200)
    m = c.fit(scores, labels)
    metrics = c.backtest(scores, labels, m)
    opt = metrics.optimal_threshold

    # Helper: compute F1 at a given threshold
    def f1_at(threshold: float) -> float:
        probs = [c.predict(s, m) for s in scores]
        tp = sum(1 for p, l in zip(probs, labels) if p >= threshold and l)
        fp = sum(1 for p, l in zip(probs, labels) if p >= threshold and not l)
        fn = sum(1 for p, l in zip(probs, labels) if p < threshold and l)
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        return 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    f1_opt = f1_at(opt)
    # Neighbors at ±0.05 should not be better
    f1_lower = f1_at(max(0.0, opt - 0.05))
    f1_upper = f1_at(min(1.0, opt + 0.05))
    assert f1_opt >= f1_lower - 1e-6
    assert f1_opt >= f1_upper - 1e-6


def test_backtest_handles_all_negative_labels_gracefully():
    """All-False labels should produce F1=0.0 and AUC=0.0 without crashing."""
    c = _make_calibrator()
    # Use identity model since fit would return identity for all-False anyway
    m = c.identity_model()
    scores = list(range(0, 100, 5))  # 20 scores
    labels = [False] * len(scores)
    metrics = c.backtest(scores, labels, m)
    assert metrics.f1 == pytest.approx(0.0)
    assert metrics.auc == pytest.approx(0.0)
