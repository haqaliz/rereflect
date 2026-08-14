"""Per-org churn classifier core — pure-compute head for the M5.3 ML challenger.

CPU-only, offline, per-org logistic-regression churn classifier built on the
leakage-free A/B spine of corrections_classifier (M5.2): no Celery, no HTTP,
no DB writes. Every function here is deterministic given its inputs; the
feature vector is frozen (see features.py); the artifact is JSON-only and
predict is pure stdlib.

Only `train_churn_classifier` (trainer.py) imports scikit-learn/numpy, and it
does so LAZILY INSIDE THE FUNCTION — importing this package (including
trainer.py's module scope) never pulls in sklearn/numpy; the rest of the
package (features, dataset transform, predict, metrics, evaluate) is pure
stdlib. This keeps the whole package importable in wheels-less venvs (e.g.
the worker-service Python 3.14 CI target) — only calling
train_churn_classifier() requires those wheels to actually be installed.
See tests/churn_classifier/test_lazy_import.py for the tripwire.
"""
from __future__ import annotations

from .labels import LABEL_WINDOW_DAYS, MARGIN, MIN_LABELS, RANDOM_STATE
from .metrics import binary_macro_f1, compute_binary_metrics
from .features import FEATURE_NAMES, build_feature_vector, missing_snapshot_defaults
from .predict import predict

__all__ = [
    "MIN_LABELS",
    "LABEL_WINDOW_DAYS",
    "MARGIN",
    "RANDOM_STATE",
    "compute_binary_metrics",
    "binary_macro_f1",
    "FEATURE_NAMES",
    "build_feature_vector",
    "missing_snapshot_defaults",
    "predict",
]
