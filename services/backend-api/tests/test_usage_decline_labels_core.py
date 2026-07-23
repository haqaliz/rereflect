"""
TDD tests for the usage-decline-churn-labels detector core (detector-core
aspect) — strict TDD (RED first). Pure logic only: no DB, no fixtures, no
mocks.

Run:
    cd services/backend-api && ./venv/bin/pytest tests/test_usage_decline_labels_core.py -v
"""

from datetime import date, timedelta

import pytest

from src.services.usage_decline_labels_core import qualifying_streak, suggestion_key


def d(offset: int) -> date:
    """Helper: a date `offset` days after a fixed epoch, for readable tests."""
    return date(2026, 1, 1) + timedelta(days=offset)


# ---------------------------------------------------------------------------
# AC1 — sustain_days consecutive sharp_decline -> streak start date
# ---------------------------------------------------------------------------

def test_exact_sustain_days_consecutive_sharp_decline_returns_streak_start():
    states = [
        (d(0), "sharp_decline"),
        (d(1), "sharp_decline"),
        (d(2), "sharp_decline"),
    ]
    assert qualifying_streak(states, sustain_days=3) == d(0)


def test_more_than_sustain_days_still_returns_correct_start():
    states = [
        (d(0), "stable"),
        (d(1), "sharp_decline"),
        (d(2), "sharp_decline"),
        (d(3), "sharp_decline"),
        (d(4), "sharp_decline"),
    ]
    # only the most recent 4 rows matter for sustain_days=4
    assert qualifying_streak(states, sustain_days=4) == d(1)


# ---------------------------------------------------------------------------
# AC2 — boundary: sustain_days - 1 consecutive -> None (both sides)
# ---------------------------------------------------------------------------

def test_one_short_of_sustain_days_returns_none():
    states = [
        (d(0), "sharp_decline"),
        (d(1), "sharp_decline"),
    ]
    assert qualifying_streak(states, sustain_days=3) is None


def test_exactly_sustain_days_boundary_returns_start_date():
    # the "other side" of the same boundary as the test above
    states = [
        (d(0), "sharp_decline"),
        (d(1), "sharp_decline"),
        (d(2), "sharp_decline"),
    ]
    assert qualifying_streak(states, sustain_days=3) == d(0)


# ---------------------------------------------------------------------------
# AC3 — a stable in the middle breaks the streak
# ---------------------------------------------------------------------------

def test_stable_in_middle_breaks_streak():
    states = [
        (d(0), "sharp_decline"),
        (d(1), "stable"),
        (d(2), "sharp_decline"),
        (d(3), "sharp_decline"),
    ]
    assert qualifying_streak(states, sustain_days=3) is None


# ---------------------------------------------------------------------------
# AC4 — insufficient_history in the middle breaks the streak (absence of
# evidence, not evidence of stability). The subtlest rule — pin it.
# ---------------------------------------------------------------------------

def test_insufficient_history_in_middle_breaks_streak():
    states = [
        (d(0), "sharp_decline"),
        (d(1), "insufficient_history"),
        (d(2), "sharp_decline"),
        (d(3), "sharp_decline"),
    ]
    assert qualifying_streak(states, sustain_days=3) is None


def test_insufficient_history_at_edge_of_window_breaks_streak():
    states = [
        (d(0), "insufficient_history"),
        (d(1), "sharp_decline"),
        (d(2), "sharp_decline"),
    ]
    assert qualifying_streak(states, sustain_days=3) is None


# ---------------------------------------------------------------------------
# AC5 — declining never qualifies, alone or mixed with sharp_decline
# ---------------------------------------------------------------------------

def test_declining_alone_never_qualifies():
    states = [
        (d(0), "declining"),
        (d(1), "declining"),
        (d(2), "declining"),
    ]
    assert qualifying_streak(states, sustain_days=3) is None


def test_declining_mixed_with_sharp_decline_never_qualifies():
    states = [
        (d(0), "sharp_decline"),
        (d(1), "declining"),
        (d(2), "sharp_decline"),
    ]
    assert qualifying_streak(states, sustain_days=3) is None


# ---------------------------------------------------------------------------
# AC6 — a calendar gap breaks the streak, even if all states in the window
# qualify. Test a gap in the middle AND at the start of the window.
# ---------------------------------------------------------------------------

def test_calendar_gap_in_middle_breaks_streak():
    states = [
        (d(0), "sharp_decline"),
        (d(2), "sharp_decline"),  # gap: d(1) missing
        (d(3), "sharp_decline"),
    ]
    assert qualifying_streak(states, sustain_days=3) is None


def test_calendar_gap_before_window_does_not_affect_qualifying_window():
    # a big gap BEFORE the window (rows outside the last sustain_days) must
    # not affect evaluation — only the window's own internal consecutiveness
    # matters.
    states = [
        (d(0), "sharp_decline"),
        (d(5), "sharp_decline"),  # big gap right before window
        (d(6), "sharp_decline"),
        (d(7), "sharp_decline"),
    ]
    # last 3 rows are d(5), d(6), d(7) — these ARE calendar-consecutive,
    # so this should qualify with start d(5).
    assert qualifying_streak(states, sustain_days=3) == d(5)


def test_calendar_gap_at_start_of_window_breaks_streak():
    # gap is inside the window, at its start: d(5) -> d(7) skips d(6)
    states = [
        (d(5), "sharp_decline"),
        (d(7), "sharp_decline"),
        (d(8), "sharp_decline"),
    ]
    assert qualifying_streak(states, sustain_days=3) is None


# ---------------------------------------------------------------------------
# Edge cases — section 6 of the plan
# ---------------------------------------------------------------------------

def test_states_shorter_than_sustain_days_returns_none():
    states = [
        (d(0), "sharp_decline"),
        (d(1), "sharp_decline"),
    ]
    assert qualifying_streak(states, sustain_days=5) is None


def test_empty_states_returns_none():
    assert qualifying_streak([], sustain_days=3) is None


@pytest.mark.parametrize("bad_sustain_days", [0, -1, -10])
def test_sustain_days_not_positive_raises_value_error(bad_sustain_days):
    states = [(d(0), "sharp_decline")]
    with pytest.raises(ValueError):
        qualifying_streak(states, sustain_days=bad_sustain_days)


def test_unsorted_states_are_sorted_defensively_before_evaluation():
    states = [
        (d(2), "sharp_decline"),
        (d(0), "sharp_decline"),
        (d(1), "sharp_decline"),
    ]
    assert qualifying_streak(states, sustain_days=3) == d(0)


def test_duplicate_dates_raise():
    states = [
        (d(0), "sharp_decline"),
        (d(1), "sharp_decline"),
        (d(1), "sharp_decline"),
    ]
    with pytest.raises(ValueError):
        qualifying_streak(states, sustain_days=3)


# ===========================================================================
# Phase 2 — suggestion_key
# ===========================================================================

def test_short_email_produces_readable_natural_form_key():
    key = suggestion_key("alice@example.com", d(0))
    assert key == f"usage:alice@example.com:{d(0).isoformat()}"
    assert len(key) <= 64


def test_255_char_email_key_still_fits_column_max():
    long_email = ("a" * 243) + "@x.com"  # exactly 249 chars, well over budget
    assert len(long_email) <= 255
    long_email = long_email.ljust(255, "b")
    assert len(long_email) == 255
    key = suggestion_key(long_email, d(0))
    assert len(key) <= 64


def test_same_inputs_produce_identical_key_twice():
    email = ("z" * 250)
    key1 = suggestion_key(email, d(0))
    key2 = suggestion_key(email, d(0))
    assert key1 == key2


def test_different_streak_start_produces_different_key():
    email = "bob@example.com"
    key1 = suggestion_key(email, d(0))
    key2 = suggestion_key(email, d(10))
    assert key1 != key2


def test_different_streak_start_produces_different_key_for_long_email():
    email = ("y" * 250)
    key1 = suggestion_key(email, d(0))
    key2 = suggestion_key(email, d(10))
    assert key1 != key2


def test_two_long_emails_sharing_200_char_prefix_produce_different_keys():
    prefix = "p" * 200
    email_a = prefix + ("a" * 55)
    email_b = prefix + ("b" * 55)
    assert len(email_a) == 255
    assert len(email_b) == 255
    key_a = suggestion_key(email_a, d(0))
    key_b = suggestion_key(email_b, d(0))
    assert key_a != key_b
    assert len(key_a) <= 64
    assert len(key_b) <= 64


# ===========================================================================
# Phase 3 — build_evidence
#
# Each test imports build_evidence locally (not added to the module-level
# import at the top of this file) so that, during the RED step, only these
# tests fail with a real ImportError/NameError -- the rest of the file keeps
# collecting and passing. This lets `-k` isolate a genuine failure instead of
# a whole-file collection error.
# ===========================================================================

import datetime as _datetime_module
import json


def test_build_evidence_round_trips_through_json_with_no_date_objects():
    from src.services.usage_decline_labels_core import build_evidence

    out = build_evidence(
        trend_state="sharp_decline",
        trend_pct=-42.5,
        baseline_active_days_14d=10,
        current_active_days_14d=2,
        streak_start_date=d(0),
        as_of_date=d(4),
        last_active_at=_datetime_module.datetime(2026, 1, 3, 12, 30, 0),
        snapshot_series=[
            (d(0), 10),
            (d(1), 8),
            (d(2), 5),
        ],
    )

    # Must survive a full JSON round-trip.
    round_tripped = json.loads(json.dumps(out))
    assert round_tripped == out

    # No raw date/datetime objects anywhere in the output.
    def _assert_no_date_objects(value):
        assert not isinstance(value, (_datetime_module.date, _datetime_module.datetime))
        if isinstance(value, dict):
            for v in value.values():
                _assert_no_date_objects(v)
        elif isinstance(value, list):
            for v in value:
                _assert_no_date_objects(v)

    _assert_no_date_objects(out)

    assert out["streak_start_date"] == d(0).isoformat()
    assert isinstance(out["streak_start_date"], str)
    assert out["last_active_at"] == "2026-01-03T12:30:00"
    for row in out["snapshot_series"]:
        assert isinstance(row["date"], str)


def test_build_evidence_snapshot_series_preserves_chronological_order():
    from src.services.usage_decline_labels_core import build_evidence

    out = build_evidence(
        trend_state="sharp_decline",
        trend_pct=-10.0,
        baseline_active_days_14d=9,
        current_active_days_14d=3,
        streak_start_date=d(0),
        as_of_date=d(2),
        last_active_at=None,
        snapshot_series=[
            (d(2), 3),
            (d(0), 9),
            (d(1), 6),
        ],
    )

    dates = [row["date"] for row in out["snapshot_series"]]
    assert dates == [d(0).isoformat(), d(1).isoformat(), d(2).isoformat()]


def test_build_evidence_streak_days_matches_span_implied_by_streak_start_date():
    from src.services.usage_decline_labels_core import build_evidence

    out = build_evidence(
        trend_state="sharp_decline",
        trend_pct=-30.0,
        baseline_active_days_14d=10,
        current_active_days_14d=1,
        streak_start_date=d(0),
        as_of_date=d(4),
        last_active_at=None,
        snapshot_series=[(d(0), 10), (d(4), 1)],
    )

    # d(0)..d(4) inclusive is a 5-day span.
    assert out["streak_days"] == 5
    assert out["streak_start_date"] == d(0).isoformat()


def test_build_evidence_none_trend_pct_serializes_as_null_not_string():
    from src.services.usage_decline_labels_core import build_evidence

    out = build_evidence(
        trend_state="insufficient_history",
        trend_pct=None,
        baseline_active_days_14d=None,
        current_active_days_14d=None,
        streak_start_date=d(0),
        as_of_date=d(0),
        last_active_at=None,
        snapshot_series=[],
    )

    serialized = json.dumps(out)
    round_tripped = json.loads(serialized)
    assert round_tripped["trend_pct"] is None
    assert round_tripped["last_active_at"] is None
    assert "None" not in serialized


