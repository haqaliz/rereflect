"""
Tests for keyword-based analysis fallback (_apply_keyword_analysis).
Verifies that when LLM is unavailable, the keyword pipeline correctly
analyzes sentiment, urgency, pain points, feature requests, tags, and churn risk.
"""

from unittest.mock import patch, MagicMock
from src.models import FeedbackItem


class TestApplyKeywordAnalysis:
    """Tests for _apply_keyword_analysis (fallback when LLM is unavailable)."""

    def _make_feedback(self, text, org_id=1):
        """Helper to create a minimal FeedbackItem."""
        f = FeedbackItem(organization_id=org_id, text=text, source="manual")
        # Initialize fields that keyword analysis sets
        f.sentiment_label = None
        f.sentiment_score = None
        f.is_urgent = False
        f.pain_point_category = None
        f.feature_request_category = None
        f.tags = None
        f.llm_analyzed = None
        f.churn_risk_score = None
        f.suggested_action = None
        return f

    def _mock_sentiment(self, compound, label):
        """Helper to create mock sentiment result."""
        return {"compound": compound, "label": label, "scores": {}}

    @patch("src.tasks.analysis.get_categorizers")
    @patch("src.tasks.analysis.get_tag_extractor")
    @patch("src.tasks.analysis.get_sentiment_analyzer")
    def test_sets_sentiment_from_vader(self, mock_sa, mock_te, mock_cats):
        """Should set sentiment_label and sentiment_score from VADER."""
        from src.tasks.analysis import _apply_keyword_analysis

        analyzer = MagicMock()
        analyzer.analyze.return_value = self._mock_sentiment(0.8, "positive")
        mock_sa.return_value = analyzer
        mock_te.return_value = MagicMock(extract_tags=MagicMock(return_value=["positive"]))
        mock_cats.return_value = (MagicMock(), MagicMock(), MagicMock())

        feedback = self._make_feedback("Love this product!")
        _apply_keyword_analysis(feedback)

        assert feedback.sentiment_label == "positive"
        assert feedback.sentiment_score == 0.8

    @patch("src.tasks.analysis.get_categorizers")
    @patch("src.tasks.analysis.get_tag_extractor")
    @patch("src.tasks.analysis.get_sentiment_analyzer")
    def test_overrides_neutral_to_negative_for_strong_keywords(self, mock_sa, mock_te, mock_cats):
        """Should override VADER 'neutral' to 'negative' when strong negative keywords present."""
        from src.tasks.analysis import _apply_keyword_analysis

        analyzer = MagicMock()
        # VADER says neutral but text has 'crash'
        analyzer.analyze.return_value = self._mock_sentiment(0.0, "neutral")
        mock_sa.return_value = analyzer
        mock_te.return_value = MagicMock(extract_tags=MagicMock(return_value=[]))

        pain_result = MagicMock(category="system_crash", level="critical", text="crash", confidence=0.8)
        mock_cats.return_value = (
            MagicMock(categorize=MagicMock(return_value=pain_result)),
            MagicMock(),
            MagicMock(),
        )

        feedback = self._make_feedback("The app crash every time")
        _apply_keyword_analysis(feedback)

        assert feedback.sentiment_label == "negative"
        assert feedback.sentiment_score <= -0.1

    @patch("src.tasks.analysis.get_categorizers")
    @patch("src.tasks.analysis.get_tag_extractor")
    @patch("src.tasks.analysis.get_sentiment_analyzer")
    def test_detects_urgency(self, mock_sa, mock_te, mock_cats):
        """Should flag as urgent when urgent keyword + very negative sentiment."""
        from src.tasks.analysis import _apply_keyword_analysis

        analyzer = MagicMock()
        analyzer.analyze.return_value = self._mock_sentiment(-0.8, "negative")
        mock_sa.return_value = analyzer
        mock_te.return_value = MagicMock(extract_tags=MagicMock(return_value=[]))

        pain_result = MagicMock(category="system_crash", level="critical", text="crash", confidence=0.9)
        urgent_result = MagicMock(category="critical_bug", level="immediate", confidence=0.9)
        mock_cats.return_value = (
            MagicMock(categorize=MagicMock(return_value=pain_result)),
            MagicMock(),
            MagicMock(categorize=MagicMock(return_value=urgent_result)),
        )

        feedback = self._make_feedback("URGENT: App is broken and crashing!")
        _apply_keyword_analysis(feedback)

        assert feedback.is_urgent is True
        assert feedback.urgent_category == "critical_bug"

    @patch("src.tasks.analysis.get_categorizers")
    @patch("src.tasks.analysis.get_tag_extractor")
    @patch("src.tasks.analysis.get_sentiment_analyzer")
    def test_detects_pain_point(self, mock_sa, mock_te, mock_cats):
        """Should categorize pain points when negative keywords present."""
        from src.tasks.analysis import _apply_keyword_analysis

        analyzer = MagicMock()
        analyzer.analyze.return_value = self._mock_sentiment(-0.5, "negative")
        mock_sa.return_value = analyzer
        mock_te.return_value = MagicMock(extract_tags=MagicMock(return_value=[]))

        pain_result = MagicMock(category="slow_performance", level="major", text="slow loading", confidence=0.7)
        mock_cats.return_value = (
            MagicMock(categorize=MagicMock(return_value=pain_result)),
            MagicMock(),
            MagicMock(),
        )

        feedback = self._make_feedback("The loading is so slow it's frustrating")
        _apply_keyword_analysis(feedback)

        assert feedback.pain_point_category == "slow_performance"
        assert feedback.pain_point_severity == "major"
        assert feedback.extracted_issue is not None

    @patch("src.tasks.analysis.get_categorizers")
    @patch("src.tasks.analysis.get_tag_extractor")
    @patch("src.tasks.analysis.get_sentiment_analyzer")
    def test_detects_feature_request(self, mock_sa, mock_te, mock_cats):
        """Should categorize feature requests when request patterns present."""
        from src.tasks.analysis import _apply_keyword_analysis

        analyzer = MagicMock()
        analyzer.analyze.return_value = self._mock_sentiment(0.1, "neutral")
        mock_sa.return_value = analyzer
        mock_te.return_value = MagicMock(extract_tags=MagicMock(return_value=[]))

        feature_result = MagicMock(category="ui_ux", level="medium", text="dark mode", confidence=0.75)
        mock_cats.return_value = (
            MagicMock(),
            MagicMock(categorize=MagicMock(return_value=feature_result)),
            MagicMock(),
        )

        feedback = self._make_feedback("Would love to see a dark mode feature")
        _apply_keyword_analysis(feedback)

        assert feedback.feature_request_category == "ui_ux"
        assert feedback.feature_request_priority == "medium"

    @patch("src.tasks.analysis.get_categorizers")
    @patch("src.tasks.analysis.get_tag_extractor")
    @patch("src.tasks.analysis.get_sentiment_analyzer")
    def test_sets_llm_analyzed_false(self, mock_sa, mock_te, mock_cats):
        """Should mark llm_analyzed=False for keyword fallback."""
        from src.tasks.analysis import _apply_keyword_analysis

        analyzer = MagicMock()
        analyzer.analyze.return_value = self._mock_sentiment(0.5, "positive")
        mock_sa.return_value = analyzer
        mock_te.return_value = MagicMock(extract_tags=MagicMock(return_value=[]))
        mock_cats.return_value = (MagicMock(), MagicMock(), MagicMock())

        feedback = self._make_feedback("This is fine")
        _apply_keyword_analysis(feedback)

        assert feedback.llm_analyzed is False

    @patch("src.tasks.analysis.get_categorizers")
    @patch("src.tasks.analysis.get_tag_extractor")
    @patch("src.tasks.analysis.get_sentiment_analyzer")
    def test_sets_churn_risk_score(self, mock_sa, mock_te, mock_cats):
        """Should compute and set churn_risk_score via heuristic."""
        from src.tasks.analysis import _apply_keyword_analysis

        analyzer = MagicMock()
        analyzer.analyze.return_value = self._mock_sentiment(-0.8, "negative")
        mock_sa.return_value = analyzer
        mock_te.return_value = MagicMock(extract_tags=MagicMock(return_value=[]))

        pain_result = MagicMock(category="billing", level="critical", text="cancel", confidence=0.9)
        feature_result = MagicMock(category=None, level=None, text="", confidence=0.3)
        mock_cats.return_value = (
            MagicMock(categorize=MagicMock(return_value=pain_result)),
            MagicMock(categorize=MagicMock(return_value=feature_result)),
            MagicMock(),
        )

        feedback = self._make_feedback("I want to cancel my subscription")
        _apply_keyword_analysis(feedback)

        assert feedback.churn_risk_score is not None
        assert feedback.churn_risk_score > 0
        assert isinstance(feedback.churn_risk_score, int)

    @patch("src.tasks.analysis.get_categorizers")
    @patch("src.tasks.analysis.get_tag_extractor")
    @patch("src.tasks.analysis.get_sentiment_analyzer")
    def test_extracts_tags(self, mock_sa, mock_te, mock_cats):
        """Should extract tags from text."""
        from src.tasks.analysis import _apply_keyword_analysis

        analyzer = MagicMock()
        analyzer.analyze.return_value = self._mock_sentiment(0.1, "neutral")
        mock_sa.return_value = analyzer
        mock_te.return_value = MagicMock(extract_tags=MagicMock(return_value=["bug", "performance"]))
        mock_cats.return_value = (MagicMock(), MagicMock(), MagicMock())

        feedback = self._make_feedback("Some text about performance bugs")
        _apply_keyword_analysis(feedback)

        assert feedback.tags == ["bug", "performance"]
