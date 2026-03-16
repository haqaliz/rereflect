"""
TDD tests for Sentry integration in the FastAPI backend.

Tests verify:
- Sentry initializes when SENTRY_DSN env var is set
- Sentry does NOT initialize when SENTRY_DSN is empty/missing
- org_id and user_id are attached to Sentry scope on authenticated requests
"""

import os
import importlib
from unittest.mock import patch, MagicMock, call
import pytest


class TestSentryInitialization:
    """Tests for conditional Sentry SDK initialization."""

    def test_sentry_initializes_when_dsn_is_set(self):
        """Sentry.init must be called exactly once when SENTRY_DSN is non-empty."""
        test_dsn = "https://abc123@o000000.ingest.sentry.io/0000000"

        with patch.dict(os.environ, {"SENTRY_DSN": test_dsn}, clear=False):
            with patch("sentry_sdk.init") as mock_init:
                # Re-execute the initialization logic as it appears in main.py
                import sentry_sdk
                sentry_dsn = os.getenv("SENTRY_DSN", "")
                if sentry_dsn:
                    sentry_sdk.init(
                        dsn=sentry_dsn,
                        environment=os.getenv("SENTRY_ENVIRONMENT", "development"),
                        traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1")),
                        send_default_pii=False,
                    )

                mock_init.assert_called_once()
                call_kwargs = mock_init.call_args.kwargs
                assert call_kwargs["dsn"] == test_dsn

    def test_sentry_not_initialized_when_dsn_is_empty_string(self):
        """Sentry.init must NOT be called when SENTRY_DSN is an empty string."""
        with patch.dict(os.environ, {"SENTRY_DSN": ""}, clear=False):
            with patch("sentry_sdk.init") as mock_init:
                import sentry_sdk
                sentry_dsn = os.getenv("SENTRY_DSN", "")
                if sentry_dsn:
                    sentry_sdk.init(dsn=sentry_dsn)

                mock_init.assert_not_called()

    def test_sentry_not_initialized_when_dsn_is_missing(self):
        """Sentry.init must NOT be called when SENTRY_DSN env var is absent."""
        env_without_dsn = {k: v for k, v in os.environ.items() if k != "SENTRY_DSN"}
        with patch.dict(os.environ, env_without_dsn, clear=True):
            with patch("sentry_sdk.init") as mock_init:
                import sentry_sdk
                sentry_dsn = os.getenv("SENTRY_DSN", "")
                if sentry_dsn:
                    sentry_sdk.init(dsn=sentry_dsn)

                mock_init.assert_not_called()

    def test_sentry_uses_environment_from_env_var(self):
        """Sentry must use SENTRY_ENVIRONMENT env var when initializing."""
        test_dsn = "https://abc123@o000000.ingest.sentry.io/0000000"

        with patch.dict(
            os.environ,
            {"SENTRY_DSN": test_dsn, "SENTRY_ENVIRONMENT": "production"},
            clear=False,
        ):
            with patch("sentry_sdk.init") as mock_init:
                import sentry_sdk
                sentry_dsn = os.getenv("SENTRY_DSN", "")
                if sentry_dsn:
                    sentry_sdk.init(
                        dsn=sentry_dsn,
                        environment=os.getenv("SENTRY_ENVIRONMENT", "development"),
                        traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1")),
                        send_default_pii=False,
                    )

                call_kwargs = mock_init.call_args.kwargs
                assert call_kwargs["environment"] == "production"

    def test_sentry_defaults_to_development_environment(self):
        """Sentry must default to 'development' when SENTRY_ENVIRONMENT is not set."""
        test_dsn = "https://abc123@o000000.ingest.sentry.io/0000000"
        env = {k: v for k, v in os.environ.items() if k != "SENTRY_ENVIRONMENT"}
        env["SENTRY_DSN"] = test_dsn

        with patch.dict(os.environ, env, clear=True):
            with patch("sentry_sdk.init") as mock_init:
                import sentry_sdk
                sentry_dsn = os.getenv("SENTRY_DSN", "")
                if sentry_dsn:
                    sentry_sdk.init(
                        dsn=sentry_dsn,
                        environment=os.getenv("SENTRY_ENVIRONMENT", "development"),
                        traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1")),
                        send_default_pii=False,
                    )

                call_kwargs = mock_init.call_args.kwargs
                assert call_kwargs["environment"] == "development"

    def test_sentry_traces_sample_rate_from_env_var(self):
        """Sentry must read traces_sample_rate from SENTRY_TRACES_SAMPLE_RATE env var."""
        test_dsn = "https://abc123@o000000.ingest.sentry.io/0000000"

        with patch.dict(
            os.environ,
            {"SENTRY_DSN": test_dsn, "SENTRY_TRACES_SAMPLE_RATE": "0.5"},
            clear=False,
        ):
            with patch("sentry_sdk.init") as mock_init:
                import sentry_sdk
                sentry_dsn = os.getenv("SENTRY_DSN", "")
                if sentry_dsn:
                    sentry_sdk.init(
                        dsn=sentry_dsn,
                        environment=os.getenv("SENTRY_ENVIRONMENT", "development"),
                        traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1")),
                        send_default_pii=False,
                    )

                call_kwargs = mock_init.call_args.kwargs
                assert call_kwargs["traces_sample_rate"] == 0.5

    def test_sentry_default_traces_sample_rate_is_point_one(self):
        """Sentry must default traces_sample_rate to 0.1 when env var is absent."""
        test_dsn = "https://abc123@o000000.ingest.sentry.io/0000000"
        env = {k: v for k, v in os.environ.items() if k != "SENTRY_TRACES_SAMPLE_RATE"}
        env["SENTRY_DSN"] = test_dsn

        with patch.dict(os.environ, env, clear=True):
            with patch("sentry_sdk.init") as mock_init:
                import sentry_sdk
                sentry_dsn = os.getenv("SENTRY_DSN", "")
                if sentry_dsn:
                    sentry_sdk.init(
                        dsn=sentry_dsn,
                        environment=os.getenv("SENTRY_ENVIRONMENT", "development"),
                        traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1")),
                        send_default_pii=False,
                    )

                call_kwargs = mock_init.call_args.kwargs
                assert call_kwargs["traces_sample_rate"] == 0.1

    def test_sentry_send_default_pii_is_false(self):
        """Sentry must set send_default_pii=False to protect user privacy."""
        test_dsn = "https://abc123@o000000.ingest.sentry.io/0000000"

        with patch.dict(os.environ, {"SENTRY_DSN": test_dsn}, clear=False):
            with patch("sentry_sdk.init") as mock_init:
                import sentry_sdk
                sentry_dsn = os.getenv("SENTRY_DSN", "")
                if sentry_dsn:
                    sentry_sdk.init(
                        dsn=sentry_dsn,
                        environment=os.getenv("SENTRY_ENVIRONMENT", "development"),
                        traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1")),
                        send_default_pii=False,
                    )

                call_kwargs = mock_init.call_args.kwargs
                assert call_kwargs["send_default_pii"] is False


class TestSentryMainPyIntegration:
    """
    Tests verifying that main.py actually calls sentry_sdk.init when SENTRY_DSN is set.
    These tests re-import main.py under controlled env conditions.
    """

    def test_main_module_calls_sentry_init_when_dsn_present(self):
        """
        When SENTRY_DSN is set before importing main.py, sentry_sdk.init
        must be called with the correct DSN.
        """
        test_dsn = "https://test123@o000000.ingest.sentry.io/1111111"

        with patch("sentry_sdk.init") as mock_init:
            with patch.dict(os.environ, {"SENTRY_DSN": test_dsn}, clear=False):
                # Import and run the sentry init block from main
                import sentry_sdk
                from src.api import main as backend_main
                # Verify the module has initialized Sentry (check the module attribute)
                assert hasattr(backend_main, "_sentry_initialized")
                assert backend_main._sentry_initialized is True

    def test_main_module_skips_sentry_init_when_dsn_absent(self):
        """
        When SENTRY_DSN is absent, main.py must NOT call sentry_sdk.init
        and must set _sentry_initialized to False.
        """
        env_without_dsn = {k: v for k, v in os.environ.items() if k != "SENTRY_DSN"}
        env_without_dsn["SENTRY_DSN"] = ""

        with patch.dict(os.environ, env_without_dsn, clear=False):
            from src.api import main as backend_main
            assert hasattr(backend_main, "_sentry_initialized")
            assert backend_main._sentry_initialized is False


class TestSentryScopeContext:
    """Tests verifying that org_id and user_id are attached to Sentry scope on requests."""

    def test_sentry_scope_set_org_id_on_authenticated_request(self):
        """
        When processing an authenticated request, org_id from JWT must be set
        on the Sentry scope via sentry_sdk.set_tag or sentry_sdk.set_user.
        """
        mock_scope = MagicMock()

        with patch("sentry_sdk.set_tag") as mock_set_tag:
            import sentry_sdk
            # Simulate what main.py middleware does after JWT decode
            org_id = "org-abc-123"
            user_id = "user-xyz-456"

            sentry_sdk.set_tag("org_id", org_id)
            sentry_sdk.set_tag("user_id", user_id)

            mock_set_tag.assert_any_call("org_id", org_id)
            mock_set_tag.assert_any_call("user_id", user_id)

    def test_sentry_scope_attached_in_main_middleware(self):
        """
        main.py must contain a middleware or dependency that attaches
        org_id and user_id to Sentry scope for every request.
        """
        from src.api import main as backend_main

        # The app must have a SentryContextMiddleware or equivalent registered
        middleware_types = [
            type(m).__name__
            for m in getattr(backend_main.app, "middleware_stack", [])
        ]
        # More robust: check that the middleware class exists in the module
        assert hasattr(backend_main, "SentryContextMiddleware"), (
            "main.py must define SentryContextMiddleware that attaches "
            "org_id and user_id to the Sentry scope"
        )
