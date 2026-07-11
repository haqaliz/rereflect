"""
Phase 3 RED: Tests for apply_classifier_override — off/shadow/auto branching
+ score mapping (backend-api).

Fake feedback object + injected fake LoadedClassifier (no dependency on
aspect B's real predict()). CLASSIFIER_SEAM_CASES is the drift-guard
behavior matrix, copied verbatim into the worker-service suite — see
test_classifier_predict_mirror.py for the equivalence check.
"""

from __future__ import annotations

import logging
import os
import sys
from unittest.mock import patch

import pytest

# TestCategorySeamMatrix below exercises the real (unmocked)
# _route_category_label, which lazily imports analyzer.categorizer — see
# test_feedback_classifier_seam.py for why this sys.path insertion is needed
# locally (Docker-only layout otherwise).
_ANALYSIS_ENGINE_SRC = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../../analysis-engine/src")
)
if _ANALYSIS_ENGINE_SRC not in sys.path:
    sys.path.insert(0, _ANALYSIS_ENGINE_SRC)

from src.services.classifier_predict import apply_classifier_override
from src.services.classifier_resolver import ResolvedClassifier


# Drift contract: (mode, promoted?, allow_override) -> (mutated?, logged?).
# Copied verbatim into services/backend-api/tests/test_classifier_predict_helper.py
# and asserted identical by test_classifier_predict_mirror.py in both suites.
CLASSIFIER_SEAM_CASES = [
    {
        "name": "off",
        "classifier_mode": "off",
        "promoted": True,
        "allow_override": True,
        "expected_mutated": False,
        "expected_logged": False,
    },
    {
        "name": "shadow_promoted",
        "classifier_mode": "shadow",
        "promoted": True,
        "allow_override": True,
        "expected_mutated": False,
        "expected_logged": True,
    },
    {
        "name": "shadow_not_promoted",
        "classifier_mode": "shadow",
        "promoted": False,
        "allow_override": True,
        "expected_mutated": False,
        "expected_logged": False,
    },
    {
        "name": "auto_allow_promoted",
        "classifier_mode": "auto",
        "promoted": True,
        "allow_override": True,
        "expected_mutated": True,
        "expected_logged": True,
    },
    {
        "name": "auto_no_allow_promoted",
        "classifier_mode": "auto",
        "promoted": True,
        "allow_override": False,
        "expected_mutated": False,
        "expected_logged": True,
    },
    {
        "name": "auto_allow_not_promoted",
        "classifier_mode": "auto",
        "promoted": False,
        "allow_override": True,
        "expected_mutated": False,
        "expected_logged": False,
    },
]


class _FakeFeedback:
    def __init__(self):
        self.id = 42
        self.organization_id = 1
        self.text = "This is fine."
        self.sentiment_label = "positive"
        self.sentiment_score = 0.5


class _FakeLoadedClassifier:
    model_id = 99
    fit_at = None

    def predict(self, text):
        return "negative", -0.7


def _resolved_for_mode(mode):
    if mode == "off":
        return None
    return ResolvedClassifier(mode=mode)


def _run(feedback, *, classifier_mode, promoted, allow_override, db=None):
    loaded = _FakeLoadedClassifier() if promoted else None
    with patch(
        "src.services.classifier_resolver.resolve_classifier",
        return_value=_resolved_for_mode(classifier_mode),
    ), patch(
        "src.services.classifier_predict.load_active_classifier",
        return_value=loaded,
    ):
        apply_classifier_override(
            feedback,
            db if db is not None else object(),
            classifier_type="sentiment",
            allow_override=allow_override,
        )


class TestClassifierSeamMatrix:
    @pytest.mark.parametrize(
        "case", CLASSIFIER_SEAM_CASES, ids=[c["name"] for c in CLASSIFIER_SEAM_CASES]
    )
    def test_seam_case(self, case, caplog):
        feedback = _FakeFeedback()

        with caplog.at_level(logging.INFO, logger="rereflect.classifier.shadow"):
            _run(
                feedback,
                classifier_mode=case["classifier_mode"],
                promoted=case["promoted"],
                allow_override=case["allow_override"],
            )

        if case["expected_mutated"]:
            assert feedback.sentiment_label == "negative"
            assert feedback.sentiment_score == pytest.approx(-0.7)
            assert -1.0 <= feedback.sentiment_score <= 1.0
        else:
            assert feedback.sentiment_label == "positive"
            assert feedback.sentiment_score == pytest.approx(0.5)

        shadow_records = [r for r in caplog.records if r.name == "rereflect.classifier.shadow"]
        if case["expected_logged"]:
            assert len(shadow_records) == 1
        else:
            assert len(shadow_records) == 0


class TestApplyClassifierOverrideExplicit:
    def test_off_is_a_pure_noop(self, caplog):
        feedback = _FakeFeedback()
        with caplog.at_level(logging.INFO, logger="rereflect.classifier.shadow"):
            _run(feedback, classifier_mode="off", promoted=True, allow_override=True)

        assert feedback.sentiment_label == "positive"
        assert feedback.sentiment_score == 0.5
        assert not any(r.name == "rereflect.classifier.shadow" for r in caplog.records)

    def test_shadow_logs_but_never_mutates(self, caplog):
        feedback = _FakeFeedback()
        with caplog.at_level(logging.INFO, logger="rereflect.classifier.shadow"):
            _run(feedback, classifier_mode="shadow", promoted=True, allow_override=True)

        assert feedback.sentiment_label == "positive"
        assert feedback.sentiment_score == 0.5
        shadow_records = [r for r in caplog.records if r.name == "rereflect.classifier.shadow"]
        assert len(shadow_records) == 1

    def test_auto_with_allow_override_and_promoted_model_mutates(self):
        feedback = _FakeFeedback()
        _run(feedback, classifier_mode="auto", promoted=True, allow_override=True)

        assert feedback.sentiment_label == "negative"
        assert feedback.sentiment_score == pytest.approx(-0.7)
        assert -1.0 <= feedback.sentiment_score <= 1.0

    def test_auto_without_allow_override_behaves_like_shadow(self, caplog):
        """Backend semantics: auto + allow_override=False logs only."""
        feedback = _FakeFeedback()
        with caplog.at_level(logging.INFO, logger="rereflect.classifier.shadow"):
            _run(feedback, classifier_mode="auto", promoted=True, allow_override=False)

        assert feedback.sentiment_label == "positive"
        assert feedback.sentiment_score == 0.5
        shadow_records = [r for r in caplog.records if r.name == "rereflect.classifier.shadow"]
        assert len(shadow_records) == 1

    def test_auto_no_promoted_model_retains_incumbent(self):
        feedback = _FakeFeedback()
        _run(feedback, classifier_mode="auto", promoted=False, allow_override=True)

        assert feedback.sentiment_label == "positive"
        assert feedback.sentiment_score == 0.5

    def test_auto_corrupt_artifact_retains_incumbent(self):
        """Corrupt artifact surfaces identically to 'not promoted' — the
        loader already collapses corrupt-json into None (see
        test_classifier_predict_loader.py::TestCorruptArtifactDefense)."""
        feedback = _FakeFeedback()
        with patch(
            "src.services.classifier_resolver.resolve_classifier",
            return_value=ResolvedClassifier(mode="auto"),
        ), patch(
            "src.services.classifier_predict.load_active_classifier",
            return_value=None,
        ):
            apply_classifier_override(
                feedback, object(), classifier_type="sentiment", allow_override=True
            )

        assert feedback.sentiment_label == "positive"
        assert feedback.sentiment_score == 0.5

    def test_swallows_internal_exception_never_raises(self):
        feedback = _FakeFeedback()
        with patch(
            "src.services.classifier_resolver.resolve_classifier",
            side_effect=RuntimeError("boom"),
        ):
            apply_classifier_override(
                feedback, object(), classifier_type="sentiment", allow_override=True
            )

        assert feedback.sentiment_label == "positive"
        assert feedback.sentiment_score == 0.5

    def test_swallows_loader_exception_never_raises(self):
        feedback = _FakeFeedback()
        with patch(
            "src.services.classifier_resolver.resolve_classifier",
            return_value=ResolvedClassifier(mode="auto"),
        ), patch(
            "src.services.classifier_predict.load_active_classifier",
            side_effect=RuntimeError("boom"),
        ):
            apply_classifier_override(
                feedback, object(), classifier_type="sentiment", allow_override=True
            )

        assert feedback.sentiment_label == "positive"
        assert feedback.sentiment_score == 0.5


# Category-branch cases. Fake feedback carries pain_point_category /
# feature_request_category instead of sentiment_label/score. "label" drives
# _route_category_label's real (unmocked) vocab lookup — use real built-in
# category names so this exercises the actual routing table, not a mock.
CATEGORY_SEAM_CASES = [
    {
        "name": "category_off",
        "classifier_mode": "off",
        "promoted": True,
        "allow_override": True,
        "label": "security_breach",
        "expected_field": None,
        "expected_logged": False,
    },
    {
        "name": "category_shadow_promoted",
        "classifier_mode": "shadow",
        "promoted": True,
        "allow_override": True,
        "label": "security_breach",
        "expected_field": None,
        "expected_logged": True,
    },
    {
        "name": "category_auto_pain_only",
        "classifier_mode": "auto",
        "promoted": True,
        "allow_override": True,
        "label": "security_breach",
        "expected_field": "pain_point_category",
        "expected_logged": True,
    },
    {
        "name": "category_auto_feature_only",
        "classifier_mode": "auto",
        "promoted": True,
        "allow_override": True,
        "label": "core_functionality",
        "expected_field": "feature_request_category",
        "expected_logged": True,
    },
    {
        "name": "category_auto_neither_vocab",
        "classifier_mode": "auto",
        "promoted": True,
        "allow_override": True,
        "label": "totally_custom_thing",
        "expected_field": None,
        "expected_logged": True,
    },
    {
        "name": "category_auto_no_allow_backend_ownership",
        "classifier_mode": "auto",
        "promoted": True,
        "allow_override": False,
        "label": "security_breach",
        "expected_field": None,
        "expected_logged": True,
    },
    {
        "name": "category_auto_not_promoted",
        "classifier_mode": "auto",
        "promoted": False,
        "allow_override": True,
        "label": "security_breach",
        "expected_field": None,
        "expected_logged": False,
    },
]


class _FakeCategoryFeedback:
    def __init__(self):
        self.id = 43
        self.organization_id = 1
        self.text = "This is fine."
        self.pain_point_category = "existing_pain"
        self.feature_request_category = "existing_feature"


class _FakeCategoryLoadedClassifier:
    model_id = 100
    fit_at = None

    def __init__(self, label):
        self._label = label

    def predict_label_only(self, text):
        return self._label


class TestCategorySeamMatrix:
    @pytest.mark.parametrize(
        "case", CATEGORY_SEAM_CASES, ids=[c["name"] for c in CATEGORY_SEAM_CASES]
    )
    def test_category_case(self, case, caplog):
        feedback = _FakeCategoryFeedback()
        loaded = _FakeCategoryLoadedClassifier(case["label"]) if case["promoted"] else None

        with patch(
            "src.services.classifier_resolver.resolve_classifier",
            return_value=_resolved_for_mode(case["classifier_mode"]),
        ), patch(
            "src.services.classifier_predict.load_active_classifier",
            return_value=loaded,
        ), caplog.at_level(logging.INFO, logger="rereflect.classifier.shadow"):
            apply_classifier_override(
                feedback, object(),
                classifier_type="category",
                allow_override=case["allow_override"],
            )

        if case["expected_field"] == "pain_point_category":
            assert feedback.pain_point_category == case["label"]
            assert feedback.feature_request_category == "existing_feature"
        elif case["expected_field"] == "feature_request_category":
            assert feedback.feature_request_category == case["label"]
            assert feedback.pain_point_category == "existing_pain"
        else:
            assert feedback.pain_point_category == "existing_pain"
            assert feedback.feature_request_category == "existing_feature"

        shadow_records = [r for r in caplog.records if r.name == "rereflect.classifier.shadow"]
        assert len(shadow_records) == (1 if case["expected_logged"] else 0)
