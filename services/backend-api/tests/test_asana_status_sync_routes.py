"""
TDD tests for the Asana inbound status-sync operator control routes
(backend-routes aspect).

Covers:
  - GET   /api/v1/integrations/asana/status         (extended with 2 new fields)
  - PATCH /api/v1/integrations/asana/status-sync     (toggle + mapping)
  - POST  /api/v1/integrations/asana/sync            (manual trigger)

Mirrors tests/test_jira_status_sync_routes.py one-for-one (Asana names/paths/model).
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.models.organization import Organization
from src.models.user import User
from src.models.asana_integration import AsanaIntegration, FeedbackAsanaTask
from src.models.feedback import FeedbackItem
from src.api.auth import hash_password, create_access_token


# ──────────────────────────── Fixtures ────────────────────────────────────────


@pytest.fixture
def owner_user(db: Session, test_organization: Organization) -> User:
    user = User(
        email="ass_owner@test.com",
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
        email="ass_admin@test.com",
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
        email="ass_member@test.com",
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
    org = Organization(name="Other Org Asana", plan="free")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


@pytest.fixture
def other_owner_user(db: Session, other_organization: Organization) -> User:
    user = User(
        email="ass_other_owner@test.com",
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
def active_integration(db: Session, test_organization: Organization) -> AsanaIntegration:
    """A fresh, active Asana integration with status sync untouched (defaults)."""
    integ = AsanaIntegration(
        organization_id=test_organization.id,
        api_token="encrypted-blob",
        token_hint="...wxyz",
        account_gid="acc-1",
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
        self, client: TestClient, active_integration: AsanaIntegration, owner_headers: dict
    ):
        resp = client.get("/api/v1/integrations/asana/status", headers=owner_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["connected"] is True
        assert body["status_sync_enabled"] is False
        assert body["last_status_synced_at"] is None
        assert body["last_sync_status"] is None
        assert body["last_error"] is None

    def test_last_status_synced_at_is_max_across_linked_tasks(
        self,
        client: TestClient,
        db: Session,
        test_organization: Organization,
        active_integration: AsanaIntegration,
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
            FeedbackAsanaTask(
                organization_id=test_organization.id,
                feedback_id=feedback.id,
                asana_task_gid="1001",
                asana_task_url="https://app.asana.com/0/1/1001",
                asana_task_name="Task 1",
                last_status_synced_at=older,
            ),
            FeedbackAsanaTask(
                organization_id=test_organization.id,
                feedback_id=feedback.id,
                asana_task_gid="1002",
                asana_task_url="https://app.asana.com/0/1/1002",
                asana_task_name="Task 2",
                last_status_synced_at=newer,
            ),
        ])
        db.commit()

        resp = client.get("/api/v1/integrations/asana/status", headers=owner_headers)
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
        active_integration: AsanaIntegration,
        owner_headers: dict,
    ):
        active_integration.last_sync_status = "error"
        active_integration.last_error = "401 invalid token"
        db.commit()

        resp = client.get("/api/v1/integrations/asana/status", headers=owner_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["last_sync_status"] == "error"
        assert body["last_error"] == "401 invalid token"

    def test_status_never_leaks_token(
        self,
        client: TestClient,
        active_integration: AsanaIntegration,
        owner_headers: dict,
    ):
        resp = client.get("/api/v1/integrations/asana/status", headers=owner_headers)
        assert resp.status_code == 200
        assert "api_token" not in resp.json()
        assert "encrypted-blob" not in resp.text

    def test_not_connected_returns_connected_false(
        self,
        client: TestClient,
        owner_headers: dict,
    ):
        resp = client.get("/api/v1/integrations/asana/status", headers=owner_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["connected"] is False
        assert body["status_sync_enabled"] is False


# ──────────────────────────── PATCH /status-sync ───────────────────────────────


class TestPatchStatusSync:
    def test_admin_toggles_enabled_true_persists(
        self,
        client: TestClient,
        db: Session,
        active_integration: AsanaIntegration,
        admin_headers: dict,
    ):
        resp = client.patch(
            "/api/v1/integrations/asana/status-sync",
            json={"enabled": True},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status_sync_enabled"] is True

        db.expire_all()
        row = db.query(AsanaIntegration).filter_by(id=active_integration.id).first()
        assert row.status_sync_enabled is True

    def test_owner_sets_valid_status_mapping_persists(
        self,
        client: TestClient,
        db: Session,
        active_integration: AsanaIntegration,
        owner_headers: dict,
    ):
        mapping = {"new": "new", "done": "closed"}
        resp = client.patch(
            "/api/v1/integrations/asana/status-sync",
            json={"enabled": True, "status_mapping": mapping},
            headers=owner_headers,
        )
        assert resp.status_code == 200

        db.expire_all()
        row = db.query(AsanaIntegration).filter_by(id=active_integration.id).first()
        assert row.status_mapping == mapping

    def test_indeterminate_key_accepted_forward_compat(
        self,
        client: TestClient,
        active_integration: AsanaIntegration,
        owner_headers: dict,
    ):
        resp = client.patch(
            "/api/v1/integrations/asana/status-sync",
            json={"enabled": True, "status_mapping": {"indeterminate": "in_review"}},
            headers=owner_headers,
        )
        assert resp.status_code == 200

    def test_invalid_mapping_key_returns_422(
        self,
        client: TestClient,
        active_integration: AsanaIntegration,
        owner_headers: dict,
    ):
        resp = client.patch(
            "/api/v1/integrations/asana/status-sync",
            json={"enabled": True, "status_mapping": {"bogus_key": "new"}},
            headers=owner_headers,
        )
        assert resp.status_code == 422

    def test_invalid_mapping_value_returns_422(
        self,
        client: TestClient,
        active_integration: AsanaIntegration,
        owner_headers: dict,
    ):
        resp = client.patch(
            "/api/v1/integrations/asana/status-sync",
            json={"enabled": True, "status_mapping": {"done": "bogus_status"}},
            headers=owner_headers,
        )
        assert resp.status_code == 422

    def test_member_forbidden(
        self,
        client: TestClient,
        active_integration: AsanaIntegration,
        member_headers: dict,
    ):
        resp = client.patch(
            "/api/v1/integrations/asana/status-sync",
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
            "/api/v1/integrations/asana/status-sync",
            json={"enabled": True},
            headers=owner_headers,
        )
        assert resp.status_code == 404

    def test_enabled_false_persists(
        self,
        client: TestClient,
        db: Session,
        active_integration: AsanaIntegration,
        owner_headers: dict,
    ):
        # Enable first.
        resp = client.patch(
            "/api/v1/integrations/asana/status-sync",
            json={"enabled": True},
            headers=owner_headers,
        )
        assert resp.status_code == 200

        # Then disable.
        resp = client.patch(
            "/api/v1/integrations/asana/status-sync",
            json={"enabled": False},
            headers=owner_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["status_sync_enabled"] is False

        db.expire_all()
        row = db.query(AsanaIntegration).filter_by(id=active_integration.id).first()
        assert row.status_sync_enabled is False


# ──────────────────────────── POST /sync ───────────────────────────────────────


class TestPostSync:
    def test_owner_can_trigger_sync(
        self,
        client: TestClient,
        active_integration: AsanaIntegration,
        owner_headers: dict,
    ):
        with patch("src.api.routes.asana_integration._get_celery_app") as mock_get_celery:
            mock_celery = MagicMock()
            mock_get_celery.return_value = mock_celery

            resp = client.post(
                "/api/v1/integrations/asana/sync",
                headers=owner_headers,
            )

        assert resp.status_code == 202
        assert resp.json()["status"] == "queued"
        mock_celery.send_task.assert_called_once_with(
            "src.tasks.asana_sync.sync_asana_org",
            args=[active_integration.id],
        )

    def test_admin_can_trigger_sync(
        self,
        client: TestClient,
        active_integration: AsanaIntegration,
        admin_headers: dict,
    ):
        with patch("src.api.routes.asana_integration._get_celery_app") as mock_get_celery:
            mock_celery = MagicMock()
            mock_get_celery.return_value = mock_celery

            resp = client.post(
                "/api/v1/integrations/asana/sync",
                headers=admin_headers,
            )

        assert resp.status_code == 202

    def test_broker_failure_returns_502(
        self,
        client: TestClient,
        active_integration: AsanaIntegration,
        owner_headers: dict,
    ):
        with patch("src.api.routes.asana_integration._get_celery_app") as mock_get_celery:
            mock_celery = MagicMock()
            mock_celery.send_task.side_effect = RuntimeError("broker unreachable")
            mock_get_celery.return_value = mock_celery

            resp = client.post(
                "/api/v1/integrations/asana/sync",
                headers=owner_headers,
            )

        assert resp.status_code == 502

    def test_member_forbidden(
        self,
        client: TestClient,
        active_integration: AsanaIntegration,
        member_headers: dict,
    ):
        resp = client.post(
            "/api/v1/integrations/asana/sync",
            headers=member_headers,
        )
        assert resp.status_code == 403

    def test_no_active_integration_returns_400(
        self,
        client: TestClient,
        owner_headers: dict,
    ):
        resp = client.post(
            "/api/v1/integrations/asana/sync",
            headers=owner_headers,
        )
        assert resp.status_code == 400

    def test_cross_org_has_no_active_integration(
        self,
        client: TestClient,
        active_integration: AsanaIntegration,
        other_owner_headers: dict,
    ):
        """An org without its own Asana integration must never trigger another org's sync."""
        resp = client.post(
            "/api/v1/integrations/asana/sync",
            headers=other_owner_headers,
        )
        assert resp.status_code == 400
