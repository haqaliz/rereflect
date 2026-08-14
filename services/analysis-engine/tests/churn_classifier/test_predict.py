"""Tests for churn_classifier.predict (M5.3 churn-classifier-core).

predict() is pure stdlib (math.sigmoid of the linear score) — no sklearn/numpy
at runtime, even though the sklearn-parity test needs sklearn to train a
reference artifact to compare against (corrections_classifier/test_predict.py
convention, tolerance tightened to 1e-9 per the aspect plan).
"""
from __future__ import annotations

import math
import sys

import pytest

from src.analyzer.churn_classifier.predict import predict


# ---------------------------------------------------------------------------
# sklearn <-> pure-predict parity (load-bearing)
# ---------------------------------------------------------------------------

def test_predict_matches_sklearn_on_training_rows():
    sklearn = pytest.importorskip("sklearn")

    from sklearn.linear_model import LogisticRegression

    from src.analyzer.churn_classifier.features import build_feature_vector
    from src.analyzer.churn_classifier.trainer import train_churn_classifier

    features = []
    labels = []
    for i in range(40):
        churned = 1 if i % 2 == 0 else 0
        features.append(
            build_feature_vector(
                {
                    "churn_risk_component": 85 - churned * 40,
                    "usage_score": 70 - churned * 35,
                    "active_days_30d": 22 - churned * 15,
                    "login_count_30d": 32 - churned * 20,
                    "count_30d": 1 + (i % 5),
                    "avg_sentiment": -0.6 if churned else 0.5,
                    "segment": "dormant" if churned else "power_user",
                }
            )
        )
        labels.append(churned)

    artifact = train_churn_classifier({"features": features, "labels": labels}, random_state=0)

    clf = LogisticRegression(max_iter=1000, random_state=0)
    clf.fit(features, labels)
    sk_probas = clf.predict_proba(features)
    # binary fit: column 1 is P(class 1) = P(churned)
    assert list(clf.classes_) == [0, 1]

    for i, feature_vector in enumerate(features):
        assert predict(artifact, feature_vector) == pytest.approx(sk_probas[i][1], abs=1e-9)


# ---------------------------------------------------------------------------
# Pure-Python guarantees (no numpy needed at predict time)
# ---------------------------------------------------------------------------

_FIXTURE_ARTIFACT = {
    "model_type": "churn_logreg",
    "version": 1,
    "features": ["f0", "f1"],
    "coef": [1.0, -1.0],
    "intercept": 0.0,
    "classes": [0, 1],
}


def test_predict_pure_python_no_numpy():
    sys.modules["numpy"] = None
    try:
        p = predict(_FIXTURE_ARTIFACT, [0.0, 0.0])
        assert p == pytest.approx(0.5)
    finally:
        del sys.modules["numpy"]


def test_hand_computed_sigmoid():
    # linear = 0 + 1*3 + (-1)*1 = 2 -> sigmoid(2)
    expected = 1.0 / (1.0 + math.exp(-2.0))
    assert predict(_FIXTURE_ARTIFACT, [3.0, 1.0]) == pytest.approx(expected)
    assert predict(_FIXTURE_ARTIFACT, [3.0, 1.0]) == pytest.approx(0.8807970779778823)


def test_zero_linear_score_is_0_5():
    assert predict(_FIXTURE_ARTIFACT, [0.0, 0.0]) == pytest.approx(0.5)


def test_extreme_scores_saturate():
    p_high = predict({"model_type": "churn_logreg", "version": 1, "features": ["f0"],
                      "coef": [1.0], "intercept": 0.0, "classes": [0, 1]}, [30.0])
    assert p_high > 0.999
    p_low = predict({"model_type": "churn_logreg", "version": 1, "features": ["f0"],
                     "coef": [1.0], "intercept": 0.0, "classes": [0, 1]}, [-30.0])
    assert p_low < 0.001


def test_monotone_in_coefficient_direction():
    """Increasing a feature whose coefficient is positive raises the predicted
    probability; for a negative coefficient it lowers it (plan: monotone in each
    coefficient's direction)."""
    p_1 = predict(_FIXTURE_ARTIFACT, [1.0, 0.0])
    p_2 = predict(_FIXTURE_ARTIFACT, [2.0, 0.0])
    assert p_2 > p_1  # coef +1 on f0
    p_a = predict(_FIXTURE_ARTIFACT, [0.0, 1.0])
    p_b = predict(_FIXTURE_ARTIFACT, [0.0, 2.0])
    assert p_b < p_a  # coef -1 on f1


def test_output_always_in_unit_interval():
    for x in (-10, -1, 0, 0.5, 1, 10):
        assert 0.0 <= predict(_FIXTURE_ARTIFACT, [x, x]) <= 1.0


def test_degenerate_single_class_artifact_predicts_majority_class():
    pos = {"model_type": "churn_logreg", "version": 1, "features": ["f0", "f1"],
           "coef": [0.0, 0.0], "intercept": 20.0, "classes": [0, 1]}
    neg = {"model_type": "churn_logreg", "version": 1, "features": ["f0", "f1"],
           "coef": [0.0, 0.0], "intercept": -20.0, "classes": [0, 1]}
    assert predict(pos, [5.0, 5.0]) > 0.999
    assert predict(neg, [5.0, 5.0]) < 0.001


def test_feature_vector_length_mismatch_raises_value_error():
    with pytest.raises(ValueError):
        predict(_FIXTURE_ARTIFACT, [1.0])
