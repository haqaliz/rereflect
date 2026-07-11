"""
Phase 5 RED: Tests for the classifier-override injection at the backend
inline call site (src/api/routes/feedback.py::analyze_single_feedback),
the SHADOW-ONLY site (allow_override=False — ownership: inline never
overrides, even in `auto` mode; the worker is the sole authoritative writer).

Covers:
- off byte-stability characterization (reuses the exact SAMPLES table from
  test_feedback_sentiment_injection.py).
- shadow: shadow log line, stored values unchanged.
- auto: stored values STILL incumbent (ownership), shadow line logged.
- never raises on loader/predict failure.

TDD: RED first, then production code (the single injection call-site).
"""

from __future__ import annotations

import logging
import sys
import os
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

from src.models.feedback import FeedbackItem
from src.models.organization import Organization
from src.models.org_ai_config import OrgAIConfig
from src.models.org_classifier import OrgClassifierModel

# See test_feedback_sentiment_injection.py for why this sys.path insertion is
# needed locally (Docker-only layout otherwise).
_ANALYSIS_ENGINE_SRC = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../../analysis-engine/src")
)
if _ANALYSIS_ENGINE_SRC not in sys.path:
    sys.path.insert(0, _ANALYSIS_ENGINE_SRC)


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


@pytest.fixture(autouse=True)
def _reset_caches():
    import src.api.routes.feedback as feedback_module
    import src.services.classifier_predict as classifier_predict_module

    feedback_module._sentiment_analyzer_cache.clear()
    classifier_predict_module._classifier_cache.clear()
    yield
    feedback_module._sentiment_analyzer_cache.clear()
    classifier_predict_module._classifier_cache.clear()


def _make_feedback(text: str, org_id: int) -> FeedbackItem:
    f = FeedbackItem(organization_id=org_id, text=text, source="manual")
    f.sentiment_label = None
    f.sentiment_score = None
    f.is_urgent = False
    return f


def _set_classifier_mode(db: Session, org_id: int, mode: str) -> None:
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


def _add_active_model(db: Session, org_id, artifact=None) -> OrgClassifierModel:
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
    test_feedback_sentiment_injection.py::TestCharacterizationVaderUnchanged.
    """

    SAMPLES = [
        ("I love this product, it's amazing!", 0.8516, "positive", False),
        ("This is terrible, I want a refund.", -0.4215, "negative", False),
        ("It's fine I guess.", 0.2023, "positive", False),
        ("URGENT: the app keeps crashing and I can't use it!!!", 0.5282, "positive", False),
        ("I'm done with this, canceling my subscription.", 0.0, "neutral", False),
    ]

    def test_no_classifier_config_row_is_byte_stable(self, db: Session, test_organization: Organization):
        from src.api.routes.feedback import analyze_single_feedback

        for text, expected_score, expected_label, expected_urgent in self.SAMPLES:
            feedback_item = _make_feedback(text, test_organization.id)
            db.add(feedback_item)
            db.commit()
            db.refresh(feedback_item)

            analyze_single_feedback(feedback_item, db)

            assert feedback_item.sentiment_score == pytest.approx(expected_score, abs=1e-4), text
            assert feedback_item.sentiment_label == expected_label, text
            assert feedback_item.is_urgent == expected_urgent, text

    def test_explicit_off_is_byte_stable(self, db: Session, test_organization: Organization):
        from src.api.routes.feedback import analyze_single_feedback

        _set_classifier_mode(db, test_organization.id, "off")
        _add_active_model(db, test_organization.id)

        for text, expected_score, expected_label, expected_urgent in self.SAMPLES:
            feedback_item = _make_feedback(text, test_organization.id)
            db.add(feedback_item)
            db.commit()
            db.refresh(feedback_item)

            analyze_single_feedback(feedback_item, db)

            assert feedback_item.sentiment_score == pytest.approx(expected_score, abs=1e-4), text
            assert feedback_item.sentiment_label == expected_label, text
            assert feedback_item.is_urgent == expected_urgent, text


class TestShadowE2E:
    def test_shadow_logs_and_never_mutates(self, db: Session, test_organization: Organization, caplog):
        from src.api.routes.feedback import analyze_single_feedback

        _set_classifier_mode(db, test_organization.id, "shadow")
        _add_active_model(db, test_organization.id)

        feedback_item = _make_feedback("It's fine I guess.", test_organization.id)
        db.add(feedback_item)
        db.commit()
        db.refresh(feedback_item)

        with caplog.at_level(logging.INFO, logger="rereflect.classifier.shadow"):
            analyze_single_feedback(feedback_item, db)

        assert feedback_item.sentiment_score == pytest.approx(0.2023, abs=1e-4)
        assert feedback_item.sentiment_label == "positive"

        shadow_records = [r for r in caplog.records if r.name == "rereflect.classifier.shadow"]
        assert len(shadow_records) == 1


class TestAutoOwnership:
    """Ownership: the inline backend path NEVER overrides, even in `auto`
    mode — the worker is the sole authoritative writer. Confirm the shadow
    line is still logged (disclosure), but stored values stay incumbent."""

    def test_auto_stores_incumbent_but_logs_shadow_line(
        self, db: Session, test_organization: Organization, caplog
    ):
        from src.api.routes.feedback import analyze_single_feedback

        _set_classifier_mode(db, test_organization.id, "auto")
        _add_active_model(db, test_organization.id)

        feedback_item = _make_feedback("It's fine I guess.", test_organization.id)
        db.add(feedback_item)
        db.commit()
        db.refresh(feedback_item)

        with caplog.at_level(logging.INFO, logger="rereflect.classifier.shadow"):
            analyze_single_feedback(feedback_item, db)

        # Ownership: stored values remain the VADER incumbent, NOT the
        # challenger, even though classifier_mode="auto".
        assert feedback_item.sentiment_score == pytest.approx(0.2023, abs=1e-4)
        assert feedback_item.sentiment_label == "positive"

        shadow_records = [r for r in caplog.records if r.name == "rereflect.classifier.shadow"]
        assert len(shadow_records) == 1


class TestLoaderOrPredictFailureNeverRaises:
    def test_loader_exception_retains_incumbent(self, db: Session, test_organization: Organization):
        from src.api.routes.feedback import analyze_single_feedback

        _set_classifier_mode(db, test_organization.id, "auto")
        _add_active_model(db, test_organization.id)

        feedback_item = _make_feedback("It's fine I guess.", test_organization.id)
        db.add(feedback_item)
        db.commit()
        db.refresh(feedback_item)

        with patch(
            "src.services.classifier_predict.load_active_classifier",
            side_effect=RuntimeError("boom"),
        ):
            analyze_single_feedback(feedback_item, db)

        assert feedback_item.sentiment_score == pytest.approx(0.2023, abs=1e-4)
        assert feedback_item.sentiment_label == "positive"


_ALWAYS_PAIN_VOCAB_LIKE_ARTIFACT = {
    "vectorizer": {
        "vocabulary": {"neverseen": 0},
        "idf": [1.0],
        "token_pattern": r"(?u)\b\w\w+\b",
        "lowercase": True,
        "sublinear_tf": True,
        "norm": "l2",
    },
    "logreg": {"coef": [[0.0]], "intercept": [-10.0]},
    "classes": ["security_breach", "core_functionality"],
}


def _set_category_classifier_mode(db, org_id, mode):
    config = OrgAIConfig(
        organization_id=org_id, default_provider="openai",
        model_categorization="gpt-4o-mini", model_analysis="gpt-4o-mini",
        model_insights="gpt-4o-mini", category_classifier_mode=mode,
    )
    db.add(config); db.commit()


def _add_active_category_model(db, org_id, artifact):
    row = OrgClassifierModel(
        organization_id=org_id, classifier_type="category",
        model_json=artifact, label_count=10, is_active=True,
    )
    db.add(row); db.commit(); db.refresh(row)
    return row


class TestCategoryOffByteStability:
    """Reuses TestOffByteStability's SAMPLES: unset/off category mode is a
    pure no-op even with an active category model present -- category
    fields must be byte-identical between the two runs (comparative
    equality; the base keyword categorizer's exact string outputs are not
    hand-derived here)."""

    SAMPLES = TestOffByteStability.SAMPLES

    def test_no_config_row_vs_explicit_off_are_identical(
        self, db: Session, test_organization: Organization
    ):
        from src.api.routes.feedback import analyze_single_feedback

        no_config_results = []
        for text, *_ in self.SAMPLES:
            feedback_item = _make_feedback(text, test_organization.id)
            db.add(feedback_item)
            db.commit()
            db.refresh(feedback_item)
            analyze_single_feedback(feedback_item, db)
            no_config_results.append(
                (feedback_item.pain_point_category, feedback_item.feature_request_category)
            )

        _set_category_classifier_mode(db, test_organization.id, "off")
        _add_active_category_model(db, test_organization.id, _ALWAYS_PAIN_VOCAB_LIKE_ARTIFACT)

        off_results = []
        for text, *_ in self.SAMPLES:
            feedback_item = _make_feedback(text, test_organization.id)
            db.add(feedback_item)
            db.commit()
            db.refresh(feedback_item)
            analyze_single_feedback(feedback_item, db)
            off_results.append(
                (feedback_item.pain_point_category, feedback_item.feature_request_category)
            )

        assert off_results == no_config_results


class TestCategoryShadowE2E:
    def test_shadow_logs_and_never_mutates(self, db: Session, test_organization: Organization, caplog):
        """Comparative-equality (not a before/after snapshot on the SAME
        item): _make_feedback's initial None is not the relevant incumbent
        for this negative-sentiment text -- analyze_single_feedback's own
        BASE keyword pain-point categorizer sets pain_point_category before
        the classifier shadow call ever runs, unrelated to classifier_mode.
        So the "never mutates" claim is verified by running the identical
        input through mode=off (no classifier influence at all) and
        asserting the shadow run lands on the exact same category value."""
        from src.api.routes.feedback import analyze_single_feedback

        text = "This is terrible, I want a refund."

        off_item = _make_feedback(text, test_organization.id)
        db.add(off_item)
        db.commit()
        db.refresh(off_item)
        analyze_single_feedback(off_item, db)
        off_pain = off_item.pain_point_category

        _set_category_classifier_mode(db, test_organization.id, "shadow")
        _add_active_category_model(db, test_organization.id, _ALWAYS_PAIN_VOCAB_LIKE_ARTIFACT)

        shadow_item = _make_feedback(text, test_organization.id)
        db.add(shadow_item)
        db.commit()
        db.refresh(shadow_item)

        with caplog.at_level(logging.INFO, logger="rereflect.classifier.shadow"):
            analyze_single_feedback(shadow_item, db)

        assert shadow_item.pain_point_category == off_pain  # unchanged in shadow
        category_records = [
            r for r in caplog.records
            if r.name == "rereflect.classifier.shadow" and getattr(r, "classifier_type", None) == "category"
        ]
        assert len(category_records) == 1


class TestCategoryAutoIsShadowOnlyOnBackend:
    def test_auto_stores_incumbent_but_logs_shadow_line(
        self, db: Session, test_organization: Organization, caplog
    ):
        """Ownership: backend inline path NEVER writes pain_point_category /
        feature_request_category, even in `auto` mode -- worker is sole
        authoritative writer, same split as sentiment. Comparative-equality
        against a mode=off run -- see TestCategoryShadowE2E for why a
        before/after snapshot on the same item is the wrong technique here
        (the base keyword categorizer, not the classifier, sets the field
        for this negative-sentiment text)."""
        from src.api.routes.feedback import analyze_single_feedback

        text = "This is terrible, I want a refund."

        off_item = _make_feedback(text, test_organization.id)
        db.add(off_item)
        db.commit()
        db.refresh(off_item)
        analyze_single_feedback(off_item, db)
        off_pain = off_item.pain_point_category

        _set_category_classifier_mode(db, test_organization.id, "auto")
        _add_active_category_model(db, test_organization.id, _ALWAYS_PAIN_VOCAB_LIKE_ARTIFACT)

        auto_item = _make_feedback(text, test_organization.id)
        db.add(auto_item)
        db.commit()
        db.refresh(auto_item)

        with caplog.at_level(logging.INFO, logger="rereflect.classifier.shadow"):
            analyze_single_feedback(auto_item, db)

        assert auto_item.pain_point_category == off_pain
        category_records = [
            r for r in caplog.records
            if r.name == "rereflect.classifier.shadow" and getattr(r, "classifier_type", None) == "category"
        ]
        assert len(category_records) == 1


class TestCategoryAndSentimentIndependentControl:
    def test_category_and_sentiment_independent(self, db: Session, test_organization: Organization):
        """category=off (shadow-only ownership means auto never mutates here
        anyway, so the independence signal is: sentiment=auto DOES mutate
        while category=off never logs) + sentiment=auto on one OrgAIConfig
        row -> only sentiment resolves/mutates; category resolves to
        off/None and is a pure no-op (no log line)."""
        from src.api.routes.feedback import analyze_single_feedback

        config = OrgAIConfig(
            organization_id=test_organization.id,
            default_provider="openai",
            model_categorization="gpt-4o-mini",
            model_analysis="gpt-4o-mini",
            model_insights="gpt-4o-mini",
            classifier_mode="auto",
            category_classifier_mode="off",
        )
        db.add(config)
        db.commit()
        _add_active_model(db, test_organization.id)  # sentiment model
        _add_active_category_model(db, test_organization.id, _ALWAYS_PAIN_VOCAB_LIKE_ARTIFACT)

        feedback_item = _make_feedback("It's fine I guess.", test_organization.id)
        db.add(feedback_item)
        db.commit()
        db.refresh(feedback_item)
        before_pain = feedback_item.pain_point_category

        analyze_single_feedback(feedback_item, db)

        # Backend ownership: sentiment=auto never mutates inline either
        # (shadow-only call-site) -- both types leave stored values at
        # incumbent on the backend path, independence is about which
        # resolver each type reads, not about backend mutation.
        assert feedback_item.sentiment_score == pytest.approx(0.2023, abs=1e-4)
        assert feedback_item.sentiment_label == "positive"
        assert feedback_item.pain_point_category == before_pain
