"""Tests for corrections_classifier.trainer — Phase 2 (M5.2 training-and-eval-core).

Guards the whole file with pytest.importorskip("sklearn") so the wheels-less CI venv
(worker-service py3.14) skips training tests entirely — disclosure/graceful-skip ethos,
matching eval_sentiment.py and calibration_refit.py's lazy-import convention.
"""
from __future__ import annotations

import json

import pytest

sklearn = pytest.importorskip("sklearn")

from src.analyzer.corrections_classifier.trainer import train_classifier  # noqa: E402

_DATASET = [
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
    artifact = train_classifier(_DATASET)
    json.dumps(artifact)  # must not raise


def test_artifact_has_no_pickle_bytes():
    artifact = train_classifier(_DATASET)
    serialized = json.dumps(artifact).encode()
    assert b"\x80" not in serialized
    _assert_json_leaf_types(artifact)


def test_artifact_carries_full_schema():
    artifact = train_classifier(_DATASET)
    assert "classes" in artifact
    assert "vocabulary" in artifact["vectorizer"]
    assert "idf" in artifact["vectorizer"]
    assert "token_pattern" in artifact["vectorizer"]
    assert "coef" in artifact["logreg"]
    assert "intercept" in artifact["logreg"]
    assert "label_count" in artifact

    vec = artifact["vectorizer"]
    assert len(vec["idf"]) == len(vec["vocabulary"])

    logreg = artifact["logreg"]
    classes = artifact["classes"]
    assert len(logreg["coef"]) == len(logreg["intercept"])
    assert len(logreg["coef"]) == len(classes) or len(logreg["coef"]) == 1


def test_determinism():
    a1 = train_classifier(_DATASET)
    a2 = train_classifier(_DATASET)
    assert json.dumps(a1, sort_keys=True) == json.dumps(a2, sort_keys=True)


def test_classes_are_sorted():
    artifact = train_classifier(_DATASET)
    labels_present = {label for _, label in _DATASET}
    assert artifact["classes"] == sorted(labels_present)


def test_model_type_and_classifier_type_are_tagged():
    artifact = train_classifier(_DATASET)
    assert artifact["model_type"] == "tfidf_logreg"
    assert artifact["classifier_type"] == "sentiment"


def test_label_count_matches_dataset_size():
    artifact = train_classifier(_DATASET)
    assert artifact["label_count"] == len(_DATASET)


def test_classifier_type_defaults_to_sentiment_byte_stable():
    """Characterization: calling train_classifier with NO classifier_type kwarg reproduces
    the exact pre-change artifact tag."""
    artifact = train_classifier(_DATASET)
    assert artifact["classifier_type"] == "sentiment"


def test_classifier_type_param_is_written_into_artifact():
    artifact = train_classifier(_DATASET, classifier_type="category")
    assert artifact["classifier_type"] == "category"


def test_classifier_type_category_with_dynamic_open_label_set():
    """Classes are dynamic from whatever the fitted model saw — no fixed category tuple
    anywhere in trainer.py."""
    category_dataset = [
        ("the button is broken", "ui_bug"),
        ("nothing happens when I click", "ui_bug"),
        ("invoice was wrong amount", "billing"),
        ("charged twice this month", "billing"),
        ("please add dark mode", "custom_feature_request"),
        ("dark theme would be great", "custom_feature_request"),
    ]
    artifact = train_classifier(category_dataset, classifier_type="category")
    assert artifact["classifier_type"] == "category"
    assert artifact["classes"] == sorted({label for _, label in category_dataset})
