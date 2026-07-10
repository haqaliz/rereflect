"""
Phase 5 RED: Tests for per-org sentiment provider injection at the backend
call site (src/api/routes/feedback.py).

Covers:
- get_sentiment_analyzer(provider_name) process-level cache (single load/process)
- construction-failure falls back to VADER, never raises
- analyze_single_feedback resolves the org's provider and injects it
- resolver failure defaults to vader
- characterization: 'vader' path (unset or explicit) is byte-identical to
  the pre-aspect pipeline output (AC10)

TDD: RED first, then production code.
"""

from __future__ import annotations

import sys
import os

import pytest
from unittest.mock import patch, MagicMock

from src.models.feedback import FeedbackItem
from src.models.organization import Organization
from src.models.org_ai_config import OrgAIConfig
from sqlalchemy.orm import Session

# get_sentiment_analyzer's own sys.path computation
# (dirname(__file__) + "../../../analysis-engine") only resolves inside the
# production Docker image (Dockerfile COPYs analysis-engine/src/analyzer to
# backend-api/analysis-engine/analyzer at build time — see Dockerfile).
# In a local dev checkout, "analyzer" lives at the sibling
# services/analysis-engine/src instead. Insert the real path here so the
# unmocked characterization tests below can import the real analyzer package
# without depending on that Docker-only layout; once "analyzer" is in
# sys.modules, feedback.py's own (locally-broken) path insertion is a no-op
# and its `from analyzer.sentiment import SentimentAnalyzer` resolves from
# the module cache like it would in production.
_ANALYSIS_ENGINE_SRC = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../../analysis-engine/src")
)
if _ANALYSIS_ENGINE_SRC not in sys.path:
    sys.path.insert(0, _ANALYSIS_ENGINE_SRC)


@pytest.fixture(autouse=True)
def _reset_sentiment_analyzer_cache():
    """The process-level cache in feedback.py must not leak across tests."""
    import src.api.routes.feedback as feedback_module
    feedback_module._sentiment_analyzer_cache.clear()
    yield
    feedback_module._sentiment_analyzer_cache.clear()


def _make_feedback(text: str, org_id: int = 1) -> FeedbackItem:
    f = FeedbackItem(organization_id=org_id, text=text, source="manual")
    f.sentiment_label = None
    f.sentiment_score = None
    f.is_urgent = False
    return f


class TestGetSentimentAnalyzerCaching:
    def test_same_provider_name_returns_cached_instance(self):
        """AC7: second call with the same provider_name does not reconstruct."""
        from src.api.routes.feedback import get_sentiment_analyzer

        a1 = get_sentiment_analyzer("vader")
        a2 = get_sentiment_analyzer("vader")

        assert a1 is a2

    def test_second_call_does_not_reconstruct(self):
        """AC7: construction is spied; a second call with the same provider_name
        must not invoke the constructor again."""
        import src.api.routes.feedback as feedback_module
        feedback_module._sentiment_analyzer_cache.clear()

        call_count = {"n": 0}

        class CountingAnalyzer:
            def __init__(self, provider="vader"):
                call_count["n"] += 1

            def analyze(self, text):
                return {"compound": 0.0, "pos": 0.0, "neu": 1.0, "neg": 0.0, "label": "neutral"}

        with patch("analyzer.sentiment.SentimentAnalyzer", CountingAnalyzer):
            feedback_module.get_sentiment_analyzer("vader")
            feedback_module.get_sentiment_analyzer("vader")

        assert call_count["n"] == 1

    def test_construction_failure_falls_back_to_vader(self):
        """AC6: SentimentAnalyzer(provider=...) raising is caught, VADER returned,
        no exception propagates."""
        import src.api.routes.feedback as feedback_module
        feedback_module._sentiment_analyzer_cache.clear()

        class FlakyAnalyzer:
            def __init__(self, provider="vader"):
                if provider == "transformer":
                    raise RuntimeError("boom: transformer unavailable")
                self.provider = provider

            def analyze(self, text):
                return {"compound": 0.0, "pos": 0.0, "neu": 1.0, "neg": 0.0, "label": "neutral"}

        with patch("analyzer.sentiment.SentimentAnalyzer", FlakyAnalyzer):
            analyzer = feedback_module.get_sentiment_analyzer("transformer")

        # Falls back to a usable analyzer instance; no exception propagated.
        assert analyzer is not None
        result = analyzer.analyze("test text")
        assert "compound" in result


class TestAnalyzeSingleFeedbackResolution:
    def test_resolves_org_provider_and_injects(self, db: Session, test_organization: Organization):
        """resolve_sentiment_provider is called with the feedback's org_id; its
        result is passed into get_sentiment_analyzer."""
        from src.api.routes import feedback as feedback_module

        feedback_item = _make_feedback("Great app!", org_id=test_organization.id)
        db.add(feedback_item)
        db.commit()
        db.refresh(feedback_item)

        with patch(
            "src.services.sentiment_resolver.resolve_sentiment_provider"
        ) as mock_resolve, patch(
            "src.api.routes.feedback.get_sentiment_analyzer"
        ) as mock_get_analyzer:
            from src.services.sentiment_resolver import ResolvedSentiment
            mock_resolve.return_value = ResolvedSentiment(provider="transformer")
            mock_analyzer = MagicMock()
            mock_analyzer.analyze.return_value = {"compound": 0.5, "label": "positive"}
            mock_get_analyzer.return_value = mock_analyzer

            feedback_module.analyze_single_feedback(feedback_item, db)

            mock_resolve.assert_called_once_with(test_organization.id, db)
            mock_get_analyzer.assert_called_once_with("transformer")

    def test_resolver_failure_defaults_to_vader(self, db: Session, test_organization: Organization):
        """resolve_sentiment_provider raising/returning None never breaks analysis."""
        from src.api.routes import feedback as feedback_module

        feedback_item = _make_feedback("Fine.", org_id=test_organization.id)
        db.add(feedback_item)
        db.commit()
        db.refresh(feedback_item)

        with patch(
            "src.services.sentiment_resolver.resolve_sentiment_provider",
            return_value=None,
        ), patch(
            "src.api.routes.feedback.get_sentiment_analyzer"
        ) as mock_get_analyzer:
            mock_analyzer = MagicMock()
            mock_analyzer.analyze.return_value = {"compound": 0.0, "label": "neutral"}
            mock_get_analyzer.return_value = mock_analyzer

            feedback_module.analyze_single_feedback(feedback_item, db)

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

    def _run_and_assert(self, db: Session, org_id: int):
        from src.api.routes.feedback import analyze_single_feedback
        import src.api.routes.feedback as feedback_module
        feedback_module._sentiment_analyzer_cache.clear()

        for text, expected_score, expected_label, expected_urgent in self.SAMPLES:
            feedback_item = _make_feedback(text, org_id=org_id)
            db.add(feedback_item)
            db.commit()
            db.refresh(feedback_item)

            analyze_single_feedback(feedback_item, db)

            assert feedback_item.sentiment_score == pytest.approx(expected_score, abs=1e-4), text
            assert feedback_item.sentiment_label == expected_label, text
            assert feedback_item.is_urgent == expected_urgent, text

    def test_vader_output_unchanged_for_unset_org(self, db: Session, test_organization: Organization):
        """No OrgAIConfig row for this org -> resolver returns None -> vader."""
        self._run_and_assert(db, test_organization.id)

    def test_vader_output_unchanged_for_explicit_vader_org(self, db: Session, test_organization: Organization):
        config = OrgAIConfig(
            organization_id=test_organization.id,
            default_provider="openai",
            model_categorization="gpt-4o-mini",
            model_analysis="gpt-4o-mini",
            model_insights="gpt-4o-mini",
            sentiment_provider="vader",
        )
        db.add(config)
        db.commit()

        self._run_and_assert(db, test_organization.id)
