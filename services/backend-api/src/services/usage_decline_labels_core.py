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

import hashlib
from datetime import date, timedelta
from typing import List, Optional, Tuple

# ChurnLabelSuggestion.external_opportunity_id is String(64)
# (src/models/churn_label_suggestion.py). This is the natural-key budget
# that suggestion_key() must respect.
SUGGESTION_KEY_MAX_LENGTH = 64

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
    """Return a deterministic natural key for a sustained-decline streak.

    Stable while a streak continues (same email + streak_start -> same key),
    which is what makes re-detection idempotent. A new episode after
    recovery (a different streak_start) mints a new key.

    Must fit `ChurnLabelSuggestion.external_opportunity_id`, a
    `String(64)` column, even though `customer_email` is `String(255)` and
    can overflow the natural form. When the natural
    `usage:{email}:{iso_date}` form would exceed
    `SUGGESTION_KEY_MAX_LENGTH`, this falls back to a deterministic SHA-256
    hash of the *full* email (never a truncation of it — truncating the
    email itself could silently collide two customers sharing a long
    prefix onto the same suggestion).
    """
    iso_date = streak_start.isoformat()
    natural_key = f"usage:{email}:{iso_date}"
    if len(natural_key) <= SUGGESTION_KEY_MAX_LENGTH:
        return natural_key

    email_hash = hashlib.sha256(email.encode("utf-8")).hexdigest()[:32]
    return f"usage:{email_hash}:{iso_date}"
