"""
RED: Tests for the effective embedding model threaded through ResolvedEmbedder.

Part of feature local-embedding-quality (M5.4), aspect staleness-model-key (Task 1).

Contract:
  - ResolvedEmbedder gains a `model` field.
  - `resolve_embedding_provider` computes
    `effective_model = model_embeddings or default_model_for_provider(provider)`
    and threads it into ResolvedEmbedder.model.
  - `default_model_for_provider` is a small pure helper in
    src/services/embeddings/defaults.py, exported from the package's public
    surface (src/services/embeddings/__init__.py).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.services.embeddings import default_model_for_provider
from src.services.embeddings.resolver import resolve_embedding_provider


def _make_config(
    default_provider: str = "openai",
    base_url: str | None = None,
    model_embeddings: str | None = None,
    has_model_embeddings: bool = True,
) -> MagicMock:
    """Build a minimal OrgAIConfig mock.

    has_model_embeddings=False simulates the pre-migration schema where the
    column does not exist at all (getattr(..., None) path), matching the
    style used in tests/embeddings/test_resolver.py.
    """
    cfg = MagicMock()
    cfg.default_provider = default_provider
    cfg.base_url = base_url
    if has_model_embeddings:
        cfg.model_embeddings = model_embeddings
    else:
        del cfg.model_embeddings
    return cfg


def _make_db_with_config(config) -> MagicMock:
    """Build a DB session mock that returns the given OrgAIConfig."""
    db = MagicMock()
    query_mock = MagicMock()
    query_mock.filter_by.return_value.first.return_value = config
    db.query.return_value = query_mock
    return db


class TestDefaultModelForProvider:
    """Pure-function contract for default_model_for_provider."""

    def test_openai_default(self):
        assert default_model_for_provider("openai") == "text-embedding-3-small"

    def test_google_default(self):
        assert default_model_for_provider("google") == "models/text-embedding-004"

    def test_ollama_default(self):
        assert default_model_for_provider("ollama") == "nomic-embed-text"

    def test_openai_compatible_has_no_default(self):
        assert default_model_for_provider("openai_compatible") is None

    def test_anthropic_has_no_default(self):
        assert default_model_for_provider("anthropic") is None

    def test_unknown_provider_has_no_default(self):
        assert default_model_for_provider("some_future_provider") is None


class TestResolvedEmbedderModelField:
    """resolve_embedding_provider must thread the effective model through."""

    def test_configured_model_embeddings_is_used_verbatim(self):
        """When config.model_embeddings is set, ResolvedEmbedder.model must match it."""
        config = _make_config(
            default_provider="openai",
            model_embeddings="text-embedding-3-large",
        )
        db = _make_db_with_config(config)

        with patch(
            "src.services.embeddings.resolver.resolve_org_byok_key",
            return_value="sk-real-key",
        ):
            result = resolve_embedding_provider(org_id=1, db=db)

        assert result is not None
        assert result.model == "text-embedding-3-large"
        assert result.model == config.model_embeddings

    def test_null_model_embeddings_falls_back_to_provider_default_openai(self):
        """When model_embeddings is NULL, ResolvedEmbedder.model must be the provider default."""
        config = _make_config(default_provider="openai", model_embeddings=None)
        db = _make_db_with_config(config)

        with patch(
            "src.services.embeddings.resolver.resolve_org_byok_key",
            return_value="sk-real-key",
        ):
            result = resolve_embedding_provider(org_id=1, db=db)

        assert result is not None
        assert result.model == default_model_for_provider("openai")
        assert result.model == "text-embedding-3-small"

    def test_null_model_embeddings_falls_back_to_provider_default_ollama(self):
        """Local provider path: model falls back to default_model_for_provider too."""
        config = _make_config(
            default_provider="ollama",
            base_url="http://localhost:11434/v1",
            model_embeddings=None,
        )
        db = _make_db_with_config(config)

        with patch("src.services.embeddings.resolver.resolve_org_byok_key"):
            result = resolve_embedding_provider(org_id=1, db=db)

        assert result is not None
        assert result.model == "nomic-embed-text"

    def test_missing_model_embeddings_column_falls_back_to_default(self):
        """Pre-migration schema (no model_embeddings column at all) must still
        produce a non-None effective model via the provider default."""
        config = _make_config(default_provider="google", has_model_embeddings=False)
        db = _make_db_with_config(config)

        with patch(
            "src.services.embeddings.resolver.resolve_org_byok_key",
            return_value="google-key",
        ):
            result = resolve_embedding_provider(org_id=1, db=db)

        assert result is not None
        assert result.model == "models/text-embedding-004"

    def test_openai_compatible_with_no_configured_model_is_none(self):
        """openai_compatible has no provider default; with no configured model,
        the effective model stays None (no silent fabrication)."""
        config = _make_config(
            default_provider="openai_compatible",
            base_url="http://localhost:8080/v1",
            model_embeddings=None,
        )
        db = _make_db_with_config(config)

        with patch("src.services.embeddings.resolver.resolve_org_byok_key"):
            result = resolve_embedding_provider(org_id=1, db=db)

        assert result is not None
        assert result.model is None


class TestResolverRegressionUnchanged:
    """Existing degrade-matrix behaviour must be unaffected by the model field."""

    def test_no_org_ai_config_still_returns_none(self):
        db = MagicMock()
        query_mock = MagicMock()
        query_mock.filter_by.return_value.first.return_value = None
        db.query.return_value = query_mock

        result = resolve_embedding_provider(org_id=999, db=db)

        assert result is None

    def test_openai_compatible_without_base_url_still_returns_none(self):
        config = _make_config(default_provider="openai_compatible", base_url=None)
        db = _make_db_with_config(config)

        result = resolve_embedding_provider(org_id=1, db=db)

        assert result is None

    def test_openai_without_byok_key_still_returns_none(self):
        config = _make_config(default_provider="openai")
        db = _make_db_with_config(config)

        with patch(
            "src.services.embeddings.resolver.resolve_org_byok_key",
            return_value=None,
        ):
            result = resolve_embedding_provider(org_id=1, db=db)

        assert result is None
