"""
TDD tests for the ZendeskIntegration database model.

Mirrors test_jira_models.py's TestJiraIntegrationModel, minus the link-table
class — there is no FeedbackZendeskIssue equivalent (this aspect is
inbound-only, no create-issue feature).
"""
import pytest
from datetime import datetime
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.models.organization import Organization
from src.models.user import User


class TestZendeskIntegrationModel:

    def test_importable(self):
        from src.models.zendesk_integration import ZendeskIntegration
        assert ZendeskIntegration is not None

    def test_exported_from_init(self):
        from src.models import ZendeskIntegration
        assert ZendeskIntegration is not None

    def test_table_name(self):
        from src.models.zendesk_integration import ZendeskIntegration
        assert ZendeskIntegration.__tablename__ == "zendesk_integrations"

    def test_columns_present(self):
        from src.models.zendesk_integration import ZendeskIntegration
        columns = ZendeskIntegration.__table__.columns.keys()
        expected = {
            "id", "organization_id", "subdomain", "email", "api_token",
            "token_hint", "webhook_secret", "account_user_id", "display_name",
            "is_active", "connected_by_user_id", "connected_at",
            "last_synced_at", "last_sync_status", "last_error",
            "created_at", "updated_at",
        }
        assert expected.issubset(set(columns))

    def test_unique_constraint_on_organization_id(self):
        from src.models.zendesk_integration import ZendeskIntegration
        constraint_names = {
            c.name for c in ZendeskIntegration.__table__.constraints
            if hasattr(c, "name") and c.name
        }
        assert "uq_zendesk_integrations_org_id" in constraint_names

    def test_create_integration(self, db: Session, test_organization: Organization, test_user: User):
        from src.models.zendesk_integration import ZendeskIntegration

        integration = ZendeskIntegration(
            organization_id=test_organization.id,
            subdomain="acme",
            email="ops@acme.com",
            api_token="encrypted_token_value",
            token_hint="...abcd",
            webhook_secret="encrypted_webhook_secret",
            account_user_id="12345",
            display_name="Acme Ops",
            connected_by_user_id=test_user.id,
        )
        db.add(integration)
        db.commit()
        db.refresh(integration)

        assert integration.id is not None
        assert integration.organization_id == test_organization.id
        assert integration.subdomain == "acme"
        assert integration.email == "ops@acme.com"
        assert integration.api_token == "encrypted_token_value"
        assert integration.token_hint == "...abcd"
        assert integration.webhook_secret == "encrypted_webhook_secret"
        assert integration.account_user_id == "12345"
        assert integration.display_name == "Acme Ops"
        assert integration.connected_by_user_id == test_user.id
        assert integration.created_at is not None
        assert integration.updated_at is not None

    def test_connected_at_defaults_to_now(self, db: Session, test_organization: Organization, test_user: User):
        from src.models.zendesk_integration import ZendeskIntegration

        before = datetime.utcnow()
        integration = ZendeskIntegration(
            organization_id=test_organization.id,
            subdomain="acme",
            email="ops@acme.com",
            api_token="token",
            connected_by_user_id=test_user.id,
        )
        db.add(integration)
        db.commit()
        db.refresh(integration)
        after = datetime.utcnow()

        assert integration.connected_at is not None
        assert before <= integration.connected_at <= after

    def test_is_active_defaults_true(self, db: Session, test_organization: Organization, test_user: User):
        from src.models.zendesk_integration import ZendeskIntegration

        integration = ZendeskIntegration(
            organization_id=test_organization.id,
            subdomain="acme",
            email="ops@acme.com",
            api_token="token",
            connected_by_user_id=test_user.id,
        )
        db.add(integration)
        db.commit()
        db.refresh(integration)

        assert integration.is_active is True

    def test_optional_fields_nullable(self, db: Session, test_organization: Organization):
        from src.models.zendesk_integration import ZendeskIntegration

        integration = ZendeskIntegration(
            organization_id=test_organization.id,
            subdomain="acme",
            email="ops@acme.com",
            api_token="token",
        )
        db.add(integration)
        db.commit()
        db.refresh(integration)

        assert integration.connected_by_user_id is None
        assert integration.token_hint is None
        assert integration.webhook_secret is None
        assert integration.account_user_id is None
        assert integration.display_name is None
        assert integration.last_synced_at is None
        assert integration.last_sync_status is None
        assert integration.last_error is None

    def test_unique_organization_id_constraint(self, db: Session, test_organization: Organization, test_user: User):
        from src.models.zendesk_integration import ZendeskIntegration

        integration1 = ZendeskIntegration(
            organization_id=test_organization.id,
            subdomain="acme",
            email="ops@acme.com",
            api_token="token1",
            connected_by_user_id=test_user.id,
        )
        db.add(integration1)
        db.commit()

        integration2 = ZendeskIntegration(
            organization_id=test_organization.id,
            subdomain="acme2",
            email="ops2@acme.com",
            api_token="token2",
            connected_by_user_id=test_user.id,
        )
        db.add(integration2)
        with pytest.raises(IntegrityError):
            db.commit()

    def test_organization_id_required(self, db: Session):
        from src.models.zendesk_integration import ZendeskIntegration

        integration = ZendeskIntegration(
            subdomain="acme",
            email="ops@acme.com",
            api_token="token",
        )
        db.add(integration)
        with pytest.raises(IntegrityError):
            db.commit()

    def test_repr(self, db: Session, test_organization: Organization, test_user: User):
        from src.models.zendesk_integration import ZendeskIntegration

        integration = ZendeskIntegration(
            organization_id=test_organization.id,
            subdomain="acme",
            email="ops@acme.com",
            api_token="token",
            connected_by_user_id=test_user.id,
        )
        db.add(integration)
        db.commit()
        db.refresh(integration)
        assert repr(integration) is not None
