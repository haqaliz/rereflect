"""
Tests for Linear issue creation endpoint.
Covers: AI generation, issue creation, duplicate warning, linked issues query, timeline entry.
"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.models.organization import Organization
from src.models.feedback import FeedbackItem


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def linear_integration(db: Session, test_organization: Organization):
    """Create an active LinearIntegration for the test org."""
    from src.models.linear_integration import LinearIntegration
    integration = LinearIntegration(
        organization_id=test_organization.id,
        access_token="encrypted-token-xyz",
        linear_org_id="linear-org-abc",
        linear_org_name="Acme Linear",
        is_active=True,
        webhook_secret="webhook-secret-123",
        webhook_id="webhook-uuid-1",
    )
    db.add(integration)
    db.commit()
    db.refresh(integration)
    return integration


@pytest.fixture
def feedback_item(db: Session, test_organization: Organization) -> FeedbackItem:
    """Create a test feedback item."""
    feedback = FeedbackItem(
        organization_id=test_organization.id,
        text="The CSV export fails for large datasets. Very frustrating!",
        source="email",
        sentiment_label="negative",
        sentiment_score=-0.85,
        is_urgent=True,
        extracted_issue="CSV export failure",
    )
    db.add(feedback)
    db.commit()
    db.refresh(feedback)
    return feedback


@pytest.fixture
def linked_issue(db: Session, test_organization: Organization, feedback_item: FeedbackItem):
    """Create a FeedbackLinearIssue link."""
    from src.models.linear_integration import FeedbackLinearIssue
    link = FeedbackLinearIssue(
        organization_id=test_organization.id,
        feedback_id=feedback_item.id,
        linear_issue_id="issue-uuid-existing",
        linear_issue_identifier="ENG-100",
        linear_issue_url="https://linear.app/acme/issue/ENG-100",
        linear_issue_title="Previous issue",
        linear_status="Todo",
    )
    db.add(link)
    db.commit()
    db.refresh(link)
    return link


# ============================================================================
# POST /api/v1/integrations/linear/issues Tests
# ============================================================================

class TestCreateLinearIssue:
    """Tests for POST /api/v1/integrations/linear/issues."""

    def test_create_issue_success(
        self,
        client: TestClient,
        auth_headers: dict,
        db: Session,
        linear_integration,
        feedback_item: FeedbackItem,
    ):
        """Should create a Linear issue and store link in DB."""
        with patch("src.api.routes.linear_integration.LinearClient") as MockLinearClient:
            mock_linear = AsyncMock()
            mock_linear.create_issue.return_value = {
                "id": "issue-uuid-new",
                "identifier": "ENG-142",
                "title": "Fix CSV export timeout for large datasets",
                "url": "https://linear.app/acme/issue/ENG-142",
                "priority": 2,
                "state": {"name": "Todo", "type": "unstarted"},
            }
            MockLinearClient.return_value = mock_linear

            response = client.post(
                "/api/v1/integrations/linear/issues",
                headers=auth_headers,
                json={
                    "feedback_id": feedback_item.id,
                    "team_id": "team-engineering",
                    "title": "Fix CSV export timeout for large datasets",
                    "description": "## Summary\n\nCSV export fails...",
                    "priority": 2,
                    "label_ids": [],
                },
            )

        assert response.status_code == 201
        data = response.json()
        assert data["linear_issue_identifier"] == "ENG-142"
        assert data["linear_issue_url"] == "https://linear.app/acme/issue/ENG-142"

        from src.models.linear_integration import FeedbackLinearIssue
        link = db.query(FeedbackLinearIssue).filter(
            FeedbackLinearIssue.feedback_id == feedback_item.id
        ).first()
        assert link is not None
        assert link.linear_issue_id == "issue-uuid-new"

    def test_create_issue_without_title_generates_ai_content(
        self,
        client: TestClient,
        auth_headers: dict,
        linear_integration,
        feedback_item: FeedbackItem,
    ):
        """Should call AI generator when title/description not provided."""
        with patch("src.api.routes.linear_integration.LinearClient") as MockLinearClient:
            mock_linear = AsyncMock()
            mock_linear.create_issue.return_value = {
                "id": "issue-uuid-ai",
                "identifier": "ENG-200",
                "title": "AI-generated title",
                "url": "https://linear.app/acme/issue/ENG-200",
                "priority": 2,
                "state": {"name": "Todo", "type": "unstarted"},
            }
            MockLinearClient.return_value = mock_linear

            with patch("src.api.routes.linear_integration.generate_linear_issue_content") as mock_gen:
                mock_gen.return_value = {
                    "title": "AI-generated title",
                    "description": "AI-generated description",
                }

                response = client.post(
                    "/api/v1/integrations/linear/issues",
                    headers=auth_headers,
                    json={
                        "feedback_id": feedback_item.id,
                        "team_id": "team-1",
                        # No title or description
                    },
                )

            mock_gen.assert_called_once()

        assert response.status_code == 201

    def test_create_issue_warns_on_duplicate(
        self,
        client: TestClient,
        auth_headers: dict,
        linear_integration,
        feedback_item: FeedbackItem,
        linked_issue,
    ):
        """Should return 200 with existing_issues warning when feedback already linked."""
        response = client.post(
            "/api/v1/integrations/linear/issues",
            headers=auth_headers,
            json={
                "feedback_id": feedback_item.id,
                "team_id": "team-1",
                "title": "Another issue",
                "description": "More details",
                "force": False,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["warning"] == "duplicate"
        assert len(data["existing_issues"]) == 1
        assert data["existing_issues"][0]["linear_issue_identifier"] == "ENG-100"

    def test_create_issue_allows_force_duplicate(
        self,
        client: TestClient,
        auth_headers: dict,
        linear_integration,
        feedback_item: FeedbackItem,
        linked_issue,
        db: Session,
    ):
        """Should create issue even if one exists when force=True."""
        with patch("src.api.routes.linear_integration.LinearClient") as MockLinearClient:
            mock_linear = AsyncMock()
            mock_linear.create_issue.return_value = {
                "id": "issue-uuid-force",
                "identifier": "ENG-999",
                "title": "Force-created issue",
                "url": "https://linear.app/acme/issue/ENG-999",
                "priority": 3,
                "state": {"name": "Todo", "type": "unstarted"},
            }
            MockLinearClient.return_value = mock_linear

            response = client.post(
                "/api/v1/integrations/linear/issues",
                headers=auth_headers,
                json={
                    "feedback_id": feedback_item.id,
                    "team_id": "team-1",
                    "title": "Force-created issue",
                    "description": "Details",
                    "force": True,
                },
            )

        assert response.status_code == 201

    def test_create_issue_requires_linear_connection(
        self,
        client: TestClient,
        auth_headers: dict,
        feedback_item: FeedbackItem,
    ):
        """Should return 400 when no active Linear integration exists."""
        response = client.post(
            "/api/v1/integrations/linear/issues",
            headers=auth_headers,
            json={
                "feedback_id": feedback_item.id,
                "team_id": "team-1",
                "title": "Test",
                "description": "Test",
            },
        )
        assert response.status_code == 400

    def test_create_issue_returns_404_for_missing_feedback(
        self,
        client: TestClient,
        auth_headers: dict,
        linear_integration,
    ):
        """Should return 404 when feedback_id does not exist."""
        response = client.post(
            "/api/v1/integrations/linear/issues",
            headers=auth_headers,
            json={
                "feedback_id": 99999,
                "team_id": "team-1",
                "title": "Test",
                "description": "Test",
            },
        )
        assert response.status_code == 404

    def test_create_issue_requires_auth(
        self,
        client: TestClient,
        feedback_item: FeedbackItem,
    ):
        """Should reject unauthenticated requests."""
        response = client.post(
            "/api/v1/integrations/linear/issues",
            json={
                "feedback_id": feedback_item.id,
                "team_id": "team-1",
                "title": "Test",
                "description": "Test",
            },
        )
        assert response.status_code == 403

    def test_create_issue_adds_timeline_entry(
        self,
        client: TestClient,
        auth_headers: dict,
        db: Session,
        linear_integration,
        feedback_item: FeedbackItem,
        test_user,
    ):
        """Should add a timeline entry to the feedback after issue creation."""
        with patch("src.api.routes.linear_integration.LinearClient") as MockLinearClient:
            mock_linear = AsyncMock()
            mock_linear.create_issue.return_value = {
                "id": "issue-timeline",
                "identifier": "ENG-300",
                "title": "Timeline test",
                "url": "https://linear.app/acme/issue/ENG-300",
                "priority": 0,
                "state": {"name": "Todo", "type": "unstarted"},
            }
            MockLinearClient.return_value = mock_linear

            client.post(
                "/api/v1/integrations/linear/issues",
                headers=auth_headers,
                json={
                    "feedback_id": feedback_item.id,
                    "team_id": "team-1",
                    "title": "Timeline test",
                    "description": "Details",
                },
            )

        # Check that a workflow event / timeline entry was created
        from src.models.feedback_workflow_event import FeedbackWorkflowEvent
        event = db.query(FeedbackWorkflowEvent).filter(
            FeedbackWorkflowEvent.feedback_id == feedback_item.id,
        ).first()
        assert event is not None
        # Event should reference the linear issue in metadata or event_type
        metadata = event.metadata_ or {}
        event_type = event.event_type or ""
        assert "ENG-300" in str(metadata) or "linear" in event_type.lower()


# ============================================================================
# GET /api/v1/integrations/linear/issues Tests
# ============================================================================

class TestGetLinkedIssues:
    """Tests for GET /api/v1/integrations/linear/issues?feedback_id=X."""

    def test_get_linked_issues_returns_list(
        self,
        client: TestClient,
        auth_headers: dict,
        feedback_item: FeedbackItem,
        linked_issue,
    ):
        """Should return list of linked issues for a feedback item."""
        response = client.get(
            f"/api/v1/integrations/linear/issues?feedback_id={feedback_item.id}",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["linear_issue_identifier"] == "ENG-100"
        assert data[0]["linear_issue_url"] == "https://linear.app/acme/issue/ENG-100"

    def test_get_linked_issues_returns_empty_when_none(
        self,
        client: TestClient,
        auth_headers: dict,
        feedback_item: FeedbackItem,
    ):
        """Should return empty list when no linked issues."""
        response = client.get(
            f"/api/v1/integrations/linear/issues?feedback_id={feedback_item.id}",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data == []

    def test_get_linked_issues_requires_feedback_id(
        self,
        client: TestClient,
        auth_headers: dict,
    ):
        """Should return 422 when feedback_id is missing."""
        response = client.get(
            "/api/v1/integrations/linear/issues",
            headers=auth_headers,
        )
        assert response.status_code == 422

    def test_get_linked_issues_scoped_to_org(
        self,
        client: TestClient,
        auth_headers: dict,
        db: Session,
        feedback_item: FeedbackItem,
    ):
        """Should not return issues linked by other orgs."""
        # Create another org and link
        other_org = Organization(name="Other Org", plan="pro")
        db.add(other_org)
        db.commit()
        db.refresh(other_org)

        from src.models.linear_integration import FeedbackLinearIssue
        other_link = FeedbackLinearIssue(
            organization_id=other_org.id,
            feedback_id=feedback_item.id,
            linear_issue_id="other-issue-uuid",
            linear_issue_identifier="OTHER-1",
            linear_issue_url="https://linear.app/other/issue/OTHER-1",
            linear_issue_title="Other org issue",
        )
        db.add(other_link)
        db.commit()

        response = client.get(
            f"/api/v1/integrations/linear/issues?feedback_id={feedback_item.id}",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        # Should not include the other org's issue
        identifiers = [d["linear_issue_identifier"] for d in data]
        assert "OTHER-1" not in identifiers

    def test_get_linked_issues_requires_auth(
        self,
        client: TestClient,
        feedback_item: FeedbackItem,
    ):
        """Should reject unauthenticated requests."""
        response = client.get(
            f"/api/v1/integrations/linear/issues?feedback_id={feedback_item.id}",
        )
        assert response.status_code == 403


# ============================================================================
# AI Content Generation Tests
# ============================================================================

class TestGenerateLinearIssueContent:
    """Tests for the AI content generation helper."""

    @pytest.mark.asyncio
    async def test_generate_content_returns_title_and_description(self):
        """Should return title and description from AI."""
        from src.api.routes.linear_integration import generate_linear_issue_content

        feedback_data = {
            "text": "CSV export fails for large datasets",
            "sentiment_label": "negative",
            "sentiment_score": -0.85,
            "is_urgent": True,
            "extracted_issue": "CSV export failure",
        }

        with patch("src.api.routes.linear_integration.call_ai_for_linear_issue") as mock_ai:
            mock_ai.return_value = {
                "title": "Fix CSV export timeout for datasets > 10K rows",
                "description": "## Summary\n\nMultiple customers report...",
            }

            result = await generate_linear_issue_content(feedback_data=feedback_data, org_id=1)

        assert "title" in result
        assert "description" in result
        assert len(result["title"]) <= 80  # Title under 80 chars per PRD

    @pytest.mark.asyncio
    async def test_generate_content_falls_back_on_ai_error(self):
        """Should return basic content when AI call fails."""
        from src.api.routes.linear_integration import generate_linear_issue_content

        feedback_data = {
            "text": "Something is broken",
            "sentiment_label": "negative",
            "sentiment_score": -0.5,
            "is_urgent": False,
            "extracted_issue": None,
        }

        with patch("src.api.routes.linear_integration.call_ai_for_linear_issue") as mock_ai:
            mock_ai.side_effect = Exception("AI service unavailable")

            result = await generate_linear_issue_content(feedback_data=feedback_data, org_id=1)

        # Should still return something, not raise
        assert "title" in result
        assert "description" in result
