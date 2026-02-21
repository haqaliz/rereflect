"""Tests for churn risk heuristic scoring (keyword fallback)."""

import pytest
from unittest.mock import MagicMock
from src.tasks.analysis import _compute_heuristic_churn_risk, _compute_heuristic_suggestion


class TestComputeHeuristicChurnRisk:
    """Tests for _compute_heuristic_churn_risk.

    Note: function now returns Tuple[int, Dict] — (score, factors).
    """

    def test_very_negative_sentiment_high_score(self):
        feedback = MagicMock()
        feedback.text = "I'm canceling my subscription, this is terrible"
        feedback.sentiment_score = -0.8
        feedback.is_urgent = True
        feedback.customer_email = None

        score, _ = _compute_heuristic_churn_risk(feedback)
        # sentiment: 15pts + urgent: 10pts + "cancel": 5pts + "terrible": 5pts = 35
        assert score >= 30

    def test_neutral_feedback_low_score(self):
        feedback = MagicMock()
        feedback.text = "The product is okay, nothing special"
        feedback.sentiment_score = 0.1
        feedback.is_urgent = False
        feedback.customer_email = None

        score, _ = _compute_heuristic_churn_risk(feedback)
        assert score < 40

    def test_churn_keywords_boost_score(self):
        feedback = MagicMock()
        feedback.text = "I want to cancel and switch to a competitor"
        feedback.sentiment_score = -0.4
        feedback.is_urgent = False
        feedback.customer_email = None

        score, _ = _compute_heuristic_churn_risk(feedback)
        # sentiment: 10pts + "cancel": 5 + "switch": 5 + "competitor": 5 = 25 (capped at 15 for keywords) = 25
        assert score >= 20

    def test_frustration_keywords_boost_score(self):
        feedback = MagicMock()
        feedback.text = "This is frustrated and disappointed with the service"
        feedback.sentiment_score = -0.6
        feedback.is_urgent = False
        feedback.customer_email = None

        score, _ = _compute_heuristic_churn_risk(feedback)
        # sentiment: 15pts + "frustrated": 5 + "disappointed": 5 = 25
        assert score >= 20

    def test_positive_feedback_zero_score(self):
        feedback = MagicMock()
        feedback.text = "Love this product, great work!"
        feedback.sentiment_score = 0.9
        feedback.is_urgent = False
        feedback.customer_email = None

        score, _ = _compute_heuristic_churn_risk(feedback)
        assert score == 0

    def test_score_capped_at_100(self):
        feedback = MagicMock()
        feedback.text = "I'm canceling, switching to competitor, leaving, this is terrible awful horrible frustrated disappointed unacceptable"
        feedback.sentiment_score = -0.9
        feedback.is_urgent = True
        feedback.customer_email = None

        score, _ = _compute_heuristic_churn_risk(feedback)
        assert score <= 100

    def test_urgent_adds_10_points(self):
        """Urgency factor contributes 10 points."""
        feedback_urgent = MagicMock()
        feedback_urgent.text = "Something broke"
        feedback_urgent.sentiment_score = -0.4
        feedback_urgent.is_urgent = True
        feedback_urgent.customer_email = None

        feedback_not_urgent = MagicMock()
        feedback_not_urgent.text = "Something broke"
        feedback_not_urgent.sentiment_score = -0.4
        feedback_not_urgent.is_urgent = False
        feedback_not_urgent.customer_email = None

        score_urgent, _ = _compute_heuristic_churn_risk(feedback_urgent)
        score_not, _ = _compute_heuristic_churn_risk(feedback_not_urgent)
        assert score_urgent - score_not == 10

    def test_none_sentiment_score(self):
        feedback = MagicMock()
        feedback.text = "Cancel my account"
        feedback.sentiment_score = None
        feedback.is_urgent = False
        feedback.customer_email = None

        score, _ = _compute_heuristic_churn_risk(feedback)
        # No sentiment: 0pts + "cancel": 5pts = 5
        assert score >= 5


class TestComputeHeuristicSuggestion:
    """Tests for _compute_heuristic_suggestion."""

    def test_no_suggestion_for_low_risk(self):
        feedback = MagicMock()
        feedback.churn_risk_score = 20
        feedback.is_urgent = False

        result = _compute_heuristic_suggestion(feedback)
        assert result is None

    def test_moderate_suggestion(self):
        feedback = MagicMock()
        feedback.churn_risk_score = 50
        feedback.is_urgent = False

        result = _compute_heuristic_suggestion(feedback)
        assert result is not None
        assert "Moderate" in result

    def test_high_risk_suggestion(self):
        feedback = MagicMock()
        feedback.churn_risk_score = 80
        feedback.is_urgent = False

        result = _compute_heuristic_suggestion(feedback)
        assert result is not None
        assert "High churn risk" in result

    def test_high_risk_urgent_suggestion(self):
        feedback = MagicMock()
        feedback.churn_risk_score = 85
        feedback.is_urgent = True

        result = _compute_heuristic_suggestion(feedback)
        assert result is not None
        assert "urgent" in result.lower()

    def test_no_suggestion_for_none_score(self):
        feedback = MagicMock()
        feedback.churn_risk_score = None
        feedback.is_urgent = False

        result = _compute_heuristic_suggestion(feedback)
        assert result is None
