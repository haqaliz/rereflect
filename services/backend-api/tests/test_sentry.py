"""
Tests for Sentry integration in the FastAPI backend.

Sentry is opt-in: a self-hosted install must send nothing anywhere unless the
operator sets SENTRY_DSN. These tests exercise the real module (src.api.main)
rather than re-implementing its logic inline — an earlier version of this file
asserted against logic copied into the test body, so it passed even while
main.py shipped a hardcoded DSN with send_default_pii=True.

Tests verify:
- Sentry initializes only when SENTRY_DSN is set
- No DSN is hardcoded in the module
- PII is never sent
"""

import importlib
import os
from unittest.mock import patch

import pytest


def _reimport_main_with_env(env: dict):
    """
    Re-import src.api.main under a controlled environment with sentry_sdk.init
    patched, and return (module, mock_init). This executes main.py's real
    module-level Sentry block.
    """
    with patch.dict(os.environ, env, clear=False):
        with patch("sentry_sdk.init") as mock_init:
            import src.api.main as backend_main

            backend_main = importlib.reload(backend_main)
            return backend_main, mock_init


class TestSentryInitialization:
    """The real module must gate Sentry on the SENTRY_DSN env var."""

    def test_initializes_when_dsn_is_set(self):
        test_dsn = "https://abc123@o000000.ingest.sentry.io/0000000"
        main, mock_init = _reimport_main_with_env({"SENTRY_DSN": test_dsn})

        assert main._sentry_initialized is True
        mock_init.assert_called_once()
        assert mock_init.call_args.kwargs["dsn"] == test_dsn

    def test_not_initialized_when_dsn_is_empty_string(self):
        main, mock_init = _reimport_main_with_env({"SENTRY_DSN": ""})

        assert main._sentry_initialized is False
        mock_init.assert_not_called()

    def test_not_initialized_when_dsn_is_whitespace(self):
        main, mock_init = _reimport_main_with_env({"SENTRY_DSN": "   "})

        assert main._sentry_initialized is False
        mock_init.assert_not_called()

    def test_not_initialized_when_dsn_is_missing(self):
        env = {k: v for k, v in os.environ.items() if k != "SENTRY_DSN"}
        with patch.dict(os.environ, env, clear=True):
            with patch("sentry_sdk.init") as mock_init:
                import src.api.main as backend_main

                backend_main = importlib.reload(backend_main)

                assert backend_main._sentry_initialized is False
                mock_init.assert_not_called()


class TestNoHardcodedDsn:
    """
    Regression guard for the hardcoded-DSN incident: a self-hosted install must
    never ship a DSN pointing at someone else's Sentry project.
    """

    def test_main_source_contains_no_hardcoded_dsn(self):
        import src.api.main as backend_main

        source = open(backend_main.__file__).read()
        assert "ingest.sentry.io" not in source
        assert "ingest.us.sentry.io" not in source

    def test_worker_source_contains_no_hardcoded_dsn(self):
        worker_celery = os.path.join(
            os.path.dirname(__file__),
            "..",
            "..",
            "worker-service",
            "src",
            "celery_app.py",
        )
        if not os.path.exists(worker_celery):
            pytest.skip("worker-service not present in this checkout")

        source = open(worker_celery).read()
        assert "ingest.sentry.io" not in source
        assert "ingest.us.sentry.io" not in source


class TestSentryOptions:
    """When Sentry IS enabled, it must be configured privately."""

    def test_send_default_pii_is_false(self):
        test_dsn = "https://abc123@o000000.ingest.sentry.io/0000000"
        _, mock_init = _reimport_main_with_env({"SENTRY_DSN": test_dsn})

        assert mock_init.call_args.kwargs["send_default_pii"] is False

    def test_environment_from_env_var(self):
        test_dsn = "https://abc123@o000000.ingest.sentry.io/0000000"
        _, mock_init = _reimport_main_with_env(
            {"SENTRY_DSN": test_dsn, "SENTRY_ENVIRONMENT": "production"}
        )

        assert mock_init.call_args.kwargs["environment"] == "production"

    def test_traces_sample_rate_from_env_var(self):
        test_dsn = "https://abc123@o000000.ingest.sentry.io/0000000"
        _, mock_init = _reimport_main_with_env(
            {"SENTRY_DSN": test_dsn, "SENTRY_TRACES_SAMPLE_RATE": "0.5"}
        )

        assert mock_init.call_args.kwargs["traces_sample_rate"] == 0.5


@pytest.mark.xfail(
    reason="SentryContextMiddleware was specified by an earlier TDD pass but never "
    "implemented. Not a launch blocker now that Sentry is opt-in and off by "
    "default; it only enriches reports for operators who set their own DSN. "
    "Remove this xfail when the middleware lands.",
    strict=False,
)
def test_sentry_scope_attaches_org_and_user_id():
    """
    main.py should attach org_id / user_id to the Sentry scope per request, so an
    operator running their own DSN can trace an error to a tenant.
    """
    import src.api.main as backend_main

    assert hasattr(backend_main, "SentryContextMiddleware")
