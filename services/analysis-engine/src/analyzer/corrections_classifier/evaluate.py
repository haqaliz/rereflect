"""Shadow-A/B evaluate — Phase 4b (M5.2 training-and-eval-core).

Runs the incumbent-vs-challenger shootout on a held-out split (stratified; k-fold when
tiny) and returns the promote/retain/skip decision. DISCLOSURE ONLY, never a build gate
(mirrors eval_sentiment.py's always-exit-0 ethos) — evaluate() never raises for degenerate
inputs; it always returns an EvalResult.

Pure stdlib (`random`) — predict.py/metrics.py are pure too, so importing this module
never pulls in sklearn/numpy (only train_classifier does, lazily, and only when called).
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Callable, Optional

from .labels import HOLDOUT_FRAC, MARGIN, MIN_HOLDOUT, MIN_LABELS, RANDOM_STATE, SENTIMENT_LABELS
from .metrics import compute_multiclass_metrics
from .predict import predict


@dataclass(frozen=True)
class EvalResult:
    decision: str  # "promoted" | "retained" | "skipped"
    n: int  # evaluated (held-out or k-fold) label count
    incumbent_macro_f1: Optional[float]
    challenger_macro_f1: Optional[float]
    macro_f1_delta: Optional[float]
    notes: str


def _empty_confusion(labels: tuple[str, ...]) -> dict[str, dict[str, int]]:
    return {true: {pred: 0 for pred in labels} for true in labels}


def _confusion_for(
    predict_fn: Callable[[str], str],
    rows: list[tuple[str, str]],
    labels: tuple[str, ...],
) -> dict[str, dict[str, int]]:
    confusion = _empty_confusion(labels)
    for text, true_label in rows:
        predicted_label = predict_fn(text)
        if true_label not in confusion or predicted_label not in confusion[true_label]:
            # Defensive: an out-of-vocab incumbent/challenger prediction outside the
            # fixed label set should never crash disclosure-only evaluation — skip
            # counting it rather than raise.
            continue
        confusion[true_label][predicted_label] += 1
    return confusion


def _stratified_indices_by_class(dataset: list[tuple[str, str]]) -> dict[str, list[int]]:
    by_class: dict[str, list[int]] = {}
    for i, (_, label) in enumerate(dataset):
        by_class.setdefault(label, []).append(i)
    return by_class


def _stratified_split(
    dataset: list[tuple[str, str]], holdout_frac: float, rng: random.Random
) -> tuple[list[int], list[int]]:
    """Stratified train/holdout split — per-class shuffle then per-class slice, so the
    holdout's class proportions mirror the full dataset's as closely as integer rounding
    allows."""
    by_class = _stratified_indices_by_class(dataset)
    holdout_idx: list[int] = []
    train_idx: list[int] = []
    for label, indices in by_class.items():
        shuffled = list(indices)
        rng.shuffle(shuffled)
        k = round(len(shuffled) * holdout_frac)
        holdout_idx.extend(shuffled[:k])
        train_idx.extend(shuffled[k:])
    return train_idx, holdout_idx


def _stratified_kfold_confusions(
    dataset: list[tuple[str, str]],
    incumbent_predict: Callable[[str], str],
    challenger_predict_fn: Callable[[str], str],
    k: int,
    rng: random.Random,
    labels: tuple[str, ...],
) -> tuple[dict[str, dict[str, int]], dict[str, dict[str, int]], int]:
    """Stratified k-fold: every row is evaluated exactly once (as part of exactly one
    fold's "test" slice), aggregating one confusion matrix per model across all folds."""
    by_class = _stratified_indices_by_class(dataset)
    fold_of_index: dict[int, int] = {}
    for label, indices in by_class.items():
        shuffled = list(indices)
        rng.shuffle(shuffled)
        for pos, idx in enumerate(shuffled):
            fold_of_index[idx] = pos % k

    incumbent_confusion = _empty_confusion(labels)
    challenger_confusion = _empty_confusion(labels)
    n = 0
    for i, (text, true_label) in enumerate(dataset):
        if true_label not in incumbent_confusion:
            continue
        n += 1
        inc_pred = incumbent_predict(text)
        chall_pred = challenger_predict_fn(text)
        if inc_pred in incumbent_confusion[true_label]:
            incumbent_confusion[true_label][inc_pred] += 1
        if chall_pred in challenger_confusion[true_label]:
            challenger_confusion[true_label][chall_pred] += 1

    return incumbent_confusion, challenger_confusion, n


def evaluate(
    dataset: list[tuple[str, str]],
    incumbent_predict: Callable[[str], str],
    challenger_artifact: dict,
    *,
    min_labels: int = MIN_LABELS,
    holdout_frac: float = HOLDOUT_FRAC,
    min_holdout: int = MIN_HOLDOUT,
    margin: float = MARGIN,
    random_state: int = RANDOM_STATE,
) -> EvalResult:
    """Shadow-A/B: score incumbent + challenger over a held-out split, decide
    promote/retain/skip. Never raises — disclosure only (see module docstring).

    incumbent_predict: Callable[[str], str] — injected so evaluate stays agnostic of
    what implementation backs it (aspect D wraps a live SentimentAnalyzer).
    challenger label = predict(challenger_artifact, text)[0].
    """
    n_total = len(dataset)
    if n_total < min_labels:
        return EvalResult(
            decision="skipped", n=n_total,
            incumbent_macro_f1=None, challenger_macro_f1=None, macro_f1_delta=None,
            notes="below min_labels",
        )

    labels = SENTIMENT_LABELS
    rng = random.Random(random_state)

    def challenger_predict_fn(text: str) -> str:
        label, _ = predict(challenger_artifact, text)
        return label

    holdout_size = round(n_total * holdout_frac)

    if holdout_size < min_holdout:
        k = max(3, math.ceil(min_holdout / max(holdout_size, 1))) if holdout_size > 0 else 3
        incumbent_confusion, challenger_confusion, n_evaluated = _stratified_kfold_confusions(
            dataset, incumbent_predict, challenger_predict_fn, k, rng, labels
        )
    else:
        _, holdout_idx = _stratified_split(dataset, holdout_frac, rng)
        holdout_rows = [dataset[i] for i in holdout_idx]
        n_evaluated = len(holdout_rows)
        incumbent_confusion = _confusion_for(incumbent_predict, holdout_rows, labels)
        challenger_confusion = _confusion_for(challenger_predict_fn, holdout_rows, labels)

    incumbent_metrics = compute_multiclass_metrics(incumbent_confusion, list(labels))
    challenger_metrics = compute_multiclass_metrics(challenger_confusion, list(labels))
    incumbent_macro_f1 = incumbent_metrics["macro_f1"]
    challenger_macro_f1 = challenger_metrics["macro_f1"]
    macro_f1_delta = challenger_macro_f1 - incumbent_macro_f1

    # "all 3 classes present" means the evaluated rows' TRUE labels cover all 3 —
    # a confusion row's sum is that label's support (count of evaluated rows whose
    # true label was `label`), independent of what either model predicted.
    classes_present = {
        label for label in labels
        if sum(incumbent_confusion[label].values()) > 0
    }
    guard_failed = n_evaluated < min_holdout or classes_present != set(labels)

    if guard_failed:
        return EvalResult(
            decision="retained", n=n_evaluated,
            incumbent_macro_f1=incumbent_macro_f1, challenger_macro_f1=challenger_macro_f1,
            macro_f1_delta=macro_f1_delta, notes="held-out too small",
        )

    if macro_f1_delta >= margin:
        decision = "promoted"
    else:
        decision = "retained"

    notes = f"{decision} (delta={macro_f1_delta:+.4f}, n={n_evaluated})"
    return EvalResult(
        decision=decision, n=n_evaluated,
        incumbent_macro_f1=incumbent_macro_f1, challenger_macro_f1=challenger_macro_f1,
        macro_f1_delta=macro_f1_delta, notes=notes,
    )
