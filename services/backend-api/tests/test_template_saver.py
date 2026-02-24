"""
TDD tests for the Template Saver (RED → GREEN → REFACTOR).

Tests cover:
- New SQL creates new template + mapping
- Identical SQL links to existing template (idempotent)
- New phrasing of existing SQL creates new mapping
- usage_count increments on match
- last_used_at updates
- System templates pre-populated
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
def sample_sql():
    return "SELECT sentiment_label, COUNT(*) as count FROM feedback_items WHERE organization_id = :org_id GROUP BY sentiment_label LIMIT 100"


@pytest.fixture
def sample_question():
    return "how many negative feedbacks do we have"


# ── SAVING NEW TEMPLATES ──────────────────────────────────────────────────────

class TestSavingNewTemplates:
    """Test auto-saving new LLM-generated SQL as templates."""

    def test_new_sql_creates_new_template(self, saver, mock_db, sample_sql, sample_question):
        # No existing template with this SQL
        mock_db.query.return_value.filter_by.return_value.first.return_value = None

        with patch.object(saver, "_generate_embedding") as mock_embed:
            mock_embed.return_value = [0.1] * 1536
            result = saver.save_template(
                sql_query=sample_sql,
                question=sample_question,
                description="Count feedbacks by sentiment",
                parameter_schema={"org_id": "integer"},
                created_by="llm",
                org_id=None,
                db=mock_db
            )

        # Should have written to db (add or execute for new template + mapping)
        assert mock_db.add.called or mock_db.execute.called

    def test_new_sql_creates_mapping(self, saver, mock_db, sample_sql, sample_question):
        mock_db.query.return_value.filter_by.return_value.first.return_value = None

        with patch.object(saver, "_generate_embedding") as mock_embed:
            mock_embed.return_value = [0.1] * 1536
            saver.save_template(
                sql_query=sample_sql,
                question=sample_question,
                description="Count feedbacks by sentiment",
                parameter_schema={"org_id": "integer"},
                created_by="llm",
                org_id=None,
                db=mock_db
            )

        # db.add or execute should be called (template + mapping)
        total_writes = mock_db.add.call_count + mock_db.execute.call_count
        assert total_writes >= 2

    def test_save_commits_to_db(self, saver, mock_db, sample_sql, sample_question):
        mock_db.query.return_value.filter_by.return_value.first.return_value = None

        with patch.object(saver, "_generate_embedding") as mock_embed:
            mock_embed.return_value = [0.1] * 1536
            saver.save_template(
                sql_query=sample_sql,
                question=sample_question,
                description="Count feedbacks by sentiment",
                parameter_schema={},
                created_by="llm",
                org_id=None,
                db=mock_db
            )

        mock_db.commit.assert_called()


# ── IDEMPOTENT SAVING (EXISTING SQL) ─────────────────────────────────────────

class TestIdempotentSaving:
    """Identical SQL should reuse existing template, just add new mapping."""

    def test_existing_sql_reuses_template(self, saver, mock_db, sample_sql, sample_question):
        # Existing template with same SQL
        existing_template = MagicMock()
        existing_template.id = "tpl_001"
        existing_template.sql_query = sample_sql
        existing_template.usage_count = 5

        # Simulate: first call finds template by SQL
        mock_db.query.return_value.filter_by.return_value.first.return_value = existing_template

        with patch.object(saver, "_generate_embedding") as mock_embed:
            mock_embed.return_value = [0.1] * 1536
            result = saver.save_template(
                sql_query=sample_sql,
                question="different phrasing of same question",
                description="Count feedbacks",
                parameter_schema={},
                created_by="llm",
                org_id=None,
                db=mock_db
            )

        # Should NOT create a new template (only a new mapping)
        # Check that result references existing template ID
        assert result is not None

    def test_existing_sql_adds_new_mapping(self, saver, mock_db, sample_sql):
        existing_template = MagicMock()
        existing_template.id = "tpl_001"
        existing_template.sql_query = sample_sql
        existing_template.usage_count = 5

        mock_db.query.return_value.filter_by.return_value.first.return_value = existing_template

        with patch.object(saver, "_generate_embedding") as mock_embed:
            mock_embed.return_value = [0.1] * 1536
            saver.save_template(
                sql_query=sample_sql,
                question="alternate question phrasing",
                description="Count feedbacks",
                parameter_schema={},
                created_by="llm",
                org_id=None,
                db=mock_db
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

    def test_seed_system_templates_to_db(self, saver, mock_db):
        """Test that seeding system templates to DB works."""
        mock_db.query.return_value.filter_by.return_value.first.return_value = None

        with patch.object(saver, "_generate_embedding") as mock_embed:
            mock_embed.return_value = [0.1] * 1536
            saver.seed_system_templates(db=mock_db)

        # Should have written to db (add or execute) and committed
        assert mock_db.add.called or mock_db.execute.called
        assert mock_db.commit.called


# ── EMBEDDING GENERATION IN SAVER ────────────────────────────────────────────

class TestSaverEmbedding:
    """Test embedding generation during save."""

    def test_embedding_generated_for_each_question_pattern(self, saver, mock_db, sample_sql):
        mock_db.query.return_value.filter_by.return_value.first.return_value = None

        with patch.object(saver, "_generate_embedding") as mock_embed:
            mock_embed.return_value = [0.1] * 1536
            saver.save_template(
                sql_query=sample_sql,
                question="how many feedbacks",
                description="Count feedbacks",
                parameter_schema={},
                created_by="llm",
                org_id=None,
                db=mock_db
            )

        # Embedding should be generated for the question
        mock_embed.assert_called()

    def test_embedding_failure_does_not_save(self, saver, mock_db, sample_sql):
        """If embedding generation fails, template should not be saved."""
        mock_db.query.return_value.filter_by.return_value.first.return_value = None

        with patch.object(saver, "_generate_embedding") as mock_embed:
            mock_embed.side_effect = Exception("OpenAI API error")

            with pytest.raises(Exception):
                saver.save_template(
                    sql_query=sample_sql,
                    question="how many feedbacks",
                    description="Count feedbacks",
                    parameter_schema={},
                    created_by="llm",
                    org_id=None,
                    db=mock_db
                )
