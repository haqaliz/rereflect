"""
Tests for GET /api/v1/settings/ai/sentiment/accuracy (eval-harness-and-card
aspect, Phase 6). Reads the committed eval_sentiment.py results artifact and
serves it as a typed, never-raising response.

TDD: RED first, then production code in
src/api/routes/sentiment_accuracy.py + src/schemas/sentiment_accuracy.py.
"""
from __future__ import annotations

import json

import pytest


FULL_ARTIFACT = {
    "generated_at": "2026-07-10T12:00:00+00:00",
    "model_id": "cardiffnlp/twitter-roberta-base-sentiment-latest",
    "model_revision": "main",
    "public": {
        "set_name": "public",
        "n": 180,
        "vader": {
            "provider": "vader",
            "n": 180,
            "macro_precision": 0.70,
            "macro_recall": 0.68,
            "macro_f1": 0.69,
            "accuracy": 0.70,
            "per_class": {
                "positive": {"precision": 0.8, "recall": 0.75, "f1": 0.77, "support": 60},
                "neutral": {"precision": 0.6, "recall": 0.6, "f1": 0.6, "support": 60},
                "negative": {"precision": 0.7, "recall": 0.7, "f1": 0.7, "support": 60},
            },
            "confusion_matrix": {
                "positive": {"positive": 45, "neutral": 10, "negative": 5},
                "neutral": {"positive": 5, "neutral": 45, "negative": 10},
                "negative": {"positive": 5, "neutral": 10, "negative": 45},
            },
        },
        "transformer": {
            "provider": "transformer",
            "n": 180,
            "macro_precision": 0.80,
            "macro_recall": 0.78,
            "macro_f1": 0.79,
            "accuracy": 0.80,
            "per_class": {
                "positive": {"precision": 0.85, "recall": 0.85, "f1": 0.85, "support": 60},
                "neutral": {"precision": 0.75, "recall": 0.7, "f1": 0.72, "support": 60},
                "negative": {"precision": 0.8, "recall": 0.8, "f1": 0.8, "support": 60},
            },
            "confusion_matrix": {
                "positive": {"positive": 51, "neutral": 6, "negative": 3},
                "neutral": {"positive": 6, "neutral": 42, "negative": 12},
                "negative": {"positive": 3, "neutral": 9, "negative": 48},
            },
        },
        "macro_f1_delta": 0.10,
        "meets_target": None,
    },
    "in_domain": {
        "set_name": "in_domain",
        "n": 169,
        "vader": {
            "provider": "vader",
            "n": 169,
            "macro_precision": 0.55,
            "macro_recall": 0.52,
            "macro_f1": 0.53,
            "accuracy": 0.55,
            "per_class": {
                "positive": {"precision": 0.6, "recall": 0.5, "f1": 0.55, "support": 52},
                "neutral": {"precision": 0.4, "recall": 0.4, "f1": 0.4, "support": 36},
                "negative": {"precision": 0.6, "recall": 0.65, "f1": 0.62, "support": 81},
            },
            "confusion_matrix": {
                "positive": {"positive": 26, "neutral": 13, "negative": 13},
                "neutral": {"positive": 10, "neutral": 14, "negative": 12},
                "negative": {"positive": 12, "neutral": 16, "negative": 53},
            },
        },
        "transformer": {
            "provider": "transformer",
            "n": 169,
            "macro_precision": 0.60,
            "macro_recall": 0.58,
            "macro_f1": 0.59,
            "accuracy": 0.60,
            "per_class": {
                "positive": {"precision": 0.65, "recall": 0.6, "f1": 0.62, "support": 52},
                "neutral": {"precision": 0.45, "recall": 0.45, "f1": 0.45, "support": 36},
                "negative": {"precision": 0.65, "recall": 0.7, "f1": 0.67, "support": 81},
            },
            "confusion_matrix": {
                "positive": {"positive": 31, "neutral": 11, "negative": 10},
                "neutral": {"positive": 9, "neutral": 16, "negative": 11},
                "negative": {"positive": 11, "neutral": 13, "negative": 57},
            },
        },
        "macro_f1_delta": 0.06,
        "meets_target": True,
    },
}


TRANSFORMER_NULL_ARTIFACT = {
    "generated_at": "2026-07-10T12:00:00+00:00",
    "model_id": "cardiffnlp/twitter-roberta-base-sentiment-latest",
    "model_revision": "main",
    "public": {**FULL_ARTIFACT["public"], "transformer": None, "macro_f1_delta": None, "meets_target": None},
    "in_domain": {**FULL_ARTIFACT["in_domain"], "transformer": None, "macro_f1_delta": None, "meets_target": None},
}


@pytest.fixture
def patch_artifact_path(monkeypatch, tmp_path):
    """Monkeypatch the route's artifact path constant to a tmp file we control."""
    import src.api.routes.sentiment_accuracy as route_module

    def _set(content: str | None):
        path = tmp_path / "sentiment_accuracy.json"
        if content is not None:
            path.write_text(content)
        monkeypatch.setattr(route_module, "_ARTIFACT_PATH", str(path))
        return path

    return _set


class TestSentimentAccuracyRoute:
    def test_missing_artifact_returns_200_has_results_false(
        self, client, auth_headers, patch_artifact_path
    ):
        patch_artifact_path(None)  # never write the file -> FileNotFoundError path

        response = client.get("/api/v1/settings/ai/sentiment/accuracy", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["has_results"] is False
        assert data["generated_at"] is None
        assert data["model_id"] is None
        assert data["public"] is None
        assert data["in_domain"] is None

    def test_full_artifact_returns_parsed_metrics(self, client, auth_headers, patch_artifact_path):
        patch_artifact_path(json.dumps(FULL_ARTIFACT))

        response = client.get("/api/v1/settings/ai/sentiment/accuracy", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["has_results"] is True
        assert data["model_id"] == "cardiffnlp/twitter-roberta-base-sentiment-latest"

        in_domain = data["in_domain"]
        assert in_domain["n"] == 169
        assert in_domain["macro_f1_delta"] == pytest.approx(0.06)
        assert in_domain["meets_target"] is True
        assert set(in_domain["vader"]["per_class"].keys()) == {"positive", "neutral", "negative"}
        assert set(in_domain["transformer"]["per_class"].keys()) == {"positive", "neutral", "negative"}

        public = data["public"]
        assert public["n"] == 180
        assert public["meets_target"] is None

    def test_transformer_null_for_a_set_is_none_no_error(
        self, client, auth_headers, patch_artifact_path
    ):
        patch_artifact_path(json.dumps(TRANSFORMER_NULL_ARTIFACT))

        response = client.get("/api/v1/settings/ai/sentiment/accuracy", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["has_results"] is True
        assert data["public"]["transformer"] is None
        assert data["public"]["macro_f1_delta"] is None
        assert data["public"]["meets_target"] is None
        assert data["in_domain"]["transformer"] is None

    def test_malformed_json_artifact_degrades_to_has_results_false(
        self, client, auth_headers, patch_artifact_path
    ):
        patch_artifact_path("{not valid json,,,")

        response = client.get("/api/v1/settings/ai/sentiment/accuracy", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["has_results"] is False

    def test_requires_auth_401_without_token(self, client, patch_artifact_path):
        patch_artifact_path(json.dumps(FULL_ARTIFACT))

        response = client.get("/api/v1/settings/ai/sentiment/accuracy")

        assert response.status_code in (401, 403)
