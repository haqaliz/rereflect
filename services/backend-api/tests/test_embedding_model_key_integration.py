"""
Task 5 -- Integration + regression sweep for model-keyed template matching.

Part of local-embedding-quality (M5.4), aspect staleness-model-key (Task 5 of 5,
closes the aspect). Prereqs (all merged on this branch):
  - Task 1 (90f4190): ResolvedEmbedder.model
  - Task 2 (ffd171c): embedding_model column + ix_mappings_provider_dim_model + backfill
  - Task 3 (3647f48): saver persists model + reseeds on model change
  - Task 4 (79be522): matcher skip-filter keys on model

This module proves the whole aspect hangs together end-to-end using a REAL
SQLite session (the `db` fixture from tests/conftest.py, same as the Task 2/3
tests) plus a hand-rolled stub EmbeddingProvider -- no real embedding model,
no DB mocks. Vectors are small (4-dim) and hand-made so that "should match"
pairs are near-identical and "should not match" pairs are genuinely distinct
(orthogonal) -- the assertions exercise the actual cosine-similarity + skip-
filter logic, not a tautology.

Scenarios (see docs/planning/local-embedding-quality/staleness-model-key/plan_20260724.md,
Phase 5):
  1. Seed -> match, steady state (byte-stable no-opt-in regression guard):
     seeding + matching under the SAME provider+model as the migration's
     backfill value (openai / text-embedding-3-small) behaves exactly as it
     did before Tasks 1-4 touched anything.
  2. Model change re-embeds + old vectors go stale (the core anti-corruption
     guarantee of the whole aspect): re-seeding under a new model on the SAME
     provider creates NEW model-B mappings (old model-A rows are untouched,
     not deleted), model-B queries match the new rows, and model-A rows are
     never wrong-space-matched by a model-B query even when a model-A vector
     would otherwise be a near-perfect coincidental match.
  3. Backfilled openai row still matches: a mapping tagged exactly like the
     migration's backfill result (('openai', <dim>, 'text-embedding-3-small'))
     is matched by a plain openai embedder with no per-org model override --
     confirming the backfill value and the saver/matcher key agree.
"""

from __future__ import annotations

from typing import Optional

import pytest

from src.services.copilot.template_saver import TemplateSaver
from src.services.copilot.template_matcher import TemplateMatcher
from src.services.embeddings.base import EmbeddingProvider
from src.services.embeddings.resolver import ResolvedEmbedder


# ── Stub embedder -- deterministic, hand-made small vectors, no real model ───

class StubEmbeddingProvider(EmbeddingProvider):
    """
    Deterministic embed(): returns a hand-made vector for known text, and a
    distinct fallback vector for anything unregistered. This lets each test
    build discriminating fixtures (near-identical vectors for pairs that
    should match, orthogonal vectors for pairs that should not) without any
    real embedding model in the loop.
    """

    def __init__(self, vectors: dict, default_vector: list, dim: int):
        self._vectors = dict(vectors)
        self._default = list(default_vector)
        self._dim = dim

    def embed(self, text: str) -> list:
        return list(self._vectors.get(text, self._default))

    @property
    def dimension(self) -> int:
        return self._dim


def _make_embedder(
    provider: str, model: Optional[str], vectors: dict, default_vector: list, dim: int
) -> ResolvedEmbedder:
    stub = StubEmbeddingProvider(vectors, default_vector, dim)
    return ResolvedEmbedder(provider=provider, embedder=stub, dimension_hint=dim, model=model)


# A small, hand-made system-template fixture (2 templates) so seeded vectors
# stay tiny and every one is test-controlled -- NOT the real 15-entry
# SYSTEM_TEMPLATES list (that's still exercised, untouched, by test_template_saver.py).
_CUSTOM_SYSTEM_TEMPLATES = [
    {
        "description": "Count total feedbacks",
        "sql_query": "SELECT COUNT(*) as total_feedbacks FROM feedback_items WHERE organization_id = :org_id",
        "parameter_schema": {"org_id": "integer"},
        "question_patterns": ["count total feedbacks"],
    },
    {
        "description": "List urgent feedbacks",
        "sql_query": "SELECT id FROM feedback_items WHERE organization_id = :org_id AND is_urgent = true",
        "parameter_schema": {"org_id": "integer"},
        "question_patterns": ["urgent feedback list"],
    },
]

# 4-dim hand-made vectors, model A (the "no-opt-in" / steady-state model).
_VEC_COUNT_MODEL_A = [1.0, 0.0, 0.0, 0.0]
_VEC_URGENT_MODEL_A = [0.0, 1.0, 0.0, 0.0]
_VEC_COUNT_QUERY_NEAR_A = [0.99, 0.02, 0.0, 0.0]   # near-identical to _VEC_COUNT_MODEL_A
_VEC_UNRELATED = [0.0, 0.0, 1.0, 0.0]                # orthogonal to everything above

# 4-dim hand-made vectors, model B (a distinct vector space -- not just a
# relabeled copy of model A's vectors, so a "wrong-space" match would be
# a genuine, discriminating false positive if the skip-filter were absent).
_VEC_COUNT_MODEL_B = [0.0, 0.0, 0.0, 1.0]
_VEC_URGENT_MODEL_B = [0.0, 0.0, 0.7, 0.7]
_VEC_COUNT_QUERY_NEAR_B = [0.0, 0.0, 0.0, 0.98]     # near-identical to _VEC_COUNT_MODEL_B


@pytest.fixture
def saver() -> TemplateSaver:
    return TemplateSaver()


@pytest.fixture
def matcher() -> TemplateMatcher:
    return TemplateMatcher()


@pytest.fixture(autouse=True)
def _small_system_templates(monkeypatch):
    """
    Seed a small, hand-made system-template list instead of the real 15-entry
    SYSTEM_TEMPLATES, so every seeded vector in this module is test-controlled
    and dimensions stay small (4-dim). Production SYSTEM_TEMPLATES content is
    untouched -- this only patches the module attribute for this test module.
    """
    import src.services.copilot.template_saver as template_saver_module

    monkeypatch.setattr(template_saver_module, "SYSTEM_TEMPLATES", _CUSTOM_SYSTEM_TEMPLATES)


# ── Scenario 1: seed -> match, steady state (byte-stable, no-opt-in) ─────────

class TestSteadyStateByteStable:
    """
    An org that never changes its embedding config (still on openai /
    text-embedding-3-small, the migration's backfill value) seeds its system
    templates and matches a question exactly as it did before Tasks 1-4.
    This is the no-opt-in regression guard.
    """

    def test_seed_then_match_hits_seeded_template(self, saver, matcher, db):
        raw_question = "how many total feedbacks are there"
        normalized_query_key = matcher.normalize_question(raw_question)

        embedder = _make_embedder(
            provider="openai",
            model="text-embedding-3-small",
            vectors={
                "count total feedbacks": _VEC_COUNT_MODEL_A,
                "urgent feedback list": _VEC_URGENT_MODEL_A,
                normalized_query_key: _VEC_COUNT_QUERY_NEAR_A,
            },
            default_vector=_VEC_UNRELATED,
            dim=4,
        )

        saver.seed_system_templates(db=db, embedder=embedder)

        result = matcher.find_match(
            question=raw_question,
            org_id=1,
            db=db,
            embedder=embedder,
            threshold=0.85,
        )

        assert result is not None
        assert result["description"] == "Count total feedbacks"
        assert result["similarity"] >= 0.85

    def test_seed_is_idempotent_for_same_provider_and_model(self, saver, matcher, db):
        """Re-seeding under the identical (provider, model) must not duplicate
        mappings -- the no-opt-in idempotency guard from Task 3, confirmed here
        with a real DB rather than mocks."""
        from src.models.query_template_mapping import QueryTemplateMapping

        embedder = _make_embedder(
            provider="openai",
            model="text-embedding-3-small",
            vectors={
                "count total feedbacks": _VEC_COUNT_MODEL_A,
                "urgent feedback list": _VEC_URGENT_MODEL_A,
            },
            default_vector=_VEC_UNRELATED,
            dim=4,
        )

        saver.seed_system_templates(db=db, embedder=embedder)
        count_after_first = db.query(QueryTemplateMapping).count()

        saver.seed_system_templates(db=db, embedder=embedder)
        count_after_second = db.query(QueryTemplateMapping).count()

        assert count_after_first == 2  # one mapping per pattern, two templates
        assert count_after_second == count_after_first


# ── Scenario 2: model change re-embeds + old vectors go stale ───────────────

class TestModelChangeAntiCorruption:
    """
    The core anti-corruption guarantee of the whole aspect: re-seeding under
    a new model on the SAME provider re-embeds (new mappings tagged model B
    appear), a model-B query matches the new mappings, and model-A rows are
    never wrong-space-matched by a model-B query -- even when a model-A
    vector would otherwise be a near-perfect coincidental match.
    """

    def _seed_model_a(self, saver, db):
        embedder_a = _make_embedder(
            provider="openai",
            model="model-a",
            vectors={
                "count total feedbacks": _VEC_COUNT_MODEL_A,
                "urgent feedback list": _VEC_URGENT_MODEL_A,
            },
            default_vector=_VEC_UNRELATED,
            dim=4,
        )
        saver.seed_system_templates(db=db, embedder=embedder_a)
        return embedder_a

    def _seed_model_b(self, saver, db):
        embedder_b = _make_embedder(
            provider="openai",
            model="model-b",
            vectors={
                "count total feedbacks": _VEC_COUNT_MODEL_B,
                "urgent feedback list": _VEC_URGENT_MODEL_B,
            },
            default_vector=_VEC_UNRELATED,
            dim=4,
        )
        saver.seed_system_templates(db=db, embedder=embedder_b)
        return embedder_b

    def test_reseed_creates_new_model_b_mappings_without_deleting_model_a(self, saver, db):
        from src.models.query_template_mapping import QueryTemplateMapping

        self._seed_model_a(saver, db)
        model_a_count_before = db.query(QueryTemplateMapping).filter_by(
            embedding_model="model-a"
        ).count()
        assert model_a_count_before == 2

        self._seed_model_b(saver, db)

        model_a_count_after = db.query(QueryTemplateMapping).filter_by(
            embedding_model="model-a"
        ).count()
        model_b_count_after = db.query(QueryTemplateMapping).filter_by(
            embedding_model="model-b"
        ).count()

        # (a) new mappings tagged model B exist ...
        assert model_b_count_after == 2
        # ... and old model-A rows are untouched (not deleted) -- they simply
        # become stale/skipped, which is what the matcher's skip-filter relies on.
        assert model_a_count_after == model_a_count_before

    def test_model_b_query_matches_model_b_mappings(self, saver, matcher, db):
        """(b) find_match with the model-B embedder matches its own mappings."""
        self._seed_model_a(saver, db)
        embedder_b = self._seed_model_b(saver, db)

        raw_question = "please count total feedbacks for me"
        normalized_query_key = matcher.normalize_question(raw_question)
        embedder_b.embedder._vectors[normalized_query_key] = _VEC_COUNT_QUERY_NEAR_B

        result = matcher.find_match(
            question=raw_question,
            org_id=1,
            db=db,
            embedder=embedder_b,
            threshold=0.85,
        )

        assert result is not None
        assert result["description"] == "Count total feedbacks"

    def test_model_b_query_never_wrong_space_matches_model_a_row(self, saver, matcher, db):
        """
        (c) The core anti-corruption assertion. Query with the model-B
        embedder using a vector that is IDENTICAL to the model-A stored
        vector for "count total feedbacks" ([1,0,0,0]) and orthogonal to
        BOTH of model B's own stored vectors ([0,0,0,1] and [0,0,0.7,0.7]).

        Without the embedding_model skip-filter, this vector would produce a
        similarity of 1.0 against the stale model-A row -- a silent,
        wrong-space match. With the filter, that model-A row is excluded
        (embedding_model='model-a' != active model='model-b') regardless of
        how similar its vector looks, so the result must be None.
        """
        self._seed_model_a(saver, db)
        embedder_b = self._seed_model_b(saver, db)

        raw_question = "trying to collide with the stale model-a vector"
        normalized_query_key = matcher.normalize_question(raw_question)
        # This is a byte-for-byte copy of _VEC_COUNT_MODEL_A -- a coincidental
        # collision with the stale row's vector, not a fresh unrelated one.
        embedder_b.embedder._vectors[normalized_query_key] = list(_VEC_COUNT_MODEL_A)

        result = matcher.find_match(
            question=raw_question,
            org_id=1,
            db=db,
            embedder=embedder_b,
            threshold=0.85,
        )

        assert result is None


# ── Scenario 3: backfilled openai row still matches ─────────────────────────

class TestBackfilledRowStillMatches:
    """
    Simulate a pre-existing mapping tagged exactly like the migration's
    backfill result (('openai', <dim>, 'text-embedding-3-small') -- see
    tests/test_mapping_embedding_model_migration.py::TestBackfill,
    which confirms the migration assigns embedding_model='text-embedding-3-small'
    to every pre-existing openai row) and confirm a plain openai embedder
    (no per-org model override, so ResolvedEmbedder.model resolves to the
    same default via default_model_for_provider) matches it. This proves the
    backfill value and the saver/matcher key agree.
    """

    def test_backfilled_openai_mapping_matches_default_openai_embedder(self, saver, matcher, db):
        from src.models.query_template import QueryTemplate
        from src.models.query_template_mapping import QueryTemplateMapping

        template = QueryTemplate(
            sql_query="SELECT COUNT(*) FROM feedback_items WHERE organization_id = :org_id",
            description="Pre-existing backfilled template",
            parameter_schema={"org_id": "integer"},
            created_by="system",
            organization_id=None,
            usage_count=0,
            is_active=True,
        )
        db.add(template)
        db.flush()

        backfilled_vector = [1.0, 0.0, 0.0, 0.0]
        mapping = QueryTemplateMapping(
            template_id=template.id,
            question_pattern="how many feedbacks total",
            question_embedding=backfilled_vector,
            embedding_provider="openai",
            embedding_dimension=len(backfilled_vector),
            embedding_model="text-embedding-3-small",  # exact migration backfill value
            match_count=0,
        )
        db.add(mapping)
        db.commit()

        raw_question = "how many feedbacks total do we have"
        normalized_query_key = matcher.normalize_question(raw_question)

        # No per-org model_embeddings override -- effective model resolves to
        # default_model_for_provider("openai") == "text-embedding-3-small",
        # the exact value the migration backfilled onto pre-existing rows.
        embedder = _make_embedder(
            provider="openai",
            model="text-embedding-3-small",
            vectors={normalized_query_key: [0.99, 0.02, 0.0, 0.0]},  # near-identical
            default_vector=_VEC_UNRELATED,
            dim=4,
        )

        result = matcher.find_match(
            question=raw_question,
            org_id=1,
            db=db,
            embedder=embedder,
            threshold=0.85,
        )

        assert result is not None
        assert result["template_id"] == str(template.id)
        assert result["description"] == "Pre-existing backfilled template"

    def test_backfilled_row_not_matched_by_unrelated_query(self, saver, matcher, db):
        """Negative control: a genuinely distinct (orthogonal) query vector
        against the same backfilled row must NOT match -- proves this is a
        real cosine-similarity + threshold check, not a tautology."""
        from src.models.query_template import QueryTemplate
        from src.models.query_template_mapping import QueryTemplateMapping

        template = QueryTemplate(
            sql_query="SELECT COUNT(*) FROM feedback_items WHERE organization_id = :org_id",
            description="Pre-existing backfilled template",
            parameter_schema={"org_id": "integer"},
            created_by="system",
            organization_id=None,
            usage_count=0,
            is_active=True,
        )
        db.add(template)
        db.flush()

        backfilled_vector = [1.0, 0.0, 0.0, 0.0]
        mapping = QueryTemplateMapping(
            template_id=template.id,
            question_pattern="how many feedbacks total",
            question_embedding=backfilled_vector,
            embedding_provider="openai",
            embedding_dimension=len(backfilled_vector),
            embedding_model="text-embedding-3-small",
            match_count=0,
        )
        db.add(mapping)
        db.commit()

        raw_question = "something entirely unrelated to this template"
        normalized_query_key = matcher.normalize_question(raw_question)

        embedder = _make_embedder(
            provider="openai",
            model="text-embedding-3-small",
            vectors={normalized_query_key: _VEC_UNRELATED},  # orthogonal to backfilled_vector
            default_vector=_VEC_UNRELATED,
            dim=4,
        )

        result = matcher.find_match(
            question=raw_question,
            org_id=1,
            db=db,
            embedder=embedder,
            threshold=0.85,
        )

        assert result is None
