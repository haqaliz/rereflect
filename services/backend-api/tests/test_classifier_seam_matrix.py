"""
Phase 6: `test_classifier_seam_matrix` — CLASSIFIER_SEAM_CASES driven
end-to-end (backend-api), through REAL resolve_classifier +
load_active_classifier + aspect B's real predict()/score_from_proba(), no
mocks. Complements test_classifier_predict_helper.py's mocked-loader matrix
by proving the same behavior matrix holds with the real DB + real predictor.

Cases copied verbatim from test_classifier_predict_helper.py's
CLASSIFIER_SEAM_CASES (see that file's module docstring for the drift
contract with the worker-service suite).
"""

from __future__ import annotations

import logging

import pytest

from src.models.org_ai_config import OrgAIConfig
from src.models.org_classifier import OrgClassifierModel
from src.services.classifier_predict import apply_classifier_override

from .test_classifier_predict_helper import CLASSIFIER_SEAM_CASES, _FakeFeedback


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
def _reset_classifier_cache():
    from src.services.classifier_predict import _classifier_cache
    _classifier_cache.clear()
    yield
    _classifier_cache.clear()


def _setup(db, org_id, *, classifier_mode, promoted):
    if classifier_mode != "off":
        config = OrgAIConfig(
            organization_id=org_id,
            default_provider="openai",
            model_categorization="gpt-4o-mini",
            model_analysis="gpt-4o-mini",
            model_insights="gpt-4o-mini",
            classifier_mode=classifier_mode,
        )
        db.add(config)
        db.commit()
    if promoted:
        row = OrgClassifierModel(
            organization_id=org_id,
            classifier_type="sentiment",
            model_json=_ALWAYS_NEGATIVE_ARTIFACT,
            label_count=10,
            is_active=True,
        )
        db.add(row)
        db.commit()


class TestClassifierSeamMatrixEndToEnd:
    @pytest.mark.parametrize(
        "case", CLASSIFIER_SEAM_CASES, ids=[c["name"] for c in CLASSIFIER_SEAM_CASES]
    )
    def test_seam_case_real_stack(self, case, db, test_organization, caplog):
        _setup(
            db, test_organization.id,
            classifier_mode=case["classifier_mode"],
            promoted=case["promoted"],
        )

        feedback = _FakeFeedback()
        feedback.organization_id = test_organization.id

        with caplog.at_level(logging.INFO, logger="rereflect.classifier.shadow"):
            apply_classifier_override(
                feedback, db,
                classifier_type="sentiment",
                allow_override=case["allow_override"],
            )

        if case["expected_mutated"]:
            assert feedback.sentiment_label == "negative"
            assert -1.0 <= feedback.sentiment_score <= 1.0
        else:
            assert feedback.sentiment_label == "positive"
            assert feedback.sentiment_score == pytest.approx(0.5)

        shadow_records = [r for r in caplog.records if r.name == "rereflect.classifier.shadow"]
        if case["expected_logged"]:
            assert len(shadow_records) == 1
        else:
            assert len(shadow_records) == 0
