"""
Phase 5 RED: Tests for resolve_embedding_provider.


Degrade matrix (the contract the whole feature leans on):
  1. Org with default_provider="openai" + valid BYOK key
     → ResolvedEmbedder with openai provider, not None
  2. Org with default_provider="openai_compatible" + base_url + no key
     → ResolvedEmbedder with local embedder (keyless), not None
  3. Org with openai_compatible but no base_url
     → None (cannot build without endpoint)
  4. Org with openai but no BYOK key
     → None (no key, no embedder)
  5. No OrgAIConfig row for the org
     → None (nothing configured)
  6. ResolvedEmbedder shape: has .provider (str), .embedder (EmbeddingProvider), .dimension_hint (int)
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from src.services.embeddings.resolver import resolve_embedding_provider, ResolvedEmbedder
from src.services.embeddings.base import EmbeddingProvider
from src.services.embeddings.providers.openai import OpenAIEmbeddingProvider
from src.services.embeddings.providers.openai_compatible import (
    OpenAICompatibleEmbeddingProvider,
)


def _make_config(
    default_provider: str = "openai",
    base_url: str | None = None,
    model_embeddings: str | None = None,
) -> MagicMock:
    """Build a minimal OrgAIConfig mock."""
    cfg = MagicMock()
    cfg.default_provider = default_provider
    cfg.base_url = base_url
    # model_embeddings does not exist in the current DB schema (added in template-matching-local)
    # Use getattr(config, "model_embeddings", None) in the resolver.
    # We set it here to simulate the future column.
    del cfg.model_embeddings  # make getattr return AttributeError → None via getattr default
    return cfg


def _make_db_with_config(config) -> MagicMock:
    """Build a DB session mock that returns the given OrgAIConfig."""
    db = MagicMock()
    query_mock = MagicMock()
    query_mock.filter_by.return_value.first.return_value = config
    db.query.return_value = query_mock
    return db


def _make_db_without_config() -> MagicMock:
    """Build a DB session mock that returns None for OrgAIConfig query."""
    db = MagicMock()
    query_mock = MagicMock()
    query_mock.filter_by.return_value.first.return_value = None
    db.query.return_value = query_mock
    return db


class TestResolveEmbeddingProvider:
    """Degrade-matrix tests for resolve_embedding_provider."""

    # ── Case 1: cloud provider + valid BYOK key ───────────────────────────────

    def test_openai_with_byok_key_returns_resolved_embedder(self):
        """Org with openai provider + valid BYOK key must return a ResolvedEmbedder."""
        config = _make_config(default_provider="openai")
        db = _make_db_with_config(config)

        with patch(
            "src.services.embeddings.resolver.resolve_org_byok_key",
            return_value="sk-real-key",
        ):
            result = resolve_embedding_provider(org_id=1, db=db)

        assert result is not None
        assert isinstance(result, ResolvedEmbedder)
        assert result.provider == "openai"
        assert isinstance(result.embedder, EmbeddingProvider)
        assert isinstance(result.embedder, OpenAIEmbeddingProvider)

    # ── Case 2: local provider + base_url, keyless ────────────────────────────

    def test_openai_compatible_with_base_url_returns_local_embedder(self):
        """Org with openai_compatible + base_url must return a keyless local ResolvedEmbedder."""
        config = _make_config(
            default_provider="openai_compatible",
            base_url="http://localhost:11434/v1",
        )
        db = _make_db_with_config(config)

        # resolve_org_byok_key must NOT be called for local providers
        with patch(
            "src.services.embeddings.resolver.resolve_org_byok_key",
        ) as mock_byok:
            result = resolve_embedding_provider(org_id=1, db=db)
            mock_byok.assert_not_called()

        assert result is not None
        assert result.provider == "openai_compatible"
        assert isinstance(result.embedder, OpenAICompatibleEmbeddingProvider)

    def test_ollama_provider_with_base_url_returns_local_embedder(self):
        """Org with ollama + base_url must return a keyless local ResolvedEmbedder."""
        config = _make_config(
            default_provider="ollama",
            base_url="http://gpu-box:11434/v1",
        )
        db = _make_db_with_config(config)

        with patch("src.services.embeddings.resolver.resolve_org_byok_key") as mock_byok:
            result = resolve_embedding_provider(org_id=1, db=db)
            mock_byok.assert_not_called()

        assert result is not None
        assert isinstance(result.embedder, OpenAICompatibleEmbeddingProvider)

    def test_ollama_without_base_url_uses_localhost_default(self):
        """Org with ollama + no base_url must use the localhost:11434/v1 default."""
        config = _make_config(
            default_provider="ollama",
            base_url=None,
        )
        db = _make_db_with_config(config)

        with patch("src.services.embeddings.resolver.resolve_org_byok_key"):
            result = resolve_embedding_provider(org_id=1, db=db)

        assert result is not None
        assert "11434" in result.embedder._base_url

    # ── Case 3: local provider + no base_url → None ───────────────────────────

    def test_openai_compatible_without_base_url_returns_none(self):
        """Org with openai_compatible but no base_url must return None."""
        config = _make_config(default_provider="openai_compatible", base_url=None)
        db = _make_db_with_config(config)

        result = resolve_embedding_provider(org_id=1, db=db)

        assert result is None

    # ── Case 4: cloud provider + no BYOK key → None ───────────────────────────

    def test_openai_without_byok_key_returns_none(self):
        """Org with openai but no BYOK key must return None."""
        config = _make_config(default_provider="openai")
        db = _make_db_with_config(config)

        with patch(
            "src.services.embeddings.resolver.resolve_org_byok_key",
            return_value=None,
        ):
            result = resolve_embedding_provider(org_id=1, db=db)

        assert result is None

    def test_google_without_byok_key_returns_none(self):
        """Org with google but no BYOK key must return None."""
        config = _make_config(default_provider="google")
        db = _make_db_with_config(config)

        with patch(
            "src.services.embeddings.resolver.resolve_org_byok_key",
            return_value=None,
        ):
            result = resolve_embedding_provider(org_id=1, db=db)

        assert result is None

    # ── Case 5: no OrgAIConfig row → None ────────────────────────────────────

    def test_no_org_ai_config_returns_none(self):
        """When there is no OrgAIConfig row for the org, resolver must return None."""
        db = _make_db_without_config()

        result = resolve_embedding_provider(org_id=999, db=db)

        assert result is None

    # ── ResolvedEmbedder shape ────────────────────────────────────────────────

    def test_resolved_embedder_has_provider_string(self):
        """ResolvedEmbedder.provider must be a string."""
        config = _make_config(default_provider="openai")
        db = _make_db_with_config(config)

        with patch(
            "src.services.embeddings.resolver.resolve_org_byok_key",
            return_value="sk-test",
        ):
            result = resolve_embedding_provider(org_id=1, db=db)

        assert isinstance(result.provider, str)

    def test_resolved_embedder_has_embedder_instance(self):
        """ResolvedEmbedder.embedder must implement EmbeddingProvider."""
        config = _make_config(default_provider="openai")
        db = _make_db_with_config(config)

        with patch(
            "src.services.embeddings.resolver.resolve_org_byok_key",
            return_value="sk-test",
        ):
            result = resolve_embedding_provider(org_id=1, db=db)

        assert isinstance(result.embedder, EmbeddingProvider)

    def test_resolved_embedder_has_dimension_hint_int(self):
        """ResolvedEmbedder.dimension_hint must be an int."""
        config = _make_config(default_provider="openai")
        db = _make_db_with_config(config)

        with patch(
            "src.services.embeddings.resolver.resolve_org_byok_key",
            return_value="sk-test",
        ):
            result = resolve_embedding_provider(org_id=1, db=db)

        assert isinstance(result.dimension_hint, int)

    def test_resolver_never_raises_on_factory_error(self):
        """If factory raises (e.g. bad config), resolver must catch and return None."""
        config = _make_config(default_provider="openai", base_url=None)
        db = _make_db_with_config(config)

        with patch(
            "src.services.embeddings.resolver.resolve_org_byok_key",
            return_value="sk-test",
        ), patch(
            "src.services.embeddings.resolver.EmbeddingProviderFactory.create",
            side_effect=Exception("boom"),
        ):
            result = resolve_embedding_provider(org_id=1, db=db)

        assert result is None
