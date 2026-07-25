"""
Phase 4 — TDD tests for provider-aware system-template seeding in lifespan.

Tests:
- seed_copilot_system_templates() calls TemplateSaver.seed_system_templates with
  the resolved embedder when one is available.
- When the embedding endpoint is unreachable (embed raises), boot is not blocked;
  the function returns without raising.
- When no embedder is resolvable (no org or no AI config), the function skips cleanly.
- When no organizations exist yet, the function skips cleanly.
"""

import pytest
from unittest.mock import MagicMock, patch, call


# ── Helpers ───────────────────────────────────────────────────────────────────

def _import_seed_fn():
    """Import the startup seeding helper added to main.py."""
    from src.api.main import seed_copilot_system_templates
    return seed_copilot_system_templates


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestStartupSeeding:
    """Verify the lifespan seeding hook behavior."""

    def test_seed_fn_exists_in_main(self):
        """The startup seeding function must be importable from main."""
        fn = _import_seed_fn()
        assert callable(fn)

    def test_seeds_with_resolved_embedder(self):
        """When an embedder resolves, seed_system_templates is called with it."""
        mock_resolved = MagicMock()
        mock_db = MagicMock()

        # Simulate finding one org and resolving an embedder for it
        mock_org = MagicMock()
        mock_org.id = 1
        mock_db.query.return_value.first.return_value = mock_org

        fn = _import_seed_fn()

        with patch(
            "src.api.main.resolve_embedding_provider", return_value=mock_resolved
        ) as mock_resolve, patch(
            "src.api.main.TemplateSaver"
        ) as MockSaver:
            mock_saver_instance = MockSaver.return_value
            fn(mock_db)

        mock_saver_instance.seed_system_templates.assert_called_once_with(
            mock_db, embedder=mock_resolved
        )

    def test_unreachable_embedder_does_not_crash_boot(self):
        """If the embedding endpoint is unreachable, the function logs and returns."""
        mock_db = MagicMock()
        mock_org = MagicMock()
        mock_org.id = 1
        mock_db.query.return_value.first.return_value = mock_org

        fn = _import_seed_fn()

        with patch(
            "src.api.main.resolve_embedding_provider", return_value=MagicMock()
        ), patch("src.api.main.TemplateSaver") as MockSaver:
            mock_saver_instance = MockSaver.return_value
            mock_saver_instance.seed_system_templates.side_effect = Exception("Connection refused")

            # Must NOT raise — boot must not be blocked
            fn(mock_db)  # no exception expected

    def test_no_embedder_skips_cleanly(self):
        """When no embedder resolves, seed_system_templates is still called (with None)."""
        mock_db = MagicMock()
        mock_org = MagicMock()
        mock_org.id = 1
        mock_db.query.return_value.first.return_value = mock_org

        fn = _import_seed_fn()

        with patch(
            "src.api.main.resolve_embedding_provider", return_value=None
        ), patch("src.api.main.TemplateSaver") as MockSaver:
            mock_saver_instance = MockSaver.return_value
            fn(mock_db)

        # seed_system_templates should be called with embedder=None
        mock_saver_instance.seed_system_templates.assert_called_once_with(
            mock_db, embedder=None
        )

    def test_no_org_skips_cleanly(self):
        """When no organization exists (fresh install), the function returns without error."""
        mock_db = MagicMock()
        # No orgs in DB
        mock_db.query.return_value.first.return_value = None

        fn = _import_seed_fn()

        # Must not raise, must not call TemplateSaver
        with patch("src.api.main.TemplateSaver") as MockSaver:
            fn(mock_db)

        MockSaver.return_value.seed_system_templates.assert_not_called()

    def test_db_error_does_not_crash_boot(self):
        """A DB error during org lookup is caught and does not crash boot."""
        mock_db = MagicMock()
        mock_db.query.side_effect = Exception("DB connection lost")

        fn = _import_seed_fn()

        # Must NOT raise
        fn(mock_db)


# ── Aspect 2 / Task 3: local embedding model pre-warm ──────────────────────────

def _mock_resolved(provider: str, embedder: MagicMock | None = None):
    """Build a fake ResolvedEmbedder-shaped MagicMock for a given provider."""
    resolved = MagicMock()
    resolved.provider = provider
    resolved.embedder = embedder if embedder is not None else MagicMock()
    return resolved


class TestLocalEmbeddingPreWarm:
    """
    When the resolved provider is `local`, seed_copilot_system_templates must
    also pre-warm the model (one `embed("warmup")` call) so the first real
    Copilot query doesn't pay the multi-second load. Best-effort: a pre-warm
    failure must never break boot.
    """

    def _mock_db_with_org(self):
        mock_db = MagicMock()
        mock_org = MagicMock()
        mock_org.id = 1
        mock_db.query.return_value.first.return_value = mock_org
        return mock_db

    def test_prewarm_invoked_for_local_provider(self):
        mock_db = self._mock_db_with_org()
        mock_embedder = MagicMock()
        resolved = _mock_resolved("local", mock_embedder)

        fn = _import_seed_fn()

        with patch(
            "src.api.main.resolve_embedding_provider", return_value=resolved
        ), patch("src.api.main.TemplateSaver"):
            fn(mock_db)

        mock_embedder.embed.assert_called_once_with("warmup")

    def test_prewarm_not_invoked_for_non_local_provider(self):
        mock_db = self._mock_db_with_org()
        mock_embedder = MagicMock()
        resolved = _mock_resolved("openai", mock_embedder)

        fn = _import_seed_fn()

        with patch(
            "src.api.main.resolve_embedding_provider", return_value=resolved
        ), patch("src.api.main.TemplateSaver"):
            fn(mock_db)

        # The warmup branch must not fire for a non-local provider — no
        # embed() call beyond whatever seed_system_templates itself does
        # (which is a separate mocked call, not on this embedder mock).
        mock_embedder.embed.assert_not_called()

    def test_prewarm_failure_does_not_break_boot(self):
        mock_db = self._mock_db_with_org()
        mock_embedder = MagicMock()
        mock_embedder.embed.side_effect = Exception("model load failed")
        resolved = _mock_resolved("local", mock_embedder)

        fn = _import_seed_fn()

        with patch(
            "src.api.main.resolve_embedding_provider", return_value=resolved
        ), patch("src.api.main.TemplateSaver"):
            fn(mock_db)  # must NOT raise

        mock_embedder.embed.assert_called_once_with("warmup")


class TestNoImportTimeModelLoad:
    """The local embedding model must never load merely from importing
    src.api.main (or the local provider module) — only a real embed() call
    (e.g. during the pre-warm above) may trigger the lazy singleton load."""

    def test_import_does_not_load_local_model(self):
        import importlib

        with patch(
            "src.services.embeddings.providers.local._get_model"
        ) as mock_get_model:
            import src.api.main as main_module

            importlib.reload(main_module)

        mock_get_model.assert_not_called()
