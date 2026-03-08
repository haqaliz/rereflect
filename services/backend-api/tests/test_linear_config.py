"""
TDD tests for Linear configuration endpoints (Task #6).

Tests cover:
1. GET /team-mappings — returns org's category-to-team mappings
2. PUT /team-mappings — replaces all mappings (full replace semantics)
3. GET /status-mappings — returns org's Linear->Rereflect status mappings
4. PUT /status-mappings — replaces all status mappings
5. GET /teams — proxies to Linear API, returns team list
6. GET /projects?team_id=X — proxies to Linear API, returns projects
7. GET /labels — proxies to Linear API, returns labels
8. Plan gating — Free plan gets 403 on all config endpoints
9. No active integration — 400 on proxy endpoints
"""
import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.models.organization import Organization
from src.models.user import User
from src.api.auth import hash_password, create_access_token


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def pro_org(db: Session) -> Organization:
    org = Organization(name="Pro Org", plan="pro")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


@pytest.fixture
def free_org(db: Session) -> Organization:
    org = Organization(name="Free Org", plan="free")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def _make_user_and_headers(db: Session, org: Organization, role: str = "admin") -> tuple:
    user = User(
        email=f"user-{org.id}-{role}@test.com",
        password_hash=hash_password("password123"),
        organization_id=org.id,
        role=role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_access_token({
        "user_id": user.id,
        "organization_id": org.id,
        "role": user.role,
    })
    return user, {"Authorization": f"Bearer {token}"}


@pytest.fixture
def pro_user_headers(db: Session, pro_org: Organization) -> dict:
    _, headers = _make_user_and_headers(db, pro_org)
    return headers


@pytest.fixture
def free_user_headers(db: Session, free_org: Organization) -> dict:
    _, headers = _make_user_and_headers(db, free_org)
    return headers


@pytest.fixture
def linear_integration(db: Session, pro_org: Organization):
    from src.models.linear_integration import LinearIntegration
    integration = LinearIntegration(
        organization_id=pro_org.id,
        access_token="enc_token_abc",
        linear_org_id="lin_org_1",
        linear_org_name="Pro Org Linear",
        is_active=True,
        webhook_secret="wh_secret",
    )
    db.add(integration)
    db.commit()
    db.refresh(integration)
    return integration


@pytest.fixture
def team_mappings(db: Session, pro_org: Organization):
    from src.models.linear_integration import LinearTeamMapping
    data = [
        ("pain_point", "team-uuid-1", "Engineering", None, None, 1),
        ("feature_request", "team-uuid-2", "Product", "proj-uuid-1", "Q1 Roadmap", 2),
    ]
    mappings = []
    for category, team_id, team_name, proj_id, proj_name, priority in data:
        m = LinearTeamMapping(
            organization_id=pro_org.id,
            rereflect_category=category,
            linear_team_id=team_id,
            linear_team_name=team_name,
            linear_project_id=proj_id,
            linear_project_name=proj_name,
            priority=priority,
        )
        db.add(m)
        mappings.append(m)
    db.commit()
    return mappings


@pytest.fixture
def status_mappings(db: Session, pro_org: Organization):
    from src.models.linear_integration import LinearStatusMapping
    defaults = [
        ("backlog", "Backlog", "new"),
        ("unstarted", "Todo", "new"),
        ("started", "In Progress", "in_review"),
        ("completed", "Done", "resolved"),
        ("canceled", "Cancelled", "closed"),
    ]
    mappings = []
    for status_type, status_name, rr_status in defaults:
        m = LinearStatusMapping(
            organization_id=pro_org.id,
            linear_status_type=status_type,
            linear_status_name=status_name,
            rereflect_status=rr_status,
        )
        db.add(m)
        mappings.append(m)
    db.commit()
    return mappings


# ---------------------------------------------------------------------------
# Plan gating
# ---------------------------------------------------------------------------
class TestConfigEndpointsPlanGating:

    def test_free_plan_blocked_on_team_mappings_get(self, client: TestClient, free_user_headers: dict):
        response = client.get("/api/v1/integrations/linear/team-mappings", headers=free_user_headers)
        assert response.status_code == 403

    def test_free_plan_blocked_on_team_mappings_put(self, client: TestClient, free_user_headers: dict):
        response = client.put(
            "/api/v1/integrations/linear/team-mappings",
            json=[],
            headers=free_user_headers,
        )
        assert response.status_code == 403

    def test_free_plan_blocked_on_status_mappings_get(self, client: TestClient, free_user_headers: dict):
        response = client.get("/api/v1/integrations/linear/status-mappings", headers=free_user_headers)
        assert response.status_code == 403

    def test_free_plan_blocked_on_status_mappings_put(self, client: TestClient, free_user_headers: dict):
        response = client.put(
            "/api/v1/integrations/linear/status-mappings",
            json=[],
            headers=free_user_headers,
        )
        assert response.status_code == 403

    def test_free_plan_blocked_on_teams_proxy(self, client: TestClient, free_user_headers: dict):
        response = client.get("/api/v1/integrations/linear/teams", headers=free_user_headers)
        assert response.status_code == 403

    def test_free_plan_blocked_on_projects_proxy(self, client: TestClient, free_user_headers: dict):
        response = client.get(
            "/api/v1/integrations/linear/projects",
            params={"team_id": "team-uuid-1"},
            headers=free_user_headers,
        )
        assert response.status_code == 403

    def test_free_plan_blocked_on_labels_proxy(self, client: TestClient, free_user_headers: dict):
        response = client.get("/api/v1/integrations/linear/labels", headers=free_user_headers)
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# GET /team-mappings
# ---------------------------------------------------------------------------
class TestGetTeamMappings:

    def test_returns_200(self, client: TestClient, pro_user_headers: dict, linear_integration, team_mappings):
        response = client.get("/api/v1/integrations/linear/team-mappings", headers=pro_user_headers)
        assert response.status_code == 200

    def test_returns_list(self, client: TestClient, pro_user_headers: dict, linear_integration, team_mappings):
        response = client.get("/api/v1/integrations/linear/team-mappings", headers=pro_user_headers)
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 2

    def test_mapping_fields_present(self, client: TestClient, pro_user_headers: dict, linear_integration, team_mappings):
        response = client.get("/api/v1/integrations/linear/team-mappings", headers=pro_user_headers)
        item = response.json()[0]
        assert "id" in item
        assert "organization_id" in item
        assert "rereflect_category" in item
        assert "linear_team_id" in item
        assert "linear_team_name" in item
        assert "priority" in item

    def test_empty_when_no_mappings(self, client: TestClient, pro_user_headers: dict, linear_integration):
        response = client.get("/api/v1/integrations/linear/team-mappings", headers=pro_user_headers)
        assert response.status_code == 200
        assert response.json() == []

    def test_ordered_by_priority(self, client: TestClient, pro_user_headers: dict, linear_integration, team_mappings):
        response = client.get("/api/v1/integrations/linear/team-mappings", headers=pro_user_headers)
        items = response.json()
        priorities = [item["priority"] for item in items]
        assert priorities == sorted(priorities)

    def test_only_returns_own_org_mappings(self, client: TestClient, db: Session, linear_integration, team_mappings):
        """A second org's mappings should not appear."""
        other_org = Organization(name="Other Org", plan="pro")
        db.add(other_org)
        db.commit()
        db.refresh(other_org)
        _, other_headers = _make_user_and_headers(db, other_org)

        response = client.get("/api/v1/integrations/linear/team-mappings", headers=other_headers)
        assert response.status_code == 200
        assert response.json() == []


# ---------------------------------------------------------------------------
# PUT /team-mappings
# ---------------------------------------------------------------------------
class TestUpdateTeamMappings:

    def test_returns_200(self, client: TestClient, pro_user_headers: dict, linear_integration):
        payload = [
            {
                "rereflect_category": "pain_point",
                "linear_team_id": "team-new-1",
                "linear_team_name": "Engineering",
                "priority": 1,
            }
        ]
        response = client.put(
            "/api/v1/integrations/linear/team-mappings",
            json=payload,
            headers=pro_user_headers,
        )
        assert response.status_code == 200

    def test_replaces_all_existing_mappings(
        self, client: TestClient, db: Session, pro_user_headers: dict, linear_integration, team_mappings
    ):
        from src.models.linear_integration import LinearTeamMapping
        # Confirm 2 exist first
        assert db.query(LinearTeamMapping).filter_by(organization_id=linear_integration.organization_id).count() == 2

        payload = [
            {
                "rereflect_category": "bug",
                "linear_team_id": "team-replace",
                "linear_team_name": "Bugs Team",
                "priority": 0,
            }
        ]
        response = client.put(
            "/api/v1/integrations/linear/team-mappings",
            json=payload,
            headers=pro_user_headers,
        )
        assert response.status_code == 200

        db.expire_all()
        count = db.query(LinearTeamMapping).filter_by(organization_id=linear_integration.organization_id).count()
        assert count == 1

    def test_empty_list_clears_all_mappings(
        self, client: TestClient, db: Session, pro_user_headers: dict, linear_integration, team_mappings
    ):
        from src.models.linear_integration import LinearTeamMapping
        response = client.put(
            "/api/v1/integrations/linear/team-mappings",
            json=[],
            headers=pro_user_headers,
        )
        assert response.status_code == 200
        db.expire_all()
        count = db.query(LinearTeamMapping).filter_by(organization_id=linear_integration.organization_id).count()
        assert count == 0

    def test_returns_created_mappings(self, client: TestClient, pro_user_headers: dict, linear_integration):
        payload = [
            {
                "rereflect_category": "feature_request",
                "linear_team_id": "team-prod",
                "linear_team_name": "Product",
                "linear_project_id": "proj-abc",
                "linear_project_name": "Roadmap",
                "priority": 2,
            }
        ]
        response = client.put(
            "/api/v1/integrations/linear/team-mappings",
            json=payload,
            headers=pro_user_headers,
        )
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["rereflect_category"] == "feature_request"
        assert data[0]["linear_team_id"] == "team-prod"
        assert data[0]["linear_project_id"] == "proj-abc"

    def test_optional_project_fields_nullable(self, client: TestClient, pro_user_headers: dict, linear_integration):
        payload = [
            {
                "rereflect_category": "pain_point",
                "linear_team_id": "team-eng",
                "linear_team_name": "Engineering",
                "priority": 1,
            }
        ]
        response = client.put(
            "/api/v1/integrations/linear/team-mappings",
            json=payload,
            headers=pro_user_headers,
        )
        assert response.status_code == 200
        item = response.json()[0]
        assert item.get("linear_project_id") is None


# ---------------------------------------------------------------------------
# GET /status-mappings
# ---------------------------------------------------------------------------
class TestGetStatusMappings:

    def test_returns_200(self, client: TestClient, pro_user_headers: dict, linear_integration, status_mappings):
        response = client.get("/api/v1/integrations/linear/status-mappings", headers=pro_user_headers)
        assert response.status_code == 200

    def test_returns_all_default_mappings(self, client: TestClient, pro_user_headers: dict, linear_integration, status_mappings):
        response = client.get("/api/v1/integrations/linear/status-mappings", headers=pro_user_headers)
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 5

    def test_mapping_fields_present(self, client: TestClient, pro_user_headers: dict, linear_integration, status_mappings):
        response = client.get("/api/v1/integrations/linear/status-mappings", headers=pro_user_headers)
        item = response.json()[0]
        assert "id" in item
        assert "organization_id" in item
        assert "linear_status_name" in item
        assert "linear_status_type" in item
        assert "rereflect_status" in item

    def test_empty_when_no_mappings(self, client: TestClient, pro_user_headers: dict, linear_integration):
        response = client.get("/api/v1/integrations/linear/status-mappings", headers=pro_user_headers)
        assert response.status_code == 200
        assert response.json() == []

    def test_only_returns_own_org_mappings(self, client: TestClient, db: Session, linear_integration, status_mappings):
        other_org = Organization(name="Other Org 2", plan="pro")
        db.add(other_org)
        db.commit()
        db.refresh(other_org)
        _, other_headers = _make_user_and_headers(db, other_org)

        response = client.get("/api/v1/integrations/linear/status-mappings", headers=other_headers)
        assert response.status_code == 200
        assert response.json() == []


# ---------------------------------------------------------------------------
# PUT /status-mappings
# ---------------------------------------------------------------------------
class TestUpdateStatusMappings:

    def test_returns_200(self, client: TestClient, pro_user_headers: dict, linear_integration):
        payload = [
            {
                "linear_status_name": "In Progress",
                "linear_status_type": "started",
                "rereflect_status": "in_review",
            }
        ]
        response = client.put(
            "/api/v1/integrations/linear/status-mappings",
            json=payload,
            headers=pro_user_headers,
        )
        assert response.status_code == 200

    def test_replaces_existing_mappings(
        self, client: TestClient, db: Session, pro_user_headers: dict, linear_integration, status_mappings
    ):
        from src.models.linear_integration import LinearStatusMapping
        payload = [
            {
                "linear_status_name": "Done",
                "linear_status_type": "completed",
                "rereflect_status": "resolved",
            }
        ]
        response = client.put(
            "/api/v1/integrations/linear/status-mappings",
            json=payload,
            headers=pro_user_headers,
        )
        assert response.status_code == 200

        db.expire_all()
        count = db.query(LinearStatusMapping).filter_by(organization_id=linear_integration.organization_id).count()
        assert count == 1

    def test_returns_updated_mappings(self, client: TestClient, pro_user_headers: dict, linear_integration):
        payload = [
            {
                "linear_status_name": "Done",
                "linear_status_type": "completed",
                "rereflect_status": "resolved",
            },
            {
                "linear_status_name": "Canceled",
                "linear_status_type": "canceled",
                "rereflect_status": "closed",
            },
        ]
        response = client.put(
            "/api/v1/integrations/linear/status-mappings",
            json=payload,
            headers=pro_user_headers,
        )
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 2

    def test_invalid_rereflect_status_returns_422(self, client: TestClient, pro_user_headers: dict, linear_integration):
        payload = [
            {
                "linear_status_name": "Done",
                "linear_status_type": "completed",
                "rereflect_status": "not_a_valid_status",
            }
        ]
        response = client.put(
            "/api/v1/integrations/linear/status-mappings",
            json=payload,
            headers=pro_user_headers,
        )
        assert response.status_code == 422

    def test_all_valid_rereflect_statuses_accepted(self, client: TestClient, pro_user_headers: dict, linear_integration):
        valid_statuses = ["new", "in_review", "resolved", "closed"]
        payload = [
            {
                "linear_status_name": f"State {i}",
                "linear_status_type": "started",
                "rereflect_status": s,
            }
            for i, s in enumerate(valid_statuses)
        ]
        response = client.put(
            "/api/v1/integrations/linear/status-mappings",
            json=payload,
            headers=pro_user_headers,
        )
        assert response.status_code == 200

    def test_empty_list_clears_mappings(
        self, client: TestClient, db: Session, pro_user_headers: dict, linear_integration, status_mappings
    ):
        from src.models.linear_integration import LinearStatusMapping
        response = client.put(
            "/api/v1/integrations/linear/status-mappings",
            json=[],
            headers=pro_user_headers,
        )
        assert response.status_code == 200
        db.expire_all()
        count = db.query(LinearStatusMapping).filter_by(organization_id=linear_integration.organization_id).count()
        assert count == 0


# ---------------------------------------------------------------------------
# GET /teams (Linear API proxy)
# ---------------------------------------------------------------------------
class TestGetLinearTeams:

    def test_returns_200(self, client: TestClient, pro_user_headers: dict, linear_integration):
        mock_teams = [
            {"id": "team-1", "name": "Engineering", "key": "ENG"},
            {"id": "team-2", "name": "Product", "key": "PRD"},
        ]
        with patch(
            "src.services.linear_client.LinearClient.get_teams",
            new_callable=AsyncMock,
            return_value=mock_teams,
        ):
            response = client.get("/api/v1/integrations/linear/teams", headers=pro_user_headers)

        assert response.status_code == 200

    def test_returns_teams_list(self, client: TestClient, pro_user_headers: dict, linear_integration):
        mock_teams = [
            {"id": "team-1", "name": "Engineering", "key": "ENG"},
            {"id": "team-2", "name": "Product", "key": "PRD"},
        ]
        with patch(
            "src.services.linear_client.LinearClient.get_teams",
            new_callable=AsyncMock,
            return_value=mock_teams,
        ):
            response = client.get("/api/v1/integrations/linear/teams", headers=pro_user_headers)

        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 2
        assert data[0]["name"] == "Engineering"

    def test_no_integration_returns_400(self, client: TestClient, pro_user_headers: dict):
        """No active integration -> 400, not 500."""
        response = client.get("/api/v1/integrations/linear/teams", headers=pro_user_headers)
        assert response.status_code == 400


# ---------------------------------------------------------------------------
# GET /projects (Linear API proxy)
# ---------------------------------------------------------------------------
class TestGetLinearProjects:

    def test_returns_200(self, client: TestClient, pro_user_headers: dict, linear_integration):
        mock_projects = [
            {"id": "proj-1", "name": "Q1 Roadmap"},
            {"id": "proj-2", "name": "Bug Fixes"},
        ]
        with patch(
            "src.services.linear_client.LinearClient.get_projects",
            new_callable=AsyncMock,
            return_value=mock_projects,
        ):
            response = client.get(
                "/api/v1/integrations/linear/projects",
                params={"team_id": "team-1"},
                headers=pro_user_headers,
            )

        assert response.status_code == 200

    def test_returns_projects_list(self, client: TestClient, pro_user_headers: dict, linear_integration):
        mock_projects = [{"id": "proj-1", "name": "Q1 Roadmap"}]
        with patch(
            "src.services.linear_client.LinearClient.get_projects",
            new_callable=AsyncMock,
            return_value=mock_projects,
        ):
            response = client.get(
                "/api/v1/integrations/linear/projects",
                params={"team_id": "team-1"},
                headers=pro_user_headers,
            )

        data = response.json()
        assert isinstance(data, list)
        assert data[0]["name"] == "Q1 Roadmap"

    def test_missing_team_id_returns_422(self, client: TestClient, pro_user_headers: dict, linear_integration):
        response = client.get("/api/v1/integrations/linear/projects", headers=pro_user_headers)
        assert response.status_code == 422

    def test_no_integration_returns_400(self, client: TestClient, pro_user_headers: dict):
        response = client.get(
            "/api/v1/integrations/linear/projects",
            params={"team_id": "team-1"},
            headers=pro_user_headers,
        )
        assert response.status_code == 400


# ---------------------------------------------------------------------------
# GET /labels (Linear API proxy)
# ---------------------------------------------------------------------------
class TestGetLinearLabels:

    def test_returns_200(self, client: TestClient, pro_user_headers: dict, linear_integration):
        mock_labels = [
            {"id": "label-1", "name": "bug", "color": "#ff0000"},
            {"id": "label-2", "name": "feature", "color": "#00ff00"},
        ]
        with patch(
            "src.services.linear_client.LinearClient.get_labels",
            new_callable=AsyncMock,
            return_value=mock_labels,
        ):
            response = client.get("/api/v1/integrations/linear/labels", headers=pro_user_headers)

        assert response.status_code == 200

    def test_returns_labels_list(self, client: TestClient, pro_user_headers: dict, linear_integration):
        mock_labels = [{"id": "label-1", "name": "bug", "color": "#ff0000"}]
        with patch(
            "src.services.linear_client.LinearClient.get_labels",
            new_callable=AsyncMock,
            return_value=mock_labels,
        ):
            response = client.get("/api/v1/integrations/linear/labels", headers=pro_user_headers)

        data = response.json()
        assert isinstance(data, list)
        assert data[0]["name"] == "bug"

    def test_no_integration_returns_400(self, client: TestClient, pro_user_headers: dict):
        response = client.get("/api/v1/integrations/linear/labels", headers=pro_user_headers)
        assert response.status_code == 400

    def test_unauthenticated_returns_403(self, client: TestClient):
        response = client.get("/api/v1/integrations/linear/labels")
        assert response.status_code == 403
