"""
Phase 5 RED: Tests for per-org sentiment provider injection at the worker
call site (src/tasks/analysis.py::_apply_keyword_analysis).

Covers:
- get_sentiment_analyzer(provider_name) process-level cache (single load/process)
- construction-failure falls back to VADER, never raises
- _apply_keyword_analysis resolves the org's provider and injects it
- resolver failure / db=None defaults to vader (matches today's only behavior)
- characterization: 'vader' path (unset or explicit) is byte-identical to
  the pre-aspect pipeline output (AC10)

TDD: RED first, then production code.
"""

from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock

from src.models import FeedbackItem, Organization, OrgAIConfig


@pytest.fixture(autouse=True)
def _reset_sentiment_analyzer_cache():
    """The process-level cache in analysis.py must not leak across tests."""
    import src.tasks.analysis as analysis_module
    analysis_module._sentiment_analyzer_cache.clear()
    yield
    analysis_module._sentiment_analyzer_cache.clear()


def _make_feedback(text: str, org_id: int = 1) -> FeedbackItem:
    f = FeedbackItem(organization_id=org_id, text=text, source="manual")
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


class TestGetSentimentAnalyzerCaching:
    def test_second_call_does_not_reconstruct(self):
        """AC7: construction is spied; a second call with the same provider_name
        must not invoke the constructor again."""
        import src.tasks.analysis as analysis_module
        analysis_module._sentiment_analyzer_cache.clear()

        call_count = {"n": 0}

        class CountingAnalyzer:
            def __init__(self, provider="vader"):
                call_count["n"] += 1

            def analyze(self, text):
                return {"compound": 0.0, "pos": 0.0, "neu": 1.0, "neg": 0.0, "label": "neutral"}

        with patch("analyzer.sentiment.SentimentAnalyzer", CountingAnalyzer):
            analysis_module.get_sentiment_analyzer("vader")
            analysis_module.get_sentiment_analyzer("vader")

        assert call_count["n"] == 1

    def test_construction_failure_falls_back_to_vader(self):
        """AC6: SentimentAnalyzer(provider=...) raising is caught, VADER returned,
        no exception propagates."""
        import src.tasks.analysis as analysis_module
        analysis_module._sentiment_analyzer_cache.clear()

        class FlakyAnalyzer:
            def __init__(self, provider="vader"):
                if provider == "transformer":
                    raise RuntimeError("boom: transformer unavailable")
                self.provider = provider

            def analyze(self, text):
                return {"compound": 0.0, "pos": 0.0, "neu": 1.0, "neg": 0.0, "label": "neutral"}

        with patch("analyzer.sentiment.SentimentAnalyzer", FlakyAnalyzer):
            analyzer = analysis_module.get_sentiment_analyzer("transformer")

        assert analyzer is not None
        result = analyzer.analyze("test text")
        assert "compound" in result


class TestApplyKeywordAnalysisResolution:
    def test_resolves_org_provider_and_injects(self, db, test_org):
        """resolve_sentiment_provider is called with the feedback's org_id; its
        result is passed into get_sentiment_analyzer."""
        from src.tasks import analysis as analysis_module

        feedback_item = _make_feedback("Great app!", org_id=test_org.id)

        with patch(
            "src.services.sentiment_resolver.resolve_sentiment_provider"
        ) as mock_resolve, patch(
            "src.tasks.analysis.get_sentiment_analyzer"
        ) as mock_get_analyzer, patch(
            "src.tasks.analysis.get_tag_extractor"
        ) as mock_te, patch(
            "src.tasks.analysis.get_categorizers"
        ) as mock_cats:
            from src.services.sentiment_resolver import ResolvedSentiment
            mock_resolve.return_value = ResolvedSentiment(provider="transformer")
            mock_analyzer = MagicMock()
            mock_analyzer.analyze.return_value = {"compound": 0.5, "label": "positive"}
            mock_get_analyzer.return_value = mock_analyzer
            mock_te.return_value = MagicMock(extract_tags=MagicMock(return_value=[]))
            mock_cats.return_value = (MagicMock(), MagicMock(), MagicMock())

            analysis_module._apply_keyword_analysis(feedback_item, db)

            mock_resolve.assert_called_once_with(test_org.id, db)
            mock_get_analyzer.assert_called_once_with("transformer")

    def test_resolver_failure_defaults_to_vader(self, db, test_org):
        """resolve_sentiment_provider raising/returning None never breaks analysis."""
        from src.tasks import analysis as analysis_module

        feedback_item = _make_feedback("Fine.", org_id=test_org.id)

        with patch(
            "src.services.sentiment_resolver.resolve_sentiment_provider",
            return_value=None,
        ), patch(
            "src.tasks.analysis.get_sentiment_analyzer"
        ) as mock_get_analyzer, patch(
            "src.tasks.analysis.get_tag_extractor"
        ) as mock_te, patch(
            "src.tasks.analysis.get_categorizers"
        ) as mock_cats:
            mock_analyzer = MagicMock()
            mock_analyzer.analyze.return_value = {"compound": 0.0, "label": "neutral"}
            mock_get_analyzer.return_value = mock_analyzer
            mock_te.return_value = MagicMock(extract_tags=MagicMock(return_value=[]))
            mock_cats.return_value = (MagicMock(), MagicMock(), MagicMock())

            analysis_module._apply_keyword_analysis(feedback_item, db)

            mock_get_analyzer.assert_called_once_with("vader")

    def test_db_none_defaults_to_vader_no_resolver_call(self):
        """When db is not passed (existing call pattern in test_keyword_analysis.py),
        no resolver call is attempted and provider defaults to vader — matches
        today's only possible behavior for callers with no DB session in scope."""
        from src.tasks import analysis as analysis_module

        feedback_item = _make_feedback("Fine.", org_id=1)

        with patch(
            "src.services.sentiment_resolver.resolve_sentiment_provider"
        ) as mock_resolve, patch(
            "src.tasks.analysis.get_sentiment_analyzer"
        ) as mock_get_analyzer, patch(
            "src.tasks.analysis.get_tag_extractor"
        ) as mock_te, patch(
            "src.tasks.analysis.get_categorizers"
        ) as mock_cats:
            mock_analyzer = MagicMock()
            mock_analyzer.analyze.return_value = {"compound": 0.0, "label": "neutral"}
            mock_get_analyzer.return_value = mock_analyzer
            mock_te.return_value = MagicMock(extract_tags=MagicMock(return_value=[]))
            mock_cats.return_value = (MagicMock(), MagicMock(), MagicMock())

            analysis_module._apply_keyword_analysis(feedback_item)

            mock_resolve.assert_not_called()
            mock_get_analyzer.assert_called_once_with("vader")


class TestCharacterizationVaderUnchanged:
    """AC10: fixed sample texts through the real (unmocked) pipeline produce the
    same sentiment_label/sentiment_score/is_urgent values as before this aspect,
    for both an unset org and an explicit 'vader' org.

    Values captured by running the pre-aspect pipeline against these exact
    samples (see per-org-resolution-report.md for the capture command).
    """

    SAMPLES = [
        ("I love this product, it's amazing!", 0.8516, "positive", False),
        ("This is terrible, I want a refund.", -0.4215, "negative", False),
        ("It's fine I guess.", 0.2023, "positive", False),
        ("URGENT: the app keeps crashing and I can't use it!!!", 0.5282, "positive", False),
        ("I'm done with this, canceling my subscription.", 0.0, "neutral", False),
    ]

    def _run_and_assert(self, db, org_id: int):
        from src.tasks.analysis import _apply_keyword_analysis
        import src.tasks.analysis as analysis_module
        analysis_module._sentiment_analyzer_cache.clear()

        for text, expected_score, expected_label, expected_urgent in self.SAMPLES:
            feedback_item = _make_feedback(text, org_id=org_id)

            _apply_keyword_analysis(feedback_item, db)

            assert feedback_item.sentiment_score == pytest.approx(expected_score, abs=1e-4), text
            assert feedback_item.sentiment_label == expected_label, text
            assert feedback_item.is_urgent == expected_urgent, text

    def test_vader_output_unchanged_for_unset_org(self, db, test_org):
        """No OrgAIConfig row for this org -> resolver returns None -> vader."""
        self._run_and_assert(db, test_org.id)

    def test_vader_output_unchanged_for_explicit_vader_org(self, db, test_org):
        config = OrgAIConfig(
            organization_id=test_org.id,
            default_provider="openai",
            model_categorization="gpt-4o-mini",
            model_analysis="gpt-4o-mini",
            model_insights="gpt-4o-mini",
            sentiment_provider="vader",
        )
        db.add(config)
        db.commit()

        self._run_and_assert(db, test_org.id)
