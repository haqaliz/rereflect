"""Churn logistic-regression trainer — JSON-only artifact (M5.3 churn-classifier-core).

Serializes ONLY to JSON-native types (never pickle): the linear-logistic
coefficients/intercept + the frozen feature-name list, enough for predict.py to
reconstruct the model from JSON alone, no sklearn model object at predict time.

sklearn is imported LAZILY inside `train_churn_classifier` (mirroring
corrections_classifier/trainer.py and calibration_refit.py's _fit_isotonic) so
this module — and the churn_classifier package as a whole — stays importable in
environments without ML wheels. Only this function may import sklearn/numpy.

Determinism contract: fixed random_state, solver lbfgs (sklearn default),
max_iter=1000 — never let these drift, or predict.py's pure-Python sigmoid will
stop reproducing sklearn's own predictions exactly (the parity test in
test_predict.py pins this contract).

Single-class (or empty) label sets CANNOT be fit by LogisticRegression; the
trainer must never crash on them, so it returns a degenerate artifact instead:
zero coefficients and an extreme signed intercept pointing at the majority
class (sigmoid(±20) ~ 0/1), which predict() resolves to the majority class for
every row. The A/B layer (evaluate.py) reports such datasets as skipped.
"""
from __future__ import annotations

from .features import FEATURE_NAMES
from .labels import RANDOM_STATE

_MODEL_TYPE = "churn_logreg"
_ARTIFACT_VERSION = 1
_DEGENERATE_INTERCEPT = 20.0


def _degenerate_artifact(labels: list) -> dict:
    """JSON artifact for a dataset sklearn cannot fit (empty or single-class).

    All-zero coefficients + an extreme signed intercept toward the majority
    class: +20 when every label is 1, -20 when every label is 0, 0 for an empty
    dataset. Deterministic; predict() resolves it to the majority class.
    """
    intercept = _DEGENERATE_INTERCEPT
    if labels and all(label == 0 for label in labels):
        intercept = -_DEGENERATE_INTERCEPT
    elif not labels:
        intercept = 0.0
    return {
        "model_type": _MODEL_TYPE,
        "version": _ARTIFACT_VERSION,
        "features": list(FEATURE_NAMES),
        "coef": [0.0] * len(FEATURE_NAMES),
        "intercept": intercept,
        "classes": [0, 1],
    }


def train_churn_classifier(dataset: dict, *, random_state: int = RANDOM_STATE) -> dict:
    """Train a binary logistic churn classifier and return a JSON-only artifact dict.

    `dataset` = {"features": [[...len(FEATURE_NAMES)...], ...], "labels": [0/1, ...]}
    (rows_to_dataset's shape). Deterministic given the same dataset + random_state.
    Never raises on degenerate (single-class/empty) label sets — see module docstring.
    """
    from sklearn.linear_model import LogisticRegression  # lazy

    X = dataset["features"]
    y = dataset["labels"]

    if len(set(y)) < 2:
        return _degenerate_artifact(y)

    clf = LogisticRegression(max_iter=1000, random_state=random_state)
    clf.fit(X, y)

    # Binary fit: sklearn produces a single coef row / single intercept; the
    # positive class (churned) is classes[1] == 1.
    return {
        "model_type": _MODEL_TYPE,
        "version": _ARTIFACT_VERSION,
        "features": list(FEATURE_NAMES),
        "coef": clf.coef_[0].tolist(),
        "intercept": float(clf.intercept_[0]),
        "classes": [0, 1],
    }
