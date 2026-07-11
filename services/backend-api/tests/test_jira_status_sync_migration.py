"""
TDD tests for Phase 1 of Jira inbound status sync: new columns on
JiraIntegration (status_sync_enabled, status_mapping) and FeedbackJiraIssue
(jira_status, jira_status_category, last_status_synced_at).

See docs/planning/jira-status-sync/inbound-status-sync/plan_20260711.md
"""
from sqlalchemy.orm import Session

from src.models.organization import Organization
from src.models.user import User
from src.models.feedback import FeedbackItem


class TestJiraIntegrationStatusSyncColumns:

    def test_status_sync_enabled_defaults_false(
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

        assert integration.status_sync_enabled is False

    def test_status_mapping_accepts_dict(
        self, db: Session, test_organization: Organization, test_user: User
    ):
        from src.models.jira_integration import JiraIntegration

        mapping = {"To Do": "open", "In Progress": "in_progress", "Done": "resolved"}
        integration = JiraIntegration(
            organization_id=test_organization.id,
            site_url="https://acme.atlassian.net",
            email="ops@acme.com",
            api_token="token",
            connected_by_user_id=test_user.id,
            status_mapping=mapping,
        )
        db.add(integration)
        db.commit()
        db.refresh(integration)

        assert integration.status_mapping == mapping


class TestFeedbackJiraIssueStatusSyncColumns:

    def test_new_status_columns_exist_and_default_none(
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

        assert issue.jira_status is None
        assert issue.jira_status_category is None
        assert issue.last_status_synced_at is None

    def test_new_status_columns_settable(
        self, db: Session, test_organization: Organization, test_user: User, test_feedback: FeedbackItem
    ):
        from datetime import datetime
        from src.models.jira_integration import FeedbackJiraIssue

        synced_at = datetime.utcnow()
        issue = FeedbackJiraIssue(
            organization_id=test_organization.id,
            feedback_id=test_feedback.id,
            jira_issue_id="10002",
            jira_issue_key="ENG-143",
            jira_issue_url="https://acme.atlassian.net/browse/ENG-143",
            jira_issue_title="Another issue",
            created_by_user_id=test_user.id,
            jira_status="In Progress",
            jira_status_category="indeterminate",
            last_status_synced_at=synced_at,
        )
        db.add(issue)
        db.commit()
        db.refresh(issue)

        assert issue.jira_status == "In Progress"
        assert issue.jira_status_category == "indeterminate"
        assert issue.last_status_synced_at == synced_at
