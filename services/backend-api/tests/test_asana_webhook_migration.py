"""
TDD tests for Phase 1 of the asana-webhook aspect (status-sync-realtime-mapping
PRD): new `asana_integrations.webhook_secret` (Text, nullable, Fernet-encrypted
at the route layer) and `asana_integrations.webhook_gid` (String, nullable --
the Asana webhook gid returned by POST /webhooks) columns.

This module only asserts the columns exist, are nullable, and round-trip an
arbitrary string; encryption itself is exercised by
tests/test_asana_webhook_routes.py. Mirrors the model-level test style of
tests/test_jira_webhook_migration.py (uses the `db` fixture, which builds
schema via Base.metadata.create_all -- see tests/conftest.py -- rather than
running the real Alembic chain; the actual
alembic/versions/<rev>_add_asana_webhook.py migration is hand-verified
separately per the plan's Validation step).

See docs/planning/status-sync-realtime-mapping/asana-webhook/plan_20260718.md
Phase 1.
"""
import pytest
from sqlalchemy.orm import Session

from src.models.organization import Organization
from src.models.user import User


class TestAsanaIntegrationWebhookColumns:

    def test_webhook_secret_defaults_none(
        self, db: Session, test_organization: Organization, test_user: User
    ):
        from src.models.asana_integration import AsanaIntegration

        integration = AsanaIntegration(
            organization_id=test_organization.id,
            api_token="token",
            connected_by_user_id=test_user.id,
        )
        db.add(integration)
        db.commit()
        db.refresh(integration)

        assert integration.webhook_secret is None

    def test_webhook_gid_defaults_none(
        self, db: Session, test_organization: Organization, test_user: User
    ):
        from src.models.asana_integration import AsanaIntegration

        integration = AsanaIntegration(
            organization_id=test_organization.id,
            api_token="token",
            connected_by_user_id=test_user.id,
        )
        db.add(integration)
        db.commit()
        db.refresh(integration)

        assert integration.webhook_gid is None

    def test_webhook_secret_settable_and_nullable(
        self, db: Session, test_organization: Organization, test_user: User
    ):
        from src.models.asana_integration import AsanaIntegration

        integration = AsanaIntegration(
            organization_id=test_organization.id,
            api_token="token",
            connected_by_user_id=test_user.id,
            webhook_secret="gAAAAA-fake-fernet-ciphertext",
        )
        db.add(integration)
        db.commit()
        db.refresh(integration)

        assert integration.webhook_secret == "gAAAAA-fake-fernet-ciphertext"

        integration.webhook_secret = None
        db.commit()
        db.refresh(integration)
        assert integration.webhook_secret is None

    def test_webhook_gid_settable_and_nullable(
        self, db: Session, test_organization: Organization, test_user: User
    ):
        from src.models.asana_integration import AsanaIntegration

        integration = AsanaIntegration(
            organization_id=test_organization.id,
            api_token="token",
            connected_by_user_id=test_user.id,
            webhook_gid="1201234567890",
        )
        db.add(integration)
        db.commit()
        db.refresh(integration)

        assert integration.webhook_gid == "1201234567890"

        integration.webhook_gid = None
        db.commit()
        db.refresh(integration)
        assert integration.webhook_gid is None

    def test_webhook_secret_is_text_column_type(self):
        from src.models.asana_integration import AsanaIntegration
        import sqlalchemy as sa

        column = AsanaIntegration.__table__.columns["webhook_secret"]
        assert isinstance(column.type, sa.Text)
        assert column.nullable is True

    def test_webhook_gid_is_string_column_type(self):
        from src.models.asana_integration import AsanaIntegration
        import sqlalchemy as sa

        column = AsanaIntegration.__table__.columns["webhook_gid"]
        assert isinstance(column.type, sa.String)
        assert column.nullable is True


class TestAsanaIntegrationWebhookUrlTokenColumn:
    """
    sec review (CRITICAL): `webhook_url_token` (String(128), nullable,
    UNIQUE-indexed) replaces the guessable integer `id` as the inbound
    receiver's org-resolution key. See src/api/routes/asana_webhook.py.
    """

    def test_webhook_url_token_defaults_none(
        self, db: Session, test_organization: Organization, test_user: User
    ):
        from src.models.asana_integration import AsanaIntegration

        integration = AsanaIntegration(
            organization_id=test_organization.id,
            api_token="token",
            connected_by_user_id=test_user.id,
        )
        db.add(integration)
        db.commit()
        db.refresh(integration)

        assert integration.webhook_url_token is None

    def test_webhook_url_token_settable_and_nullable(
        self, db: Session, test_organization: Organization, test_user: User
    ):
        from src.models.asana_integration import AsanaIntegration

        integration = AsanaIntegration(
            organization_id=test_organization.id,
            api_token="token",
            connected_by_user_id=test_user.id,
            webhook_url_token="a-fake-unguessable-token-value",
        )
        db.add(integration)
        db.commit()
        db.refresh(integration)

        assert integration.webhook_url_token == "a-fake-unguessable-token-value"

        integration.webhook_url_token = None
        db.commit()
        db.refresh(integration)
        assert integration.webhook_url_token is None

    def test_webhook_url_token_is_string_column_type(self):
        from src.models.asana_integration import AsanaIntegration
        import sqlalchemy as sa

        column = AsanaIntegration.__table__.columns["webhook_url_token"]
        assert isinstance(column.type, sa.String)
        assert column.nullable is True

    def test_webhook_url_token_has_unique_index(self):
        from src.models.asana_integration import AsanaIntegration

        indexes = {
            index.name: index for index in AsanaIntegration.__table__.indexes
        }
        assert "ix_asana_integrations_webhook_url_token" in indexes
        index = indexes["ix_asana_integrations_webhook_url_token"]
        assert index.unique is True
        assert {col.name for col in index.columns} == {"webhook_url_token"}

    def test_webhook_url_token_uniqueness_enforced(
        self, db: Session, test_organization: Organization
    ):
        from src.models.asana_integration import AsanaIntegration
        from src.models.organization import Organization as OrgModel
        from sqlalchemy.exc import IntegrityError

        other_org = OrgModel(name="Other Org")
        db.add(other_org)
        db.commit()
        db.refresh(other_org)

        integration1 = AsanaIntegration(
            organization_id=test_organization.id,
            api_token="token1",
            webhook_url_token="duplicate-token-value",
        )
        db.add(integration1)
        db.commit()

        integration2 = AsanaIntegration(
            organization_id=other_org.id,
            api_token="token2",
            webhook_url_token="duplicate-token-value",
        )
        db.add(integration2)
        with pytest.raises(IntegrityError):
            db.commit()
