"""
Phase 2 RED: Tests for _route_category_label + LoadedClassifier.predict_label_only
(worker-service mirror).

Covers the built-in-vocab routing table (predict-seam spec's
unambiguous-routing rule) and the score-bypassing category predict path,
independent of apply_classifier_override's higher-level branching (see
test_classifier_predict_helper.py::TestCategorySeamMatrix for that).

No sys.path insertion needed: conftest.py's eager `import src.celery_app`
already appends analysis-engine/src to sys.path as a side effect (see
src/celery_app.py) before any test module runs.
"""

from __future__ import annotations


class TestRouteCategoryLabel:
    def test_pain_only_label_routes_to_pain_point(self):
        from src.services.classifier_predict import _route_category_label
        assert _route_category_label("security_breach") == "pain_point_category"

    def test_feature_only_label_routes_to_feature_request(self):
        from src.services.classifier_predict import _route_category_label
        assert _route_category_label("core_functionality") == "feature_request_category"

    def test_custom_label_in_neither_vocab_returns_none(self):
        from src.services.classifier_predict import _route_category_label
        assert _route_category_label("totally_custom_thing") is None

    def test_label_in_both_vocabs_returns_none(self, monkeypatch):
        """Contrived collision — today's base vocabs are disjoint, but the
        routing rule must defend against a future overlap."""
        from analyzer.categorizer import PainPointCategorizer, FeatureRequestCategorizer
        from src.services.classifier_predict import _route_category_label

        monkeypatch.setitem(
            FeatureRequestCategorizer._BASE_CATEGORIES, "security_breach",
            {"keywords": ["x"], "priority": "high"},
        )
        assert _route_category_label("security_breach") is None


class TestPredictLabelOnly:
    _ARTIFACT = {
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

    def test_returns_label_only_no_score(self):
        from src.services.classifier_predict import LoadedClassifier

        loaded = LoadedClassifier(model_id=1, fit_at=None, artifact=self._ARTIFACT)
        result = loaded.predict_label_only("anything, vocabulary never matches")

        assert result == "security_breach"  # classes[0]; deterministic, see artifact comment
        assert isinstance(result, str)
