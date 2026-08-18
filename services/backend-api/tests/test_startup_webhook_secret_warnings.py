"""
Boot-time fail-closed notice for unconfigured Slack / email webhook secrets.

source_webhooks.verify_slack_signature and email_webhooks._verify_webhook_signature
fail closed: when their secret is unset every delivery is rejected (401). That
per-request log is easy to miss under normal traffic, so this is the boot-time
equivalent: loud, once, at startup, only when it actually matters (there's a
live integration/source that needs the secret).
"""
import pytest
from unittest.mock import patch
from sqlalchemy.orm import Session

from src.models.organization import Organization
from src.models.integration import Integration
from src.models.feedback_source import FeedbackSource


def _import_fn():
    from src.api.main import warn_unconfigured_webhook_secrets
    return warn_unconfigured_webhook_secrets


@pytest.fixture
def org(db: Session) -> Organization:
    o = Organization(name="Startup Warnings Co", plan="pro")
    db.add(o)
    db.commit()
    db.refresh(o)
    return o


class TestSlackStartupWarning:
    @patch("src.api.routes.source_webhooks.SLACK_SIGNING_SECRET", "")
    def test_warns_when_active_slack_integration_and_secret_unset(
        self, db: Session, org: Organization, caplog: pytest.LogCaptureFixture
    ):
        integration = Integration(
            organization_id=org.id, type="slack", is_active=True, config={}
        )
        db.add(integration)
        db.commit()

        fn = _import_fn()
        with caplog.at_level("WARNING"):
            fn(db)

        assert any(
            "deliveries will be rejected" in r.message
            and "SLACK_SIGNING_SECRET" in r.message
            for r in caplog.records
        )

    @patch("src.api.routes.source_webhooks.SLACK_SIGNING_SECRET", "configured-secret")
    def test_no_warning_when_secret_configured(
        self, db: Session, org: Organization, caplog: pytest.LogCaptureFixture
    ):
        integration = Integration(
            organization_id=org.id, type="slack", is_active=True, config={}
        )
        db.add(integration)
        db.commit()

        fn = _import_fn()
        with caplog.at_level("WARNING"):
            fn(db)

        assert not any("will be rejected" in r.message for r in caplog.records)

    @patch("src.api.routes.source_webhooks.SLACK_SIGNING_SECRET", "")
    def test_no_warning_when_no_active_slack_integration(
        self, db: Session, org: Organization, caplog: pytest.LogCaptureFixture
    ):
        # inactive integration only
        integration = Integration(
            organization_id=org.id, type="slack", is_active=False, config={}
        )
        db.add(integration)
        db.commit()

        fn = _import_fn()
        with caplog.at_level("WARNING"):
            fn(db)

        assert not any("will be rejected" in r.message for r in caplog.records)


class TestEmailStartupWarning:
    @patch("src.api.routes.email_webhooks.RESEND_INBOUND_WEBHOOK_SECRET", None)
    def test_warns_when_active_email_source_and_secret_unset(
        self, db: Session, org: Organization, caplog: pytest.LogCaptureFixture
    ):
        source = FeedbackSource(
            organization_id=org.id,
            source_type="email",
            is_active=True,
            provider_config={"inbound_address": "feedback-abc@rereflect.ca"},
        )
        db.add(source)
        db.commit()

        fn = _import_fn()
        with caplog.at_level("WARNING"):
            fn(db)

        assert any(
            "deliveries will be rejected" in r.message
            and "RESEND_INBOUND_WEBHOOK_SECRET" in r.message
            for r in caplog.records
        )

    @patch("src.api.routes.email_webhooks.RESEND_INBOUND_WEBHOOK_SECRET", "configured-secret")
    def test_no_warning_when_secret_configured(
        self, db: Session, org: Organization, caplog: pytest.LogCaptureFixture
    ):
        source = FeedbackSource(
            organization_id=org.id,
            source_type="email",
            is_active=True,
            provider_config={"inbound_address": "feedback-abc@rereflect.ca"},
        )
        db.add(source)
        db.commit()

        fn = _import_fn()
        with caplog.at_level("WARNING"):
            fn(db)

        assert not any("will be rejected" in r.message for r in caplog.records)

    @patch("src.api.routes.email_webhooks.RESEND_INBOUND_WEBHOOK_SECRET", None)
    def test_no_warning_when_no_active_email_source(
        self, db: Session, org: Organization, caplog: pytest.LogCaptureFixture
    ):
        source = FeedbackSource(
            organization_id=org.id,
            source_type="email",
            is_active=False,
            provider_config={"inbound_address": "feedback-abc@rereflect.ca"},
        )
        db.add(source)
        db.commit()

        fn = _import_fn()
        with caplog.at_level("WARNING"):
            fn(db)

        assert not any("will be rejected" in r.message for r in caplog.records)


class TestStartupWarningNeverBlocksBoot:
    def test_db_error_does_not_raise(self):
        """A DB error during the lookup must not crash boot."""
        from unittest.mock import MagicMock

        mock_db = MagicMock()
        mock_db.query.side_effect = Exception("DB connection lost")

        fn = _import_fn()
        fn(mock_db)  # must not raise
