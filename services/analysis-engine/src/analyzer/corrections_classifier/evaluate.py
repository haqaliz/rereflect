"""Shadow-A/B evaluate — Phase 4b (M5.2 training-and-eval-core).

Runs the incumbent-vs-challenger shootout on a held-out split (stratified; k-fold when
tiny) and returns the promote/retain/skip decision. DISCLOSURE ONLY, never a build gate
(mirrors eval_sentiment.py's always-exit-0 ethos) — evaluate() never raises for degenerate
inputs; it always returns an EvalResult.

LEAKAGE-FREE CONTRACT: `evaluate` receives a `train_fn` callback (production:
`trainer.train_classifier`) and trains the challenger ITSELF, only on the TRAIN half of a
disjoint train/holdout split — never on rows it is later scored on. A single stratified
holdout is used when it is big enough; for small datasets a genuine per-fold k-fold retrain
is used instead (each fold's challenger is trained only on the OTHER folds, so every row is
scored by a model that never trained on it). This is what makes the promote decision a fair
measurement rather than an optimistic, leaky one.

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


def _classes_present(rows: list[tuple[str, str]], labels: tuple[str, ...]) -> set[str]:
    return {label for label in labels if any(row_label == label for _, row_label in rows)}


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


def _simple_holdout_confusions(
    dataset: list[tuple[str, str]],
    incumbent_predict: Callable[[str], str],
    train_fn: Callable[[list[tuple[str, str]]], dict],
    holdout_frac: float,
    rng: random.Random,
    labels: tuple[str, ...],
) -> tuple[dict[str, dict[str, int]], dict[str, dict[str, int]], int, set[str]]:
    """Single stratified holdout: the challenger is trained ONLY on the TRAIN split and
    scored ONLY on the (disjoint) HOLDOUT split — no row is ever both trained-on and
    scored (leakage-free)."""
    train_idx, holdout_idx = _stratified_split(dataset, holdout_frac, rng)
    train_rows = [dataset[i] for i in train_idx]
    holdout_rows = [dataset[i] for i in holdout_idx]

    challenger_artifact = train_fn(train_rows)

    def challenger_predict_fn(text: str) -> str:
        label, _ = predict(challenger_artifact, text)
        return label

    incumbent_confusion = _confusion_for(incumbent_predict, holdout_rows, labels)
    challenger_confusion = _confusion_for(challenger_predict_fn, holdout_rows, labels)
    holdout_classes = _classes_present(holdout_rows, labels)
    return incumbent_confusion, challenger_confusion, len(holdout_rows), holdout_classes


def _stratified_kfold_confusions(
    dataset: list[tuple[str, str]],
    incumbent_predict: Callable[[str], str],
    train_fn: Callable[[list[tuple[str, str]]], dict],
    k: int,
    rng: random.Random,
    labels: tuple[str, ...],
) -> tuple[dict[str, dict[str, int]], dict[str, dict[str, int]], int, set[str]]:
    """Stratified k-fold, GENUINE per-fold retrain: fold `f`'s challenger is trained ONLY
    on the OTHER folds' rows, then scored on fold `f`'s own held rows — so every row is
    evaluated by a model that never trained on it (leakage-free), aggregating one
    confusion matrix per model across all folds."""
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
    evaluated_rows: list[tuple[str, str]] = []

    for fold in range(k):
        held_idx = [i for i, f in fold_of_index.items() if f == fold]
        train_idx = [i for i, f in fold_of_index.items() if f != fold]
        if not held_idx or not train_idx:
            continue
        train_rows = [dataset[i] for i in train_idx]
        held_rows = [dataset[i] for i in held_idx]

        challenger_artifact = train_fn(train_rows)

        def challenger_predict_fn(text: str, _artifact=challenger_artifact) -> str:
            label, _ = predict(_artifact, text)
            return label

        for text, true_label in held_rows:
            if true_label not in incumbent_confusion:
                continue
            n += 1
            evaluated_rows.append((text, true_label))
            inc_pred = incumbent_predict(text)
            chall_pred = challenger_predict_fn(text)
            if inc_pred in incumbent_confusion[true_label]:
                incumbent_confusion[true_label][inc_pred] += 1
            if chall_pred in challenger_confusion[true_label]:
                challenger_confusion[true_label][chall_pred] += 1

    holdout_classes = _classes_present(evaluated_rows, labels)
    return incumbent_confusion, challenger_confusion, n, holdout_classes


def evaluate(
    dataset: list[tuple[str, str]],
    incumbent_predict: Callable[[str], str],
    train_fn: Callable[[list[tuple[str, str]]], dict],
    *,
    min_labels: int = MIN_LABELS,
    holdout_frac: float = HOLDOUT_FRAC,
    min_holdout: int = MIN_HOLDOUT,
    margin: float = MARGIN,
    random_state: int = RANDOM_STATE,
) -> EvalResult:
    """Leakage-free shadow-A/B: TRAIN the challenger only on a TRAIN split, score both
    incumbent + challenger only on a disjoint HOLDOUT split, decide promote/retain/skip.
    Never raises — disclosure only (see module docstring).

    train_fn: Callable[[list[(text, label)]], artifact_json] — called by evaluate()
    ITSELF on the TRAIN split only (production: trainer.train_classifier; tests inject
    fakes/spies). evaluate() never receives a pre-trained challenger, so it can never be
    handed one that was (even partially) trained on the rows it is about to score.

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
    holdout_size = round(n_total * holdout_frac)

    try:
        if holdout_size >= min_holdout:
            incumbent_confusion, challenger_confusion, n_evaluated, holdout_classes = (
                _simple_holdout_confusions(
                    dataset, incumbent_predict, train_fn, holdout_frac, rng, labels
                )
            )
        else:
            k = max(3, math.ceil(min_holdout / max(holdout_size, 1))) if holdout_size > 0 else 3
            incumbent_confusion, challenger_confusion, n_evaluated, holdout_classes = (
                _stratified_kfold_confusions(dataset, incumbent_predict, train_fn, k, rng, labels)
            )
    except Exception:
        # A split so degenerate that train_fn itself cannot fit a model (e.g. a class has
        # too few examples to survive into every fold's/split's training portion, so a
        # real trainer like sklearn's LogisticRegression raises) — disclosure only, never
        # raise: treat it the same as an unusable, missing-class holdout.
        return EvalResult(
            decision="retained", n=0,
            incumbent_macro_f1=None, challenger_macro_f1=None, macro_f1_delta=None,
            notes="held-out missing class",
        )

    incumbent_metrics = compute_multiclass_metrics(incumbent_confusion, list(labels))
    challenger_metrics = compute_multiclass_metrics(challenger_confusion, list(labels))
    incumbent_macro_f1 = incumbent_metrics["macro_f1"]
    challenger_macro_f1 = challenger_metrics["macro_f1"]
    macro_f1_delta = challenger_macro_f1 - incumbent_macro_f1

    # Small-sample guard, with the note naming the real cause: too few evaluated rows vs.
    # a class entirely absent from the evaluated set (checked in that priority order).
    if n_evaluated < min_holdout:
        return EvalResult(
            decision="retained", n=n_evaluated,
            incumbent_macro_f1=incumbent_macro_f1, challenger_macro_f1=challenger_macro_f1,
            macro_f1_delta=macro_f1_delta, notes="held-out too small",
        )
    if holdout_classes != set(labels):
        return EvalResult(
            decision="retained", n=n_evaluated,
            incumbent_macro_f1=incumbent_macro_f1, challenger_macro_f1=challenger_macro_f1,
            macro_f1_delta=macro_f1_delta, notes="held-out missing class",
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
