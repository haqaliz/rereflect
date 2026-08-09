"""
RBAC tests for Linear integration routes.

Regression coverage for the P1 gap where member-role users could drive
Linear OAuth connect/disconnect, edit config, and create issues.
Per the RBAC matrix, integration management is Owner/Admin only.
"""
import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.models.organization import Organization
from src.models.user import User
from src.models.feedback import FeedbackItem
from src.api.auth import hash_password, create_access_token


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def member_user(db: Session, test_organization: Organization) -> User:
    user = User(
        email="linear_member@test.com",
        password_hash=hash_password("password123"),
        organization_id=test_organization.id,
        role="member",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def member_headers(member_user: User) -> dict:
    token = create_access_token({
        "user_id": member_user.id,
        "organization_id": member_user.organization_id,
        "role": member_user.role,
    })
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def linear_integration(db: Session, test_organization: Organization):
    from src.models.linear_integration import LinearIntegration
    integration = LinearIntegration(
        organization_id=test_organization.id,
        access_token="enc_token_abc",
        linear_org_id="lin_org_1",
        linear_org_name="Test Linear",
        connected_by_user_id=None,
        is_active=True,
        webhook_secret="wh_secret",
        webhook_id="webhook-uuid-1",
    )
    db.add(integration)
    db.commit()
    db.refresh(integration)
    return integration


@pytest.fixture
def feedback_item(db: Session, test_organization: Organization) -> FeedbackItem:
    feedback = FeedbackItem(
        organization_id=test_organization.id,
        text="The CSV export fails for large datasets.",
        source="email",
        sentiment_label="negative",
        sentiment_score=-0.85,
        is_urgent=False,
        extracted_issue=None,
    )
    db.add(feedback)
    db.commit()
    db.refresh(feedback)
    return feedback


# ---------------------------------------------------------------------------
# GET /connect
# ---------------------------------------------------------------------------
class TestConnectRBAC:

    @patch("src.api.routes.linear_integration.LINEAR_CLIENT_ID", "test-linear-client-id")
    def test_member_forbidden_on_connect(self, client: TestClient, member_headers: dict):
        response = client.get("/api/v1/integrations/linear/connect", headers=member_headers)
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# DELETE /disconnect
# ---------------------------------------------------------------------------
class TestDisconnectRBAC:

    def test_member_forbidden_on_disconnect(
        self, client: TestClient, member_headers: dict, linear_integration
    ):
        with patch("src.api.routes.linear_integration.LinearClient") as MockLinearClient:
            mock_linear = AsyncMock()
            mock_linear.delete_webhook = AsyncMock(return_value=None)
            MockLinearClient.return_value = mock_linear
            response = client.delete("/api/v1/integrations/linear/disconnect", headers=member_headers)
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# GET /status
# ---------------------------------------------------------------------------
class TestStatusRBAC:

    def test_member_forbidden_on_status(
        self, client: TestClient, member_headers: dict, linear_integration
    ):
        response = client.get("/api/v1/integrations/linear/status", headers=member_headers)
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# GET/PUT /config
# ---------------------------------------------------------------------------
class TestConfigRBAC:

    def test_member_forbidden_on_config_get(
        self, client: TestClient, member_headers: dict, linear_integration
    ):
        response = client.get("/api/v1/integrations/linear/config", headers=member_headers)
        assert response.status_code == 403

    def test_member_forbidden_on_config_put(
        self, client: TestClient, member_headers: dict, linear_integration
    ):
        response = client.put(
            "/api/v1/integrations/linear/config",
            headers=member_headers,
            json={
                "issue_title_template": "{{text}}",
                "issue_description_template": "## Feedback\n\n{{text}}",
            },
        )
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# POST /test
# ---------------------------------------------------------------------------
class TestConnectionTestRBAC:

    def test_member_forbidden_on_connection_test(
        self, client: TestClient, member_headers: dict, linear_integration
    ):
        with patch(
            "src.services.linear_client.LinearClient.get_organization",
            new_callable=AsyncMock,
            return_value={"id": "lin_org_1", "name": "Test Linear"},
        ):
            response = client.post("/api/v1/integrations/linear/test", headers=member_headers)
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# GET /template-variables
# ---------------------------------------------------------------------------
class TestTemplateVariablesRBAC:

    def test_member_forbidden_on_template_variables(
        self, client: TestClient, member_headers: dict
    ):
        response = client.get("/api/v1/integrations/linear/template-variables", headers=member_headers)
        assert response.status_code == 403

    def test_template_variables_requires_auth(self, client: TestClient):
        response = client.get("/api/v1/integrations/linear/template-variables")
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# POST /issues
# ---------------------------------------------------------------------------
class TestCreateIssueRBAC:

    def test_member_forbidden_on_create_issue(
        self,
        client: TestClient,
        member_headers: dict,
        linear_integration,
        feedback_item: FeedbackItem,
    ):
        with patch("src.api.routes.linear_integration.LinearClient") as MockLinearClient:
            mock_linear = AsyncMock()
            mock_linear.create_issue.return_value = {
                "id": "issue-uuid-rbac",
                "identifier": "ENG-1",
                "title": "Test issue",
                "url": "https://linear.app/acme/issue/ENG-1",
                "priority": 1,
                "state": {"name": "Todo", "type": "unstarted"},
            }
            MockLinearClient.return_value = mock_linear
            response = client.post(
                "/api/v1/integrations/linear/issues",
                headers=member_headers,
                json={
                    "feedback_id": feedback_item.id,
                    "team_id": "team-1",
                    "title": "Test issue",
                    "description": "Details",
                },
            )
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# GET /issues
# ---------------------------------------------------------------------------
class TestGetLinkedIssuesRBAC:

    def test_member_forbidden_on_get_linked_issues(
        self,
        client: TestClient,
        member_headers: dict,
        linear_integration,
        feedback_item: FeedbackItem,
    ):
        response = client.get(
            f"/api/v1/integrations/linear/issues?feedback_id={feedback_item.id}",
            headers=member_headers,
        )
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# Linear API proxy endpoints (teams, projects, labels)
# ---------------------------------------------------------------------------
class TestProxyEndpointsRBAC:

    def test_member_forbidden_on_teams(
        self, client: TestClient, member_headers: dict, linear_integration
    ):
        with patch(
            "src.services.linear_client.LinearClient.get_teams",
            new_callable=AsyncMock,
            return_value=[{"id": "team-1", "name": "Engineering", "key": "ENG"}],
        ):
            response = client.get("/api/v1/integrations/linear/teams", headers=member_headers)
        assert response.status_code == 403

    def test_member_forbidden_on_projects(
        self, client: TestClient, member_headers: dict, linear_integration
    ):
        with patch(
            "src.services.linear_client.LinearClient.get_projects",
            new_callable=AsyncMock,
            return_value=[{"id": "proj-1", "name": "Q1 Roadmap"}],
        ):
            response = client.get(
                "/api/v1/integrations/linear/projects",
                params={"team_id": "team-1"},
                headers=member_headers,
            )
        assert response.status_code == 403

    def test_member_forbidden_on_labels(
        self, client: TestClient, member_headers: dict, linear_integration
    ):
        with patch(
            "src.services.linear_client.LinearClient.get_labels",
            new_callable=AsyncMock,
            return_value=[{"id": "label-1", "name": "bug", "color": "#ff0000"}],
        ):
            response = client.get("/api/v1/integrations/linear/labels", headers=member_headers)
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# GET/PUT /team-mappings and /status-mappings
# ---------------------------------------------------------------------------
class TestMappingsRBAC:

    def test_member_forbidden_on_team_mappings_get(
        self, client: TestClient, member_headers: dict, linear_integration
    ):
        response = client.get("/api/v1/integrations/linear/team-mappings", headers=member_headers)
        assert response.status_code == 403

    def test_member_forbidden_on_team_mappings_put(
        self, client: TestClient, member_headers: dict, linear_integration
    ):
        response = client.put(
            "/api/v1/integrations/linear/team-mappings",
            headers=member_headers,
            json=[
                {
                    "rereflect_category": "pain_point",
                    "linear_team_id": "team-new-1",
                    "linear_team_name": "Engineering",
                    "priority": 1,
                }
            ],
        )
        assert response.status_code == 403

    def test_member_forbidden_on_status_mappings_get(
        self, client: TestClient, member_headers: dict, linear_integration
    ):
        response = client.get("/api/v1/integrations/linear/status-mappings", headers=member_headers)
        assert response.status_code == 403

    def test_member_forbidden_on_status_mappings_put(
        self, client: TestClient, member_headers: dict, linear_integration
    ):
        response = client.put(
            "/api/v1/integrations/linear/status-mappings",
            headers=member_headers,
            json=[
                {
                    "linear_status_name": "Done",
                    "linear_status_type": "completed",
                    "rereflect_status": "resolved",
                }
            ],
        )
        assert response.status_code == 403
