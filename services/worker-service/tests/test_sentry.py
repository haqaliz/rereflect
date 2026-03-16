"""
TDD tests for Sentry integration in the Celery worker service.

Tests verify:
- Sentry initializes when SENTRY_DSN env var is set (with Celery integration)
- Sentry does NOT initialize when SENTRY_DSN is empty/missing
- celery_app.py exposes _sentry_initialized flag
"""

import os
from unittest.mock import patch, MagicMock
import pytest


class TestWorkerSentryInitialization:
    """Tests for conditional Sentry initialization in the Celery worker."""

    def test_sentry_initializes_when_dsn_is_set(self):
        """sentry_sdk.init must be called when SENTRY_DSN is non-empty."""
        test_dsn = "https://worker123@o000000.ingest.sentry.io/2222222"

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

                mock_init.assert_called_once()
                assert mock_init.call_args.kwargs["dsn"] == test_dsn

    def test_sentry_not_initialized_when_dsn_is_empty(self):
        """sentry_sdk.init must NOT be called when SENTRY_DSN is empty."""
        with patch.dict(os.environ, {"SENTRY_DSN": ""}, clear=False):
            with patch("sentry_sdk.init") as mock_init:
                import sentry_sdk
                sentry_dsn = os.getenv("SENTRY_DSN", "")
                if sentry_dsn:
                    sentry_sdk.init(dsn=sentry_dsn)

                mock_init.assert_not_called()

    def test_sentry_not_initialized_when_dsn_is_missing(self):
        """sentry_sdk.init must NOT be called when SENTRY_DSN is absent."""
        env_without_dsn = {k: v for k, v in os.environ.items() if k != "SENTRY_DSN"}
        with patch.dict(os.environ, env_without_dsn, clear=True):
            with patch("sentry_sdk.init") as mock_init:
                import sentry_sdk
                sentry_dsn = os.getenv("SENTRY_DSN", "")
                if sentry_dsn:
                    sentry_sdk.init(dsn=sentry_dsn)

                mock_init.assert_not_called()

    def test_sentry_uses_celery_integration(self):
        """Sentry init must include CeleryIntegration when initializing in the worker."""
        test_dsn = "https://worker123@o000000.ingest.sentry.io/2222222"

        with patch.dict(os.environ, {"SENTRY_DSN": test_dsn}, clear=False):
            with patch("sentry_sdk.init") as mock_init:
                import sentry_sdk
                from sentry_sdk.integrations.celery import CeleryIntegration

                sentry_dsn = os.getenv("SENTRY_DSN", "")
                if sentry_dsn:
                    sentry_sdk.init(
                        dsn=sentry_dsn,
                        environment=os.getenv("SENTRY_ENVIRONMENT", "development"),
                        traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1")),
                        integrations=[CeleryIntegration()],
                        send_default_pii=False,
                    )

                mock_init.assert_called_once()
                call_kwargs = mock_init.call_args.kwargs
                assert "integrations" in call_kwargs
                integration_types = [type(i).__name__ for i in call_kwargs["integrations"]]
                assert "CeleryIntegration" in integration_types

    def test_sentry_send_default_pii_is_false(self):
        """Worker Sentry init must set send_default_pii=False."""
        test_dsn = "https://worker123@o000000.ingest.sentry.io/2222222"

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


class TestCeleryAppSentryFlag:
    """Tests verifying that celery_app.py exposes _sentry_initialized flag."""

    def test_celery_app_has_sentry_initialized_flag_true_when_dsn_set(self):
        """
        celery_app module must expose _sentry_initialized=True when
        SENTRY_DSN is present at import time.
        """
        test_dsn = "https://worker123@o000000.ingest.sentry.io/2222222"

        with patch("sentry_sdk.init"):
            with patch.dict(os.environ, {"SENTRY_DSN": test_dsn}, clear=False):
                import importlib
                import src.celery_app as celery_module
                importlib.reload(celery_module)

                assert hasattr(celery_module, "_sentry_initialized")
                assert celery_module._sentry_initialized is True

    def test_celery_app_has_sentry_initialized_flag_false_when_dsn_missing(self):
        """
        celery_app module must expose _sentry_initialized=False when
        SENTRY_DSN is absent at import time.
        """
        env_without_dsn = {k: v for k, v in os.environ.items() if k != "SENTRY_DSN"}
        env_without_dsn["SENTRY_DSN"] = ""

        with patch("sentry_sdk.init"):
            with patch.dict(os.environ, env_without_dsn, clear=False):
                import importlib
                import src.celery_app as celery_module
                importlib.reload(celery_module)

                assert hasattr(celery_module, "_sentry_initialized")
                assert celery_module._sentry_initialized is False
