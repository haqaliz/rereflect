"""
Tests for scripts/eval_embeddings.py — the offline retrieval eval harness
(retrieval-eval-card aspect, M5.4 disclosure layer, Task 2 of 5).

TDD: RED first, then production code in scripts/eval_embeddings.py.

All tests use a hand-rolled StubEmbeddingProvider (deterministic, crafted fixed
vectors) — no real embedding model, no network, no ollama/bge dependency. The
real run against ollama/bge is a later task (Task 3).
"""
from __future__ import annotations

import json
import os

import pytest

from src.services.embeddings.base import EmbeddingProvider
from src.services.embeddings.resolver import ResolvedEmbedder

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures", "embedding_eval")
TINY_FIXTURE_PATH = os.path.join(FIXTURES_DIR, "queries_tiny.jsonl")
FULL_FIXTURE_PATH = os.path.join(FIXTURES_DIR, "queries.jsonl")


# ---------------------------------------------------------------------------
# Stub embedder — deterministic, hand-made vectors, no real model in the loop.
# Mirrors tests/test_embedding_model_key_integration.py's StubEmbeddingProvider.
# ---------------------------------------------------------------------------

class StubEmbeddingProvider(EmbeddingProvider):
    def __init__(self, vectors: dict, default_vector: list, dim: int):
        self._vectors = dict(vectors)
        self._default = list(default_vector)
        self._dim = dim

    def embed(self, text: str) -> list:
        return list(self._vectors.get(text, self._default))

    @property
    def dimension(self) -> int:
        return self._dim


def _make_embedder(provider: str, model: str, vectors: dict, default_vector: list, dim: int) -> ResolvedEmbedder:
    stub = StubEmbeddingProvider(vectors, default_vector, dim)
    return ResolvedEmbedder(provider=provider, embedder=stub, dimension_hint=dim, model=model)


# 3 orthonormal-basis system templates, one question pattern each, so seeded
# vectors are small (3-dim) and every one is test-controlled — NOT the real
# 15-entry SYSTEM_TEMPLATES list (that's exercised elsewhere).
_CUSTOM_SYSTEM_TEMPLATES = [
    {
        "description": "Template A",
        "sql_query": "SELECT 1 AS a",
        "parameter_schema": {},
        "question_patterns": ["template a pattern"],
    },
    {
        "description": "Template B",
        "sql_query": "SELECT 1 AS b",
        "parameter_schema": {},
        "question_patterns": ["template b pattern"],
    },
    {
        "description": "Template C",
        "sql_query": "SELECT 1 AS c",
        "parameter_schema": {},
        "question_patterns": ["template c pattern"],
    },
]

_VEC_A = [1.0, 0.0, 0.0]
_VEC_B = [0.0, 1.0, 0.0]
_VEC_C = [0.0, 0.0, 1.0]

# Query vectors, hand-picked (see cosine calculations in the class docstring
# below) so recall@1 / MRR / false_match_rate come out to known exact fractions.
_P1_HITS_A = [1.0, 0.0, 0.0]          # sim(A)=1.0 -> hit, rank 1, RR=1.0
_P2_HITS_B = [0.0, 1.0, 0.0]          # sim(B)=1.0 -> hit, rank 1, RR=1.0
_P3_RANK1_BELOW_THRESHOLD = [0.0, 0.6, 0.8]   # sim(C)=0.8 (rank1, <0.85 -> recall miss), RR=1.0
_P4_WRONG_TEMPLATE_ABOVE_THRESHOLD = [0.3, 0.95, 0.0]  # sim(B)=0.9536 (wrong, >=0.85 -> recall miss), gold A rank2, RR=0.5
_N1_TRUE_NEGATIVE = [0.3, 0.3, 0.3]   # all sims ~0.577 < 0.85 -> correctly no match
_N2_FALSE_MATCH = [0.95, 0.1, 0.0]    # sim(A)=0.9945 >= 0.85 -> false match


@pytest.fixture(autouse=True)
def _small_system_templates(monkeypatch):
    """Patch SYSTEM_TEMPLATES to the small 3-template fixture above for every
    test in this module, so seeded vectors stay tiny and test-controlled."""
    import src.services.copilot.template_saver as template_saver_module

    monkeypatch.setattr(template_saver_module, "SYSTEM_TEMPLATES", _CUSTOM_SYSTEM_TEMPLATES)


# ---------------------------------------------------------------------------
# load_fixtures
# ---------------------------------------------------------------------------

class TestLoadFixtures:
    def test_parses_tiny_fixture(self):
        from scripts.eval_embeddings import load_fixtures

        rows = load_fixtures(TINY_FIXTURE_PATH)

        assert len(rows) == 6
        assert all(set(row.keys()) == {"query", "expected"} for row in rows)
        assert rows[0]["query"] == "what's our total number of feedback entries?"
        assert rows[0]["expected"] == "Count total feedbacks"
        # A row with expected: null (a negative fixture)
        assert any(row["expected"] is None for row in rows)

    def test_parses_full_fixture_count(self):
        from scripts.eval_embeddings import load_fixtures

        rows = load_fixtures(FULL_FIXTURE_PATH)
        assert len(rows) == 69

    def test_rejects_malformed_line_with_clear_value_error(self, tmp_path):
        from scripts.eval_embeddings import load_fixtures

        bad_file = tmp_path / "bad.jsonl"
        bad_file.write_text(
            "\n".join(
                [
                    json.dumps({"query": "valid one", "expected": "Some Template"}),
                    "{not valid json",
                    json.dumps({"expected": "missing query key"}),
                    json.dumps({"query": "", "expected": None}),
                    json.dumps({"query": "bad expected type", "expected": 42}),
                ]
            ),
            encoding="utf-8",
        )

        with pytest.raises(ValueError) as exc_info:
            load_fixtures(str(bad_file))

        message = str(exc_info.value)
        assert "line 2" in message  # invalid JSON
        assert "line 3" in message  # missing query
        assert "line 4" in message  # empty query
        assert "line 5" in message  # bad expected type

    def test_empty_file_returns_empty_list(self, tmp_path):
        from scripts.eval_embeddings import load_fixtures

        empty_file = tmp_path / "empty.jsonl"
        empty_file.write_text("", encoding="utf-8")

        assert load_fixtures(str(empty_file)) == []


# ---------------------------------------------------------------------------
# run_provider — exact recall@1 / MRR / false_match_rate arithmetic
# ---------------------------------------------------------------------------

class TestRunProvider:
    """
    Fixture set (4 positives, 2 negatives) against 3 orthonormal templates
    A/B/C (see cosine similarities computed in eval_embeddings.py's docstring
    for _best_similarity_per_template). Hand-verified similarities:

        P1 [1,0,0]:        simA=1.0000 simB=0.0000 simC=0.0000
        P2 [0,1,0]:        simA=0.0000 simB=1.0000 simC=0.0000
        P3 [0,0.6,0.8]:    simA=0.0000 simB=0.6000 simC=0.8000
        P4 [0.3,0.95,0]:   simA=0.3011 simB=0.9536 simC=0.0000
        N1 [0.3,0.3,0.3]:  simA=simB=simC=0.5774
        N2 [0.95,0.1,0]:   simA=0.9945 simB=0.1047 simC=0.0000

    recall@1 (threshold 0.85):
        P1 expected=A: find_match returns A (sim 1.0)          -> HIT
        P2 expected=B: find_match returns B (sim 1.0)          -> HIT
        P3 expected=C: best sim is C=0.8 < 0.85 -> no match    -> MISS
        P4 expected=A: find_match returns B (sim 0.9536, wrong) -> MISS
        => recall_at_1 = 2/4 = 0.5

    MRR (full ranking, NOT threshold-gated):
        P1: gold A rank 1 -> RR = 1.0
        P2: gold B rank 1 -> RR = 1.0
        P3: gold C rank 1 (0.8 is the top similarity even though below
            threshold) -> RR = 1.0
        P4: ranking is B(0.9536) > A(0.3011) > C(0.0); gold A is rank 2
            -> RR = 0.5
        => mrr = (1.0 + 1.0 + 1.0 + 0.5) / 4 = 3.5 / 4 = 0.875

    false_match_rate:
        N1: all sims < 0.85 -> no match -> correct (not a false match)
        N2: sim A = 0.9945 >= 0.85 -> find_match returns a match -> FALSE MATCH
        => false_match_rate = 1/2 = 0.5
    """

    FIXTURES = [
        {"query": "alpha lookup query", "expected": "Template A"},
        {"query": "bravo lookup query", "expected": "Template B"},
        {"query": "charlie ambiguous query", "expected": "Template C"},
        {"query": "delta conflicting query", "expected": "Template A"},
        {"query": "unrelated negative query", "expected": None},
        {"query": "sneaky negative query", "expected": None},
    ]

    def _resolved(self):
        vectors = {
            "template a pattern": _VEC_A,
            "template b pattern": _VEC_B,
            "template c pattern": _VEC_C,
            "alpha lookup query": _P1_HITS_A,
            "bravo lookup query": _P2_HITS_B,
            "charlie ambiguous query": _P3_RANK1_BELOW_THRESHOLD,
            "delta conflicting query": _P4_WRONG_TEMPLATE_ABOVE_THRESHOLD,
            "unrelated negative query": _N1_TRUE_NEGATIVE,
            "sneaky negative query": _N2_FALSE_MATCH,
        }
        return _make_embedder(
            provider="stub", model="stub-model-v1", vectors=vectors, default_vector=[0.0, 0.0, 0.0], dim=3
        )

    def test_exact_recall_mrr_false_match_rate(self, db):
        from scripts.eval_embeddings import run_provider

        result = run_provider(self._resolved(), self.FIXTURES, db, org_id=1)

        assert result["provider"] == "stub"
        assert result["model"] == "stub-model-v1"
        assert result["n"] == 6
        assert result["n_pos"] == 4
        assert result["n_neg"] == 2
        assert result["recall_at_1"] == pytest.approx(0.5)
        assert result["mrr"] == pytest.approx(0.875)
        assert result["false_match_rate"] == pytest.approx(0.5)

    def test_never_raises_on_empty_fixtures(self, db):
        from scripts.eval_embeddings import run_provider

        result = run_provider(self._resolved(), [], db, org_id=1)

        assert result["n"] == 0
        assert result["n_pos"] == 0
        assert result["n_neg"] == 0
        assert result["recall_at_1"] == 0.0
        assert result["mrr"] == 0.0
        assert result["false_match_rate"] == 0.0


# ---------------------------------------------------------------------------
# compare()
# ---------------------------------------------------------------------------

class TestCompare:
    def test_passes_by_margin(self):
        from scripts.eval_embeddings import compare

        baseline = {"recall_at_1": 0.50, "false_match_rate": 0.20}
        candidate = {"recall_at_1": 0.60, "false_match_rate": 0.10}

        result = compare(baseline, candidate)

        assert result["recall_at_1_delta"] == pytest.approx(0.10)
        assert result["meets_target"] is True

    def test_fails_on_delta_too_small(self):
        from scripts.eval_embeddings import compare

        baseline = {"recall_at_1": 0.50, "false_match_rate": 0.20}
        candidate = {"recall_at_1": 0.53, "false_match_rate": 0.10}  # delta=0.03 < 0.05

        result = compare(baseline, candidate)

        assert result["recall_at_1_delta"] == pytest.approx(0.03)
        assert result["meets_target"] is False

    def test_fails_on_false_match_regression(self):
        from scripts.eval_embeddings import compare

        baseline = {"recall_at_1": 0.50, "false_match_rate": 0.10}
        candidate = {"recall_at_1": 0.60, "false_match_rate": 0.20}  # delta=0.10 >= 0.05 but fm regressed

        result = compare(baseline, candidate)

        assert result["recall_at_1_delta"] == pytest.approx(0.10)
        assert result["meets_target"] is False

    def test_provider_unavailable_baseline_none(self):
        from scripts.eval_embeddings import compare

        result = compare(None, {"recall_at_1": 0.6, "false_match_rate": 0.1})

        assert result["recall_at_1_delta"] is None
        assert result["meets_target"] is None

    def test_provider_unavailable_candidate_none(self):
        from scripts.eval_embeddings import compare

        result = compare({"recall_at_1": 0.5, "false_match_rate": 0.1}, None)

        assert result["recall_at_1_delta"] is None
        assert result["meets_target"] is None

    def test_both_providers_unavailable(self):
        from scripts.eval_embeddings import compare

        result = compare(None, None)

        assert result["recall_at_1_delta"] is None
        assert result["meets_target"] is None


# ---------------------------------------------------------------------------
# run_eval — artifact assembly
# ---------------------------------------------------------------------------

class TestRunEval:
    FIXTURES = [
        {"query": "alpha lookup query", "expected": "Template A"},
        {"query": "bravo lookup query", "expected": "Template B"},
        {"query": "unrelated negative query", "expected": None},
    ]

    def _resolved(self, provider: str, model: str):
        vectors = {
            "template a pattern": _VEC_A,
            "template b pattern": _VEC_B,
            "template c pattern": _VEC_C,
            "alpha lookup query": _P1_HITS_A,
            "bravo lookup query": _P2_HITS_B,
            "unrelated negative query": _N1_TRUE_NEGATIVE,
        }
        return _make_embedder(provider=provider, model=model, vectors=vectors, default_vector=[0.0, 0.0, 0.0], dim=3)

    def test_assembles_artifact_with_documented_keys(self, db):
        from scripts.eval_embeddings import run_eval

        providers = {
            "baseline": self._resolved("stub-baseline", "stub-baseline-model"),
            "candidate": self._resolved("stub-candidate", "stub-candidate-model"),
        }

        artifact = run_eval(self.FIXTURES, providers, db, org_id=1)

        assert set(artifact.keys()) == {
            "generated_at", "threshold", "n", "n_positives", "n_negatives",
            "baseline", "candidate", "recall_at_1_delta", "meets_target",
        }
        assert artifact["threshold"] == 0.85
        assert artifact["n"] == 3
        assert artifact["n_positives"] == 2
        assert artifact["n_negatives"] == 1

        for side in ("baseline", "candidate"):
            provider_result = artifact[side]
            assert set(provider_result.keys()) == {
                "provider", "model", "n", "n_pos", "n_neg",
                "recall_at_1", "mrr", "false_match_rate",
            }

        # Both providers embed identically -> perfect recall/mrr on both sides,
        # so delta is 0.0 (does not meet the >=0.05 improvement target).
        assert artifact["recall_at_1_delta"] == pytest.approx(0.0)
        assert artifact["meets_target"] is False

    def test_candidate_unavailable_degrades_to_null(self, db):
        from scripts.eval_embeddings import run_eval

        providers = {
            "baseline": self._resolved("stub-baseline", "stub-baseline-model"),
            "candidate": None,
        }

        artifact = run_eval(self.FIXTURES, providers, db, org_id=1)

        assert artifact["baseline"] is not None
        assert artifact["candidate"] is None
        assert artifact["recall_at_1_delta"] is None
        assert artifact["meets_target"] is None

    def test_never_raises_on_empty_fixtures(self, db):
        from scripts.eval_embeddings import run_eval

        providers = {
            "baseline": self._resolved("stub-baseline", "stub-baseline-model"),
            "candidate": self._resolved("stub-candidate", "stub-candidate-model"),
        }

        artifact = run_eval([], providers, db, org_id=1)

        assert artifact["n"] == 0
        assert artifact["n_positives"] == 0
        assert artifact["n_negatives"] == 0
        assert artifact["baseline"]["recall_at_1"] == 0.0
        assert artifact["candidate"]["recall_at_1"] == 0.0
