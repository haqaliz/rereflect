"""Shadow-A/B evaluate for the churn head (M5.3 churn-classifier-core).

Runs the incumbent-vs-challenger shootout on a held-out split (stratified;
k-fold when tiny) and returns the promote/retain/skip decision. DISCLOSURE
ONLY, never a build gate — evaluate_churn() never raises for degenerate
inputs; it always returns an EvalResult.

LEAKAGE-FREE CONTRACT (mirrors corrections_classifier/evaluate.py): `evaluate_churn`
receives a `train_fn` callback (production: trainer.train_churn_classifier) and
trains the challenger ITSELF, only on the TRAIN half of a disjoint
train/holdout split — never on rows it is later scored on. A single stratified
holdout is used when it is big enough; for small datasets a genuine per-fold
k-fold retrain is used instead (each fold's challenger is trained only on the
OTHER folds, so every row is scored by a model that never trained on it).

REUSE, NOT FORK: the holdout SPLIT MECHANICS (`_stratified_split` /
`_stratified_indices_by_class`) are imported from corrections_classifier's
evaluate.py — the same leakage-free machinery, one implementation. The scoring
loop is necessarily churn-specific: both sides score feature VECTORS into
PROBABILITIES (thresholded at 0.5 into binary macro-F1, the gate study's
metric), where the corrections loop scores texts into labels.

`build_incumbent_predict(calibration_loader)` defines the incumbent's interface:
the worker (aspect 4) injects a loader that returns the fitted calibrated
heuristic as a p(churn_risk_component)->[0,1] callable, or None (identity
fallback p = component/100) — the heuristic the M5.3 head must beat.

Pure stdlib (`random`, `math`) — no sklearn/numpy at module scope.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Callable, List, Optional

from ..corrections_classifier.evaluate import (  # reuse — M5.2 split machinery
    _stratified_indices_by_class,
    _stratified_split,
)
from ..corrections_classifier.labels import HOLDOUT_FRAC, MIN_HOLDOUT  # reuse — M5.2 knobs
from .features import FEATURE_NAMES
from .labels import MARGIN, MIN_LABELS, RANDOM_STATE
from .metrics import binary_macro_f1
from .predict import predict

_CHURN_RISK_COMPONENT_INDEX = FEATURE_NAMES.index("churn_risk_component")


@dataclass(frozen=True)
class EvalResult:
    decision: str  # "promoted" | "retained" | "skipped"
    n: int  # evaluated (held-out or k-fold) label count
    incumbent_macro_f1: Optional[float]
    challenger_macro_f1: Optional[float]
    macro_f1_delta: Optional[float]
    notes: str


def _to_dataset(rows: list[tuple[List[float], int]]) -> dict:
    return {"features": [vector for vector, _ in rows], "labels": [label for _, label in rows]}


def _simple_holdout_scores(
    rows: list[tuple[List[float], int]],
    incumbent_predict: Callable[[List[float]], float],
    train_fn: Callable[[dict], dict],
    holdout_frac: float,
    rng: random.Random,
) -> tuple[List[float], List[float], List[int], int]:
    """Single stratified holdout: challenger trained ONLY on the TRAIN split and
    scored ONLY on the (disjoint) HOLDOUT split; both sides scored on the SAME
    holdout rows (leakage-free)."""
    train_idx, holdout_idx = _stratified_split(rows, holdout_frac, rng)
    artifact = train_fn(_to_dataset([rows[i] for i in train_idx]))

    incumbent_probs: list[float] = []
    challenger_probs: list[float] = []
    scored_labels: list[int] = []
    for i in holdout_idx:
        vector, label = rows[i]
        incumbent_probs.append(float(incumbent_predict(vector)))
        challenger_probs.append(float(predict(artifact, vector)))
        scored_labels.append(label)
    return incumbent_probs, challenger_probs, scored_labels, len(holdout_idx)


def _kfold_scores(
    rows: list[tuple[List[float], int]],
    incumbent_predict: Callable[[List[float]], float],
    train_fn: Callable[[dict], dict],
    k: int,
    rng: random.Random,
) -> tuple[List[float], List[float], List[int], int]:
    """Stratified k-fold, GENUINE per-fold retrain: fold `f`'s challenger is
    trained ONLY on the OTHER folds' rows, then scored on fold `f`'s own held
    rows — every row evaluated by a model that never trained on it."""
    by_class = _stratified_indices_by_class(rows)
    fold_of_index: dict[int, int] = {}
    for label, indices in by_class.items():
        shuffled = list(indices)
        rng.shuffle(shuffled)
        for pos, idx in enumerate(shuffled):
            fold_of_index[idx] = pos % k

    incumbent_probs: list[float] = []
    challenger_probs: list[float] = []
    scored_labels: list[int] = []

    for fold in range(k):
        held_idx = [i for i, f in fold_of_index.items() if f == fold]
        train_idx = [i for i, f in fold_of_index.items() if f != fold]
        if not held_idx or not train_idx:
            continue
        artifact = train_fn(_to_dataset([rows[i] for i in train_idx]))
        for i in held_idx:
            vector, label = rows[i]
            incumbent_probs.append(float(incumbent_predict(vector)))
            challenger_probs.append(float(predict(artifact, vector)))
            scored_labels.append(label)

    return incumbent_probs, challenger_probs, scored_labels, len(scored_labels)


def evaluate_churn(
    dataset: dict,
    incumbent_predict: Callable[[List[float]], float],
    train_fn: Callable[[dict], dict],
    *,
    min_labels: int = MIN_LABELS,
    holdout_frac: float = HOLDOUT_FRAC,
    min_holdout: int = MIN_HOLDOUT,
    margin: float = MARGIN,
    random_state: int = RANDOM_STATE,
) -> EvalResult:
    """Leakage-free shadow-A/B for the churn head. Never raises — disclosure only.

    `dataset` = {"features": [...], "labels": [0/1...]} (rows_to_dataset's shape).
    `train_fn` = Callable[[sub-dataset dict], artifact_json] — called by
    evaluate_churn ITSELF on the TRAIN split only (production:
    trainer.train_churn_classifier); evaluate never receives a pre-trained
    challenger, so it can never be handed one trained on rows it will score.
    `incumbent_predict` = Callable[[feature_vector], p_churn] — injected
    (production: build_incumbent_predict(calibration_loader)).
    Both sides are scored on the SAME holdout rows; promoted iff
    challenger_macro_f1 - incumbent_macro_f1 >= margin (0.02 default).
    """
    features = dataset["features"]
    labels = dataset["labels"]
    n_total = len(labels)

    if n_total < min_labels:
        return EvalResult(
            decision="skipped", n=n_total,
            incumbent_macro_f1=None, challenger_macro_f1=None, macro_f1_delta=None,
            notes="below min_labels",
        )
    if len(set(labels)) < 2:
        return EvalResult(
            decision="skipped", n=n_total,
            incumbent_macro_f1=None, challenger_macro_f1=None, macro_f1_delta=None,
            notes="single-class labels",
        )

    rows: list[tuple[List[float], int]] = list(zip(features, labels))
    rng = random.Random(random_state)
    holdout_size = round(n_total * holdout_frac)

    try:
        if holdout_size >= min_holdout:
            incumbent_probs, challenger_probs, scored_labels, n_evaluated = _simple_holdout_scores(
                rows, incumbent_predict, train_fn, holdout_frac, rng
            )
        else:
            k = max(3, math.ceil(min_holdout / max(holdout_size, 1))) if holdout_size > 0 else 3
            incumbent_probs, challenger_probs, scored_labels, n_evaluated = _kfold_scores(
                rows, incumbent_predict, train_fn, k, rng
            )
    except Exception:
        # A split so degenerate that train_fn cannot fit a model — disclosure
        # only, never raise (corrections_classifier/evaluate.py convention).
        return EvalResult(
            decision="retained", n=0,
            incumbent_macro_f1=None, challenger_macro_f1=None, macro_f1_delta=None,
            notes="held-out missing class",
        )

    incumbent_macro_f1 = binary_macro_f1(incumbent_probs, scored_labels)
    challenger_macro_f1 = binary_macro_f1(challenger_probs, scored_labels)
    macro_f1_delta = challenger_macro_f1 - incumbent_macro_f1

    # Small-sample guards, in corrections' priority order (too-small first,
    # then missing-class), each naming the real cause in the note.
    if n_evaluated < min_holdout:
        return EvalResult(
            decision="retained", n=n_evaluated,
            incumbent_macro_f1=incumbent_macro_f1, challenger_macro_f1=challenger_macro_f1,
            macro_f1_delta=macro_f1_delta, notes="held-out too small",
        )
    if set(scored_labels) != {0, 1}:
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


def build_incumbent_predict(calibration_loader: Callable[[], Optional[Callable[[float], float]]]) -> Callable[[List[float]], float]:
    """Wrap the calibrated-heuristic incumbent as a p(feature_vector) callable.

    `calibration_loader` (injected by the worker in aspect 4) returns the fitted
    calibrated heuristic — a p(churn_risk_component)->[0,1] callable — or None,
    in which case the identity fallback p = churn_risk_component / 100 applies
    (the pre-calibration heuristic shape). The component is always read from
    the frozen churn_risk_component position of the feature vector.
    """

    def incumbent_predict(feature_vector: List[float]) -> float:
        component = float(feature_vector[_CHURN_RISK_COMPONENT_INDEX])
        calibrated = calibration_loader()
        if calibrated is None:
            return component / 100.0
        return float(calibrated(component))

    return incumbent_predict
