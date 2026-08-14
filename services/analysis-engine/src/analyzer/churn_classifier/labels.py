"""Locked knobs for the per-org churn classifier core (M5.3, aspect 3).

Every constant here is parity-pinned to its source-of-truth definition in the
pre-existing churn calibration path — see tests/churn_classifier/test_labels.py:

- MIN_LABELS == backend-api churn_calibrator.py's MIN_LABELS (the per-org fit
  gate: at least this many non-auto-suggested labels before any per-org model).
- LABEL_WINDOW_DAYS == worker calibration_refit.py's _LABEL_WINDOW_DAYS (the
  180-day observation window that defines a churn label).
- MARGIN / RANDOM_STATE mirror corrections_classifier.labels (M5.2 A/B): the
  macro-F1 promotion margin and the fixed split/train seed.
"""
from __future__ import annotations

MIN_LABELS: int = 20
LABEL_WINDOW_DAYS: int = 180
MARGIN: float = 0.02
RANDOM_STATE: int = 0
