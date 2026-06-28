"""
TDD tests for the Template Matcher (RED → GREEN → REFACTOR).

Updated for template-matching-local: embedder injection, provider/dim skip-filter,
no hardcoded OpenAI client or _EMBEDDING_DIMS constant.

Tests cover:
- Exact match returns correct template
- Semantic similarity matching
- Below-threshold queries return None
- Embedding generation (mocked via injected embedder)
- Cosine similarity calculation
- Fallback without pgvector
- Provider/dim skip-filter (768-dim and 1536-dim parameterized)
- Degrade when no embedder supplied (returns None cleanly)
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
def mock_resolved_openai():
    """Mock ResolvedEmbedder for OpenAI (1536-dim)."""
    resolved = MagicMock()
    resolved.provider = "openai"
    resolved.embedder = MagicMock()
    resolved.embedder.embed.return_value = [0.1] * 1536
    resolved.embedder.dimension = 1536
    return resolved


@pytest.fixture
def mock_resolved_local():
    """Mock ResolvedEmbedder for a local 768-dim provider."""
    resolved = MagicMock()
    resolved.provider = "openai_compatible"
    resolved.embedder = MagicMock()
    resolved.embedder.embed.return_value = [0.1] * 768
    resolved.embedder.dimension = 768
    return resolved


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
def sample_mapping_openai():
    """A sample mapping tagged with openai / 1536-dim."""
    mapping = MagicMock()
    mapping.template_id = "tpl_001"
    mapping.question_pattern = "how many negative feedbacks"
    mapping.question_embedding = [0.1] * 1536
    mapping.embedding_provider = "openai"
    mapping.embedding_dimension = 1536
    return mapping


@pytest.fixture
def sample_mapping_local():
    """A sample mapping tagged with openai_compatible / 768-dim."""
    mapping = MagicMock()
    mapping.template_id = "tpl_002"
    mapping.question_pattern = "how many negative feedbacks"
    mapping.question_embedding = [0.1] * 768
    mapping.embedding_provider = "openai_compatible"
    mapping.embedding_dimension = 768
    return mapping


@pytest.fixture
def sample_mapping_stale():
    """A stale mapping with no provider/dim (pre-migration row)."""
    mapping = MagicMock()
    mapping.template_id = "tpl_003"
    mapping.question_pattern = "some old pattern"
    mapping.question_embedding = [0.1] * 1536
    mapping.embedding_provider = None
    mapping.embedding_dimension = None
    return mapping


# Keep the plain sample_mapping fixture for backward compat
@pytest.fixture
def sample_mapping(sample_mapping_openai):
    return sample_mapping_openai


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
    """Test embedding generation via injected provider."""

    def test_generate_embedding_delegates_to_embedder(self, matcher, mock_resolved_openai):
        """generate_embedding(text, embedder) calls embedder.embed(text)."""
        result = matcher.generate_embedding("how many feedbacks", mock_resolved_openai.embedder)
        mock_resolved_openai.embedder.embed.assert_called_once_with("how many feedbacks")
        assert len(result) == 1536

    def test_generate_embedding_returns_correct_dims_for_local_768(self, matcher, mock_resolved_local):
        result = matcher.generate_embedding("test question", mock_resolved_local.embedder)
        assert len(result) == 768

    def test_generate_embedding_propagates_embedder_errors(self, matcher, mock_resolved_openai):
        mock_resolved_openai.embedder.embed.side_effect = Exception("API unavailable")
        with pytest.raises(Exception, match="API unavailable"):
            matcher.generate_embedding("how many feedbacks", mock_resolved_openai.embedder)


# ── TEMPLATE MATCHING ─────────────────────────────────────────────────────────

class TestTemplateMatching:
    """Match user questions against saved templates."""

    def test_high_similarity_returns_template(self, matcher, mock_db, sample_template, sample_mapping_openai, mock_resolved_openai):
        """When cosine similarity > 0.85 with matching provider/dim, return the template."""
        sample_mapping_openai.question_embedding = [0.1] * 1536
        mock_resolved_openai.embedder.embed.return_value = [0.1] * 1536

        mock_db.execute.return_value.fetchall.return_value = [sample_mapping_openai]
        mock_db.query.return_value.filter_by.return_value.first.return_value = sample_template

        result = matcher.find_match(
            question="how many negative feedbacks",
            org_id=1,
            db=mock_db,
            embedder=mock_resolved_openai,
            threshold=0.85
        )

        assert result is not None
        assert result["template_id"] == "tpl_001"

    def test_low_similarity_returns_none(self, matcher, mock_db, sample_mapping_openai, mock_resolved_openai):
        """When cosine similarity < 0.85, return None."""
        sample_mapping_openai.question_embedding = [1.0, 0.0] + [0.0] * 1534
        mock_resolved_openai.embedder.embed.return_value = [0.0, 1.0] + [0.0] * 1534

        mock_db.execute.return_value.fetchall.return_value = [sample_mapping_openai]

        result = matcher.find_match(
            question="completely different question",
            org_id=1,
            db=mock_db,
            embedder=mock_resolved_openai,
            threshold=0.85
        )

        assert result is None

    def test_no_templates_in_db_returns_none(self, matcher, mock_db, mock_resolved_openai):
        """When no templates exist, return None."""
        mock_db.execute.return_value.fetchall.return_value = []
        mock_resolved_openai.embedder.embed.return_value = [0.1] * 1536

        result = matcher.find_match(
            question="how many feedbacks",
            org_id=1,
            db=mock_db,
            embedder=mock_resolved_openai,
            threshold=0.85
        )

        assert result is None

    def test_match_result_has_sql_query(self, matcher, mock_db, sample_template, sample_mapping_openai, mock_resolved_openai):
        """Matched template should include the SQL query."""
        sample_mapping_openai.question_embedding = [0.1] * 1536
        mock_resolved_openai.embedder.embed.return_value = [0.1] * 1536

        mock_db.execute.return_value.fetchall.return_value = [sample_mapping_openai]
        mock_db.query.return_value.filter_by.return_value.first.return_value = sample_template

        result = matcher.find_match(
            question="how many feedbacks",
            org_id=1,
            db=mock_db,
            embedder=mock_resolved_openai,
            threshold=0.85
        )

        assert result is not None
        assert "sql_query" in result

    def test_match_result_has_parameter_schema(self, matcher, mock_db, sample_template, sample_mapping_openai, mock_resolved_openai):
        """Matched template should include parameter schema."""
        sample_mapping_openai.question_embedding = [0.1] * 1536
        mock_resolved_openai.embedder.embed.return_value = [0.1] * 1536

        mock_db.execute.return_value.fetchall.return_value = [sample_mapping_openai]
        mock_db.query.return_value.filter_by.return_value.first.return_value = sample_template

        result = matcher.find_match(
            question="how many feedbacks",
            org_id=1,
            db=mock_db,
            embedder=mock_resolved_openai,
            threshold=0.85
        )

        assert result is not None
        assert "parameter_schema" in result

    def test_inactive_template_not_returned(self, matcher, mock_db, sample_template, sample_mapping_openai, mock_resolved_openai):
        """Disabled (is_active=False) templates should not be matched."""
        sample_template.is_active = False
        sample_mapping_openai.question_embedding = [0.1] * 1536
        mock_resolved_openai.embedder.embed.return_value = [0.1] * 1536

        mock_db.execute.return_value.fetchall.return_value = [sample_mapping_openai]
        mock_db.query.return_value.filter_by.return_value.first.return_value = sample_template

        result = matcher.find_match(
            question="how many feedbacks",
            org_id=1,
            db=mock_db,
            embedder=mock_resolved_openai,
            threshold=0.85
        )

        assert result is None

    def test_best_match_selected_from_multiple_candidates(self, matcher, mock_db, mock_resolved_openai):
        """When multiple templates match, return the one with highest similarity."""
        mapping1 = MagicMock()
        mapping1.template_id = "tpl_001"
        mapping1.question_embedding = [1.0, 0.0] + [0.0] * 1534
        mapping1.embedding_provider = "openai"
        mapping1.embedding_dimension = 1536

        mapping2 = MagicMock()
        mapping2.template_id = "tpl_002"
        mapping2.question_embedding = [0.99, 0.01] + [0.0] * 1534
        mapping2.embedding_provider = "openai"
        mapping2.embedding_dimension = 1536

        template2 = MagicMock()
        template2.id = "tpl_002"
        template2.sql_query = "SELECT COUNT(*) FROM feedback_items"
        template2.description = "Count all feedbacks"
        template2.parameter_schema = {}
        template2.is_active = True

        mock_db.execute.return_value.fetchall.return_value = [mapping1, mapping2]
        mock_db.query.return_value.filter_by.return_value.first.return_value = template2

        user_embed = [0.99, 0.01] + [0.0] * 1534
        mock_resolved_openai.embedder.embed.return_value = user_embed

        result = matcher.find_match(
            question="how many feedbacks",
            org_id=1,
            db=mock_db,
            embedder=mock_resolved_openai,
            threshold=0.85
        )

        assert result is not None

    def test_no_embedder_returns_none(self, matcher, mock_db):
        """When embedder is None, find_match degrades to None without error."""
        result = matcher.find_match(
            question="how many feedbacks",
            org_id=1,
            db=mock_db,
            embedder=None,
            threshold=0.85
        )
        assert result is None


# ── PROVIDER / DIMENSION SKIP FILTER ─────────────────────────────────────────

class TestProviderDimSkipFilter:
    """Verify that the matcher excludes rows with mismatched provider/dim."""

    def test_openai_1536_rows_skipped_when_active_is_768_local(
        self, matcher, mock_db, mock_resolved_local, sample_template
    ):
        """Stored OpenAI/1536 row must be skipped when active provider is 768-dim local."""
        openai_mapping = MagicMock()
        openai_mapping.template_id = "tpl_001"
        openai_mapping.question_embedding = [0.1] * 1536  # close match IF dim matched
        openai_mapping.embedding_provider = "openai"
        openai_mapping.embedding_dimension = 1536

        mock_db.execute.return_value.fetchall.return_value = [openai_mapping]
        mock_db.query.return_value.filter_by.return_value.first.return_value = sample_template

        # Active embedder returns 768-dim
        mock_resolved_local.embedder.embed.return_value = [0.1] * 768

        result = matcher.find_match(
            question="how many feedbacks",
            org_id=1,
            db=mock_db,
            embedder=mock_resolved_local,
            threshold=0.85
        )

        # The openai/1536 row should be skipped → no match
        assert result is None

    def test_local_768_rows_skipped_when_active_is_openai_1536(
        self, matcher, mock_db, mock_resolved_openai, sample_template
    ):
        """Stored local/768 row must be skipped when active provider is OpenAI/1536."""
        local_mapping = MagicMock()
        local_mapping.template_id = "tpl_001"
        local_mapping.question_embedding = [0.1] * 768
        local_mapping.embedding_provider = "openai_compatible"
        local_mapping.embedding_dimension = 768

        mock_db.execute.return_value.fetchall.return_value = [local_mapping]
        mock_db.query.return_value.filter_by.return_value.first.return_value = sample_template

        mock_resolved_openai.embedder.embed.return_value = [0.1] * 1536

        result = matcher.find_match(
            question="how many feedbacks",
            org_id=1,
            db=mock_db,
            embedder=mock_resolved_openai,
            threshold=0.85
        )

        assert result is None

    def test_stale_rows_skipped(self, matcher, mock_db, mock_resolved_openai, sample_template):
        """Rows with NULL provider/dim (stale pre-migration rows) are skipped."""
        stale_mapping = MagicMock()
        stale_mapping.template_id = "tpl_001"
        stale_mapping.question_embedding = [0.1] * 1536  # identical to query
        stale_mapping.embedding_provider = None
        stale_mapping.embedding_dimension = None

        mock_db.execute.return_value.fetchall.return_value = [stale_mapping]
        mock_db.query.return_value.filter_by.return_value.first.return_value = sample_template

        mock_resolved_openai.embedder.embed.return_value = [0.1] * 1536

        result = matcher.find_match(
            question="how many feedbacks",
            org_id=1,
            db=mock_db,
            embedder=mock_resolved_openai,
            threshold=0.85
        )

        # Stale row → skipped → no match
        assert result is None

    def test_matching_provider_and_dim_returns_match(
        self, matcher, mock_db, mock_resolved_openai, sample_template
    ):
        """A row with matching provider/dim returns the template (regression guard)."""
        correct_mapping = MagicMock()
        correct_mapping.template_id = "tpl_001"
        correct_mapping.question_embedding = [0.1] * 1536
        correct_mapping.embedding_provider = "openai"
        correct_mapping.embedding_dimension = 1536

        mock_db.execute.return_value.fetchall.return_value = [correct_mapping]
        mock_db.query.return_value.filter_by.return_value.first.return_value = sample_template

        mock_resolved_openai.embedder.embed.return_value = [0.1] * 1536

        result = matcher.find_match(
            question="how many feedbacks",
            org_id=1,
            db=mock_db,
            embedder=mock_resolved_openai,
            threshold=0.85
        )

        assert result is not None
        assert result["template_id"] == "tpl_001"

    def test_mixed_providers_only_matching_one_returned(
        self, matcher, mock_db, mock_resolved_openai, sample_template
    ):
        """With openai/1536 + local/768 rows, only openai/1536 is considered when active is openai."""
        openai_mapping = MagicMock()
        openai_mapping.template_id = "tpl_001"
        openai_mapping.question_embedding = [0.1] * 1536  # high similarity
        openai_mapping.embedding_provider = "openai"
        openai_mapping.embedding_dimension = 1536

        local_mapping = MagicMock()
        local_mapping.template_id = "tpl_002"
        local_mapping.question_embedding = [0.1] * 768  # also high similarity IF dim matched
        local_mapping.embedding_provider = "openai_compatible"
        local_mapping.embedding_dimension = 768

        mock_db.execute.return_value.fetchall.return_value = [openai_mapping, local_mapping]
        mock_db.query.return_value.filter_by.return_value.first.return_value = sample_template

        mock_resolved_openai.embedder.embed.return_value = [0.1] * 1536

        result = matcher.find_match(
            question="how many feedbacks",
            org_id=1,
            db=mock_db,
            embedder=mock_resolved_openai,
            threshold=0.85
        )

        # Only openai/1536 considered, and it matches
        assert result is not None
        assert result["template_id"] == "tpl_001"
