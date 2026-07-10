"""Tests for corrections_classifier.predict — Phase 3 (M5.2 training-and-eval-core).

predict() and score_from_proba() are pure stdlib (re, math) — no sklearn/numpy needed
at runtime, even though the sklearn-parity test (below) needs sklearn to train a
reference artifact to compare against.
"""
from __future__ import annotations

import math
import random
import sys

import pytest

from src.analyzer.corrections_classifier.predict import predict, score_from_proba

_TRAIN_ROWS = [
    ("I love this product it is amazing", "positive"),
    ("This is the best thing ever, fantastic", "positive"),
    ("Absolutely wonderful experience, great job", "positive"),
    ("Pretty good, works as expected", "positive"),
    ("It's okay, nothing special", "neutral"),
    ("Average experience, could be better", "neutral"),
    ("Neither good nor bad, just fine", "neutral"),
    ("Standard product, does what it says", "neutral"),
    ("I hate this, it is terrible", "negative"),
    ("Worst experience ever, awful", "negative"),
    ("This is broken and useless", "negative"),
    ("Very disappointing, do not buy", "negative"),
]


# ---------------------------------------------------------------------------
# sklearn <-> pure-predict parity (load-bearing)
# ---------------------------------------------------------------------------

def test_predict_matches_sklearn_on_training_rows():
    sklearn = pytest.importorskip("sklearn")
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression

    from src.analyzer.corrections_classifier.trainer import train_classifier

    artifact = train_classifier(_TRAIN_ROWS)

    texts = [t for t, _ in _TRAIN_ROWS]
    labels = [l for _, l in _TRAIN_ROWS]
    vec = TfidfVectorizer(lowercase=True, ngram_range=(1, 1), norm="l2",
                           sublinear_tf=False, smooth_idf=True)
    X = vec.fit_transform(texts)
    clf = LogisticRegression(multi_class="multinomial", solver="lbfgs",
                              random_state=0, max_iter=1000)
    clf.fit(X, labels)

    sk_labels = clf.predict(X)
    sk_probas = clf.predict_proba(X)
    classes = clf.classes_.tolist()

    for i, text in enumerate(texts):
        pred_label, pred_proba = predict(artifact, text)
        assert pred_label == sk_labels[i]
        for j, cls in enumerate(classes):
            assert pred_proba[cls] == pytest.approx(sk_probas[i][j], abs=1e-6)


def test_predict_binary_artifact():
    sklearn = pytest.importorskip("sklearn")
    from src.analyzer.corrections_classifier.trainer import train_classifier

    two_class_rows = [
        ("I love this product", "positive"),
        ("This is fantastic and great", "positive"),
        ("I hate this, terrible", "negative"),
        ("Worst experience ever, awful", "negative"),
    ]
    artifact = train_classifier(two_class_rows)
    assert len(artifact["classes"]) == 2
    assert len(artifact["logreg"]["coef"]) == 1

    label, proba = predict(artifact, "I love this, great job")
    assert label in artifact["classes"]
    assert set(proba.keys()) == set(artifact["classes"])
    assert sum(proba.values()) == pytest.approx(1.0, abs=1e-6)


# ---------------------------------------------------------------------------
# Pure-Python guarantees (no numpy needed at predict time)
# ---------------------------------------------------------------------------

_FIXTURE_ARTIFACT = {
    "model_type": "tfidf_logreg",
    "classifier_type": "sentiment",
    "classes": ["negative", "neutral", "positive"],
    "vectorizer": {
        "vocabulary": {"good": 0, "bad": 1, "okay": 2},
        "idf": [1.5, 1.5, 1.5],
        "lowercase": True,
        "token_pattern": r"(?u)\b\w\w+\b",
        "ngram_range": [1, 1],
        "norm": "l2",
        "sublinear_tf": False,
        "smooth_idf": True,
    },
    "logreg": {
        "coef": [
            [0.0, 2.0, 0.0],   # negative <- "bad"
            [0.0, 0.0, 2.0],   # neutral  <- "okay"
            [2.0, 0.0, 0.0],   # positive <- "good"
        ],
        "intercept": [0.0, 0.0, 0.0],
        "multi_class": "multinomial",
    },
    "label_count": 30,
}


def test_predict_pure_python_no_numpy():
    sys.modules["numpy"] = None
    try:
        label, proba = predict(_FIXTURE_ARTIFACT, "this is good")
        assert label == "positive"
        assert set(proba.keys()) == {"negative", "neutral", "positive"}
    finally:
        del sys.modules["numpy"]


def test_proba_dict_keys_are_classes():
    _, proba = predict(_FIXTURE_ARTIFACT, "this is good")
    assert set(proba.keys()) == set(_FIXTURE_ARTIFACT["classes"])


def test_proba_sums_to_one():
    _, proba = predict(_FIXTURE_ARTIFACT, "this is good")
    assert sum(proba.values()) == pytest.approx(1.0)


def test_unknown_tokens_ignored():
    label, proba = predict(_FIXTURE_ARTIFACT, "zzz yyy xxx not in vocab at all")
    assert label in _FIXTURE_ARTIFACT["classes"]
    assert sum(proba.values()) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# score_from_proba
# ---------------------------------------------------------------------------

def test_score_from_proba_pos_one_returns_1():
    assert score_from_proba({"positive": 1.0, "neutral": 0.0, "negative": 0.0}) == 1.0


def test_score_from_proba_neg_one_returns_minus_1():
    assert score_from_proba({"positive": 0.0, "neutral": 0.0, "negative": 1.0}) == -1.0


def test_score_from_proba_uniform_near_zero():
    third = 1.0 / 3.0
    result = score_from_proba({"positive": third, "neutral": third, "negative": third})
    assert result == pytest.approx(0.0)


def test_score_from_proba_always_in_range():
    rng = random.Random(42)
    for _ in range(200):
        proba = {
            "positive": rng.random(),
            "neutral": rng.random(),
            "negative": rng.random(),
        }
        result = score_from_proba(proba)
        assert -1.0 <= result <= 1.0


def test_score_from_proba_missing_class_treated_as_zero():
    assert score_from_proba({"neutral": 1.0}) == 0.0
    assert score_from_proba({"positive": 1.0}) == 1.0
    assert score_from_proba({"negative": 1.0}) == -1.0
