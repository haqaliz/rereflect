"""
TDD tests for Asana integration database models.

Tests cover 2 new tables:
1. AsanaIntegration — org-wide Asana connection (Personal Access Token, Bearer auth)
2. FeedbackAsanaTask — links feedback items to Asana tasks
"""
import pytest
from datetime import datetime
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.models.organization import Organization
from src.models.user import User
from src.models.feedback import FeedbackItem


# ---------------------------------------------------------------------------
# 1. AsanaIntegration
# ---------------------------------------------------------------------------
class TestAsanaIntegrationModel:

    def test_importable(self):
        from src.models.asana_integration import AsanaIntegration
        assert AsanaIntegration is not None

    def test_exported_from_init(self):
        from src.models import AsanaIntegration
        assert AsanaIntegration is not None

    def test_table_name(self):
        from src.models.asana_integration import AsanaIntegration
        assert AsanaIntegration.__tablename__ == "asana_integrations"

    def test_columns_present(self):
        from src.models.asana_integration import AsanaIntegration
        columns = AsanaIntegration.__table__.columns.keys()
        expected = {
            "id", "organization_id", "api_token", "token_hint",
            "account_gid", "display_name", "is_active",
            "connected_by_user_id", "connected_at", "last_synced_at",
            "last_sync_status", "last_error", "created_at", "updated_at",
        }
        assert expected.issubset(set(columns))

    def test_no_site_url_or_email_columns(self):
        """Asana is Bearer PAT + fixed host — no site_url/email columns (contrast with Jira)."""
        from src.models.asana_integration import AsanaIntegration
        columns = set(AsanaIntegration.__table__.columns.keys())
        assert "site_url" not in columns
        assert "email" not in columns

    def test_unique_constraint_on_organization_id(self):
        from src.models.asana_integration import AsanaIntegration
        constraint_names = {
            c.name for c in AsanaIntegration.__table__.constraints
            if hasattr(c, "name") and c.name
        }
        assert "uq_asana_integrations_org_id" in constraint_names

    def test_index_on_organization_id(self):
        from src.models.asana_integration import AsanaIntegration
        indexed_columns = set()
        for index in AsanaIntegration.__table__.indexes:
            for col in index.columns:
                indexed_columns.add(col.name)
        assert "organization_id" in indexed_columns

    def test_create_integration(self, db: Session, test_organization: Organization, test_user: User):
        from src.models.asana_integration import AsanaIntegration

        integration = AsanaIntegration(
            organization_id=test_organization.id,
            api_token="encrypted_token_value",
            token_hint="...abcd",
            account_gid="account_gid_123",
            display_name="Acme Ops",
            connected_by_user_id=test_user.id,
        )
        db.add(integration)
        db.commit()
        db.refresh(integration)

        assert integration.id is not None
        assert integration.organization_id == test_organization.id
        assert integration.api_token == "encrypted_token_value"
        assert integration.token_hint == "...abcd"
        assert integration.account_gid == "account_gid_123"
        assert integration.display_name == "Acme Ops"
        assert integration.connected_by_user_id == test_user.id
        assert integration.created_at is not None
        assert integration.updated_at is not None

    def test_connected_at_defaults_to_now(self, db: Session, test_organization: Organization, test_user: User):
        from src.models.asana_integration import AsanaIntegration

        before = datetime.utcnow()
        integration = AsanaIntegration(
            organization_id=test_organization.id,
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
        from src.models.asana_integration import AsanaIntegration

        integration = AsanaIntegration(
            organization_id=test_organization.id,
            api_token="token",
            connected_by_user_id=test_user.id,
        )
        db.add(integration)
        db.commit()
        db.refresh(integration)

        assert integration.is_active is True

    def test_optional_fields_nullable(self, db: Session, test_organization: Organization):
        from src.models.asana_integration import AsanaIntegration

        integration = AsanaIntegration(
            organization_id=test_organization.id,
            api_token="token",
        )
        db.add(integration)
        db.commit()
        db.refresh(integration)

        assert integration.connected_by_user_id is None
        assert integration.token_hint is None
        assert integration.account_gid is None
        assert integration.display_name is None
        assert integration.last_synced_at is None
        assert integration.last_sync_status is None
        assert integration.last_error is None

    def test_unique_organization_id_constraint(self, db: Session, test_organization: Organization, test_user: User):
        from src.models.asana_integration import AsanaIntegration

        integration1 = AsanaIntegration(
            organization_id=test_organization.id,
            api_token="token1",
            connected_by_user_id=test_user.id,
        )
        db.add(integration1)
        db.commit()

        integration2 = AsanaIntegration(
            organization_id=test_organization.id,
            api_token="token2",
            connected_by_user_id=test_user.id,
        )
        db.add(integration2)
        with pytest.raises(IntegrityError):
            db.commit()

    def test_organization_id_required(self, db: Session):
        from src.models.asana_integration import AsanaIntegration

        integration = AsanaIntegration(
            api_token="token",
        )
        db.add(integration)
        with pytest.raises(IntegrityError):
            db.commit()

    def test_connected_by_user_id_is_set_null_on_delete(self):
        """FK config check — actual cascade behavior requires DB-level FK enforcement
        (not active under the in-memory SQLite test engine), so this asserts the
        ondelete configuration directly (mirrors the Jira precedent's approach)."""
        from src.models.asana_integration import AsanaIntegration

        fk = next(iter(AsanaIntegration.__table__.c.connected_by_user_id.foreign_keys))
        assert fk.ondelete == "SET NULL"

    def test_organization_id_is_cascade_on_delete(self):
        from src.models.asana_integration import AsanaIntegration

        fk = next(iter(AsanaIntegration.__table__.c.organization_id.foreign_keys))
        assert fk.ondelete == "CASCADE"

    def test_repr(self, db: Session, test_organization: Organization, test_user: User):
        from src.models.asana_integration import AsanaIntegration

        integration = AsanaIntegration(
            organization_id=test_organization.id,
            api_token="token",
            connected_by_user_id=test_user.id,
        )
        db.add(integration)
        db.commit()
        db.refresh(integration)
        assert repr(integration) is not None

    def test_repr_excludes_token(self, db: Session, test_organization: Organization, test_user: User):
        from src.models.asana_integration import AsanaIntegration

        integration = AsanaIntegration(
            organization_id=test_organization.id,
            api_token="super-secret-plaintext-or-encrypted",
            connected_by_user_id=test_user.id,
        )
        db.add(integration)
        db.commit()
        db.refresh(integration)
        assert "super-secret-plaintext-or-encrypted" not in repr(integration)
        assert "super-secret-plaintext-or-encrypted" not in str(integration)


# ---------------------------------------------------------------------------
# 2. FeedbackAsanaTask
# ---------------------------------------------------------------------------
class TestFeedbackAsanaTaskModel:

    def test_importable(self):
        from src.models.asana_integration import FeedbackAsanaTask
        assert FeedbackAsanaTask is not None

    def test_exported_from_init(self):
        from src.models import FeedbackAsanaTask
        assert FeedbackAsanaTask is not None

    def test_table_name(self):
        from src.models.asana_integration import FeedbackAsanaTask
        assert FeedbackAsanaTask.__tablename__ == "feedback_asana_tasks"

    def test_columns_present(self):
        from src.models.asana_integration import FeedbackAsanaTask
        columns = FeedbackAsanaTask.__table__.columns.keys()
        expected = {
            "id", "organization_id", "feedback_id", "asana_task_gid",
            "asana_task_url", "asana_task_name",
            "created_by_user_id", "created_at",
        }
        assert expected.issubset(set(columns))

    def test_indexes_on_feedback_id_and_organization_id(self):
        from src.models.asana_integration import FeedbackAsanaTask
        indexed_columns = set()
        for index in FeedbackAsanaTask.__table__.indexes:
            for col in index.columns:
                indexed_columns.add(col.name)
        assert "feedback_id" in indexed_columns
        assert "organization_id" in indexed_columns

    def test_create_feedback_asana_task(
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
        db.add(task)
        db.commit()
        db.refresh(task)

        assert task.id is not None
        assert task.organization_id == test_organization.id
        assert task.feedback_id == test_feedback.id
        assert task.asana_task_gid == "1201234567890"
        assert task.asana_task_url == "https://app.asana.com/0/123/1201234567890"
        assert task.asana_task_name == "Fix CSV export timeout"
        assert task.created_by_user_id == test_user.id
        assert task.created_at is not None

    def test_multiple_tasks_same_feedback(
        self, db: Session, test_organization: Organization, test_user: User, test_feedback: FeedbackItem
    ):
        """Multiple Asana tasks can be linked to the same feedback."""
        from src.models.asana_integration import FeedbackAsanaTask

        for i in range(3):
            task = FeedbackAsanaTask(
                organization_id=test_organization.id,
                feedback_id=test_feedback.id,
                asana_task_gid=f"120123456789{i}",
                asana_task_url=f"https://app.asana.com/0/123/120123456789{i}",
                asana_task_name=f"Task {i}",
                created_by_user_id=test_user.id,
            )
            db.add(task)
        db.commit()

        from sqlalchemy import select
        from src.models.asana_integration import FeedbackAsanaTask as FAT
        results = db.execute(
            select(FAT).where(FAT.feedback_id == test_feedback.id)
        ).scalars().all()
        assert len(results) == 3

    def test_organization_id_required(self, db: Session, test_feedback: FeedbackItem, test_user: User):
        from src.models.asana_integration import FeedbackAsanaTask

        task = FeedbackAsanaTask(
            feedback_id=test_feedback.id,
            asana_task_gid="1201234567999",
            asana_task_url="https://app.asana.com/0/123/1201234567999",
            asana_task_name="No org task",
            created_by_user_id=test_user.id,
        )
        db.add(task)
        with pytest.raises(IntegrityError):
            db.commit()

    def test_feedback_id_is_cascade_on_delete(self):
        """FK config check — see AsanaIntegration's equivalent test for rationale."""
        from src.models.asana_integration import FeedbackAsanaTask

        fk = next(iter(FeedbackAsanaTask.__table__.c.feedback_id.foreign_keys))
        assert fk.ondelete == "CASCADE"

    def test_created_at_defaults_to_now(
        self, db: Session, test_organization: Organization, test_user: User, test_feedback: FeedbackItem
    ):
        from src.models.asana_integration import FeedbackAsanaTask

        before = datetime.utcnow()
        task = FeedbackAsanaTask(
            organization_id=test_organization.id,
            feedback_id=test_feedback.id,
            asana_task_gid="1201234567500",
            asana_task_url="https://app.asana.com/0/123/1201234567500",
            asana_task_name="Timestamp test",
            created_by_user_id=test_user.id,
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        after = datetime.utcnow()

        assert before <= task.created_at <= after

    def test_repr(
        self, db: Session, test_organization: Organization, test_user: User, test_feedback: FeedbackItem
    ):
        from src.models.asana_integration import FeedbackAsanaTask

        task = FeedbackAsanaTask(
            organization_id=test_organization.id,
            feedback_id=test_feedback.id,
            asana_task_gid="1201234567501",
            asana_task_url="https://app.asana.com/0/123/1201234567501",
            asana_task_name="Repr test",
            created_by_user_id=test_user.id,
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        assert repr(task) is not None
