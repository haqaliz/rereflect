"""
TDD tests for Phase 1 of the jira-webhook aspect (status-sync-realtime-mapping
PRD): a new `jira_integrations.webhook_secret` column (Text, nullable,
Fernet-encrypted at the route layer — this module only asserts the column
exists, is nullable, and round-trips an arbitrary string; encryption itself
is exercised by tests/test_jira_webhook_routes.py).

Mirrors the model-level test style of tests/test_jira_status_sync_migration.py
(uses the `db` fixture, which builds schema via Base.metadata.create_all —
see tests/conftest.py — rather than running the real Alembic chain; the
actual alembic/versions/<rev>_add_jira_webhook_secret.py migration is
hand-verified separately per the plan's Validation step, since the full
chain requires PostgreSQL-only DDL used by earlier migrations).

See docs/planning/status-sync-realtime-mapping/jira-webhook/plan_20260718.md
Phase 1.
"""
from sqlalchemy.orm import Session

from src.models.organization import Organization
from src.models.user import User


class TestJiraIntegrationWebhookSecretColumn:

    def test_webhook_secret_defaults_none(
        self, db: Session, test_organization: Organization, test_user: User
    ):
        from src.models.jira_integration import JiraIntegration

        integration = JiraIntegration(
            organization_id=test_organization.id,
            site_url="https://acme.atlassian.net",
            email="ops@acme.com",
            api_token="token",
            connected_by_user_id=test_user.id,
        )
        db.add(integration)
        db.commit()
        db.refresh(integration)

        assert integration.webhook_secret is None

    def test_webhook_secret_settable_and_nullable(
        self, db: Session, test_organization: Organization, test_user: User
    ):
        from src.models.jira_integration import JiraIntegration

        integration = JiraIntegration(
            organization_id=test_organization.id,
            site_url="https://acme.atlassian.net",
            email="ops@acme.com",
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

    def test_webhook_secret_is_text_column_type(self):
        from src.models.jira_integration import JiraIntegration
        import sqlalchemy as sa

        column = JiraIntegration.__table__.columns["webhook_secret"]
        assert isinstance(column.type, sa.Text)
        assert column.nullable is True
