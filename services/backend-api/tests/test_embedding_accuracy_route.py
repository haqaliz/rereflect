"""
Tests for GET /api/v1/settings/ai/embeddings/accuracy (retrieval-eval-card
aspect, M5.4 disclosure layer). Reads the committed eval_retrieval.py results
artifact and serves it as a typed, never-raising response.

TDD: RED first, then production code in
src/api/routes/embedding_accuracy.py + src/schemas/embedding_accuracy.py.

Mirrors tests/test_sentiment_accuracy_route.py exactly.
"""
from __future__ import annotations

import json

import pytest


FULL_ARTIFACT = {
    "generated_at": "2026-07-25T01:17:41.783498+00:00",
    "threshold": 0.85,
    "n": 69,
    "n_positives": 45,
    "n_negatives": 24,
    "baseline": {
        "provider": "ollama",
        "model": "nomic-embed-text",
        "n": 69,
        "n_pos": 45,
        "n_neg": 24,
        "recall_at_1": 0.08888888888888889,
        "mrr": 0.7483597883597883,
        "false_match_rate": 0.125,
    },
    "candidate": {
        "provider": "local",
        "model": "BAAI/bge-small-en-v1.5",
        "n": 69,
        "n_pos": 45,
        "n_neg": 24,
        "recall_at_1": 0.17777777777777778,
        "mrr": 0.7468967452300785,
        "false_match_rate": 0.125,
    },
    "recall_at_1_delta": 0.08888888888888889,
    "meets_target": True,
}


BASELINE_NULL_ARTIFACT = {
    **FULL_ARTIFACT,
    "baseline": None,
    "recall_at_1_delta": None,
    "meets_target": None,
}


@pytest.fixture
def patch_artifact_path(monkeypatch, tmp_path):
    """Monkeypatch the route's artifact path constant to a tmp file we control."""
    import src.api.routes.embedding_accuracy as route_module

    def _set(content: str | None):
        path = tmp_path / "retrieval_accuracy.json"
        if content is not None:
            path.write_text(content)
        monkeypatch.setattr(route_module, "_ARTIFACT_PATH", str(path))
        return path

    return _set


class TestEmbeddingAccuracyRoute:
    def test_missing_artifact_returns_200_has_results_false(
        self, client, auth_headers, patch_artifact_path
    ):
        patch_artifact_path(None)  # never write the file -> FileNotFoundError path

        response = client.get("/api/v1/settings/ai/embeddings/accuracy", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["has_results"] is False
        assert data["generated_at"] is None
        assert data["threshold"] is None
        assert data["baseline"] is None
        assert data["candidate"] is None
        assert data["meets_target"] is None

    def test_full_artifact_returns_parsed_metrics(self, client, auth_headers, patch_artifact_path):
        patch_artifact_path(json.dumps(FULL_ARTIFACT))

        response = client.get("/api/v1/settings/ai/embeddings/accuracy", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["has_results"] is True
        assert data["candidate"]["recall_at_1"] == pytest.approx(0.17777777777777778)
        assert data["baseline"]["model"] == "nomic-embed-text"
        assert data["meets_target"] is True
        assert data["n"] == 69
        assert data["n_positives"] == 45
        assert data["n_negatives"] == 24
        assert data["recall_at_1_delta"] == pytest.approx(0.08888888888888889)

    def test_baseline_null_is_none_no_error(self, client, auth_headers, patch_artifact_path):
        patch_artifact_path(json.dumps(BASELINE_NULL_ARTIFACT))

        response = client.get("/api/v1/settings/ai/embeddings/accuracy", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["has_results"] is True
        assert data["baseline"] is None
        assert data["recall_at_1_delta"] is None
        assert data["meets_target"] is None
        assert data["candidate"]["model"] == "BAAI/bge-small-en-v1.5"

    def test_malformed_json_artifact_degrades_to_has_results_false(
        self, client, auth_headers, patch_artifact_path
    ):
        patch_artifact_path("{not valid json,,,")

        response = client.get("/api/v1/settings/ai/embeddings/accuracy", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["has_results"] is False

    def test_requires_auth_401_without_token(self, client, patch_artifact_path):
        patch_artifact_path(json.dumps(FULL_ARTIFACT))

        response = client.get("/api/v1/settings/ai/embeddings/accuracy")

        assert response.status_code in (401, 403)
