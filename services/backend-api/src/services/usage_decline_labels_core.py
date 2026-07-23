# DUPLICATED: keep in sync with the worker-service copy
# (services/worker-service/src/services/usage_decline_labels_core.py)
"""
Usage-decline churn-label detector core (detector-core aspect).

Pure logic only — no database, no Celery, no HTTP. Every function here takes
plain data and returns plain data so it is testable without fixtures or
mocks, and so it can be mirrored byte-identically into worker-service (which
cannot import backend-api code).

See docs/planning/usage-decline-churn-labels/detector-core/spec.md
"""

from datetime import date, timedelta
from typing import List, Optional, Tuple

# States that count toward a qualifying sustained-decline streak. Anything
# else — "stable", "declining", "insufficient_history", or an unrecognised
# value — breaks the streak. "insufficient_history" is deliberately absent:
# it is an absence of evidence, not evidence of stability, so it must break
# a streak exactly like "stable" does.
QUALIFYING_STATE = "sharp_decline"


def qualifying_streak(
    states: List[Tuple[date, str]],
    sustain_days: int,
) -> Optional[date]:
    """Return the streak start date if the most recent `sustain_days`
    calendar-consecutive snapshots are all `sharp_decline`; else `None`.

    `states` is a list of (snapshot_date, usage_trend_state) tuples. The
    caller's ordering (documented as newest-LAST) is not trusted — this
    function sorts defensively by date before evaluating.

    Raises:
        ValueError: if `sustain_days` is not positive, or if `states`
            contains duplicate dates (a data error, not something to guess
            around).
    """
    if sustain_days <= 0:
        raise ValueError(f"sustain_days must be positive, got {sustain_days}")

    if not states:
        return None

    sorted_states = sorted(states, key=lambda row: row[0])

    dates_seen = [row[0] for row in sorted_states]
    if len(dates_seen) != len(set(dates_seen)):
        raise ValueError("duplicate snapshot_date entries in states")

    if len(sorted_states) < sustain_days:
        return None

    window = sorted_states[-sustain_days:]

    # Every state in the window must be the qualifying state.
    if any(state != QUALIFYING_STATE for _, state in window):
        return None

    # Every date in the window must be calendar-consecutive (no gaps).
    for previous_row, current_row in zip(window, window[1:]):
        previous_date, current_date = previous_row[0], current_row[0]
        if current_date - previous_date != timedelta(days=1):
            return None

    return window[0][0]


def suggestion_key(email: str, streak_start: date) -> str:
    """Phase 2 stub — implemented after Phase 1 sign-off."""
    raise NotImplementedError("suggestion_key is implemented in Phase 2")
