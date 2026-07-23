"""
TDD tests for the usage-trend severity ordering helper (trigger-registration,
Phase 1) — strict TDD (RED first).

Run:
    cd services/backend-api && ./venv/bin/pytest tests/test_usage_trend_severity.py -v
"""

import pytest

from src.services.usage_trend_severity import is_worsening_transition


# ---------------------------------------------------------------------------
# AC1 — firing transitions (strictly worsening, both ranked)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "old_state,new_state",
    [
        ("stable", "declining"),
        ("stable", "sharp_decline"),
        ("declining", "sharp_decline"),
    ],
)
def test_worsening_transitions_fire(old_state, new_state):
    assert is_worsening_transition(old_state, new_state) is True


# ---------------------------------------------------------------------------
# AC2 — equal states never fire
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "state",
    ["stable", "declining", "sharp_decline"],
)
def test_equal_state_does_not_fire(state):
    assert is_worsening_transition(state, state) is False


# ---------------------------------------------------------------------------
# AC3 — insufficient_history has no rank; every transition touching it,
# in EITHER direction, must not fire. This includes the specific warm-up
# guard case insufficient_history -> sharp_decline (PRD E3).
# ---------------------------------------------------------------------------

def test_insufficient_history_to_sharp_decline_does_not_fire_warmup_guard():
    """The warm-up guard: a customer's very first classification landing on
    sharp_decline must NOT fire, because insufficient_history has no rank
    and this is a baseline observation, not a worsening transition."""
    assert is_worsening_transition("insufficient_history", "sharp_decline") is False


@pytest.mark.parametrize(
    "old_state,new_state",
    [
        ("insufficient_history", "stable"),
        ("insufficient_history", "declining"),
        ("insufficient_history", "sharp_decline"),
        ("insufficient_history", "insufficient_history"),
        ("stable", "insufficient_history"),
        ("declining", "insufficient_history"),
        ("sharp_decline", "insufficient_history"),
    ],
)
def test_insufficient_history_never_fires_either_direction(old_state, new_state):
    assert is_worsening_transition(old_state, new_state) is False


# ---------------------------------------------------------------------------
# AC4 — improvements never fire
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "old_state,new_state",
    [
        ("sharp_decline", "declining"),
        ("sharp_decline", "stable"),
        ("declining", "stable"),
    ],
)
def test_improvement_does_not_fire(old_state, new_state):
    assert is_worsening_transition(old_state, new_state) is False


# ---------------------------------------------------------------------------
# AC5 — missing/None on either side never fires, never raises
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "old_state,new_state",
    [
        (None, "sharp_decline"),
        ("stable", None),
        (None, None),
    ],
)
def test_none_never_fires_never_raises(old_state, new_state):
    assert is_worsening_transition(old_state, new_state) is False


# ---------------------------------------------------------------------------
# Unrecognised state strings fall through fail-closed
# ---------------------------------------------------------------------------

def test_unknown_state_string_does_not_fire():
    assert is_worsening_transition("stable", "some_future_state") is False
    assert is_worsening_transition("some_future_state", "sharp_decline") is False
