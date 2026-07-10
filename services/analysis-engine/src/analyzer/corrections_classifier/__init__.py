"""Per-org sentiment corrections classifier — pure-compute core (M5.2).

CPU-only, offline, per-org TF-IDF + logistic-regression sentiment classifier,
mirroring the churn split (`churn_calibrator.py` pure compute driven by
`calibration_refit.py`): no Celery, no HTTP, no DB writes. Every function here
is deterministic given its inputs.

Only `train_classifier` (trainer.py) imports scikit-learn/numpy, and it does so
lazily inside the function — the rest of this package (dataset transform,
predict, metrics, evaluate) is pure stdlib so it stays importable in
wheels-less venvs (e.g. the worker-service Python 3.14 CI target).

Public surface is re-exported incrementally as each phase lands.
"""
from __future__ import annotations

from .labels import (
    HOLDOUT_FRAC,
    MARGIN,
    MIN_HOLDOUT,
    MIN_LABELS,
    RANDOM_STATE,
    SENTIMENT_LABELS,
)

__all__ = [
    "SENTIMENT_LABELS",
    "MIN_LABELS",
    "HOLDOUT_FRAC",
    "MIN_HOLDOUT",
    "MARGIN",
    "RANDOM_STATE",
]
