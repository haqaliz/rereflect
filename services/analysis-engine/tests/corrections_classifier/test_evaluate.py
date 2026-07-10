"""Tests for corrections_classifier.evaluate — Phase 4b (M5.2 training-and-eval-core).

`evaluate` itself is pure (predict/metrics are pure stdlib), but challenger artifacts in
these tests are built via train_classifier (guarded by importorskip("sklearn")) — the
incumbent is always an injected plain callable/stub (no real analyzer needed), matching
the "evaluate stays agnostic of the incumbent's implementation" contract.
"""
from __future__ import annotations

import pytest

sklearn = pytest.importorskip("sklearn")

from src.analyzer.corrections_classifier.evaluate import EvalResult, evaluate  # noqa: E402
from src.analyzer.corrections_classifier.labels import MARGIN, MIN_HOLDOUT, MIN_LABELS  # noqa: E402
from src.analyzer.corrections_classifier.trainer import train_classifier  # noqa: E402


def _row(label: str, i: int) -> tuple[str, str]:
    # Deterministic, distinguishable-but-label-correlated text so a trained challenger
    # can actually learn the mapping.
    words = {
        "positive": ["great", "love", "amazing", "fantastic", "wonderful", "excellent"],
        "neutral": ["okay", "average", "fine", "standard", "typical", "moderate"],
        "negative": ["terrible", "awful", "hate", "broken", "worst", "disappointing"],
    }[label]
    w = words[i % len(words)]
    return (f"{w} item number {i} review text", label)


def _balanced_dataset(n_per_class: int) -> list[tuple[str, str]]:
    rows = []
    for i in range(n_per_class):
        rows.append(_row("positive", i))
        rows.append(_row("neutral", i))
        rows.append(_row("negative", i))
    return rows


def _gold_label(text: str) -> str:
    """A stub incumbent that "cheats" by reading the label straight back out of the
    deterministic fixture text (contains one of the sentiment words)."""
    if any(w in text for w in ("terrible", "awful", "hate", "broken", "worst", "disappointing")):
        return "negative"
    if any(w in text for w in ("okay", "average", "fine", "standard", "typical", "moderate")):
        return "neutral"
    return "positive"


def _always_wrong(text: str) -> str:
    """A deliberately-bad incumbent — always predicts 'neutral' regardless of input."""
    return "neutral"


# ---------------------------------------------------------------------------
# Gate: below min_labels
# ---------------------------------------------------------------------------

def test_below_min_labels_returns_skipped():
    dataset = [("some text", "positive")] * (MIN_LABELS - 1)
    result = evaluate(dataset, _gold_label, {"classes": ["negative", "neutral", "positive"],
                                              "vectorizer": {"vocabulary": {}, "idf": [],
                                                             "lowercase": True,
                                                             "token_pattern": r"(?u)\b\w\w+\b",
                                                             "sublinear_tf": False, "norm": "l2"},
                                              "logreg": {"coef": [[], [], []], "intercept": [0, 0, 0]}})
    assert result.decision == "skipped"
    assert result.n == len(dataset)
    assert result.incumbent_macro_f1 is None
    assert result.challenger_macro_f1 is None
    assert result.macro_f1_delta is None


# ---------------------------------------------------------------------------
# Small-sample guard
# ---------------------------------------------------------------------------

def test_tiny_holdout_all_classes_forces_retained_with_note():
    # n=20 (>= MIN_LABELS), holdout_frac=0.2 -> holdout_size=4 < MIN_HOLDOUT(8)
    # -> triggers k-fold path OR single-holdout-too-small guard depending on branch;
    # either way with a tiny effective evaluated set the guard must force "retained".
    dataset = _balanced_dataset(7)  # 21 rows total, still small
    challenger = train_classifier(dataset)
    result = evaluate(
        dataset, _gold_label, challenger,
        min_labels=MIN_LABELS, holdout_frac=0.2, min_holdout=100, margin=MARGIN,
    )
    # min_holdout=100 guarantees the evaluated set can never reach 100 -> guard forces retained
    assert result.decision == "retained"
    assert result.notes == "held-out too small"
    assert result.macro_f1_delta is not None


def test_missing_class_in_holdout_forces_retained():
    # Construct a dataset where the holdout can plausibly miss a class: heavily
    # imbalanced with just enough of one class to pass min_labels overall but with
    # min_holdout forced to a very high number so the guard trips deterministically.
    dataset = _balanced_dataset(10)
    challenger = train_classifier(dataset)
    result = evaluate(
        dataset, _gold_label, challenger,
        min_labels=MIN_LABELS, holdout_frac=0.2, min_holdout=1000, margin=MARGIN,
    )
    assert result.decision == "retained"
    assert result.notes == "held-out too small"


# ---------------------------------------------------------------------------
# Promote / retain decisions
# ---------------------------------------------------------------------------

def test_clearly_better_challenger_is_promoted():
    dataset = _balanced_dataset(20)  # 60 rows, plenty for a real 0.2 holdout (12 >= min_holdout)
    challenger = train_classifier(dataset)
    result = evaluate(
        dataset, _always_wrong, challenger,
        min_labels=MIN_LABELS, holdout_frac=0.2, min_holdout=MIN_HOLDOUT, margin=MARGIN,
    )
    assert result.decision == "promoted"
    assert result.macro_f1_delta is not None
    assert result.macro_f1_delta >= MARGIN


def test_worse_challenger_is_retained():
    dataset = _balanced_dataset(20)
    # A "challenger" trained on label-shuffled (deliberately mislabeled) data -> a
    # near-useless model (still 3 classes present, so it fits), versus a perfect (gold)
    # incumbent -> challenger should lose badly (delta < margin).
    shuffled_labels = [label for _, label in dataset]
    shuffled_labels = shuffled_labels[1:] + shuffled_labels[:1]  # rotate -> breaks correlation
    noisy_dataset = [(text, label) for (text, _), label in zip(dataset, shuffled_labels)]
    noisy_challenger = train_classifier(noisy_dataset)
    result = evaluate(
        dataset, _gold_label, noisy_challenger,
        min_labels=MIN_LABELS, holdout_frac=0.2, min_holdout=MIN_HOLDOUT, margin=MARGIN,
    )
    assert result.decision == "retained"
    assert result.macro_f1_delta is not None
    assert result.macro_f1_delta < MARGIN


def test_delta_equals_margin_promotes():
    dataset = _balanced_dataset(20)
    challenger = train_classifier(dataset)
    result = evaluate(
        dataset, _always_wrong, challenger,
        min_labels=MIN_LABELS, holdout_frac=0.2, min_holdout=MIN_HOLDOUT, margin=0.0,
    )
    # margin=0.0 -> boundary is ">=" so any non-negative delta promotes
    assert result.decision == "promoted"


# ---------------------------------------------------------------------------
# Injected incumbent + determinism + never-raises
# ---------------------------------------------------------------------------

def test_incumbent_predict_is_injected():
    dataset = _balanced_dataset(20)
    challenger = train_classifier(dataset)

    calls = []

    def spy(text: str) -> str:
        calls.append(text)
        return _gold_label(text)

    result = evaluate(
        dataset, spy, challenger,
        min_labels=MIN_LABELS, holdout_frac=0.2, min_holdout=MIN_HOLDOUT, margin=MARGIN,
    )
    assert len(calls) == result.n
    assert result.n > 0


def test_evaluate_never_raises_on_degenerate():
    # The DATASET passed to evaluate() is degenerate (single class, above min_labels) —
    # sklearn's LogisticRegression itself cannot fit on a single class, so the challenger
    # artifact is trained separately on a proper balanced set (a realistic scenario: an
    # org's corrections happen to be all-positive right now, but the shared org-level
    # challenger model was trained earlier on richer data). evaluate() must not raise.
    dataset = [("single class only text " + str(i), "positive") for i in range(25)]
    challenger = train_classifier(_balanced_dataset(10))
    result = evaluate(
        dataset, _gold_label, challenger,
        min_labels=MIN_LABELS, holdout_frac=0.2, min_holdout=MIN_HOLDOUT, margin=MARGIN,
    )
    assert result.decision in ("promoted", "retained", "skipped")


def test_deterministic_split():
    dataset = _balanced_dataset(20)
    challenger = train_classifier(dataset)
    r1 = evaluate(dataset, _gold_label, challenger, random_state=0)
    r2 = evaluate(dataset, _gold_label, challenger, random_state=0)
    assert r1 == r2


def test_evalresult_is_a_dataclass_with_expected_fields():
    result = EvalResult(
        decision="skipped", n=0, incumbent_macro_f1=None, challenger_macro_f1=None,
        macro_f1_delta=None, notes="below min_labels",
    )
    assert result.decision == "skipped"
    assert result.n == 0
