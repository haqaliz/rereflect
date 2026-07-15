"""
Tests for Sentry integration in the Celery worker.

Sentry is opt-in: a self-hosted worker must send nothing anywhere unless the
operator sets SENTRY_DSN. These tests exercise the real module (src.celery_app)
rather than re-implementing its logic inline — an earlier version of this file
asserted against logic copied into the test body, so it passed even while
celery_app.py shipped a hardcoded DSN with send_default_pii=True.

Tests verify:
- Sentry initializes only when SENTRY_DSN is set (with Celery integration)
- No DSN is hardcoded in the module
- PII is never sent
"""

import importlib
import os
from unittest.mock import patch

import pytest


def _reimport_celery_app_with_env(env: dict, clear: bool = False):
    """
    Re-import src.celery_app under a controlled environment with sentry_sdk.init
    patched, and return (module, mock_init). This executes celery_app.py's real
    module-level Sentry block.
    """
    with patch.dict(os.environ, env, clear=clear):
        with patch("sentry_sdk.init") as mock_init:
            import src.celery_app as celery_module

            celery_module = importlib.reload(celery_module)
            return celery_module, mock_init


class TestWorkerSentryInitialization:
    """The real module must gate Sentry on the SENTRY_DSN env var."""

    def test_initializes_when_dsn_is_set(self):
        test_dsn = "https://worker123@o000000.ingest.sentry.io/2222222"
        mod, mock_init = _reimport_celery_app_with_env({"SENTRY_DSN": test_dsn})

        assert mod._sentry_initialized is True
        mock_init.assert_called_once()
        assert mock_init.call_args.kwargs["dsn"] == test_dsn

    def test_not_initialized_when_dsn_is_empty(self):
        mod, mock_init = _reimport_celery_app_with_env({"SENTRY_DSN": ""})

        assert mod._sentry_initialized is False
        mock_init.assert_not_called()

    def test_not_initialized_when_dsn_is_whitespace(self):
        mod, mock_init = _reimport_celery_app_with_env({"SENTRY_DSN": "   "})

        assert mod._sentry_initialized is False
        mock_init.assert_not_called()

    def test_not_initialized_when_dsn_is_missing(self):
        env = {k: v for k, v in os.environ.items() if k != "SENTRY_DSN"}
        mod, mock_init = _reimport_celery_app_with_env(env, clear=True)

        assert mod._sentry_initialized is False
        mock_init.assert_not_called()


class TestNoHardcodedDsn:
    """
    Regression guard for the hardcoded-DSN incident: a self-hosted worker must
    never ship a DSN pointing at someone else's Sentry project.
    """

    def test_celery_app_source_contains_no_hardcoded_dsn(self):
        import src.celery_app as celery_module

        source = open(celery_module.__file__).read()
        assert "ingest.sentry.io" not in source
        assert "ingest.us.sentry.io" not in source


class TestWorkerSentryOptions:
    """When Sentry IS enabled, it must be configured privately and for Celery."""

    def test_send_default_pii_is_false(self):
        test_dsn = "https://worker123@o000000.ingest.sentry.io/2222222"
        _, mock_init = _reimport_celery_app_with_env({"SENTRY_DSN": test_dsn})

        assert mock_init.call_args.kwargs["send_default_pii"] is False

    def test_uses_celery_integration(self):
        test_dsn = "https://worker123@o000000.ingest.sentry.io/2222222"
        _, mock_init = _reimport_celery_app_with_env({"SENTRY_DSN": test_dsn})

        integrations = mock_init.call_args.kwargs.get("integrations", [])
        assert "CeleryIntegration" in [type(i).__name__ for i in integrations]

    def test_environment_from_env_var(self):
        test_dsn = "https://worker123@o000000.ingest.sentry.io/2222222"
        _, mock_init = _reimport_celery_app_with_env(
            {"SENTRY_DSN": test_dsn, "SENTRY_ENVIRONMENT": "production"}
        )

        assert mock_init.call_args.kwargs["environment"] == "production"

    def test_traces_sample_rate_from_env_var(self):
        test_dsn = "https://worker123@o000000.ingest.sentry.io/2222222"
        _, mock_init = _reimport_celery_app_with_env(
            {"SENTRY_DSN": test_dsn, "SENTRY_TRACES_SAMPLE_RATE": "0.5"}
        )

        assert mock_init.call_args.kwargs["traces_sample_rate"] == 0.5
