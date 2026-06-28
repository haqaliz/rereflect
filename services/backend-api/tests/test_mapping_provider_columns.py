"""
Phase 1 — TDD (RED → GREEN) tests for embedding_provider + embedding_dimension
columns on QueryTemplateMapping, and the length-based backfill rule.

Tests:
- Model has the two new columns as attributes.
- A row with a 1536-length question_embedding backfills to ('openai', 1536).
- A row with a null/short embedding backfills to stale (None, None).
- Round-trip: write a mapping with provider/dim, read it back correctly.
"""

import json
import pytest
from unittest.mock import MagicMock


# ── Helpers (mirrors the migration backfill logic) ────────────────────────────

def _backfill_provider_dim(question_embedding):
    """
    Mirrors the migration's length-based backfill rule.

    Rule:
      len == 1536 → provider='openai', dimension=1536
      null/short/other → provider=None, dimension=None (stale)

    Args:
        question_embedding: JSON string, list, or None

    Returns:
        (provider: str | None, dimension: int | None)
    """
    if question_embedding is None:
        return (None, None)

    if isinstance(question_embedding, str):
        try:
            vec = json.loads(question_embedding)
        except (json.JSONDecodeError, ValueError):
            return (None, None)
    elif isinstance(question_embedding, list):
        vec = question_embedding
    else:
        return (None, None)

    if len(vec) == 1536:
        return ("openai", 1536)
    return (None, None)


# ── Model column existence tests ──────────────────────────────────────────────

class TestModelColumns:
    """Verify that the ORM model has the new columns."""

    def test_model_has_embedding_provider_column(self):
        from src.models.query_template_mapping import QueryTemplateMapping
        mapping = QueryTemplateMapping()
        # Column must exist as an attribute (even if None by default)
        assert hasattr(mapping, "embedding_provider"), (
            "QueryTemplateMapping must have an 'embedding_provider' column"
        )

    def test_model_has_embedding_dimension_column(self):
        from src.models.query_template_mapping import QueryTemplateMapping
        mapping = QueryTemplateMapping()
        assert hasattr(mapping, "embedding_dimension"), (
            "QueryTemplateMapping must have an 'embedding_dimension' column"
        )

    def test_embedding_provider_defaults_none(self):
        from src.models.query_template_mapping import QueryTemplateMapping
        mapping = QueryTemplateMapping()
        # New rows default to None (nullable, no default)
        assert mapping.embedding_provider is None

    def test_embedding_dimension_defaults_none(self):
        from src.models.query_template_mapping import QueryTemplateMapping
        mapping = QueryTemplateMapping()
        assert mapping.embedding_dimension is None

    def test_can_set_embedding_provider(self):
        from src.models.query_template_mapping import QueryTemplateMapping
        mapping = QueryTemplateMapping(embedding_provider="openai")
        assert mapping.embedding_provider == "openai"

    def test_can_set_embedding_dimension(self):
        from src.models.query_template_mapping import QueryTemplateMapping
        mapping = QueryTemplateMapping(embedding_dimension=1536)
        assert mapping.embedding_dimension == 1536


# ── Backfill logic tests ──────────────────────────────────────────────────────

class TestBackfillLogic:
    """Verify the migration backfill rule maps vector length → provider/dim."""

    def test_1536_vector_backfills_to_openai_1536(self):
        vec = [0.1] * 1536
        provider, dim = _backfill_provider_dim(vec)
        assert provider == "openai"
        assert dim == 1536

    def test_1536_json_string_backfills_to_openai_1536(self):
        vec = json.dumps([0.1] * 1536)
        provider, dim = _backfill_provider_dim(vec)
        assert provider == "openai"
        assert dim == 1536

    def test_null_embedding_is_stale(self):
        provider, dim = _backfill_provider_dim(None)
        assert provider is None
        assert dim is None

    def test_short_embedding_is_stale(self):
        vec = [0.1] * 768  # e.g. a 768-dim local model vector
        provider, dim = _backfill_provider_dim(vec)
        assert provider is None
        assert dim is None

    def test_empty_list_is_stale(self):
        provider, dim = _backfill_provider_dim([])
        assert provider is None
        assert dim is None

    def test_non_1536_dim_is_stale(self):
        for dim_size in (384, 512, 1024, 2000):
            vec = [0.1] * dim_size
            provider, dim = _backfill_provider_dim(vec)
            assert provider is None, f"Expected stale for dim={dim_size}"
            assert dim is None, f"Expected stale for dim={dim_size}"


# ── Round-trip persistence tests (using SQLite from conftest) ─────────────────

class TestRoundTrip:
    """Write a QueryTemplateMapping with provider/dim, read it back."""

    def test_write_and_read_provider_dim(self, db):
        from src.models.query_template import QueryTemplate
        from src.models.query_template_mapping import QueryTemplateMapping

        # Create a template first (FK constraint)
        template = QueryTemplate(
            sql_query="SELECT 1",
            description="test",
            parameter_schema={},
            created_by="system",
            organization_id=None,
            usage_count=0,
            is_active=True,
        )
        db.add(template)
        db.flush()

        vec = [0.5] * 768
        mapping = QueryTemplateMapping(
            template_id=template.id,
            question_pattern="test question",
            question_embedding=vec,
            embedding_provider="openai_compatible",
            embedding_dimension=768,
            match_count=0,
        )
        db.add(mapping)
        db.commit()

        fetched = db.query(QueryTemplateMapping).filter_by(id=mapping.id).first()
        assert fetched.embedding_provider == "openai_compatible"
        assert fetched.embedding_dimension == 768

    def test_write_openai_provider_1536(self, db):
        from src.models.query_template import QueryTemplate
        from src.models.query_template_mapping import QueryTemplateMapping

        template = QueryTemplate(
            sql_query="SELECT 2",
            description="test2",
            parameter_schema={},
            created_by="system",
            organization_id=None,
            usage_count=0,
            is_active=True,
        )
        db.add(template)
        db.flush()

        vec = [0.1] * 1536
        mapping = QueryTemplateMapping(
            template_id=template.id,
            question_pattern="openai pattern",
            question_embedding=vec,
            embedding_provider="openai",
            embedding_dimension=1536,
            match_count=0,
        )
        db.add(mapping)
        db.commit()

        fetched = db.query(QueryTemplateMapping).filter_by(id=mapping.id).first()
        assert fetched.embedding_provider == "openai"
        assert fetched.embedding_dimension == 1536

    def test_stale_row_has_null_provider_dim(self, db):
        from src.models.query_template import QueryTemplate
        from src.models.query_template_mapping import QueryTemplateMapping

        template = QueryTemplate(
            sql_query="SELECT 3",
            description="test3",
            parameter_schema={},
            created_by="system",
            organization_id=None,
            usage_count=0,
            is_active=True,
        )
        db.add(template)
        db.flush()

        # No provider/dim set (stale row)
        mapping = QueryTemplateMapping(
            template_id=template.id,
            question_pattern="stale pattern",
            question_embedding=None,
            match_count=0,
        )
        db.add(mapping)
        db.commit()

        fetched = db.query(QueryTemplateMapping).filter_by(id=mapping.id).first()
        assert fetched.embedding_provider is None
        assert fetched.embedding_dimension is None
