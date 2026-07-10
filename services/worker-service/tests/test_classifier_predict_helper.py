"""
Phase 3 RED: Tests for apply_classifier_override — off/shadow/auto branching
+ score mapping (worker-service).

Fake feedback object + injected fake LoadedClassifier (no dependency on
aspect B's real predict()). CLASSIFIER_SEAM_CASES is the drift-guard
behavior matrix, copied verbatim into the backend-api suite — see
test_classifier_predict_mirror.py for the equivalence check.
"""

from __future__ import annotations

import logging
from unittest.mock import patch

import pytest

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
