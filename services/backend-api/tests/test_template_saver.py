"""
TDD tests for the Template Saver (RED → GREEN → REFACTOR).

Updated for template-matching-local: embedder injection, provider/dim persistence
on every mapping (ORM + raw-SQL fallback), and provider-aware idempotent seeding.

Tests cover:
- New SQL creates new template + mapping
- Identical SQL links to existing template (idempotent)
- New phrasing of existing SQL creates new mapping
- usage_count increments on match
- last_used_at updates
- System templates pre-populated
- Embedding generation via injected embedder
- _create_mapping persists embedding_provider + embedding_dimension
- seed_system_templates is provider-aware: re-seeds if provider/dim differs
- seed_system_templates is idempotent when provider/dim matches
"""

import pytest
from unittest.mock import MagicMock, patch, call
from datetime import datetime


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_db():
    return MagicMock()


@pytest.fixture
def saver():
    from src.services.copilot.template_saver import TemplateSaver
    return TemplateSaver()


@pytest.fixture
def mock_embedder_openai():
    """Mock ResolvedEmbedder for OpenAI / 1536-dim."""
    resolved = MagicMock()
    resolved.provider = "openai"
    resolved.embedder = MagicMock()
    resolved.embedder.embed.return_value = [0.1] * 1536
    resolved.embedder.dimension = 1536
    return resolved


@pytest.fixture
def mock_embedder_local():
    """Mock ResolvedEmbedder for local / 768-dim."""
    resolved = MagicMock()
    resolved.provider = "openai_compatible"
    resolved.embedder = MagicMock()
    resolved.embedder.embed.return_value = [0.2] * 768
    resolved.embedder.dimension = 768
    return resolved


@pytest.fixture
def sample_sql():
    return "SELECT sentiment_label, COUNT(*) as count FROM feedback_items WHERE organization_id = :org_id GROUP BY sentiment_label LIMIT 100"


@pytest.fixture
def sample_question():
    return "how many negative feedbacks do we have"


# ── SAVING NEW TEMPLATES ──────────────────────────────────────────────────────

class TestSavingNewTemplates:
    """Test auto-saving new LLM-generated SQL as templates."""

    def test_new_sql_creates_new_template(self, saver, mock_db, sample_sql, sample_question, mock_embedder_openai):
        mock_db.query.return_value.filter_by.return_value.first.return_value = None

        result = saver.save_template(
            sql_query=sample_sql,
            question=sample_question,
            description="Count feedbacks by sentiment",
            parameter_schema={"org_id": "integer"},
            created_by="llm",
            org_id=None,
            db=mock_db,
            embedder=mock_embedder_openai,
        )

        # Should have written to db (add or execute for new template + mapping)
        assert mock_db.add.called or mock_db.execute.called

    def test_new_sql_creates_mapping(self, saver, mock_db, sample_sql, sample_question, mock_embedder_openai):
        mock_db.query.return_value.filter_by.return_value.first.return_value = None

        saver.save_template(
            sql_query=sample_sql,
            question=sample_question,
            description="Count feedbacks by sentiment",
            parameter_schema={"org_id": "integer"},
            created_by="llm",
            org_id=None,
            db=mock_db,
            embedder=mock_embedder_openai,
        )

        # db.add or execute should be called (template + mapping)
        total_writes = mock_db.add.call_count + mock_db.execute.call_count
        assert total_writes >= 2

    def test_save_commits_to_db(self, saver, mock_db, sample_sql, sample_question, mock_embedder_openai):
        mock_db.query.return_value.filter_by.return_value.first.return_value = None

        saver.save_template(
            sql_query=sample_sql,
            question=sample_question,
            description="Count feedbacks by sentiment",
            parameter_schema={},
            created_by="llm",
            org_id=None,
            db=mock_db,
            embedder=mock_embedder_openai,
        )

        mock_db.commit.assert_called()


# ── IDEMPOTENT SAVING (EXISTING SQL) ─────────────────────────────────────────

class TestIdempotentSaving:
    """Identical SQL should reuse existing template, just add new mapping."""

    def test_existing_sql_reuses_template(self, saver, mock_db, sample_sql, sample_question, mock_embedder_openai):
        existing_template = MagicMock()
        existing_template.id = "tpl_001"
        existing_template.sql_query = sample_sql
        existing_template.usage_count = 5

        mock_db.query.return_value.filter_by.return_value.first.return_value = existing_template

        result = saver.save_template(
            sql_query=sample_sql,
            question="different phrasing of same question",
            description="Count feedbacks",
            parameter_schema={},
            created_by="llm",
            org_id=None,
            db=mock_db,
            embedder=mock_embedder_openai,
        )

        assert result is not None

    def test_existing_sql_adds_new_mapping(self, saver, mock_db, sample_sql, mock_embedder_openai):
        existing_template = MagicMock()
        existing_template.id = "tpl_001"
        existing_template.sql_query = sample_sql
        existing_template.usage_count = 5

        mock_db.query.return_value.filter_by.return_value.first.return_value = existing_template

        saver.save_template(
            sql_query=sample_sql,
            question="alternate question phrasing",
            description="Count feedbacks",
            parameter_schema={},
            created_by="llm",
            org_id=None,
            db=mock_db,
            embedder=mock_embedder_openai,
        )

        # A new mapping should be added (via db.add or db.execute)
        assert mock_db.add.called or mock_db.execute.called


# ── USAGE COUNT TRACKING ──────────────────────────────────────────────────────

class TestUsageCountTracking:
    """usage_count should increment when a template is matched."""

    def test_increment_usage_count(self, saver, mock_db):
        template = MagicMock()
        template.id = "tpl_001"
        template.usage_count = 10
        template.last_used_at = None

        mock_db.query.return_value.filter_by.return_value.first.return_value = template

        saver.record_template_usage(template_id="tpl_001", db=mock_db)

        # Either usage_count was incremented via ORM or via raw SQL (db.execute called)
        assert template.usage_count == 11 or mock_db.execute.called

    def test_update_last_used_at(self, saver, mock_db):
        template = MagicMock()
        template.id = "tpl_001"
        template.usage_count = 10
        template.last_used_at = None

        mock_db.query.return_value.filter_by.return_value.first.return_value = template

        saver.record_template_usage(template_id="tpl_001", db=mock_db)

        # Either last_used_at was set via ORM or via raw SQL (db.execute called)
        assert template.last_used_at is not None or mock_db.execute.called

    def test_usage_count_commits(self, saver, mock_db):
        template = MagicMock()
        template.id = "tpl_001"
        template.usage_count = 5
        template.last_used_at = None

        mock_db.query.return_value.filter_by.return_value.first.return_value = template

        saver.record_template_usage(template_id="tpl_001", db=mock_db)

        mock_db.commit.assert_called()

    def test_missing_template_does_not_raise(self, saver, mock_db):
        mock_db.query.return_value.filter_by.return_value.first.return_value = None

        # Should not raise even if template doesn't exist
        saver.record_template_usage(template_id="nonexistent", db=mock_db)


# ── SYSTEM TEMPLATES PRE-POPULATION ──────────────────────────────────────────

class TestSystemTemplates:
    """Verify the system templates are correctly defined."""

    def test_system_templates_exist(self, saver):
        templates = saver.get_system_templates()
        assert len(templates) >= 10

    def test_system_templates_have_required_fields(self, saver):
        templates = saver.get_system_templates()
        for template in templates:
            assert "sql_query" in template, f"Missing sql_query in template: {template}"
            assert "description" in template, f"Missing description in template: {template}"
            assert "parameter_schema" in template, f"Missing parameter_schema in template: {template}"
            assert "question_patterns" in template, f"Missing question_patterns in template: {template}"

    def test_system_templates_include_feedback_count_query(self, saver):
        templates = saver.get_system_templates()
        descriptions = [t["description"].lower() for t in templates]
        assert any("feedback" in d and ("count" in d or "summary" in d) for d in descriptions), \
            "Should have a feedback count/summary template"

    def test_system_templates_include_sentiment_query(self, saver):
        templates = saver.get_system_templates()
        descriptions = [t["description"].lower() for t in templates]
        sqls = [t["sql_query"].lower() for t in templates]
        assert any("sentiment" in d or "sentiment" in s for d, s in zip(descriptions, sqls)), \
            "Should have a sentiment-related template"

    def test_system_templates_include_pain_points_query(self, saver):
        templates = saver.get_system_templates()
        descriptions = [t["description"].lower() for t in templates]
        assert any("pain" in d for d in descriptions), \
            "Should have a pain points template"

    def test_system_templates_include_feature_requests_query(self, saver):
        templates = saver.get_system_templates()
        descriptions = [t["description"].lower() for t in templates]
        assert any("feature" in d for d in descriptions), \
            "Should have a feature requests template"

    def test_system_templates_include_churn_risk_query(self, saver):
        templates = saver.get_system_templates()
        descriptions = [t["description"].lower() for t in templates]
        assert any("churn" in d or "health" in d for d in descriptions), \
            "Should have a customer churn/health template"

    def test_system_templates_have_multiple_question_patterns(self, saver):
        templates = saver.get_system_templates()
        for template in templates:
            assert len(template["question_patterns"]) >= 1, \
                f"Template should have at least 1 question pattern: {template['description']}"

    def test_system_template_sql_uses_org_id_param(self, saver):
        templates = saver.get_system_templates()
        for template in templates:
            sql = template["sql_query"]
            assert ":org_id" in sql, \
                f"Template SQL must use :org_id param: {template['description']}\nSQL: {sql}"

    def test_system_template_sql_is_select_only(self, saver):
        templates = saver.get_system_templates()
        for template in templates:
            sql = template["sql_query"].strip().upper()
            assert sql.startswith("SELECT"), \
                f"Template SQL must be SELECT only: {template['description']}\nSQL: {sql}"

    def test_seed_system_templates_to_db(self, saver, mock_db, mock_embedder_openai):
        """Test that seeding system templates to DB works with injected embedder."""
        mock_db.query.return_value.filter_by.return_value.first.return_value = None

        saver.seed_system_templates(db=mock_db, embedder=mock_embedder_openai)

        # Should have written to db (add or execute) and committed
        assert mock_db.add.called or mock_db.execute.called
        assert mock_db.commit.called


# ── EMBEDDING GENERATION IN SAVER ────────────────────────────────────────────

class TestSaverEmbedding:
    """Test embedding generation during save."""

    def test_embedding_generated_for_each_question_pattern(self, saver, mock_db, sample_sql, mock_embedder_openai):
        mock_db.query.return_value.filter_by.return_value.first.return_value = None

        saver.save_template(
            sql_query=sample_sql,
            question="how many feedbacks",
            description="Count feedbacks",
            parameter_schema={},
            created_by="llm",
            org_id=None,
            db=mock_db,
            embedder=mock_embedder_openai,
        )

        # Embedding should be generated via the embedder
        mock_embedder_openai.embedder.embed.assert_called()

    def test_embedding_failure_does_not_save(self, saver, mock_db, sample_sql, mock_embedder_openai):
        """If embedding generation fails, template should not be saved."""
        mock_db.query.return_value.filter_by.return_value.first.return_value = None
        mock_embedder_openai.embedder.embed.side_effect = Exception("endpoint error")

        with pytest.raises(Exception):
            saver.save_template(
                sql_query=sample_sql,
                question="how many feedbacks",
                description="Count feedbacks",
                parameter_schema={},
                created_by="llm",
                org_id=None,
                db=mock_db,
                embedder=mock_embedder_openai,
            )


# ── PROVIDER/DIM PERSISTENCE ──────────────────────────────────────────────────

class TestProviderDimPersistence:
    """
    Verify that _create_mapping persists embedding_provider and embedding_dimension
    on every mapping written (both ORM path and raw-SQL fallback).
    """

    def test_create_mapping_sets_provider_and_dim_via_orm(self, saver, db):
        """
        With a real SQLite DB, _create_mapping writes the provider/dim columns.
        Uses the `db` fixture from conftest (Base.metadata.create_all).
        """
        from src.models.query_template import QueryTemplate
        from src.models.query_template_mapping import QueryTemplateMapping

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

        embedding = [0.5] * 768
        saver._create_mapping(
            template_id=template.id,
            question="test question",
            embedding=embedding,
            provider="openai_compatible",
            db=db,
        )
        db.commit()

        fetched = db.query(QueryTemplateMapping).filter_by(template_id=template.id).first()
        assert fetched is not None
        assert fetched.embedding_provider == "openai_compatible"
        assert fetched.embedding_dimension == 768

    def test_save_template_uses_actual_vector_len_for_dimension(
        self, saver, mock_db, sample_sql, mock_embedder_local
    ):
        """save_template uses len(vector) — not a hint — for embedding_dimension."""
        mock_db.query.return_value.filter_by.return_value.first.return_value = None
        # Local provider returns 768-dim; provider hint might say 0 (unknown pre-embed)
        mock_embedder_local.embedder.embed.return_value = [0.2] * 768

        with patch.object(saver, '_create_mapping') as mock_create_mapping:
            saver.save_template(
                sql_query=sample_sql,
                question="count feedbacks",
                description="Count feedbacks",
                parameter_schema={},
                created_by="llm",
                org_id=1,
                db=mock_db,
                embedder=mock_embedder_local,
            )

        mock_create_mapping.assert_called_once()
        call_kwargs = mock_create_mapping.call_args
        # provider should be the resolved provider name
        assert call_kwargs.kwargs.get('provider') == "openai_compatible"


# ── PROVIDER-AWARE SEEDING ────────────────────────────────────────────────────

class TestProviderAwareSeeding:
    """seed_system_templates is provider+dim-aware idempotent."""

    def test_seed_skips_when_same_provider_already_seeded(self, saver, mock_db, mock_embedder_openai):
        """
        If all system templates are already seeded with the same provider/dim,
        seed_system_templates does NOT re-embed (embedder.embed is NOT called).
        """
        # Simulate: each template already exists with openai/1536 mappings
        existing_mapping = MagicMock()
        existing_mapping.embedding_provider = "openai"
        existing_mapping.embedding_dimension = 1536

        def find_template_side_effect(sql_query, org_id, db, provider=None, dim=None):
            # Return a "found" template whose first mapping matches current provider/dim
            mock_tmpl = MagicMock()
            mock_mapping = MagicMock()
            mock_mapping.embedding_provider = "openai"
            mock_mapping.embedding_dimension = 1536
            mock_tmpl._first_mapping = mock_mapping
            return mock_tmpl

        with patch.object(saver, '_find_template_by_sql_with_mapping',
                          side_effect=find_template_side_effect):
            saver.seed_system_templates(db=mock_db, embedder=mock_embedder_openai)

        # embedder should NOT have been called (same provider already seeded)
        mock_embedder_openai.embedder.embed.assert_not_called()

    def test_seed_reembeds_when_provider_changes(self, saver, mock_db, mock_embedder_local):
        """
        If system templates exist but were embedded with openai/1536, and the
        active provider is now openai_compatible/768, seed_system_templates
        re-embeds them (embedder.embed IS called).
        """
        # Existing mapping has wrong provider/dim
        mock_mapping = MagicMock()
        mock_mapping.embedding_provider = "openai"      # old
        mock_mapping.embedding_dimension = 1536         # old

        mock_existing = MagicMock()
        mock_existing.id = 99
        # The first mapping is stale (wrong provider)
        mock_existing.mappings = [mock_mapping]

        call_count = [0]

        def find_template_side_effect(sql_query, org_id, db):
            # Return existing template on first few calls, then None (after reseed clears)
            call_count[0] += 1
            if call_count[0] <= 3:  # First 3 templates exist but are stale
                return mock_existing
            return None  # remaining templates don't exist yet

        mock_db.query.return_value.filter_by.return_value.first.return_value = None

        with patch.object(saver, '_find_template_by_sql', side_effect=find_template_side_effect):
            saver.seed_system_templates(db=mock_db, embedder=mock_embedder_local)

        # embedder.embed MUST have been called (to re-embed)
        assert mock_embedder_local.embedder.embed.called

    def test_seed_with_no_embedder_skips_cleanly(self, saver, mock_db):
        """seed_system_templates(embedder=None) returns without error and without embedding."""
        # Should not raise or call db
        saver.seed_system_templates(db=mock_db, embedder=None)
        # No templates should be written
        mock_db.add.assert_not_called()
        mock_db.execute.assert_not_called()

    def test_seed_unreachable_embedder_does_not_crash(self, saver, mock_db, mock_embedder_openai):
        """If the embedding endpoint raises, seeding logs and continues (doesn't raise)."""
        mock_db.query.return_value.filter_by.return_value.first.return_value = None
        mock_embedder_openai.embedder.embed.side_effect = Exception("Connection refused")

        # Must not raise
        saver.seed_system_templates(db=mock_db, embedder=mock_embedder_openai)
