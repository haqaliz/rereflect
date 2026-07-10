"""
Phase 4 RED: Tests for the classifier-override injection at the worker call
site (src/tasks/analysis.py::_apply_keyword_analysis /
_analyze_feedback_item), the authoritative `allow_override=True` site.

Covers:
- off byte-stability characterization (reuses the exact SAMPLES table from
  test_keyword_analysis_sentiment_provider.py — unset classifier_mode is a
  pure no-op on top of the existing per-org sentiment-provider seam).
- shadow e2e: real _apply_keyword_analysis, stored values unchanged, one
  shadow log line.
- auto e2e: promoted fake model overrides sentiment_label; sentiment_score
  coherent [-1, 1].
- downstream-health coherence characterization: after an auto override, a
  func.avg(FeedbackItem.sentiment_score) query (the exact aggregate shape
  backend-api's health_score_service.py L667-720 runs) sees a numeric in
  range and does not raise.
- loader/predict failure -> analysis completes, incumbent (VADER) retained,
  never raises.

TDD: RED first, then production code (the two injection call-sites).
"""

from __future__ import annotations

import logging
from unittest.mock import patch

import pytest
from sqlalchemy import func

from src.models import FeedbackItem, OrgAIConfig, OrgClassifierModel


# A deterministic "always negative" artifact: the single vocabulary token
# ("neverseen") never matches any of the SAMPLES text below, so the TF-IDF
# vector is always empty and the decision collapses to the intercept ->
# sigmoid(-10) ~= 0 -> P(positive) ~= 0, P(negative) ~= 1 -> label="negative",
# score_from_proba ~= -1.0. Deterministic regardless of input text.
_ALWAYS_NEGATIVE_ARTIFACT = {
    "vectorizer": {
        "vocabulary": {"neverseen": 0},
        "idf": [1.0],
        "token_pattern": r"(?u)\b\w\w+\b",
        "lowercase": True,
        "sublinear_tf": True,
        "norm": "l2",
    },
    "logreg": {"coef": [[0.0]], "intercept": [-10.0]},
    "classes": ["negative", "positive"],
}

# Artifact that passes loader validation (non-empty vocab, coef/intercept
# same length) but raises inside aspect B's predict() itself: "fine" (a
# token that actually appears in the "It's fine I guess." sample used below)
# maps to vocabulary index 5, but idf only has 1 entry -> IndexError inside
# _tfidf_vector. A non-matching vocabulary token would never trigger this
# (the sparse vector would stay empty and predict() would silently succeed).
_PREDICT_RAISES_ARTIFACT = {
    "vectorizer": {
        "vocabulary": {"fine": 5},
        "idf": [1.0],
        "token_pattern": r"(?u)\b\w\w+\b",
        "lowercase": True,
        "sublinear_tf": True,
        "norm": "l2",
    },
    "logreg": {"coef": [[0.0]], "intercept": [0.0]},
    "classes": ["negative", "positive"],
}


@pytest.fixture(autouse=True)
def _reset_caches():
    import src.tasks.analysis as analysis_module
    import src.services.classifier_predict as classifier_predict_module

    analysis_module._sentiment_analyzer_cache.clear()
    classifier_predict_module._classifier_cache.clear()
    yield
    analysis_module._sentiment_analyzer_cache.clear()
    classifier_predict_module._classifier_cache.clear()


def _make_feedback(text: str, org_id: int) -> FeedbackItem:
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


def _set_classifier_mode(db, org_id: int, mode: str) -> None:
    config = OrgAIConfig(
        organization_id=org_id,
        default_provider="openai",
        model_categorization="gpt-4o-mini",
        model_analysis="gpt-4o-mini",
        model_insights="gpt-4o-mini",
        classifier_mode=mode,
    )
    db.add(config)
    db.commit()


def _add_active_model(db, org_id, artifact=None) -> OrgClassifierModel:
    row = OrgClassifierModel(
        organization_id=org_id,
        classifier_type="sentiment",
        model_json=artifact or _ALWAYS_NEGATIVE_ARTIFACT,
        label_count=10,
        is_active=True,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


class TestOffByteStability:
    """Reuses the exact SAMPLES table + expected values from
    test_keyword_analysis_sentiment_provider.py::TestCharacterizationVaderUnchanged.
    """

    SAMPLES = [
        ("I love this product, it's amazing!", 0.8516, "positive", False),
        ("This is terrible, I want a refund.", -0.4215, "negative", False),
        ("It's fine I guess.", 0.2023, "positive", False),
        ("URGENT: the app keeps crashing and I can't use it!!!", 0.5282, "positive", False),
        ("I'm done with this, canceling my subscription.", 0.0, "neutral", False),
    ]

    def test_no_classifier_config_row_is_byte_stable(self, db, test_org):
        """No OrgAIConfig row at all -> resolve_classifier returns None -> no-op."""
        from src.tasks.analysis import _apply_keyword_analysis

        for text, expected_score, expected_label, expected_urgent in self.SAMPLES:
            feedback_item = _make_feedback(text, test_org.id)

            _apply_keyword_analysis(feedback_item, db)

            assert feedback_item.sentiment_score == pytest.approx(expected_score, abs=1e-4), text
            assert feedback_item.sentiment_label == expected_label, text
            assert feedback_item.is_urgent == expected_urgent, text

    def test_explicit_off_is_byte_stable(self, db, test_org):
        from src.tasks.analysis import _apply_keyword_analysis

        _set_classifier_mode(db, test_org.id, "off")
        # Even with a promoted model available, off must never touch it.
        _add_active_model(db, test_org.id)

        for text, expected_score, expected_label, expected_urgent in self.SAMPLES:
            feedback_item = _make_feedback(text, test_org.id)

            _apply_keyword_analysis(feedback_item, db)

            assert feedback_item.sentiment_score == pytest.approx(expected_score, abs=1e-4), text
            assert feedback_item.sentiment_label == expected_label, text
            assert feedback_item.is_urgent == expected_urgent, text


class TestShadowE2E:
    def test_shadow_logs_and_never_mutates(self, db, test_org, caplog):
        from src.tasks.analysis import _apply_keyword_analysis

        _set_classifier_mode(db, test_org.id, "shadow")
        _add_active_model(db, test_org.id)

        feedback_item = _make_feedback("It's fine I guess.", test_org.id)

        with caplog.at_level(logging.INFO, logger="rereflect.classifier.shadow"):
            _apply_keyword_analysis(feedback_item, db)

        # Incumbent VADER values retained (see TestOffByteStability sample 3).
        assert feedback_item.sentiment_score == pytest.approx(0.2023, abs=1e-4)
        assert feedback_item.sentiment_label == "positive"

        shadow_records = [r for r in caplog.records if r.name == "rereflect.classifier.shadow"]
        assert len(shadow_records) == 1


class TestAutoE2E:
    def test_auto_overrides_with_promoted_model(self, db, test_org):
        from src.tasks.analysis import _apply_keyword_analysis

        _set_classifier_mode(db, test_org.id, "auto")
        _add_active_model(db, test_org.id)

        feedback_item = _make_feedback("It's fine I guess.", test_org.id)

        _apply_keyword_analysis(feedback_item, db)

        assert feedback_item.sentiment_label == "negative"
        assert -1.0 <= feedback_item.sentiment_score <= 1.0
        assert feedback_item.sentiment_score < -0.9  # deterministic strong-negative artifact

    def test_auto_overrides_llm_branch_too(self, db, ai_enabled_org, unanalyzed_feedback):
        """The classifier override is injected on BOTH _analyze_feedback_item
        branches — this covers the `if llm_result:` branch (after
        _apply_llm_result), which TestAutoE2E above does not exercise."""
        from src.tasks.analysis import _analyze_feedback_item

        _set_classifier_mode(db, ai_enabled_org.id, "auto")
        _add_active_model(db, ai_enabled_org.id)

        llm_result = {
            "sentiment_label": "positive",
            "sentiment_score": 0.6,
            "is_urgent": False,
            "confidence": 0.9,
        }

        with patch("src.tasks.analysis.categorize_feedback", return_value=llm_result):
            _analyze_feedback_item(unanalyzed_feedback, db)

        assert unanalyzed_feedback.llm_analyzed is True  # LLM branch did run
        assert unanalyzed_feedback.sentiment_label == "negative"  # then overridden
        assert -1.0 <= unanalyzed_feedback.sentiment_score <= 1.0
        assert unanalyzed_feedback.sentiment_score < -0.9


class TestDownstreamHealthCoherence:
    def test_overridden_score_is_coherent_for_health_avg_query(self, db, test_org):
        """After an auto override, the value backend-api's health_score_service
        (L667-720: db.query(func.avg(FeedbackItem.sentiment_score))...) would
        average is the overridden float — same aggregate query shape, run
        here against the worker's own FeedbackItem mirror/db."""
        from src.tasks.analysis import _apply_keyword_analysis

        _set_classifier_mode(db, test_org.id, "auto")
        _add_active_model(db, test_org.id)

        for text in ("It's fine I guess.", "I love this product, it's amazing!"):
            feedback_item = _make_feedback(text, test_org.id)
            _apply_keyword_analysis(feedback_item, db)
            db.add(feedback_item)
        db.commit()

        avg_sentiment = (
            db.query(func.avg(FeedbackItem.sentiment_score))
            .filter(
                FeedbackItem.organization_id == test_org.id,
                FeedbackItem.sentiment_score.isnot(None),
            )
            .scalar()
        )

        assert avg_sentiment is not None
        assert -1.0 <= float(avg_sentiment) <= 1.0
        # Both items were overridden to the strong-negative challenger.
        assert float(avg_sentiment) < -0.9


class TestLoaderOrPredictFailureNeverRaises:
    def test_predict_failure_retains_incumbent(self, db, test_org):
        from src.tasks.analysis import _apply_keyword_analysis

        _set_classifier_mode(db, test_org.id, "auto")
        _add_active_model(db, test_org.id, artifact=_PREDICT_RAISES_ARTIFACT)

        feedback_item = _make_feedback("It's fine I guess.", test_org.id)

        # Must not raise.
        _apply_keyword_analysis(feedback_item, db)

        assert feedback_item.sentiment_score == pytest.approx(0.2023, abs=1e-4)
        assert feedback_item.sentiment_label == "positive"

    def test_loader_exception_retains_incumbent(self, db, test_org):
        from src.tasks.analysis import _apply_keyword_analysis

        _set_classifier_mode(db, test_org.id, "auto")
        _add_active_model(db, test_org.id)

        feedback_item = _make_feedback("It's fine I guess.", test_org.id)

        with patch(
            "src.services.classifier_predict.load_active_classifier",
            side_effect=RuntimeError("boom"),
        ):
            _apply_keyword_analysis(feedback_item, db)

        assert feedback_item.sentiment_score == pytest.approx(0.2023, abs=1e-4)
        assert feedback_item.sentiment_label == "positive"
