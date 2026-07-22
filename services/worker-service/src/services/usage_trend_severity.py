# DUPLICATED: keep in sync with the backend-api copy
# (services/backend-api/src/services/usage_trend_severity.py)
"""
Usage-trend severity ordering — the single source of truth for "is this
transition strictly worsening?" used by the AutomationEngine's usage_trend
trigger checker (backend-api) and the worker's daily trend evaluator
(worker-service, which cannot import backend-api code).

Deliberately dependency-free: this module must be safe to copy verbatim
into worker-service without pulling in any backend-api-only imports.
"""

from typing import Optional

TREND_SEVERITY = {"stable": 0, "declining": 1, "sharp_decline": 2}
# NOTE: "insufficient_history" is deliberately absent — it means "unknown",
# not "healthy". Its absence is what makes the baseline-seed (warm-up) rule
# work: any transition touching it, in either direction, falls through the
# .get() below to None and never fires.


def is_worsening_transition(old_state: Optional[str], new_state: Optional[str]) -> bool:
    """Return True iff *new_state* is strictly more severe than *old_state*.

    `None`, `"insufficient_history"`, and any unrecognised state string all
    fall out as `False` through the same `.get()` path — one rule, no
    special cases. Never raises.
    """
    old_rank = TREND_SEVERITY.get(old_state)
    new_rank = TREND_SEVERITY.get(new_state)
    if old_rank is None or new_rank is None:
        return False
    return new_rank > old_rank
