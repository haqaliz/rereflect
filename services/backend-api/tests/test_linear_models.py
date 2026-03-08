"""
TDD tests for Linear Integration database models.

Tests cover all 4 new tables:
1. LinearIntegration — org-wide OAuth connection
2. LinearTeamMapping — maps Rereflect categories to Linear teams
3. LinearStatusMapping — maps Linear status types to Rereflect statuses
4. FeedbackLinearIssue — links feedback items to Linear issues
"""
import pytest
from datetime import datetime
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.models.organization import Organization
from src.models.user import User
from src.models.feedback import FeedbackItem


# ---------------------------------------------------------------------------
# 1. LinearIntegration
# ---------------------------------------------------------------------------
class TestLinearIntegrationModel:

    def test_importable(self):
        from src.models.linear_integration import LinearIntegration
        assert LinearIntegration is not None

    def test_exported_from_init(self):
        from src.models import LinearIntegration
        assert LinearIntegration is not None

    def test_table_name(self):
        from src.models.linear_integration import LinearIntegration
        assert LinearIntegration.__tablename__ == "linear_integrations"

    def test_create_integration(self, db: Session, test_organization: Organization, test_user: User):
        from src.models.linear_integration import LinearIntegration

        integration = LinearIntegration(
            organization_id=test_organization.id,
            access_token="encrypted_token_value",
            linear_org_id="lin_org_abc123",
            linear_org_name="Acme Corp",
            connected_by_user_id=test_user.id,
            is_active=True,
            webhook_secret="wh_secret_xyz",
        )
        db.add(integration)
        db.commit()
        db.refresh(integration)

        assert integration.id is not None
        assert integration.organization_id == test_organization.id
        assert integration.access_token == "encrypted_token_value"
        assert integration.linear_org_id == "lin_org_abc123"
        assert integration.linear_org_name == "Acme Corp"
        assert integration.connected_by_user_id == test_user.id
        assert integration.is_active is True
        assert integration.webhook_secret == "wh_secret_xyz"
        assert integration.created_at is not None
        assert integration.updated_at is not None

    def test_connected_at_defaults_to_now(self, db: Session, test_organization: Organization, test_user: User):
        from src.models.linear_integration import LinearIntegration

        before = datetime.utcnow()
        integration = LinearIntegration(
            organization_id=test_organization.id,
            access_token="token",
            linear_org_id="lin_org_1",
            linear_org_name="Org 1",
            connected_by_user_id=test_user.id,
            webhook_secret="secret",
        )
        db.add(integration)
        db.commit()
        db.refresh(integration)
        after = datetime.utcnow()

        assert integration.connected_at is not None
        assert before <= integration.connected_at <= after

    def test_is_active_defaults_true(self, db: Session, test_organization: Organization, test_user: User):
        from src.models.linear_integration import LinearIntegration

        integration = LinearIntegration(
            organization_id=test_organization.id,
            access_token="token",
            linear_org_id="lin_org_2",
            linear_org_name="Org 2",
            connected_by_user_id=test_user.id,
            webhook_secret="secret",
        )
        db.add(integration)
        db.commit()
        db.refresh(integration)

        assert integration.is_active is True

    def test_unique_organization_id_constraint(self, db: Session, test_organization: Organization, test_user: User):
        from src.models.linear_integration import LinearIntegration

        integration1 = LinearIntegration(
            organization_id=test_organization.id,
            access_token="token1",
            linear_org_id="lin_org_dup",
            linear_org_name="Dup Org",
            connected_by_user_id=test_user.id,
            webhook_secret="secret1",
        )
        db.add(integration1)
        db.commit()

        integration2 = LinearIntegration(
            organization_id=test_organization.id,
            access_token="token2",
            linear_org_id="lin_org_dup2",
            linear_org_name="Dup Org 2",
            connected_by_user_id=test_user.id,
            webhook_secret="secret2",
        )
        db.add(integration2)
        with pytest.raises(IntegrityError):
            db.commit()

    def test_organization_id_required(self, db: Session):
        from src.models.linear_integration import LinearIntegration

        integration = LinearIntegration(
            access_token="token",
            linear_org_id="lin_org_3",
            linear_org_name="Org 3",
            webhook_secret="secret",
        )
        db.add(integration)
        with pytest.raises(IntegrityError):
            db.commit()

    def test_repr(self, db: Session, test_organization: Organization, test_user: User):
        from src.models.linear_integration import LinearIntegration

        integration = LinearIntegration(
            organization_id=test_organization.id,
            access_token="token",
            linear_org_id="lin_org_r",
            linear_org_name="Repr Org",
            connected_by_user_id=test_user.id,
            webhook_secret="secret",
        )
        db.add(integration)
        db.commit()
        db.refresh(integration)
        assert repr(integration) is not None


# ---------------------------------------------------------------------------
# 2. LinearTeamMapping
# ---------------------------------------------------------------------------
class TestLinearTeamMappingModel:

    def test_importable(self):
        from src.models.linear_integration import LinearTeamMapping
        assert LinearTeamMapping is not None

    def test_exported_from_init(self):
        from src.models import LinearTeamMapping
        assert LinearTeamMapping is not None

    def test_table_name(self):
        from src.models.linear_integration import LinearTeamMapping
        assert LinearTeamMapping.__tablename__ == "linear_team_mappings"

    def test_create_team_mapping(self, db: Session, test_organization: Organization):
        from src.models.linear_integration import LinearTeamMapping

        mapping = LinearTeamMapping(
            organization_id=test_organization.id,
            rereflect_category="pain_point",
            linear_team_id="team_uuid_abc",
            linear_team_name="Engineering",
            linear_project_id="proj_uuid_xyz",
            linear_project_name="Q1 Roadmap",
            priority=1,
        )
        db.add(mapping)
        db.commit()
        db.refresh(mapping)

        assert mapping.id is not None
        assert mapping.organization_id == test_organization.id
        assert mapping.rereflect_category == "pain_point"
        assert mapping.linear_team_id == "team_uuid_abc"
        assert mapping.linear_team_name == "Engineering"
        assert mapping.linear_project_id == "proj_uuid_xyz"
        assert mapping.linear_project_name == "Q1 Roadmap"
        assert mapping.priority == 1

    def test_optional_project_fields(self, db: Session, test_organization: Organization):
        from src.models.linear_integration import LinearTeamMapping

        mapping = LinearTeamMapping(
            organization_id=test_organization.id,
            rereflect_category="feature_request",
            linear_team_id="team_uuid_def",
            linear_team_name="Product",
            priority=0,
        )
        db.add(mapping)
        db.commit()
        db.refresh(mapping)

        assert mapping.linear_project_id is None
        assert mapping.linear_project_name is None

    def test_multiple_categories_same_org(self, db: Session, test_organization: Organization):
        from src.models.linear_integration import LinearTeamMapping

        categories = ["pain_point", "feature_request", "bug"]
        for i, category in enumerate(categories):
            mapping = LinearTeamMapping(
                organization_id=test_organization.id,
                rereflect_category=category,
                linear_team_id=f"team_{i}",
                linear_team_name=f"Team {i}",
                priority=i,
            )
            db.add(mapping)
        db.commit()

        from sqlalchemy import select
        from src.models.linear_integration import LinearTeamMapping as LTM
        results = db.execute(
            select(LTM).where(LTM.organization_id == test_organization.id)
        ).scalars().all()
        assert len(results) == 3

    def test_organization_id_required(self, db: Session):
        from src.models.linear_integration import LinearTeamMapping

        mapping = LinearTeamMapping(
            rereflect_category="pain_point",
            linear_team_id="team_xyz",
            linear_team_name="Engineering",
            priority=0,
        )
        db.add(mapping)
        with pytest.raises(IntegrityError):
            db.commit()


# ---------------------------------------------------------------------------
# 3. LinearStatusMapping
# ---------------------------------------------------------------------------
class TestLinearStatusMappingModel:

    def test_importable(self):
        from src.models.linear_integration import LinearStatusMapping
        assert LinearStatusMapping is not None

    def test_exported_from_init(self):
        from src.models import LinearStatusMapping
        assert LinearStatusMapping is not None

    def test_table_name(self):
        from src.models.linear_integration import LinearStatusMapping
        assert LinearStatusMapping.__tablename__ == "linear_status_mappings"

    def test_create_status_mapping(self, db: Session, test_organization: Organization):
        from src.models.linear_integration import LinearStatusMapping

        mapping = LinearStatusMapping(
            organization_id=test_organization.id,
            linear_status_name="In Progress",
            linear_status_type="started",
            rereflect_status="in_review",
        )
        db.add(mapping)
        db.commit()
        db.refresh(mapping)

        assert mapping.id is not None
        assert mapping.organization_id == test_organization.id
        assert mapping.linear_status_name == "In Progress"
        assert mapping.linear_status_type == "started"
        assert mapping.rereflect_status == "in_review"

    def test_all_default_status_types(self, db: Session, test_organization: Organization):
        """Verify that all default Linear status types can be stored."""
        from src.models.linear_integration import LinearStatusMapping

        default_mappings = [
            ("backlog", "Backlog", "new"),
            ("unstarted", "Todo", "new"),
            ("started", "In Progress", "in_review"),
            ("completed", "Done", "resolved"),
            ("canceled", "Cancelled", "closed"),
        ]
        for status_type, status_name, rr_status in default_mappings:
            mapping = LinearStatusMapping(
                organization_id=test_organization.id,
                linear_status_type=status_type,
                linear_status_name=status_name,
                rereflect_status=rr_status,
            )
            db.add(mapping)
        db.commit()

        from sqlalchemy import select
        from src.models.linear_integration import LinearStatusMapping as LSM
        results = db.execute(
            select(LSM).where(LSM.organization_id == test_organization.id)
        ).scalars().all()
        assert len(results) == 5

    def test_organization_id_required(self, db: Session):
        from src.models.linear_integration import LinearStatusMapping

        mapping = LinearStatusMapping(
            linear_status_name="Done",
            linear_status_type="completed",
            rereflect_status="resolved",
        )
        db.add(mapping)
        with pytest.raises(IntegrityError):
            db.commit()


# ---------------------------------------------------------------------------
# 4. FeedbackLinearIssue
# ---------------------------------------------------------------------------
class TestFeedbackLinearIssueModel:

    def test_importable(self):
        from src.models.linear_integration import FeedbackLinearIssue
        assert FeedbackLinearIssue is not None

    def test_exported_from_init(self):
        from src.models import FeedbackLinearIssue
        assert FeedbackLinearIssue is not None

    def test_table_name(self):
        from src.models.linear_integration import FeedbackLinearIssue
        assert FeedbackLinearIssue.__tablename__ == "feedback_linear_issues"

    def test_create_feedback_linear_issue(
        self, db: Session, test_organization: Organization, test_user: User, test_feedback: FeedbackItem
    ):
        from src.models.linear_integration import FeedbackLinearIssue

        issue = FeedbackLinearIssue(
            organization_id=test_organization.id,
            feedback_id=test_feedback.id,
            linear_issue_id="lin_issue_uuid_123",
            linear_issue_identifier="ENG-142",
            linear_issue_url="https://linear.app/acme/issue/ENG-142",
            linear_issue_title="Fix CSV export timeout",
            linear_status="In Progress",
            linear_assignee="Jane Doe",
            linear_priority=2,
            created_by_user_id=test_user.id,
        )
        db.add(issue)
        db.commit()
        db.refresh(issue)

        assert issue.id is not None
        assert issue.organization_id == test_organization.id
        assert issue.feedback_id == test_feedback.id
        assert issue.linear_issue_id == "lin_issue_uuid_123"
        assert issue.linear_issue_identifier == "ENG-142"
        assert issue.linear_issue_url == "https://linear.app/acme/issue/ENG-142"
        assert issue.linear_issue_title == "Fix CSV export timeout"
        assert issue.linear_status == "In Progress"
        assert issue.linear_assignee == "Jane Doe"
        assert issue.linear_priority == 2
        assert issue.created_by_user_id == test_user.id
        assert issue.created_at is not None
        assert issue.updated_at is not None

    def test_optional_status_assignee_priority(
        self, db: Session, test_organization: Organization, test_user: User, test_feedback: FeedbackItem
    ):
        from src.models.linear_integration import FeedbackLinearIssue

        issue = FeedbackLinearIssue(
            organization_id=test_organization.id,
            feedback_id=test_feedback.id,
            linear_issue_id="lin_issue_uuid_456",
            linear_issue_identifier="ENG-200",
            linear_issue_url="https://linear.app/acme/issue/ENG-200",
            linear_issue_title="Another issue",
            created_by_user_id=test_user.id,
        )
        db.add(issue)
        db.commit()
        db.refresh(issue)

        assert issue.linear_status is None
        assert issue.linear_assignee is None
        assert issue.linear_priority is None

    def test_multiple_issues_same_feedback(
        self, db: Session, test_organization: Organization, test_user: User, test_feedback: FeedbackItem
    ):
        """Multiple Linear issues can be linked to the same feedback."""
        from src.models.linear_integration import FeedbackLinearIssue

        for i in range(3):
            issue = FeedbackLinearIssue(
                organization_id=test_organization.id,
                feedback_id=test_feedback.id,
                linear_issue_id=f"lin_issue_{i}",
                linear_issue_identifier=f"ENG-{300 + i}",
                linear_issue_url=f"https://linear.app/acme/issue/ENG-{300 + i}",
                linear_issue_title=f"Issue {i}",
                created_by_user_id=test_user.id,
            )
            db.add(issue)
        db.commit()

        from sqlalchemy import select
        from src.models.linear_integration import FeedbackLinearIssue as FLI
        results = db.execute(
            select(FLI).where(FLI.feedback_id == test_feedback.id)
        ).scalars().all()
        assert len(results) == 3

    def test_organization_id_required(self, db: Session, test_feedback: FeedbackItem, test_user: User):
        from src.models.linear_integration import FeedbackLinearIssue

        issue = FeedbackLinearIssue(
            feedback_id=test_feedback.id,
            linear_issue_id="lin_issue_xyz",
            linear_issue_identifier="ENG-999",
            linear_issue_url="https://linear.app/acme/issue/ENG-999",
            linear_issue_title="No org issue",
            created_by_user_id=test_user.id,
        )
        db.add(issue)
        with pytest.raises(IntegrityError):
            db.commit()

    def test_created_at_defaults_to_now(
        self, db: Session, test_organization: Organization, test_user: User, test_feedback: FeedbackItem
    ):
        from src.models.linear_integration import FeedbackLinearIssue

        before = datetime.utcnow()
        issue = FeedbackLinearIssue(
            organization_id=test_organization.id,
            feedback_id=test_feedback.id,
            linear_issue_id="lin_ts_test",
            linear_issue_identifier="ENG-500",
            linear_issue_url="https://linear.app/acme/issue/ENG-500",
            linear_issue_title="Timestamp test",
            created_by_user_id=test_user.id,
        )
        db.add(issue)
        db.commit()
        db.refresh(issue)
        after = datetime.utcnow()

        assert before <= issue.created_at <= after
