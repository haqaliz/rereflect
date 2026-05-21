"""
Integration tests verifying that probability_updater and winback_detector are
both called from _analyze_feedback_item, and that failures are isolated.

Phase 3.2 — TDD GREEN phase.

Strategy: analysis.py imports probability_updater and winback_detector via
lazy `from src.services.X import Y` inside the function body. We inject mock
module objects into sys.modules before the function runs, capturing calls.
The `analyzer` package (analysis-engine) is also not installed in the test
venv so _apply_keyword_analysis must be patched too.
"""

import sys
from unittest.mock import MagicMock, patch

import pytest

from src.models import FeedbackItem


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_feedback(db, org_id: int, email: str, text: str = "some text") -> FeedbackItem:
    feedback = FeedbackItem(
        organization_id=org_id,
        text=text,
        source="email",
        customer_email=email,
    )
    db.add(feedback)
    db.commit()
    return feedback


def _make_prob_mock(side_effect=None):
    """Build a sys.modules-compatible mock for probability_updater."""
    m = MagicMock()
    if side_effect is not None:
        m.update.side_effect = side_effect
    return m


def _make_winback_mock(side_effect=None):
    """Build a sys.modules-compatible mock for winback_detector."""
    m = MagicMock()
    if side_effect is not None:
        m.check.side_effect = side_effect
    return m


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_analyze_feedback_calls_probability_updater_after_update_customer_health(
    db, ai_enabled_org
):
    """probability_updater.update is called with (org_id, email, db) during ingest."""
    feedback = _make_feedback(
        db, ai_enabled_org.id, "alice@example.com",
        "I think this might be the last time I use this product.",
    )
    mock_prob = _make_prob_mock()
    mock_winback = _make_winback_mock()
    sys.modules["src.services.probability_updater"] = mock_prob
    sys.modules["src.services.winback_detector"] = mock_winback
    try:
        with patch("src.tasks.analysis.categorize_feedback", return_value=None), \
             patch("src.tasks.analysis._apply_keyword_analysis"):
            from src.tasks.analysis import _analyze_feedback_item
            _analyze_feedback_item(feedback, db)
    finally:
        sys.modules.pop("src.services.probability_updater", None)
        sys.modules.pop("src.services.winback_detector", None)

    mock_prob.update.assert_called_once_with(ai_enabled_org.id, "alice@example.com", db)


def test_analyze_feedback_calls_winback_detector_after_update_customer_health(
    db, ai_enabled_org
):
    """winback_detector.check is called with (org_id, email, db) during ingest."""
    feedback = _make_feedback(
        db, ai_enabled_org.id, "bob@example.com", "Coming back to try again."
    )
    mock_prob = _make_prob_mock()
    mock_winback = _make_winback_mock()
    sys.modules["src.services.probability_updater"] = mock_prob
    sys.modules["src.services.winback_detector"] = mock_winback
    try:
        with patch("src.tasks.analysis.categorize_feedback", return_value=None), \
             patch("src.tasks.analysis._apply_keyword_analysis"):
            from src.tasks.analysis import _analyze_feedback_item
            _analyze_feedback_item(feedback, db)
    finally:
        sys.modules.pop("src.services.probability_updater", None)
        sys.modules.pop("src.services.winback_detector", None)

    mock_winback.check.assert_called_once_with(ai_enabled_org.id, "bob@example.com", db)


def test_probability_failure_does_not_block_winback_detection(
    db, ai_enabled_org
):
    """If probability_updater.update raises, winback_detector.check is still called."""
    feedback = _make_feedback(
        db, ai_enabled_org.id, "carol@example.com", "Testing isolation."
    )
    mock_prob = _make_prob_mock(side_effect=RuntimeError("prob exploded"))
    mock_winback = _make_winback_mock()
    sys.modules["src.services.probability_updater"] = mock_prob
    sys.modules["src.services.winback_detector"] = mock_winback
    try:
        with patch("src.tasks.analysis.categorize_feedback", return_value=None), \
             patch("src.tasks.analysis._apply_keyword_analysis"):
            from src.tasks.analysis import _analyze_feedback_item
            # Must not raise
            _analyze_feedback_item(feedback, db)
    finally:
        sys.modules.pop("src.services.probability_updater", None)
        sys.modules.pop("src.services.winback_detector", None)

    mock_winback.check.assert_called_once_with(ai_enabled_org.id, "carol@example.com", db)


def test_winback_failure_does_not_block_analysis_completion(
    db, ai_enabled_org
):
    """If winback_detector.check raises, _analyze_feedback_item still completes."""
    feedback = _make_feedback(
        db, ai_enabled_org.id, "dave@example.com", "Another test."
    )
    mock_prob = _make_prob_mock()
    mock_winback = _make_winback_mock(side_effect=RuntimeError("winback exploded"))
    sys.modules["src.services.probability_updater"] = mock_prob
    sys.modules["src.services.winback_detector"] = mock_winback
    try:
        with patch("src.tasks.analysis.categorize_feedback", return_value=None), \
             patch("src.tasks.analysis._apply_keyword_analysis"):
            from src.tasks.analysis import _analyze_feedback_item
            # Must not raise — two isolated try/except blocks
            _analyze_feedback_item(feedback, db)
    finally:
        sys.modules.pop("src.services.probability_updater", None)
        sys.modules.pop("src.services.winback_detector", None)
