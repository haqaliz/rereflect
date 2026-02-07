"""Tests for churn risk heuristic scoring (keyword fallback)."""

import pytest
from unittest.mock import MagicMock
from src.tasks.analysis import _compute_heuristic_churn_risk, _compute_heuristic_suggestion


class TestComputeHeuristicChurnRisk:
    """Tests for _compute_heuristic_churn_risk."""

    def test_very_negative_sentiment_high_score(self):
        feedback = MagicMock()
        feedback.text = "I'm canceling my subscription, this is terrible"
        feedback.sentiment_score = -0.8
        feedback.is_urgent = True

        score = _compute_heuristic_churn_risk(feedback)
        # -0.8 sentiment: 40pts + urgent: 20pts + "cancel": 10pts + "terrible": 5pts = 75
        assert score >= 70

    def test_neutral_feedback_low_score(self):
        feedback = MagicMock()
        feedback.text = "The product is okay, nothing special"
        feedback.sentiment_score = 0.1
        feedback.is_urgent = False

        score = _compute_heuristic_churn_risk(feedback)
        assert score < 40

    def test_churn_keywords_boost_score(self):
        feedback = MagicMock()
        feedback.text = "I want to cancel and switch to a competitor"
        feedback.sentiment_score = -0.4
        feedback.is_urgent = False

        score = _compute_heuristic_churn_risk(feedback)
        # -0.4 sentiment: 20pts + "cancel": 10pts + "switch": 10pts + "competitor": 10pts = 50 (capped at 25 for keywords)
        assert score >= 40

    def test_frustration_keywords_boost_score(self):
        feedback = MagicMock()
        feedback.text = "This is frustrated and disappointed with the service"
        feedback.sentiment_score = -0.6
        feedback.is_urgent = False

        score = _compute_heuristic_churn_risk(feedback)
        # -0.6 sentiment: 30pts + "frustrated": 5pts + "disappointed": 5pts = 40
        assert score >= 40

    def test_positive_feedback_zero_score(self):
        feedback = MagicMock()
        feedback.text = "Love this product, great work!"
        feedback.sentiment_score = 0.9
        feedback.is_urgent = False

        score = _compute_heuristic_churn_risk(feedback)
        assert score == 0

    def test_score_capped_at_100(self):
        feedback = MagicMock()
        feedback.text = "I'm canceling, switching to competitor, leaving, this is terrible awful horrible frustrated disappointed unacceptable"
        feedback.sentiment_score = -0.9
        feedback.is_urgent = True

        score = _compute_heuristic_churn_risk(feedback)
        assert score <= 100

    def test_urgent_adds_20_points(self):
        feedback_urgent = MagicMock()
        feedback_urgent.text = "Something broke"
        feedback_urgent.sentiment_score = -0.4
        feedback_urgent.is_urgent = True

        feedback_not_urgent = MagicMock()
        feedback_not_urgent.text = "Something broke"
        feedback_not_urgent.sentiment_score = -0.4
        feedback_not_urgent.is_urgent = False

        score_urgent = _compute_heuristic_churn_risk(feedback_urgent)
        score_not = _compute_heuristic_churn_risk(feedback_not_urgent)
        assert score_urgent - score_not == 20

    def test_none_sentiment_score(self):
        feedback = MagicMock()
        feedback.text = "Cancel my account"
        feedback.sentiment_score = None
        feedback.is_urgent = False

        score = _compute_heuristic_churn_risk(feedback)
        # No sentiment: 0pts + "cancel": 10pts = 10
        assert score >= 10


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
