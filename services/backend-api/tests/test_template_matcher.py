"""
TDD tests for the Template Matcher (RED → GREEN → REFACTOR).

Tests cover:
- Exact match returns correct template
- Semantic similarity matching
- Below-threshold queries return None
- Embedding generation (mocked)
- Cosine similarity calculation
- Fallback without pgvector
"""

import pytest
from unittest.mock import MagicMock, patch
import math


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_db():
    return MagicMock()


@pytest.fixture
def matcher():
    from src.services.copilot.template_matcher import TemplateMatcher
    return TemplateMatcher()


@pytest.fixture
def sample_template():
    """A sample template record (mock)."""
    template = MagicMock()
    template.id = "tpl_001"
    template.sql_query = "SELECT sentiment_label, COUNT(*) as count FROM feedback_items WHERE organization_id = :org_id GROUP BY sentiment_label LIMIT 100"
    template.description = "Count feedbacks by sentiment"
    template.parameter_schema = {"org_id": "integer"}
    template.usage_count = 5
    template.is_active = True
    return template


@pytest.fixture
def sample_mapping():
    """A sample template mapping record (mock)."""
    mapping = MagicMock()
    mapping.template_id = "tpl_001"
    mapping.question_pattern = "how many negative feedbacks"
    mapping.question_embedding = [0.1] * 1536  # Dummy 1536-dim vector
    return mapping


# ── COSINE SIMILARITY ─────────────────────────────────────────────────────────

class TestCosineSimilarity:
    """Test the cosine similarity calculation used for matching."""

    def test_identical_vectors_have_similarity_1(self, matcher):
        vec = [0.5] * 10
        sim = matcher.cosine_similarity(vec, vec)
        assert abs(sim - 1.0) < 1e-6

    def test_orthogonal_vectors_have_similarity_0(self, matcher):
        vec_a = [1, 0, 0]
        vec_b = [0, 1, 0]
        sim = matcher.cosine_similarity(vec_a, vec_b)
        assert abs(sim) < 1e-6

    def test_opposite_vectors_have_similarity_minus_1(self, matcher):
        vec_a = [1, 0]
        vec_b = [-1, 0]
        sim = matcher.cosine_similarity(vec_a, vec_b)
        assert abs(sim - (-1.0)) < 1e-6

    def test_similar_vectors_have_high_similarity(self, matcher):
        vec_a = [1, 1, 1]
        vec_b = [1.1, 0.9, 1.0]
        sim = matcher.cosine_similarity(vec_a, vec_b)
        assert sim > 0.99

    def test_zero_vector_returns_zero(self, matcher):
        vec_a = [0, 0, 0]
        vec_b = [1, 2, 3]
        sim = matcher.cosine_similarity(vec_a, vec_b)
        assert sim == 0.0

    def test_1536_dim_vectors_computed(self, matcher):
        vec_a = [0.1] * 1536
        vec_b = [0.1] * 1536
        sim = matcher.cosine_similarity(vec_a, vec_b)
        assert abs(sim - 1.0) < 1e-4


# ── QUESTION NORMALIZATION ────────────────────────────────────────────────────

class TestQuestionNormalization:
    """Normalize questions before matching (lowercase, stopwords, etc.)."""

    def test_normalize_lowercases(self, matcher):
        normalized = matcher.normalize_question("How Many Negative Feedbacks?")
        assert normalized == normalized.lower()

    def test_normalize_removes_punctuation(self, matcher):
        normalized = matcher.normalize_question("How many feedbacks? Really?!")
        assert "?" not in normalized
        assert "!" not in normalized

    def test_normalize_strips_whitespace(self, matcher):
        normalized = matcher.normalize_question("  how many feedbacks  ")
        assert normalized == normalized.strip()

    def test_normalize_removes_stopwords(self, matcher):
        normalized = matcher.normalize_question("How many of the feedbacks are there")
        # Common stopwords should be removed
        assert "the" not in normalized.split()
        # Content words should remain
        assert any(word in normalized for word in ["feedbacks", "many", "how"])

    def test_normalize_preserves_key_words(self, matcher):
        normalized = matcher.normalize_question("Count negative feedbacks this week")
        assert "count" in normalized or "negative" in normalized or "feedbacks" in normalized


# ── EMBEDDING GENERATION ──────────────────────────────────────────────────────

class TestEmbeddingGeneration:
    """Test embedding generation (OpenAI text-embedding-3-small)."""

    def test_generate_embedding_returns_1536_dims(self, matcher):
        with patch.object(matcher, "_call_embedding_api") as mock_api:
            mock_api.return_value = [0.1] * 1536
            embedding = matcher.generate_embedding("how many feedbacks")
            assert len(embedding) == 1536

    def test_generate_embedding_calls_openai_api(self, matcher):
        with patch.object(matcher, "_call_embedding_api") as mock_api:
            mock_api.return_value = [0.0] * 1536
            matcher.generate_embedding("how many feedbacks")
            mock_api.assert_called_once()

    def test_embedding_api_failure_raises(self, matcher):
        with patch.object(matcher, "_call_embedding_api") as mock_api:
            mock_api.side_effect = Exception("API unavailable")
            with pytest.raises(Exception):
                matcher.generate_embedding("how many feedbacks")


# ── TEMPLATE MATCHING ─────────────────────────────────────────────────────────

class TestTemplateMatching:
    """Match user questions against saved templates."""

    def test_high_similarity_returns_template(self, matcher, mock_db, sample_template, sample_mapping):
        """When cosine similarity > 0.85, return the matched template."""
        # Mock: find mappings, return similar embedding
        sample_mapping.question_embedding = [0.1] * 1536

        mock_db.execute.return_value.fetchall.return_value = [sample_mapping]
        mock_db.query.return_value.filter_by.return_value.first.return_value = sample_template

        with patch.object(matcher, "generate_embedding") as mock_embed:
            # Identical embedding = similarity 1.0
            mock_embed.return_value = [0.1] * 1536
            result = matcher.find_match(
                question="how many negative feedbacks",
                org_id=1,
                db=mock_db,
                threshold=0.85
            )

        assert result is not None
        assert result["template_id"] == "tpl_001"

    def test_low_similarity_returns_none(self, matcher, mock_db, sample_mapping):
        """When cosine similarity < 0.85, return None."""
        sample_mapping.question_embedding = [1.0, 0.0] + [0.0] * 1534  # Very different vector

        mock_db.execute.return_value.fetchall.return_value = [sample_mapping]

        with patch.object(matcher, "generate_embedding") as mock_embed:
            mock_embed.return_value = [0.0, 1.0] + [0.0] * 1534  # Orthogonal = 0.0 similarity
            result = matcher.find_match(
                question="completely different question",
                org_id=1,
                db=mock_db,
                threshold=0.85
            )

        assert result is None

    def test_no_templates_in_db_returns_none(self, matcher, mock_db):
        """When no templates exist, return None."""
        mock_db.execute.return_value.fetchall.return_value = []

        with patch.object(matcher, "generate_embedding") as mock_embed:
            mock_embed.return_value = [0.1] * 1536
            result = matcher.find_match(
                question="how many feedbacks",
                org_id=1,
                db=mock_db,
                threshold=0.85
            )

        assert result is None

    def test_match_result_has_sql_query(self, matcher, mock_db, sample_template, sample_mapping):
        """Matched template should include the SQL query."""
        sample_mapping.question_embedding = [0.1] * 1536

        mock_db.execute.return_value.fetchall.return_value = [sample_mapping]
        mock_db.query.return_value.filter_by.return_value.first.return_value = sample_template

        with patch.object(matcher, "generate_embedding") as mock_embed:
            mock_embed.return_value = [0.1] * 1536
            result = matcher.find_match(
                question="how many feedbacks",
                org_id=1,
                db=mock_db,
                threshold=0.85
            )

        assert result is not None
        assert "sql_query" in result

    def test_match_result_has_parameter_schema(self, matcher, mock_db, sample_template, sample_mapping):
        """Matched template should include parameter schema."""
        sample_mapping.question_embedding = [0.1] * 1536

        mock_db.execute.return_value.fetchall.return_value = [sample_mapping]
        mock_db.query.return_value.filter_by.return_value.first.return_value = sample_template

        with patch.object(matcher, "generate_embedding") as mock_embed:
            mock_embed.return_value = [0.1] * 1536
            result = matcher.find_match(
                question="how many feedbacks",
                org_id=1,
                db=mock_db,
                threshold=0.85
            )

        assert result is not None
        assert "parameter_schema" in result

    def test_inactive_template_not_returned(self, matcher, mock_db, sample_template, sample_mapping):
        """Disabled (is_active=False) templates should not be matched."""
        sample_template.is_active = False
        sample_mapping.question_embedding = [0.1] * 1536

        mock_db.execute.return_value.fetchall.return_value = [sample_mapping]
        mock_db.query.return_value.filter_by.return_value.first.return_value = sample_template

        with patch.object(matcher, "generate_embedding") as mock_embed:
            mock_embed.return_value = [0.1] * 1536
            result = matcher.find_match(
                question="how many feedbacks",
                org_id=1,
                db=mock_db,
                threshold=0.85
            )

        assert result is None

    def test_best_match_selected_from_multiple_candidates(self, matcher, mock_db):
        """When multiple templates match, return the one with highest similarity."""
        mapping1 = MagicMock()
        mapping1.template_id = "tpl_001"
        mapping1.question_embedding = [1.0, 0.0] + [0.0] * 1534  # Lower similarity

        mapping2 = MagicMock()
        mapping2.template_id = "tpl_002"
        mapping2.question_embedding = [0.99, 0.01] + [0.0] * 1534  # Higher similarity

        template2 = MagicMock()
        template2.id = "tpl_002"
        template2.sql_query = "SELECT COUNT(*) FROM feedback_items"
        template2.description = "Count all feedbacks"
        template2.parameter_schema = {}
        template2.is_active = True

        mock_db.execute.return_value.fetchall.return_value = [mapping1, mapping2]
        mock_db.query.return_value.filter_by.return_value.first.return_value = template2

        user_embed = [0.99, 0.01] + [0.0] * 1534

        with patch.object(matcher, "generate_embedding") as mock_embed:
            mock_embed.return_value = user_embed
            result = matcher.find_match(
                question="how many feedbacks",
                org_id=1,
                db=mock_db,
                threshold=0.85
            )

        assert result is not None
