"""Pure-stdlib churn predict from JSON artifact (M5.3 churn-classifier-core).

Reconstructs the binary logistic decision from a trainer.py JSON artifact
WITHOUT sklearn/numpy — stdlib only (`math`). This is what makes predict-time
(hot-path) scoring safe to call from anywhere, including envs without ML
wheels: only `train_churn_classifier` ever needs sklearn/numpy, never `predict`.

Reproduces sklearn's own predictions exactly (pinned by test_predict.py's
sklearn<->pure parity test at 1e-9) BECAUSE trainer.py pins deterministic,
fixed logreg params (lbfgs, max_iter=1000) — this module must never drift out
of sync with that contract. Returns P(churned) (the probability of classes[1],
the positive class in sklearn's binary shape), a float in [0, 1].
"""
from __future__ import annotations

import math
from typing import List, Union

Number = Union[int, float]


def _sigmoid(x: float) -> float:
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)


def predict(artifact: dict, feature_vector: List[Number]) -> float:
    """P(churned) = sigmoid(intercept + sum(coef_j * feature_j)).

    Pure Python — no sklearn/numpy required. The artifact is a trainer.py
    churn_logreg JSON dict (binary: single coef row, classes [0, 1]); a length
    mismatch between the vector and the coefficient row is a contract violation
    (drift between the frozen feature vector and the trained artifact) and
    raises ValueError rather than silently mispredicting.
    """
    coef: list[float] = artifact["coef"]
    if len(feature_vector) != len(coef):
        raise ValueError(
            f"feature vector length {len(feature_vector)} does not match "
            f"artifact coefficients {len(coef)}"
        )
    linear = float(artifact["intercept"])
    for coef_j, x_j in zip(coef, feature_vector):
        linear += coef_j * x_j
    return _sigmoid(linear)
