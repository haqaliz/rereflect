"""Tests for corrections_classifier.evaluate — Phase 4b (M5.2 training-and-eval-core).

`evaluate` itself is pure (predict/metrics are pure stdlib), but it now TRAINS the
challenger itself via an injected `train_fn` callback (production: `trainer.train_classifier`,
guarded here by `pytest.importorskip("sklearn")`) — the incumbent is always an injected plain
callable/stub (no real analyzer needed), matching the "evaluate stays agnostic of the
incumbent's implementation" contract.

`train_fn` is called by `evaluate` ONLY on the TRAIN half of a disjoint train/holdout split
(or, for small datasets, only on the OTHER folds in a k-fold retrain) — never on rows it is
later scored on. This is the leakage-free contract this module exists to prove.
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


def _imbalanced_dataset(counts: dict[str, int]) -> list[tuple[str, str]]:
    rows = []
    for label, n in counts.items():
        for i in range(n):
            rows.append(_row(label, i))
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


def _never_call(rows):
    raise AssertionError("train_fn must not be called below min_labels")


# ---------------------------------------------------------------------------
# Gate: below min_labels
# ---------------------------------------------------------------------------

def test_below_min_labels_returns_skipped():
    dataset = [("some text", "positive")] * (MIN_LABELS - 1)
    result = evaluate(dataset, _gold_label, _never_call)
    assert result.decision == "skipped"
    assert result.n == len(dataset)
    assert result.incumbent_macro_f1 is None
    assert result.challenger_macro_f1 is None
    assert result.macro_f1_delta is None


# ---------------------------------------------------------------------------
# Small-sample guard
# ---------------------------------------------------------------------------

def test_tiny_holdout_all_classes_forces_retained_with_note():
    # n=21 (>= MIN_LABELS), holdout_frac=0.2 -> holdout_size=4 < min_holdout(100)
    # -> triggers the k-fold path, but the aggregated evaluated set (21) can never reach
    # min_holdout=100 -> guard must force "retained" naming the real cause: too small.
    dataset = _balanced_dataset(7)  # 21 rows total, still small
    result = evaluate(
        dataset, _gold_label, train_classifier,
        min_labels=MIN_LABELS, holdout_frac=0.2, min_holdout=100, margin=MARGIN,
    )
    assert result.decision == "retained"
    assert result.notes == "held-out too small"
    assert result.macro_f1_delta is not None


def test_missing_class_in_holdout_forces_retained():
    # REALISTIC knobs (default MIN_HOLDOUT=8, not cranked to an unrealistic number): a
    # heavily imbalanced dataset where 'negative' has only 1 row overall — the stratified
    # per-class split rounds round(1 * 0.2) == 0, so ALL of 'negative' lands in TRAIN and
    # NONE lands in HOLDOUT, even though the holdout (16 rows: 8 positive + 8 neutral) is
    # otherwise comfortably above min_holdout. This is a plausible real-world shape: an
    # org whose corrections happen to be almost entirely positive/neutral with one stray
    # negative correction.
    dataset = _imbalanced_dataset({"positive": 40, "neutral": 40, "negative": 1})
    result = evaluate(
        dataset, _gold_label, train_classifier,
        min_labels=MIN_LABELS, holdout_frac=0.2, min_holdout=MIN_HOLDOUT, margin=MARGIN,
    )
    assert result.decision == "retained"
    assert result.notes == "held-out missing class"
    # Prove this really is the "missing class" cause, not the "too small" cause.
    assert result.n >= MIN_HOLDOUT


# ---------------------------------------------------------------------------
# Leakage-free contract: challenger is trained on data DISJOINT from what it's scored on
# ---------------------------------------------------------------------------

def test_challenger_trained_only_on_train_split_disjoint_from_scored_holdout():
    dataset = _balanced_dataset(20)  # 60 rows -> holdout_size=12 >= MIN_HOLDOUT -> simple-holdout path
    trained_texts_per_call: list[set[str]] = []

    def spy_train_fn(rows):
        trained_texts_per_call.append({text for text, _ in rows})
        return train_classifier(rows)

    scored_texts: list[str] = []

    def spy_incumbent(text):
        scored_texts.append(text)
        return _gold_label(text)

    result = evaluate(
        dataset, spy_incumbent, spy_train_fn,
        min_labels=MIN_LABELS, holdout_frac=0.2, min_holdout=MIN_HOLDOUT, margin=MARGIN,
    )

    assert len(trained_texts_per_call) == 1  # single-holdout path -> exactly one train call
    trained_texts = trained_texts_per_call[0]
    assert len(scored_texts) > 0
    # THE load-bearing leakage-free assertion: no row scored was also trained on.
    assert trained_texts.isdisjoint(scored_texts)
    assert result.decision in ("promoted", "retained")


def test_kfold_path_trains_each_fold_only_on_rows_outside_its_own_held_fold():
    dataset = _balanced_dataset(7)  # 21 rows -> triggers the k-fold path
    trained_texts_per_call: list[set[str]] = []

    def spy_train_fn(rows):
        trained_texts_per_call.append({text for text, _ in rows})
        return train_classifier(rows)

    scored_per_call: list[set[str]] = []

    def spy_incumbent(text):
        # evaluate()'s k-fold loop trains fold i's challenger, THEN scores fold i's held
        # rows, before moving to fold i+1 — so "the fold currently being scored" is
        # always trained_texts_per_call[-1] at the moment this spy fires.
        idx = len(trained_texts_per_call) - 1
        while len(scored_per_call) <= idx:
            scored_per_call.append(set())
        scored_per_call[idx].add(text)
        return _gold_label(text)

    evaluate(
        dataset, spy_incumbent, spy_train_fn,
        min_labels=MIN_LABELS, holdout_frac=0.2, min_holdout=MIN_HOLDOUT, margin=MARGIN,
    )

    assert len(trained_texts_per_call) >= 3  # k-fold path -> one train call per active fold
    assert len(scored_per_call) == len(trained_texts_per_call)
    for trained_texts, scored_texts in zip(trained_texts_per_call, scored_per_call):
        # Every fold's challenger was trained only on rows OUTSIDE its own held fold.
        assert trained_texts.isdisjoint(scored_texts)


# ---------------------------------------------------------------------------
# Promote / retain decisions
# ---------------------------------------------------------------------------

def test_clearly_better_challenger_is_promoted():
    dataset = _balanced_dataset(20)  # 60 rows, plenty for a real 0.2 holdout (12 >= min_holdout)
    result = evaluate(
        dataset, _always_wrong, train_classifier,
        min_labels=MIN_LABELS, holdout_frac=0.2, min_holdout=MIN_HOLDOUT, margin=MARGIN,
    )
    assert result.decision == "promoted"
    assert result.macro_f1_delta is not None
    assert result.macro_f1_delta >= MARGIN


def test_worse_challenger_is_retained():
    dataset = _balanced_dataset(20)

    def noisy_train_fn(rows):
        # A deliberately-bad train_fn: it trains on label-shuffled (mislabeled) rows
        # rather than the clean TRAIN split evaluate() hands it -> a near-useless model
        # (still 3 classes present, so it fits) — but evaluate() still SCORES it on the
        # genuine, clean HOLDOUT split, so a perfect (gold) incumbent should win badly.
        texts = [t for t, _ in rows]
        labels = [label for _, label in rows]
        shuffled_labels = labels[1:] + labels[:1]  # rotate -> breaks correlation
        noisy_rows = list(zip(texts, shuffled_labels))
        return train_classifier(noisy_rows)

    result = evaluate(
        dataset, _gold_label, noisy_train_fn,
        min_labels=MIN_LABELS, holdout_frac=0.2, min_holdout=MIN_HOLDOUT, margin=MARGIN,
    )
    assert result.decision == "retained"
    assert result.macro_f1_delta is not None
    assert result.macro_f1_delta < MARGIN


def test_delta_equals_margin_promotes():
    dataset = _balanced_dataset(20)
    result = evaluate(
        dataset, _always_wrong, train_classifier,
        min_labels=MIN_LABELS, holdout_frac=0.2, min_holdout=MIN_HOLDOUT, margin=0.0,
    )
    # margin=0.0 -> boundary is ">=" so any non-negative delta promotes
    assert result.decision == "promoted"


# ---------------------------------------------------------------------------
# Injected incumbent + determinism + never-raises
# ---------------------------------------------------------------------------

def test_incumbent_predict_is_injected():
    dataset = _balanced_dataset(20)

    calls = []

    def spy(text: str) -> str:
        calls.append(text)
        return _gold_label(text)

    result = evaluate(
        dataset, spy, train_classifier,
        min_labels=MIN_LABELS, holdout_frac=0.2, min_holdout=MIN_HOLDOUT, margin=MARGIN,
    )
    assert len(calls) == result.n
    assert result.n > 0


def test_evaluate_never_raises_on_degenerate():
    # The DATASET passed to evaluate() is degenerate (single class, above min_labels) —
    # sklearn's LogisticRegression cannot fit on a single class, so train_fn (the REAL
    # train_classifier) will raise on whatever split/fold evaluate() derives from this
    # dataset. evaluate() must not raise — it must catch that and disclose a guarded
    # "retained" result instead.
    dataset = [("single class only text " + str(i), "positive") for i in range(25)]
    result = evaluate(
        dataset, _gold_label, train_classifier,
        min_labels=MIN_LABELS, holdout_frac=0.2, min_holdout=MIN_HOLDOUT, margin=MARGIN,
    )
    assert result.decision in ("promoted", "retained", "skipped")


def test_deterministic_split():
    dataset = _balanced_dataset(20)
    r1 = evaluate(dataset, _gold_label, train_classifier, random_state=0)
    r2 = evaluate(dataset, _gold_label, train_classifier, random_state=0)
    assert r1 == r2


def test_evalresult_is_a_dataclass_with_expected_fields():
    result = EvalResult(
        decision="skipped", n=0, incumbent_macro_f1=None, challenger_macro_f1=None,
        macro_f1_delta=None, notes="below min_labels",
    )
    assert result.decision == "skipped"
    assert result.n == 0
