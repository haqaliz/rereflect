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


# Deterministic category artifacts — binary shape (coef=[[0.0]], very
# negative intercept) collapses P(classes[1])->0 regardless of input text
# (vocabulary token "neverseen" never matches), so argmax always picks
# classes[0]. Same proven pattern as _ALWAYS_NEGATIVE_ARTIFACT, just with
# category class names.
_ALWAYS_PAIN_VOCAB_ARTIFACT = {
    "vectorizer": {
        "vocabulary": {"neverseen": 0}, "idf": [1.0],
        "token_pattern": r"(?u)\b\w\w+\b", "lowercase": True,
        "sublinear_tf": True, "norm": "l2",
    },
    "logreg": {"coef": [[0.0]], "intercept": [-10.0]},
    "classes": ["security_breach", "core_functionality"],
}
_ALWAYS_FEATURE_VOCAB_ARTIFACT = {
    **_ALWAYS_PAIN_VOCAB_ARTIFACT,
    "classes": ["core_functionality", "security_breach"],  # swap order -> classes[0] now feature-vocab
}
_ALWAYS_CUSTOM_LABEL_ARTIFACT = {
    **_ALWAYS_PAIN_VOCAB_ARTIFACT,
    "classes": ["totally_custom_thing", "another_custom_thing"],
}


def _set_category_classifier_mode(db, org_id: int, mode: str) -> None:
    config = OrgAIConfig(
        organization_id=org_id,
        default_provider="openai",
        model_categorization="gpt-4o-mini",
        model_analysis="gpt-4o-mini",
        model_insights="gpt-4o-mini",
        category_classifier_mode=mode,
    )
    db.add(config)
    db.commit()


def _add_active_category_model(db, org_id, artifact) -> OrgClassifierModel:
    row = OrgClassifierModel(
        organization_id=org_id,
        classifier_type="category",
        model_json=artifact,
        label_count=10,
        is_active=True,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


class TestCategoryOffByteStability:
    """Reuses TestOffByteStability's SAMPLES: unset/off category mode is a
    pure no-op even with an active category model present -- category
    fields must be byte-identical between the two runs."""

    SAMPLES = TestOffByteStability.SAMPLES

    def test_no_config_row_vs_explicit_off_are_identical(self, db, test_org):
        from src.tasks.analysis import _apply_keyword_analysis

        no_config_results = []
        for text, *_ in self.SAMPLES:
            feedback_item = _make_feedback(text, test_org.id)
            _apply_keyword_analysis(feedback_item, db)
            no_config_results.append(
                (feedback_item.pain_point_category, feedback_item.feature_request_category)
            )

        _set_category_classifier_mode(db, test_org.id, "off")
        _add_active_category_model(db, test_org.id, _ALWAYS_PAIN_VOCAB_ARTIFACT)

        off_results = []
        for text, *_ in self.SAMPLES:
            feedback_item = _make_feedback(text, test_org.id)
            _apply_keyword_analysis(feedback_item, db)
            off_results.append(
                (feedback_item.pain_point_category, feedback_item.feature_request_category)
            )

        assert off_results == no_config_results


class TestCategoryAutoRouting:
    def test_auto_overrides_pain_point_category(self, db, test_org):
        from src.tasks.analysis import _apply_keyword_analysis

        _set_category_classifier_mode(db, test_org.id, "auto")
        _add_active_category_model(db, test_org.id, _ALWAYS_PAIN_VOCAB_ARTIFACT)

        # Positive text -> base keyword path sets feature_request_category,
        # leaves pain_point_category at None -> proves the category override
        # fires unconditionally (not gated on the base categorizer having run).
        feedback_item = _make_feedback("I love this product, it's amazing!", test_org.id)
        _apply_keyword_analysis(feedback_item, db)

        assert feedback_item.pain_point_category == "security_breach"

    def test_auto_overrides_feature_request_category(self, db, test_org):
        from src.tasks.analysis import _apply_keyword_analysis

        _set_category_classifier_mode(db, test_org.id, "auto")
        _add_active_category_model(db, test_org.id, _ALWAYS_FEATURE_VOCAB_ARTIFACT)

        feedback_item = _make_feedback("This is terrible, I want a refund.", test_org.id)
        _apply_keyword_analysis(feedback_item, db)

        assert feedback_item.feature_request_category == "core_functionality"

    def test_auto_neither_vocab_leaves_both_fields_untouched(self, db, test_org, caplog):
        from src.tasks.analysis import _apply_keyword_analysis

        _set_category_classifier_mode(db, test_org.id, "auto")
        _add_active_category_model(db, test_org.id, _ALWAYS_CUSTOM_LABEL_ARTIFACT)

        feedback_item = _make_feedback("This is terrible, I want a refund.", test_org.id)
        with caplog.at_level(logging.INFO, logger="rereflect.classifier.shadow"):
            _apply_keyword_analysis(feedback_item, db)

        # Base keyword categorizer's own pain_point_category is untouched by
        # the classifier (no write, ambiguous label) -- do NOT assert None,
        # assert it matches whatever the keyword categorizer itself set.
        shadow_records = [r for r in caplog.records if r.name == "rereflect.classifier.shadow"]
        category_records = [r for r in shadow_records if r.classifier_type == "category"]
        assert len(category_records) == 1
        assert category_records[0].target_field is None

    def test_auto_both_vocabs_ambiguous_leaves_fields_untouched(self, db, test_org, monkeypatch, caplog):
        """A label in BOTH built-in vocabs (contrived collision) must not be
        written to either field -- the classifier override is a no-op on
        top of whatever the BASE keyword categorizer already set (D7:
        the override runs unconditionally, but "no target_field" means "no
        setattr call", not "field forced back to None"). Verified via the
        shadow log's target_field=None rather than a before/after value
        comparison, since _make_feedback's initial None is not the relevant
        "incumbent" here -- the base keyword categorizer runs first and is
        the true incumbent (same technique as
        test_auto_neither_vocab_leaves_both_fields_untouched above)."""
        from analyzer.categorizer import FeatureRequestCategorizer
        from src.tasks.analysis import _apply_keyword_analysis

        monkeypatch.setitem(
            FeatureRequestCategorizer._BASE_CATEGORIES, "security_breach",
            {"keywords": ["x"], "priority": "high"},
        )
        _set_category_classifier_mode(db, test_org.id, "auto")
        _add_active_category_model(db, test_org.id, _ALWAYS_PAIN_VOCAB_ARTIFACT)

        feedback_item = _make_feedback("This is terrible, I want a refund.", test_org.id)
        with caplog.at_level(logging.INFO, logger="rereflect.classifier.shadow"):
            _apply_keyword_analysis(feedback_item, db)

        shadow_records = [r for r in caplog.records if r.name == "rereflect.classifier.shadow"]
        category_records = [r for r in shadow_records if r.classifier_type == "category"]
        assert len(category_records) == 1
        assert category_records[0].target_field is None
        # Never written to security_breach (the classifier's challenger
        # label) by the override -- whatever value is present came only
        # from the base keyword categorizer.
        assert feedback_item.pain_point_category != "security_breach"

    def test_category_and_sentiment_independent(self, db, test_org):
        """category=auto + sentiment=off (mixed independently on one
        OrgAIConfig row) -> only category mutates."""
        from src.tasks.analysis import _apply_keyword_analysis

        config = OrgAIConfig(
            organization_id=test_org.id,
            default_provider="openai",
            model_categorization="gpt-4o-mini",
            model_analysis="gpt-4o-mini",
            model_insights="gpt-4o-mini",
            classifier_mode="off",
            category_classifier_mode="auto",
        )
        db.add(config)
        db.commit()
        _add_active_category_model(db, test_org.id, _ALWAYS_PAIN_VOCAB_ARTIFACT)
        _add_active_model(db, test_org.id)  # sentiment model, irrelevant since sentiment=off

        feedback_item = _make_feedback("It's fine I guess.", test_org.id)
        _apply_keyword_analysis(feedback_item, db)

        assert feedback_item.pain_point_category == "security_breach"  # category auto fired
        assert feedback_item.sentiment_score == pytest.approx(0.2023, abs=1e-4)  # sentiment off, untouched
        assert feedback_item.sentiment_label == "positive"


class TestCategoryLLMBranch:
    def test_auto_overrides_category_on_llm_branch_too(self, db, ai_enabled_org, unanalyzed_feedback):
        from src.tasks.analysis import _analyze_feedback_item

        _set_category_classifier_mode(db, ai_enabled_org.id, "auto")
        _add_active_category_model(db, ai_enabled_org.id, _ALWAYS_PAIN_VOCAB_ARTIFACT)

        llm_result = {
            "sentiment_label": "positive", "sentiment_score": 0.6, "is_urgent": False,
            "confidence": 0.9,
            "pain_point_category": None,
            "feature_request_category": "ui_enhancement",  # LLM's own guess
        }

        with patch("src.tasks.analysis.categorize_feedback", return_value=llm_result):
            _analyze_feedback_item(unanalyzed_feedback, db)

        assert unanalyzed_feedback.llm_analyzed is True
        assert unanalyzed_feedback.pain_point_category == "security_breach"  # overridden post-LLM


# Deterministic urgency artifacts -- binary shape (coef=[[0.0]], very
# negative intercept) collapses P(classes[1])->0 regardless of input text
# (vocabulary token "neverseen" never matches), so argmax always picks
# classes[0]. Same proven pattern as _ALWAYS_NEGATIVE_ARTIFACT /
# _ALWAYS_PAIN_VOCAB_ARTIFACT above, just with urgency class names.
_ALWAYS_URGENT_ARTIFACT = {
    "vectorizer": {
        "vocabulary": {"neverseen": 0}, "idf": [1.0],
        "token_pattern": r"(?u)\b\w\w+\b", "lowercase": True,
        "sublinear_tf": True, "norm": "l2",
    },
    "logreg": {"coef": [[0.0]], "intercept": [-10.0]},
    "classes": ["urgent", "not_urgent"],
}
_ALWAYS_NOT_URGENT_ARTIFACT = {
    **_ALWAYS_URGENT_ARTIFACT,
    "classes": ["not_urgent", "urgent"],  # swap order -> classes[0] now "not_urgent"
}

# Real-VADER text that pushes both has_urgent_keyword ("broken", "crash") AND
# is_very_negative (compound < -0.5) True, so the base keyword heuristic sets
# is_urgent=True BEFORE the classifier override call-site runs -- the correct
# fixture for the no-de-escalation guard test.
_URGENT_HEURISTIC_TEXT = (
    "URGENT: This is broken, terrible, and a complete failure. "
    "Everything is crashing and awful, I hate it."
)


def _set_urgency_classifier_mode(db, org_id: int, mode: str) -> None:
    config = OrgAIConfig(
        organization_id=org_id,
        default_provider="openai",
        model_categorization="gpt-4o-mini",
        model_analysis="gpt-4o-mini",
        model_insights="gpt-4o-mini",
        urgency_classifier_mode=mode,
    )
    db.add(config)
    db.commit()


def _add_active_urgency_model(db, org_id, artifact) -> OrgClassifierModel:
    row = OrgClassifierModel(
        organization_id=org_id,
        classifier_type="urgency",
        model_json=artifact,
        label_count=10,
        is_active=True,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


class TestUrgencyOffByteStability:
    """Reuses TestOffByteStability's SAMPLES (all is_urgent=False by the
    heuristic): unset/off urgency mode is a pure no-op even with an active
    urgency model present -- is_urgent must be byte-identical between the
    two runs."""

    SAMPLES = TestOffByteStability.SAMPLES

    def test_no_config_row_vs_explicit_off_are_identical(self, db, test_org):
        from src.tasks.analysis import _apply_keyword_analysis

        no_config_results = []
        for text, *_ in self.SAMPLES:
            feedback_item = _make_feedback(text, test_org.id)
            _apply_keyword_analysis(feedback_item, db)
            no_config_results.append(feedback_item.is_urgent)

        _set_urgency_classifier_mode(db, test_org.id, "off")
        _add_active_urgency_model(db, test_org.id, _ALWAYS_URGENT_ARTIFACT)

        off_results = []
        for text, *_ in self.SAMPLES:
            feedback_item = _make_feedback(text, test_org.id)
            _apply_keyword_analysis(feedback_item, db)
            off_results.append(feedback_item.is_urgent)

        assert off_results == no_config_results
        # Byte-identical to today's pure heuristic -- none of these five
        # samples trip the urgent-keyword + very-negative heuristic.
        assert off_results == [expected for *_, expected in self.SAMPLES]


class TestUrgencyAutoEscalates:
    def test_auto_escalates_not_urgent_heuristic_to_urgent(self, db, test_org):
        from src.tasks.analysis import _apply_keyword_analysis

        _set_urgency_classifier_mode(db, test_org.id, "auto")
        _add_active_urgency_model(db, test_org.id, _ALWAYS_URGENT_ARTIFACT)

        # Heuristic-not-urgent text (see TestOffByteStability.SAMPLES row 3).
        feedback_item = _make_feedback("It's fine I guess.", test_org.id)
        _apply_keyword_analysis(feedback_item, db)

        assert feedback_item.is_urgent is True

    def test_auto_never_deescalates_heuristic_urgent(self, db, test_org):
        """MANDATORY add-only guard, ingest-level: heuristic already set
        is_urgent=True; the promoted model predicts 'not_urgent' -> is_urgent
        STAYS True (no de-escalation)."""
        from src.tasks.analysis import _apply_keyword_analysis

        _set_urgency_classifier_mode(db, test_org.id, "auto")
        _add_active_urgency_model(db, test_org.id, _ALWAYS_NOT_URGENT_ARTIFACT)

        feedback_item = _make_feedback(_URGENT_HEURISTIC_TEXT, test_org.id)
        _apply_keyword_analysis(feedback_item, db)

        assert feedback_item.is_urgent is True  # heuristic baseline, untouched


class TestUrgencyLLMBranch:
    def test_auto_escalates_on_llm_branch_too(self, db, ai_enabled_org, unanalyzed_feedback):
        from src.tasks.analysis import _analyze_feedback_item

        _set_urgency_classifier_mode(db, ai_enabled_org.id, "auto")
        _add_active_urgency_model(db, ai_enabled_org.id, _ALWAYS_URGENT_ARTIFACT)

        llm_result = {
            "sentiment_label": "positive", "sentiment_score": 0.6, "is_urgent": False,
            "confidence": 0.9,
        }

        with patch("src.tasks.analysis.categorize_feedback", return_value=llm_result):
            _analyze_feedback_item(unanalyzed_feedback, db)

        assert unanalyzed_feedback.llm_analyzed is True
        assert unanalyzed_feedback.is_urgent is True  # escalated post-LLM

    def test_auto_never_deescalates_on_llm_branch(self, db, ai_enabled_org, unanalyzed_feedback):
        from src.tasks.analysis import _analyze_feedback_item

        _set_urgency_classifier_mode(db, ai_enabled_org.id, "auto")
        _add_active_urgency_model(db, ai_enabled_org.id, _ALWAYS_NOT_URGENT_ARTIFACT)

        llm_result = {
            "sentiment_label": "negative", "sentiment_score": -0.9, "is_urgent": True,
            "confidence": 0.9,
        }

        with patch("src.tasks.analysis.categorize_feedback", return_value=llm_result):
            _analyze_feedback_item(unanalyzed_feedback, db)

        assert unanalyzed_feedback.llm_analyzed is True
        assert unanalyzed_feedback.is_urgent is True  # LLM's own True, never de-escalated
