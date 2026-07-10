"""Per-org sentiment corrections classifier — pure-compute core (M5.2).

CPU-only, offline, per-org TF-IDF + logistic-regression sentiment classifier,
mirroring the churn split (`churn_calibrator.py` pure compute driven by
`calibration_refit.py`): no Celery, no HTTP, no DB writes. Every function here
is deterministic given its inputs.

Only `train_classifier` (trainer.py) imports scikit-learn/numpy, and it does so
LAZILY INSIDE THE FUNCTION — importing this package (including trainer.py's module
scope) never pulls in sklearn/numpy; the rest of the package (dataset transform,
predict, metrics, evaluate) is pure stdlib. This keeps the whole package importable
in wheels-less venvs (e.g. the worker-service Python 3.14 CI target) — only calling
train_classifier() requires those wheels to actually be installed.
See tests/corrections_classifier/test_lazy_import.py for the tripwire.
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
from .dataset import build_sentiment_dataset, rows_to_dataset
from .predict import predict, score_from_proba
from .evaluate import EvalResult, evaluate
from .trainer import train_classifier

__all__ = [
    "SENTIMENT_LABELS",
    "MIN_LABELS",
    "HOLDOUT_FRAC",
    "MIN_HOLDOUT",
    "MARGIN",
    "RANDOM_STATE",
    "build_sentiment_dataset",
    "rows_to_dataset",
    "train_classifier",
    "predict",
    "score_from_proba",
    "evaluate",
    "EvalResult",
]
