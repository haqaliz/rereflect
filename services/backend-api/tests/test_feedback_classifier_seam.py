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
