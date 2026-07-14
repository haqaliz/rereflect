"""Cross-cutting sanity: binary urgency train/predict/evaluate end-to-end — urgency-core
(Phase 4, M urgency-classifier-head).

Test-only phase: proves the untouched trainer/predict/evaluate spine (no code changes in
this aspect) correctly handles a 2-class URGENCY_LABELS dataset, so worker-trainer can rely
on it. Guarded with pytest.importorskip("sklearn") since it calls train_classifier.
"""
from __future__ import annotations

import pytest

sklearn = pytest.importorskip("sklearn")

from src.analyzer.corrections_classifier.evaluate import EvalResult, evaluate  # noqa: E402
from src.analyzer.corrections_classifier.labels import (  # noqa: E402
    MARGIN,
    MIN_HOLDOUT,
    MIN_LABELS,
    URGENCY_LABELS,
)
from src.analyzer.corrections_classifier.predict import predict  # noqa: E402
from src.analyzer.corrections_classifier.trainer import train_classifier  # noqa: E402

_URGENT_WORDS = ["outage", "critical", "emergency", "down", "broken", "urgent"]
_NOT_URGENT_WORDS = ["cosmetic", "minor", "someday", "typo", "whenever", "trivial"]


def _row(label: str, i: int) -> tuple[str, str]:
    words = _URGENT_WORDS if label == "urgent" else _NOT_URGENT_WORDS
    w = words[i % len(words)]
    return (f"{w} feedback item number {i} details", label)


def _balanced_urgency_dataset(n_per_class: int) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for i in range(n_per_class):
        rows.append(_row("urgent", i))
        rows.append(_row("not_urgent", i))
    return rows


# 20 per class = 40 rows total -> holdout_size = round(40 * 0.2) = 8 >= MIN_HOLDOUT(8),
# so evaluate() takes the simple-holdout path (not k-fold).
_DATASET = _balanced_urgency_dataset(20)


def test_train_classifier_binary_urgency_artifact():
    art = train_classifier(_DATASET, classifier_type="urgency")
    assert art["classifier_type"] == "urgency"
    assert set(art["classes"]) == {"urgent", "not_urgent"}
    assert len(art["logreg"]["coef"]) == 1  # binary shape


def test_predict_on_urgency_artifact():
    art = train_classifier(_DATASET, classifier_type="urgency")

    label, proba = predict(art, "critical outage, everything is down")
    assert label in URGENCY_LABELS
    assert set(proba.keys()) == set(URGENCY_LABELS)
    assert proba["urgent"] > proba["not_urgent"]


def test_evaluate_binary_urgency_beats_always_not_urgent_incumbent():
    def always_not_urgent(text: str) -> str:
        return "not_urgent"

    assert len(_DATASET) >= MIN_LABELS

    result = evaluate(
        _DATASET,
        always_not_urgent,
        train_classifier,
        labels=URGENCY_LABELS,
        min_labels=MIN_LABELS,
        min_holdout=MIN_HOLDOUT,
        margin=MARGIN,
    )

    assert isinstance(result, EvalResult)
    assert result.n > 0
    assert result.incumbent_macro_f1 is not None
    assert result.challenger_macro_f1 is not None
    assert result.macro_f1_delta is not None
    # An always-"not_urgent" stub gets 0 recall on the urgent class -> a challenger that
    # learns real signal should beat it on macro-F1 (guards R-3).
    assert result.challenger_macro_f1 > result.incumbent_macro_f1
    assert result.decision == "promoted"
