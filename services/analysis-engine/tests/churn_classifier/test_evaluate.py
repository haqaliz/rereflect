"""Tests for churn_classifier.evaluate (M5.3 churn-classifier-core).

`evaluate_churn` runs the incumbent-vs-challenger A/B on a leakage-free
stratified holdout (k-fold when tiny), scoring BOTH sides on the SAME holdout
rows as probabilities (thresholded at 0.5 into binary macro-F1 — the gate
study's metric). It trains the challenger itself via an injected `train_fn`
(production: trainer.train_churn_classifier), never on rows it later scores,
and never raises.

`build_incumbent_predict` wraps the calibrated-heuristic incumbent: an injected
calibration_loader() returns a calibrated p(churn_risk_component)->[0,1]
callable or None (identity fallback p = component/100). The loader itself is
supplied by the worker in aspect 4 — this package only defines the contract.

The holdout SPLIT MECHANISM is reused from corrections_classifier/evaluate.py
(_stratified_split + _stratified_indices_by_class); the scoring loop is
churn-specific because both sides score feature VECTORS into probabilities,
not texts into labels.
"""
from __future__ import annotations

import pytest

sklearn = pytest.importorskip("sklearn")

from src.analyzer.churn_classifier.evaluate import (  # noqa: E402
    EvalResult,
    build_incumbent_predict,
    evaluate_churn,
)
from src.analyzer.churn_classifier.features import FEATURE_NAMES, build_feature_vector  # noqa: E402
from src.analyzer.churn_classifier.labels import MARGIN, MIN_LABELS  # noqa: E402
from src.analyzer.corrections_classifier.labels import MIN_HOLDOUT  # noqa: E402
from src.analyzer.churn_classifier.trainer import train_churn_classifier  # noqa: E402


def _row_vec(i: int, churned: int) -> list[float]:
    """Deterministic feature vector with a strong, learnable churn signal.

    Per-row jitter (corrections' "item number {i}" trick) keeps every row's
    vector unique so the leakage tests can assert vector-level disjointness;
    the jitter is tiny and never disturbs the class signal. Churned customers
    carry a HIGH churn_risk_component (and low usage), so the identity
    incumbent p = component/100 is a good baseline.
    """
    return build_feature_vector(
        {
            "churn_risk_component": 30 + churned * 60,
            "usage_score": 75 - churned * 50,
            "active_days_30d": 24 - churned * 18,
            "login_count_30d": 34 - churned * 24,
            "count_30d": 1 + i % 8,
            "avg_sentiment": -0.7 - (i % 13) * 0.005 if churned else 0.6 + (i % 13) * 0.005,
            "segment": "dormant" if churned else "power_user",
        }
    )


def _dataset(n: int = 40) -> dict:
    features = []
    labels = []
    for i in range(n):
        churned = 1 if i % 2 == 0 else 0
        features.append(_row_vec(i, churned))
        labels.append(churned)
    return {"features": features, "labels": labels}


def _incumbent_identity(feature_vector: list[float]) -> float:
    """The calibrated-heuristic shape: p = churn_risk_component / 100."""
    component_idx = FEATURE_NAMES.index("churn_risk_component")
    return feature_vector[component_idx] / 100.0


def _incumbent_wrong(feature_vector: list[float]) -> float:
    """Always predicts the NON-churned class (p < 0.5) — a beatable incumbent."""
    return 0.1


def _never_call(rows):
    raise AssertionError("train_fn must not be called below min_labels")


# ---------------------------------------------------------------------------
# Gate + degenerate paths — skipped, never raises
# ---------------------------------------------------------------------------

def test_below_min_labels_returns_skipped():
    dataset = {"features": [_row_vec(i, i % 2) for i in range(MIN_LABELS - 1)],
               "labels": [i % 2 for i in range(MIN_LABELS - 1)]}
    result = evaluate_churn(dataset, _incumbent_identity, _never_call)
    assert result.decision == "skipped"
    assert result.n == len(dataset["labels"])
    assert result.incumbent_macro_f1 is None
    assert result.challenger_macro_f1 is None
    assert result.macro_f1_delta is None
    assert "below min_labels" in result.notes


def test_single_class_dataset_returns_skipped():
    dataset = {"features": [_row_vec(i, 1) for i in range(30)], "labels": [1] * 30}
    result = evaluate_churn(dataset, _incumbent_identity, _never_call)
    assert result.decision == "skipped"
    assert result.notes == "single-class labels"
    assert result.n == 30


def test_evaluate_never_raises_on_degenerate():
    dataset = {"features": [_row_vec(i, 1) for i in range(25)], "labels": [1] * 25}
    result = evaluate_churn(dataset, _incumbent_identity, train_churn_classifier)
    assert result.decision in ("promoted", "retained", "skipped")


def test_all_missing_feature_rows_do_not_crash_ab():
    dataset = {"features": [build_feature_vector({}) for _ in range(40)],
               "labels": [1 if i % 2 == 0 else 0 for i in range(40)]}
    result = evaluate_churn(dataset, _incumbent_identity, train_churn_classifier)
    assert result.decision in ("promoted", "retained", "skipped")


# ---------------------------------------------------------------------------
# Leakage-free contract
# ---------------------------------------------------------------------------

def test_challenger_trained_only_on_train_split_disjoint_from_scored_holdout():
    dataset = _dataset(60)
    trained_vectors_per_call: list[list[list[float]]] = []

    def spy_train_fn(sub_dataset):
        trained_vectors_per_call.append(sub_dataset["features"])
        return train_churn_classifier(sub_dataset)

    scored_vectors: list[list[float]] = []

    def spy_incumbent(feature_vector):
        scored_vectors.append(feature_vector)
        return _incumbent_identity(feature_vector)

    result = evaluate_churn(dataset, spy_incumbent, spy_train_fn,
                            min_labels=MIN_LABELS, min_holdout=MIN_HOLDOUT, margin=MARGIN)

    assert len(trained_vectors_per_call) == 1  # holdout_size=12 >= MIN_HOLDOUT -> single-holdout path
    trained = trained_vectors_per_call[0]
    assert len(scored_vectors) > 0
    # THE load-bearing leakage-free assertion: no scored vector was trained on.
    trained_set = {tuple(v) for v in trained}
    scored_set = {tuple(v) for v in scored_vectors}
    assert trained_set.isdisjoint(scored_set)
    assert result.decision in ("promoted", "retained")


def test_kfold_path_trains_each_fold_only_on_rows_outside_its_held_fold():
    dataset = _dataset(21)  # holdout_size = round(21*0.2) = 4 < MIN_HOLDOUT(8) -> k-fold path
    trained_per_call: list[list[list[float]]] = []
    scored_per_call: list[list[list[float]]] = []

    def spy_train_fn(sub_dataset):
        trained_per_call.append(sub_dataset["features"])
        return train_churn_classifier(sub_dataset)

    def spy_incumbent(feature_vector):
        # evaluate's k-fold loop trains fold i's challenger, THEN scores fold i's
        # held rows — the fold being scored is always the last-trained fold.
        idx = len(trained_per_call) - 1
        while len(scored_per_call) <= idx:
            scored_per_call.append([])
        scored_per_call[idx].append(feature_vector)
        return _incumbent_identity(feature_vector)

    evaluate_churn(dataset, spy_incumbent, spy_train_fn,
                   min_labels=MIN_LABELS, min_holdout=MIN_HOLDOUT, margin=MARGIN)

    assert len(trained_per_call) >= 3
    assert len(scored_per_call) == len(trained_per_call)
    for trained, scored in zip(trained_per_call, scored_per_call):
        assert {tuple(v) for v in trained}.isdisjoint({tuple(v) for v in scored})


def test_both_sides_scored_on_the_same_holdout_rows():
    dataset = _dataset(60)
    incumbent_seen: list[tuple] = []
    challenger_seen: list[tuple] = []

    real = train_churn_classifier  # local alias for the spy

    def spy_incumbent(feature_vector):
        incumbent_seen.append(tuple(feature_vector))
        return _incumbent_identity(feature_vector)

    # Wrap predict to record what the challenger scores.
    import src.analyzer.churn_classifier.evaluate as evaluate_mod

    original_predict = evaluate_mod.predict

    def spy_predict(artifact, feature_vector):
        challenger_seen.append(tuple(feature_vector))
        return original_predict(artifact, feature_vector)

    evaluate_mod.predict = spy_predict
    try:
        evaluate_churn(dataset, spy_incumbent, real,
                       min_labels=MIN_LABELS, min_holdout=MIN_HOLDOUT, margin=MARGIN)
    finally:
        evaluate_mod.predict = original_predict

    assert set(incumbent_seen) == set(challenger_seen)
    assert len(incumbent_seen) == len(challenger_seen) > 0


# ---------------------------------------------------------------------------
# Promote / retain decisions
# ---------------------------------------------------------------------------

def test_clearly_better_challenger_is_promoted():
    dataset = _dataset(60)
    result = evaluate_churn(dataset, _incumbent_wrong, train_churn_classifier,
                            min_labels=MIN_LABELS, min_holdout=MIN_HOLDOUT, margin=MARGIN)
    assert result.decision == "promoted"
    assert result.macro_f1_delta is not None
    assert result.macro_f1_delta >= MARGIN


def test_worse_challenger_is_retained():
    dataset = _dataset(60)

    def noisy_train_fn(sub_dataset):
        # Deliberately-bad train_fn: trains on label-shuffled rows (still fits)
        # but is scored on the genuine holdout — the gold-ish incumbent wins.
        labels = sub_dataset["labels"]
        shuffled = labels[1:] + labels[:1]
        return train_churn_classifier({"features": sub_dataset["features"], "labels": shuffled})

    result = evaluate_churn(dataset, _incumbent_identity, noisy_train_fn,
                            min_labels=MIN_LABELS, min_holdout=MIN_HOLDOUT, margin=MARGIN)
    assert result.decision == "retained"
    assert result.macro_f1_delta is not None
    assert result.macro_f1_delta < MARGIN


def test_delta_equals_margin_promotes():
    dataset = _dataset(60)
    result = evaluate_churn(dataset, _incumbent_wrong, train_churn_classifier,
                            min_labels=MIN_LABELS, min_holdout=MIN_HOLDOUT, margin=0.0)
    assert result.decision == "promoted"


# ---------------------------------------------------------------------------
# Determinism + result shape
# ---------------------------------------------------------------------------

def test_deterministic_split():
    dataset = _dataset(60)
    r1 = evaluate_churn(dataset, _incumbent_identity, train_churn_classifier, random_state=0)
    r2 = evaluate_churn(dataset, _incumbent_identity, train_churn_classifier, random_state=0)
    assert r1 == r2


def test_evalresult_is_a_dataclass_with_expected_fields():
    result = EvalResult(decision="skipped", n=0, incumbent_macro_f1=None,
                        challenger_macro_f1=None, macro_f1_delta=None, notes="below min_labels")
    assert result.decision == "skipped"
    assert result.n == 0


# ---------------------------------------------------------------------------
# build_incumbent_predict — the calibration_loader contract
# ---------------------------------------------------------------------------

def test_incumbent_predict_identity_fallback_when_loader_returns_none():
    incumbent = build_incumbent_predict(lambda: None)
    vector = build_feature_vector({"churn_risk_component": 80})
    assert incumbent(vector) == pytest.approx(0.8)


def test_incumbent_predict_uses_loader_calibrated_fn_when_present():
    def loader():
        return lambda component: component / 100.0  # calibrated shape

    incumbent = build_incumbent_predict(loader)
    vector = build_feature_vector({"churn_risk_component": 80})
    assert incumbent(vector) == pytest.approx(0.8)


def test_incumbent_predict_calibrated_fn_receives_the_component_value():
    seen = []

    def loader():
        return lambda component: seen.append(component) or 0.5

    incumbent = build_incumbent_predict(loader)
    vector = build_feature_vector({"churn_risk_component": 42, "usage_score": 99})
    incumbent(vector)
    assert seen == [42.0]


def test_incumbent_predict_reads_component_from_the_frozen_index():
    """The component must come from the churn_risk_component position in the
    feature vector regardless of the other fields' values."""
    incumbent = build_incumbent_predict(lambda: None)
    vec_a = build_feature_vector({"churn_risk_component": 70, "health_score": 10})
    vec_b = build_feature_vector({"churn_risk_component": 70, "health_score": 95})
    assert incumbent(vec_a) == pytest.approx(0.7)
    assert incumbent(vec_b) == pytest.approx(0.7)


def test_incumbent_predict_loader_called_per_prediction():
    calls = []
    incumbent = build_incumbent_predict(lambda: calls.append(1) or None)
    incumbent(build_feature_vector({}))
    incumbent(build_feature_vector({}))
    assert len(calls) == 2
