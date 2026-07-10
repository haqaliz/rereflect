"""Fixed sentiment label vocabulary + locked knobs for the corrections classifier (M5.2).

`SENTIMENT_LABELS` is sorted so it matches sklearn's `classes_` ordering when the
trainer fits on these exact labels (LogisticRegression sorts classes lexicographically).
"""
from __future__ import annotations

SENTIMENT_LABELS: tuple[str, ...] = ("negative", "neutral", "positive")

MIN_LABELS: int = 20
HOLDOUT_FRAC: float = 0.2
MIN_HOLDOUT: int = 8
MARGIN: float = 0.02
RANDOM_STATE: int = 0
