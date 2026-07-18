"""
TDD tests for the Jira inbound status-sync operator control routes (Phase 5).

Covers:
  - GET   /api/v1/integrations/jira/status         (extended with 4 new fields)
  - PATCH /api/v1/integrations/jira/status-sync     (toggle + mapping)
  - POST  /api/v1/integrations/jira/sync            (manual trigger)

Mirrors the test style of tests/test_jira_connection.py (fixtures) and
tests/test_zendesk_sync_endpoint.py (send_task / 502 pattern).
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.models.organization import Organization
from src.models.user import User
from src.models.jira_integration import JiraIntegration, FeedbackJiraIssue
from src.models.feedback import FeedbackItem
from src.api.auth import hash_password, create_access_token


SITE_URL = "https://acme.atlassian.net"
EMAIL = "operator@acme.com"


# ──────────────────────────── Fixtures ────────────────────────────────────────


@pytest.fixture
def owner_user(db: Session, test_organization: Organization) -> User:
    user = User(
        email="jss_owner@test.com",
        password_hash=hash_password("pw"),
        organization_id=test_organization.id,
        role="owner",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def owner_headers(owner_user: User) -> dict:
    token = create_access_token({
        "user_id": owner_user.id,
        "organization_id": owner_user.organization_id,
        "role": owner_user.role,
    })
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def admin_user(db: Session, test_organization: Organization) -> User:
    user = User(
        email="jss_admin@test.com",
        password_hash=hash_password("pw"),
        organization_id=test_organization.id,
        role="admin",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def admin_headers(admin_user: User) -> dict:
    token = create_access_token({
        "user_id": admin_user.id,
        "organization_id": admin_user.organization_id,
        "role": admin_user.role,
    })
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def member_user(db: Session, test_organization: Organization) -> User:
    user = User(
        email="jss_member@test.com",
        password_hash=hash_password("pw"),
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
def other_organization(db: Session) -> Organization:
    org = Organization(name="Other Org", plan="free")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


@pytest.fixture
def other_owner_user(db: Session, other_organization: Organization) -> User:
    user = User(
        email="jss_other_owner@test.com",
        password_hash=hash_password("pw"),
        organization_id=other_organization.id,
        role="owner",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def other_owner_headers(other_owner_user: User) -> dict:
    token = create_access_token({
        "user_id": other_owner_user.id,
        "organization_id": other_owner_user.organization_id,
        "role": other_owner_user.role,
    })
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def active_integration(db: Session, test_organization: Organization) -> JiraIntegration:
    """A fresh, active Jira integration with status sync untouched (defaults)."""
    integ = JiraIntegration(
        organization_id=test_organization.id,
        site_url=SITE_URL,
        email=EMAIL,
        api_token="encrypted-blob",
        token_hint="...wxyz",
        account_id="acc-1",
        display_name="Display Name",
        is_active=True,
        connected_at=datetime.utcnow(),
    )
    db.add(integ)
    db.commit()
    db.refresh(integ)
    return integ


# ──────────────────────────── GET /status (extended) ──────────────────────────


class TestStatusEndpointStatusSyncFields:
    def test_fresh_integration_returns_status_sync_defaults(
        self, client: TestClient, active_integration: JiraIntegration, owner_headers: dict
    ):
        resp = client.get("/api/v1/integrations/jira/status", headers=owner_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["connected"] is True
        assert body["status_sync_enabled"] is False
        assert body["last_status_synced_at"] is None
        assert body["last_sync_status"] is None
        assert body["last_error"] is None

    def test_last_status_synced_at_is_max_across_linked_issues(
        self,
        client: TestClient,
        db: Session,
        test_organization: Organization,
        active_integration: JiraIntegration,
        owner_headers: dict,
    ):
        feedback = FeedbackItem(
            organization_id=test_organization.id,
            text="Some feedback",
            source="csv",
        )
        db.add(feedback)
        db.commit()
        db.refresh(feedback)

        older = datetime.utcnow() - timedelta(days=1)
        newer = datetime.utcnow()

        db.add_all([
            FeedbackJiraIssue(
                organization_id=test_organization.id,
                feedback_id=feedback.id,
                jira_issue_id="1001",
                jira_issue_key="ENG-1",
                jira_issue_url="https://acme.atlassian.net/browse/ENG-1",
                jira_issue_title="Issue 1",
                last_status_synced_at=older,
            ),
            FeedbackJiraIssue(
                organization_id=test_organization.id,
                feedback_id=feedback.id,
                jira_issue_id="1002",
                jira_issue_key="ENG-2",
                jira_issue_url="https://acme.atlassian.net/browse/ENG-2",
                jira_issue_title="Issue 2",
                last_status_synced_at=newer,
            ),
        ])
        db.commit()

        resp = client.get("/api/v1/integrations/jira/status", headers=owner_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["last_status_synced_at"] is not None
        # Compare on date truncated to seconds to avoid microsecond serialization flakiness.
        returned = datetime.fromisoformat(body["last_status_synced_at"])
        assert abs((returned.replace(tzinfo=None) - newer).total_seconds()) < 2

    def test_last_sync_status_and_error_reflect_integration_row(
        self,
        client: TestClient,
        db: Session,
        active_integration: JiraIntegration,
        owner_headers: dict,
    ):
        active_integration.last_sync_status = "error"
        active_integration.last_error = "401 invalid token"
        db.commit()

        resp = client.get("/api/v1/integrations/jira/status", headers=owner_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["last_sync_status"] == "error"
        assert body["last_error"] == "401 invalid token"

    def test_status_mapping_is_null_when_unset(
        self, client: TestClient, active_integration: JiraIntegration, owner_headers: dict
    ):
        resp = client.get("/api/v1/integrations/jira/status", headers=owner_headers)
        assert resp.status_code == 200
        assert resp.json()["status_mapping"] is None

    def test_status_mapping_reflects_stored_value(
        self,
        client: TestClient,
        db: Session,
        active_integration: JiraIntegration,
        owner_headers: dict,
    ):
        active_integration.status_mapping = {"new": "new", "indeterminate": "in_review", "done": "resolved"}
        db.commit()

        resp = client.get("/api/v1/integrations/jira/status", headers=owner_headers)
        assert resp.status_code == 200
        assert resp.json()["status_mapping"] == {
            "new": "new",
            "indeterminate": "in_review",
            "done": "resolved",
        }


# ──────────────────────────── PATCH /status-sync ───────────────────────────────


class TestPatchStatusSync:
    def test_admin_toggles_enabled_true_persists(
        self,
        client: TestClient,
        db: Session,
        active_integration: JiraIntegration,
        admin_headers: dict,
    ):
        resp = client.patch(
            "/api/v1/integrations/jira/status-sync",
            json={"enabled": True},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status_sync_enabled"] is True

        db.expire_all()
        row = db.query(JiraIntegration).filter_by(id=active_integration.id).first()
        assert row.status_sync_enabled is True

    def test_owner_sets_valid_status_mapping_persists(
        self,
        client: TestClient,
        db: Session,
        active_integration: JiraIntegration,
        owner_headers: dict,
    ):
        mapping = {"new": "new", "indeterminate": "in_review", "done": "closed"}
        resp = client.patch(
            "/api/v1/integrations/jira/status-sync",
            json={"enabled": True, "status_mapping": mapping},
            headers=owner_headers,
        )
        assert resp.status_code == 200

        db.expire_all()
        row = db.query(JiraIntegration).filter_by(id=active_integration.id).first()
        assert row.status_mapping == mapping

    def test_invalid_mapping_key_returns_422(
        self,
        client: TestClient,
        active_integration: JiraIntegration,
        owner_headers: dict,
    ):
        resp = client.patch(
            "/api/v1/integrations/jira/status-sync",
            json={"enabled": True, "status_mapping": {"bogus_key": "new"}},
            headers=owner_headers,
        )
        assert resp.status_code == 422

    def test_invalid_mapping_value_returns_422(
        self,
        client: TestClient,
        active_integration: JiraIntegration,
        owner_headers: dict,
    ):
        resp = client.patch(
            "/api/v1/integrations/jira/status-sync",
            json={"enabled": True, "status_mapping": {"new": "bogus_status"}},
            headers=owner_headers,
        )
        assert resp.status_code == 422

    def test_member_forbidden(
        self,
        client: TestClient,
        active_integration: JiraIntegration,
        member_headers: dict,
    ):
        resp = client.patch(
            "/api/v1/integrations/jira/status-sync",
            json={"enabled": True},
            headers=member_headers,
        )
        assert resp.status_code == 403

    def test_no_integration_returns_404(
        self,
        client: TestClient,
        owner_headers: dict,
    ):
        resp = client.patch(
            "/api/v1/integrations/jira/status-sync",
            json={"enabled": True},
            headers=owner_headers,
        )
        assert resp.status_code == 404


# ──────────────────────────── POST /sync ───────────────────────────────────────


class TestPostSync:
    def test_owner_can_trigger_sync(
        self,
        client: TestClient,
        active_integration: JiraIntegration,
        owner_headers: dict,
    ):
        with patch("src.api.routes.jira_integration._get_celery_app") as mock_get_celery:
            mock_celery = MagicMock()
            mock_get_celery.return_value = mock_celery

            resp = client.post(
                "/api/v1/integrations/jira/sync",
                headers=owner_headers,
            )

        assert resp.status_code == 202
        assert resp.json()["status"] == "queued"
        mock_celery.send_task.assert_called_once_with(
            "src.tasks.jira_sync.sync_jira_org",
            args=[active_integration.id],
        )

    def test_admin_can_trigger_sync(
        self,
        client: TestClient,
        active_integration: JiraIntegration,
        admin_headers: dict,
    ):
        with patch("src.api.routes.jira_integration._get_celery_app") as mock_get_celery:
            mock_celery = MagicMock()
            mock_get_celery.return_value = mock_celery

            resp = client.post(
                "/api/v1/integrations/jira/sync",
                headers=admin_headers,
            )

        assert resp.status_code == 202

    def test_broker_failure_returns_502(
        self,
        client: TestClient,
        active_integration: JiraIntegration,
        owner_headers: dict,
    ):
        with patch("src.api.routes.jira_integration._get_celery_app") as mock_get_celery:
            mock_celery = MagicMock()
            mock_celery.send_task.side_effect = RuntimeError("broker unreachable")
            mock_get_celery.return_value = mock_celery

            resp = client.post(
                "/api/v1/integrations/jira/sync",
                headers=owner_headers,
            )

        assert resp.status_code == 502

    def test_member_forbidden(
        self,
        client: TestClient,
        active_integration: JiraIntegration,
        member_headers: dict,
    ):
        resp = client.post(
            "/api/v1/integrations/jira/sync",
            headers=member_headers,
        )
        assert resp.status_code == 403

    def test_no_active_integration_returns_400_or_404(
        self,
        client: TestClient,
        owner_headers: dict,
    ):
        resp = client.post(
            "/api/v1/integrations/jira/sync",
            headers=owner_headers,
        )
        assert resp.status_code in (400, 404)

    def test_cross_org_has_no_active_integration(
        self,
        client: TestClient,
        active_integration: JiraIntegration,
        other_owner_headers: dict,
    ):
        """An org without its own Jira integration must never trigger another org's sync."""
        resp = client.post(
            "/api/v1/integrations/jira/sync",
            headers=other_owner_headers,
        )
        assert resp.status_code in (400, 404)
