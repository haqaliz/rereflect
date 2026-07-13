"""Fixed sentiment label vocabulary + locked knobs for the corrections classifier (M5.2).

`SENTIMENT_LABELS` is sorted so it matches sklearn's `classes_` ordering when the
trainer fits on these exact labels (LogisticRegression sorts classes lexicographically).
"""
from __future__ import annotations

SENTIMENT_LABELS: tuple[str, ...] = ("negative", "neutral", "positive")

# Fixed binary urgency vocab (sorted so classes[0]="not_urgent", classes[1]="urgent" —
# "urgent" is the positive class for predict()'s binary sigmoid branch, coef.shape==(1,n)).
URGENCY_LABELS: tuple[str, ...] = ("not_urgent", "urgent")

MIN_LABELS: int = 20
HOLDOUT_FRAC: float = 0.2
MIN_HOLDOUT: int = 8
MARGIN: float = 0.02
RANDOM_STATE: int = 0
