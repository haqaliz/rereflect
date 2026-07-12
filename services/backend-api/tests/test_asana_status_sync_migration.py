"""
TDD tests for the model-migrations aspect of asana-status-sync: new columns on
AsanaIntegration (status_sync_enabled, status_mapping) and FeedbackAsanaTask
(asana_completed, asana_status_category, last_status_synced_at).

Mirrors tests/test_jira_status_sync_migration.py.
See docs/planning/asana-status-sync/model-migrations/plan_20260712.md
"""
from datetime import datetime
from sqlalchemy.orm import Session

from src.models.organization import Organization
from src.models.user import User
from src.models.feedback import FeedbackItem


class TestAsanaIntegrationStatusSyncColumns:

    def test_status_sync_enabled_defaults_false(
        self, db: Session, test_organization: Organization, test_user: User
    ):
        from src.models.asana_integration import AsanaIntegration
        integration = AsanaIntegration(
            organization_id=test_organization.id,
            api_token="token",
            connected_by_user_id=test_user.id,
        )
        db.add(integration); db.commit(); db.refresh(integration)
        assert integration.status_sync_enabled is False

    def test_status_mapping_defaults_none(
        self, db: Session, test_organization: Organization, test_user: User
    ):
        from src.models.asana_integration import AsanaIntegration
        integration = AsanaIntegration(
            organization_id=test_organization.id,
            api_token="token",
            connected_by_user_id=test_user.id,
        )
        db.add(integration); db.commit(); db.refresh(integration)
        assert integration.status_mapping is None

    def test_status_mapping_accepts_dict(
        self, db: Session, test_organization: Organization, test_user: User
    ):
        from src.models.asana_integration import AsanaIntegration
        mapping = {"done": "resolved", "new": "new"}
        integration = AsanaIntegration(
            organization_id=test_organization.id,
            api_token="token",
            connected_by_user_id=test_user.id,
            status_mapping=mapping,
        )
        db.add(integration); db.commit(); db.refresh(integration)
        assert integration.status_mapping == mapping


class TestFeedbackAsanaTaskStatusSyncColumns:

    def test_new_status_columns_default_none(
        self, db: Session, test_organization: Organization, test_user: User, test_feedback: FeedbackItem
    ):
        from src.models.asana_integration import FeedbackAsanaTask
        task = FeedbackAsanaTask(
            organization_id=test_organization.id,
            feedback_id=test_feedback.id,
            asana_task_gid="1201234567890",
            asana_task_url="https://app.asana.com/0/123/1201234567890",
            asana_task_name="Fix CSV export timeout",
            created_by_user_id=test_user.id,
        )
        db.add(task); db.commit(); db.refresh(task)
        assert task.asana_completed is None
        assert task.asana_status_category is None
        assert task.last_status_synced_at is None

    def test_new_status_columns_settable(
        self, db: Session, test_organization: Organization, test_user: User, test_feedback: FeedbackItem
    ):
        from src.models.asana_integration import FeedbackAsanaTask
        synced_at = datetime.utcnow()
        task = FeedbackAsanaTask(
            organization_id=test_organization.id,
            feedback_id=test_feedback.id,
            asana_task_gid="1201234567891",
            asana_task_url="https://app.asana.com/0/123/1201234567891",
            asana_task_name="Another task",
            created_by_user_id=test_user.id,
            asana_completed=True,
            asana_status_category="done",
            last_status_synced_at=synced_at,
        )
        db.add(task); db.commit(); db.refresh(task)
        assert task.asana_completed is True
        assert task.asana_status_category == "done"
        assert task.last_status_synced_at == synced_at
