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
