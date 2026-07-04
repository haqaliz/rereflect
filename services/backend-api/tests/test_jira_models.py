"""
TDD tests for Jira Cloud integration database models.

Tests cover 2 new tables:
1. JiraIntegration — org-wide Jira Cloud connection (email + API token, Basic auth)
2. FeedbackJiraIssue — links feedback items to Jira issues
"""
import pytest
from datetime import datetime
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.models.organization import Organization
from src.models.user import User
from src.models.feedback import FeedbackItem


# ---------------------------------------------------------------------------
# 1. JiraIntegration
# ---------------------------------------------------------------------------
class TestJiraIntegrationModel:

    def test_importable(self):
        from src.models.jira_integration import JiraIntegration
        assert JiraIntegration is not None

    def test_exported_from_init(self):
        from src.models import JiraIntegration
        assert JiraIntegration is not None

    def test_table_name(self):
        from src.models.jira_integration import JiraIntegration
        assert JiraIntegration.__tablename__ == "jira_integrations"

    def test_columns_present(self):
        from src.models.jira_integration import JiraIntegration
        columns = JiraIntegration.__table__.columns.keys()
        expected = {
            "id", "organization_id", "site_url", "email", "api_token",
            "token_hint", "account_id", "display_name", "is_active",
            "connected_by_user_id", "connected_at", "last_synced_at",
            "last_sync_status", "last_error", "created_at", "updated_at",
        }
        assert expected.issubset(set(columns))

    def test_unique_constraint_on_organization_id(self):
        from src.models.jira_integration import JiraIntegration
        constraint_names = {
            c.name for c in JiraIntegration.__table__.constraints
            if hasattr(c, "name") and c.name
        }
        assert "uq_jira_integrations_org_id" in constraint_names

    def test_create_integration(self, db: Session, test_organization: Organization, test_user: User):
        from src.models.jira_integration import JiraIntegration

        integration = JiraIntegration(
            organization_id=test_organization.id,
            site_url="https://acme.atlassian.net",
            email="ops@acme.com",
            api_token="encrypted_token_value",
            token_hint="...abcd",
            account_id="account_uuid_123",
            display_name="Acme Ops",
            connected_by_user_id=test_user.id,
        )
        db.add(integration)
        db.commit()
        db.refresh(integration)

        assert integration.id is not None
        assert integration.organization_id == test_organization.id
        assert integration.site_url == "https://acme.atlassian.net"
        assert integration.email == "ops@acme.com"
        assert integration.api_token == "encrypted_token_value"
        assert integration.token_hint == "...abcd"
        assert integration.account_id == "account_uuid_123"
        assert integration.display_name == "Acme Ops"
        assert integration.connected_by_user_id == test_user.id
        assert integration.created_at is not None
        assert integration.updated_at is not None

    def test_connected_at_defaults_to_now(self, db: Session, test_organization: Organization, test_user: User):
        from src.models.jira_integration import JiraIntegration

        before = datetime.utcnow()
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
        after = datetime.utcnow()

        assert integration.connected_at is not None
        assert before <= integration.connected_at <= after

    def test_is_active_defaults_true(self, db: Session, test_organization: Organization, test_user: User):
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

        assert integration.is_active is True

    def test_optional_fields_nullable(self, db: Session, test_organization: Organization):
        from src.models.jira_integration import JiraIntegration

        integration = JiraIntegration(
            organization_id=test_organization.id,
            site_url="https://acme.atlassian.net",
            email="ops@acme.com",
            api_token="token",
        )
        db.add(integration)
        db.commit()
        db.refresh(integration)

        assert integration.connected_by_user_id is None
        assert integration.token_hint is None
        assert integration.account_id is None
        assert integration.display_name is None
        assert integration.last_synced_at is None
        assert integration.last_sync_status is None
        assert integration.last_error is None

    def test_unique_organization_id_constraint(self, db: Session, test_organization: Organization, test_user: User):
        from src.models.jira_integration import JiraIntegration

        integration1 = JiraIntegration(
            organization_id=test_organization.id,
            site_url="https://acme.atlassian.net",
            email="ops@acme.com",
            api_token="token1",
            connected_by_user_id=test_user.id,
        )
        db.add(integration1)
        db.commit()

        integration2 = JiraIntegration(
            organization_id=test_organization.id,
            site_url="https://acme2.atlassian.net",
            email="ops2@acme.com",
            api_token="token2",
            connected_by_user_id=test_user.id,
        )
        db.add(integration2)
        with pytest.raises(IntegrityError):
            db.commit()

    def test_organization_id_required(self, db: Session):
        from src.models.jira_integration import JiraIntegration

        integration = JiraIntegration(
            site_url="https://acme.atlassian.net",
            email="ops@acme.com",
            api_token="token",
        )
        db.add(integration)
        with pytest.raises(IntegrityError):
            db.commit()

    def test_repr(self, db: Session, test_organization: Organization, test_user: User):
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
        assert repr(integration) is not None


# ---------------------------------------------------------------------------
# 2. FeedbackJiraIssue
# ---------------------------------------------------------------------------
class TestFeedbackJiraIssueModel:

    def test_importable(self):
        from src.models.jira_integration import FeedbackJiraIssue
        assert FeedbackJiraIssue is not None

    def test_exported_from_init(self):
        from src.models import FeedbackJiraIssue
        assert FeedbackJiraIssue is not None

    def test_table_name(self):
        from src.models.jira_integration import FeedbackJiraIssue
        assert FeedbackJiraIssue.__tablename__ == "feedback_jira_issues"

    def test_columns_present(self):
        from src.models.jira_integration import FeedbackJiraIssue
        columns = FeedbackJiraIssue.__table__.columns.keys()
        expected = {
            "id", "organization_id", "feedback_id", "jira_issue_id",
            "jira_issue_key", "jira_issue_url", "jira_issue_title",
            "created_by_user_id", "created_at",
        }
        assert expected.issubset(set(columns))

    def test_indexes_on_feedback_id_and_organization_id(self):
        from src.models.jira_integration import FeedbackJiraIssue
        indexed_columns = set()
        for index in FeedbackJiraIssue.__table__.indexes:
            for col in index.columns:
                indexed_columns.add(col.name)
        assert "feedback_id" in indexed_columns
        assert "organization_id" in indexed_columns

    def test_create_feedback_jira_issue(
        self, db: Session, test_organization: Organization, test_user: User, test_feedback: FeedbackItem
    ):
        from src.models.jira_integration import FeedbackJiraIssue

        issue = FeedbackJiraIssue(
            organization_id=test_organization.id,
            feedback_id=test_feedback.id,
            jira_issue_id="10001",
            jira_issue_key="ENG-142",
            jira_issue_url="https://acme.atlassian.net/browse/ENG-142",
            jira_issue_title="Fix CSV export timeout",
            created_by_user_id=test_user.id,
        )
        db.add(issue)
        db.commit()
        db.refresh(issue)

        assert issue.id is not None
        assert issue.organization_id == test_organization.id
        assert issue.feedback_id == test_feedback.id
        assert issue.jira_issue_id == "10001"
        assert issue.jira_issue_key == "ENG-142"
        assert issue.jira_issue_url == "https://acme.atlassian.net/browse/ENG-142"
        assert issue.jira_issue_title == "Fix CSV export timeout"
        assert issue.created_by_user_id == test_user.id
        assert issue.created_at is not None

    def test_multiple_issues_same_feedback(
        self, db: Session, test_organization: Organization, test_user: User, test_feedback: FeedbackItem
    ):
        """Multiple Jira issues can be linked to the same feedback."""
        from src.models.jira_integration import FeedbackJiraIssue

        for i in range(3):
            issue = FeedbackJiraIssue(
                organization_id=test_organization.id,
                feedback_id=test_feedback.id,
                jira_issue_id=f"1000{i}",
                jira_issue_key=f"ENG-{300 + i}",
                jira_issue_url=f"https://acme.atlassian.net/browse/ENG-{300 + i}",
                jira_issue_title=f"Issue {i}",
                created_by_user_id=test_user.id,
            )
            db.add(issue)
        db.commit()

        from sqlalchemy import select
        from src.models.jira_integration import FeedbackJiraIssue as FJI
        results = db.execute(
            select(FJI).where(FJI.feedback_id == test_feedback.id)
        ).scalars().all()
        assert len(results) == 3

    def test_organization_id_required(self, db: Session, test_feedback: FeedbackItem, test_user: User):
        from src.models.jira_integration import FeedbackJiraIssue

        issue = FeedbackJiraIssue(
            feedback_id=test_feedback.id,
            jira_issue_id="10002",
            jira_issue_key="ENG-999",
            jira_issue_url="https://acme.atlassian.net/browse/ENG-999",
            jira_issue_title="No org issue",
            created_by_user_id=test_user.id,
        )
        db.add(issue)
        with pytest.raises(IntegrityError):
            db.commit()

    def test_created_at_defaults_to_now(
        self, db: Session, test_organization: Organization, test_user: User, test_feedback: FeedbackItem
    ):
        from src.models.jira_integration import FeedbackJiraIssue

        before = datetime.utcnow()
        issue = FeedbackJiraIssue(
            organization_id=test_organization.id,
            feedback_id=test_feedback.id,
            jira_issue_id="10003",
            jira_issue_key="ENG-500",
            jira_issue_url="https://acme.atlassian.net/browse/ENG-500",
            jira_issue_title="Timestamp test",
            created_by_user_id=test_user.id,
        )
        db.add(issue)
        db.commit()
        db.refresh(issue)
        after = datetime.utcnow()

        assert before <= issue.created_at <= after

    def test_repr(
        self, db: Session, test_organization: Organization, test_user: User, test_feedback: FeedbackItem
    ):
        from src.models.jira_integration import FeedbackJiraIssue

        issue = FeedbackJiraIssue(
            organization_id=test_organization.id,
            feedback_id=test_feedback.id,
            jira_issue_id="10004",
            jira_issue_key="ENG-501",
            jira_issue_url="https://acme.atlassian.net/browse/ENG-501",
            jira_issue_title="Repr test",
            created_by_user_id=test_user.id,
        )
        db.add(issue)
        db.commit()
        db.refresh(issue)
        assert repr(issue) is not None
