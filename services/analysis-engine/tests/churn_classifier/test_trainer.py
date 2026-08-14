"""Tests for churn_classifier.trainer (M5.3 churn-classifier-core).

Guards the whole file with pytest.importorskip("sklearn") so wheels-less venvs
skip training tests entirely (corrections_classifier/test_trainer.py
convention). The artifact contract under test: JSON-only, no pickle, lazy
sklearn import (module-level importability is pinned by test_lazy_import.py),
deterministic under a fixed seed, and single-class-safe (a degenerate dataset
must produce a predictable majority-class artifact, never raise).
"""
from __future__ import annotations

import json

import pytest

sklearn = pytest.importorskip("sklearn")

from src.analyzer.churn_classifier.features import FEATURE_NAMES, build_feature_vector  # noqa: E402
from src.analyzer.churn_classifier.labels import RANDOM_STATE  # noqa: E402
from src.analyzer.churn_classifier.trainer import train_churn_classifier  # noqa: E402


def _row_vec(i: int, churned: int) -> list[float]:
    """Deterministic feature vector with a learnable churn signal."""
    return build_feature_vector(
        {
            "churn_risk_component": 80 - churned * 20,
            "usage_score": 60 - churned * 25,
            "active_days_30d": 20 - churned * 10,
            "login_count_30d": 30 - churned * 15,
            "count_30d": 2 + i % 3,
            "avg_sentiment": -0.5 if churned else 0.4,
            "segment": "at_risk" if churned else "power_user",
        }
    )


def _dataset(n: int = 24) -> dict:
    features = []
    labels = []
    for i in range(n):
        churned = 1 if i < n // 2 else 0
        features.append(_row_vec(i, churned))
        labels.append(churned)
    return {"features": features, "labels": labels}


def _assert_json_leaf_types(obj) -> None:
    if isinstance(obj, dict):
        for v in obj.values():
            _assert_json_leaf_types(v)
    elif isinstance(obj, list):
        for v in obj:
            _assert_json_leaf_types(v)
    else:
        assert isinstance(obj, (str, int, float, bool)) or obj is None, (
            f"non-JSON-native leaf type: {type(obj)!r} ({obj!r})"
        )


def test_returns_json_serializable_artifact():
    artifact = train_churn_classifier(_dataset())
    json.dumps(artifact)  # must not raise


def test_artifact_has_no_pickle_bytes():
    artifact = train_churn_classifier(_dataset())
    serialized = json.dumps(artifact).encode()
    assert b"\x80" not in serialized
    _assert_json_leaf_types(artifact)


def test_artifact_carries_full_schema():
    artifact = train_churn_classifier(_dataset())
    assert artifact["model_type"] == "churn_logreg"
    assert artifact["version"] == 1
    assert artifact["features"] == FEATURE_NAMES
    assert artifact["classes"] == [0, 1]
    assert isinstance(artifact["intercept"], float)
    assert isinstance(artifact["coef"], list)


def test_artifact_coef_shape_is_binary_single_row():
    artifact = train_churn_classifier(_dataset())
    assert len(artifact["coef"]) == len(FEATURE_NAMES)
    # sklearn's binary LogisticRegression produces a single coef row; the
    # pure-stdlib predict relies on that shape (classes[1] is the positive class).
    assert len(artifact["coef"]) == 28


def test_determinism_under_fixed_seed():
    a1 = train_churn_classifier(_dataset())
    a2 = train_churn_classifier(_dataset())
    assert json.dumps(a1, sort_keys=True) == json.dumps(a2, sort_keys=True)


def test_determinism_respects_random_state():
    """Same seed -> identical artifact. (Different seeds may also agree: the
    L2-regularized logistic loss is strictly convex, so lbfgs converges to the
    same optimum from any initialization — seed differences are not required
    to change the artifact.)"""
    a1 = train_churn_classifier(_dataset(), random_state=7)
    a2 = train_churn_classifier(_dataset(), random_state=7)
    a3 = train_churn_classifier(_dataset(), random_state=8)
    assert json.dumps(a1, sort_keys=True) == json.dumps(a2, sort_keys=True)
    assert json.dumps(a1, sort_keys=True) == json.dumps(a3, sort_keys=True)


def test_default_random_state_matches_labels_constant():
    assert train_churn_classifier(_dataset()) == train_churn_classifier(_dataset(), random_state=RANDOM_STATE)


def test_artifact_trains_on_missing_feature_rows():
    """All-missing-feature rows (R3) are legitimate training material — the
    documented-default vector must train without raising."""
    dataset = {
        "features": [build_feature_vector({}) for _ in range(24)],
        "labels": [1, 0] * 12,
    }
    artifact = train_churn_classifier(dataset)
    assert artifact["model_type"] == "churn_logreg"


def test_single_class_dataset_does_not_raise():
    dataset = {"features": [_row_vec(i, 1) for i in range(24)], "labels": [1] * 24}
    artifact = train_churn_classifier(dataset)
    assert artifact["classes"] == [0, 1]
    # degenerate artifact: zero coefficients, extreme signed intercept pointing
    # at the majority class — sigmoid(intercept) ~ 1 for class 1.
    assert all(c == 0.0 for c in artifact["coef"])
    assert artifact["intercept"] > 0


def test_single_class_all_zero_dataset_points_at_class_zero():
    dataset = {"features": [_row_vec(i, 0) for i in range(24)], "labels": [0] * 24}
    artifact = train_churn_classifier(dataset)
    assert all(c == 0.0 for c in artifact["coef"])
    assert artifact["intercept"] < 0


def test_single_class_artifact_is_deterministic():
    dataset = {"features": [_row_vec(i, 1) for i in range(24)], "labels": [1] * 24}
    a1 = train_churn_classifier(dataset)
    a2 = train_churn_classifier(dataset)
    assert json.dumps(a1, sort_keys=True) == json.dumps(a2, sort_keys=True)


def test_empty_dataset_does_not_raise():
    artifact = train_churn_classifier({"features": [], "labels": []})
    assert artifact["model_type"] == "churn_logreg"
    assert artifact["intercept"] == 0.0
    assert all(c == 0.0 for c in artifact["coef"])
