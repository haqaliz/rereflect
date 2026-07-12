"""
TDD tests for the Zendesk inbound status-sync operator control routes.

Covers:
  - GET   /api/v1/integrations/zendesk/status         (extended with 4 new fields)
  - PATCH /api/v1/integrations/zendesk/status-sync     (toggle + mapping)
  - POST  /api/v1/integrations/zendesk/status-sync/sync (manual trigger, 202)

Mirrors the test style of tests/test_jira_status_sync_routes.py, adapted for
Zendesk's vocab (ZENDESK_STATUSES / VALID_STATUSES) and its distinct
/status-sync/sync sub-path (kept separate from the existing ingestion
POST /sync, covered by tests/test_zendesk_sync_endpoint.py).
"""
import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.models.organization import Organization
from src.models.user import User
from src.models.zendesk_integration import ZendeskIntegration
from src.api.auth import hash_password, create_access_token


SUBDOMAIN = "acmeco"
EMAIL = "operator@acmeco.com"


# ──────────────────────────── Fixtures ────────────────────────────────────────


@pytest.fixture
def owner_user(db: Session, test_organization: Organization) -> User:
    user = User(
        email="zss_owner@test.com",
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
        email="zss_admin@test.com",
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
        email="zss_member@test.com",
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
        email="zss_other_owner@test.com",
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
def active_integration(db: Session, test_organization: Organization) -> ZendeskIntegration:
    """A fresh, active Zendesk integration with status sync untouched (defaults)."""
    integ = ZendeskIntegration(
        organization_id=test_organization.id,
        subdomain=SUBDOMAIN,
        email=EMAIL,
        api_token="encrypted-blob",
        token_hint="...wxyz",
        account_user_id="acc-1",
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
        self, client: TestClient, active_integration: ZendeskIntegration, owner_headers: dict
    ):
        resp = client.get("/api/v1/integrations/zendesk/status", headers=owner_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["connected"] is True
        assert body["status_sync_enabled"] is False
        assert body["status_mapping"] is None
        assert body["last_status_synced_at"] is None
        assert body["last_status_sync_error"] is None
        # Ingestion fields untouched
        assert body["last_synced_at"] is None
        assert body["last_sync_status"] is None
        assert body["last_error"] is None

    def test_status_sync_fields_reflect_row_state(
        self,
        client: TestClient,
        db: Session,
        active_integration: ZendeskIntegration,
        owner_headers: dict,
    ):
        mapping = {"solved": "resolved", "closed": "closed"}
        now = datetime.utcnow()
        active_integration.status_sync_enabled = True
        active_integration.status_mapping = mapping
        active_integration.last_status_synced_at = now
        active_integration.last_status_sync_error = "boom"
        # Ingestion fields set to different values to prove no cross-talk.
        active_integration.last_sync_status = "success"
        active_integration.last_error = None
        db.commit()

        resp = client.get("/api/v1/integrations/zendesk/status", headers=owner_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["status_sync_enabled"] is True
        assert body["status_mapping"] == mapping
        assert body["last_status_sync_error"] == "boom"
        returned = datetime.fromisoformat(body["last_status_synced_at"])
        assert abs((returned.replace(tzinfo=None) - now).total_seconds()) < 2
        # Ingestion fields still independently reported
        assert body["last_sync_status"] == "success"
        assert body["last_error"] is None


# ──────────────────────────── PATCH /status-sync ───────────────────────────────


class TestPatchStatusSync:
    def test_admin_toggles_enabled_true_persists(
        self,
        client: TestClient,
        db: Session,
        active_integration: ZendeskIntegration,
        admin_headers: dict,
    ):
        resp = client.patch(
            "/api/v1/integrations/zendesk/status-sync",
            json={"enabled": True},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status_sync_enabled"] is True

        db.expire_all()
        row = db.query(ZendeskIntegration).filter_by(id=active_integration.id).first()
        assert row.status_sync_enabled is True

    def test_owner_sets_valid_status_mapping_persists(
        self,
        client: TestClient,
        db: Session,
        active_integration: ZendeskIntegration,
        owner_headers: dict,
    ):
        mapping = {"solved": "resolved", "open": "in_review"}
        resp = client.patch(
            "/api/v1/integrations/zendesk/status-sync",
            json={"enabled": True, "status_mapping": mapping},
            headers=owner_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status_mapping"] == mapping

        db.expire_all()
        row = db.query(ZendeskIntegration).filter_by(id=active_integration.id).first()
        assert row.status_mapping == mapping

    def test_invalid_mapping_key_returns_422(
        self,
        client: TestClient,
        active_integration: ZendeskIntegration,
        owner_headers: dict,
    ):
        resp = client.patch(
            "/api/v1/integrations/zendesk/status-sync",
            json={"enabled": True, "status_mapping": {"bogus_key": "resolved"}},
            headers=owner_headers,
        )
        assert resp.status_code == 422

    def test_invalid_mapping_value_returns_422(
        self,
        client: TestClient,
        active_integration: ZendeskIntegration,
        owner_headers: dict,
    ):
        resp = client.patch(
            "/api/v1/integrations/zendesk/status-sync",
            json={"enabled": True, "status_mapping": {"solved": "bogus_status"}},
            headers=owner_headers,
        )
        assert resp.status_code == 422

    def test_member_forbidden(
        self,
        client: TestClient,
        active_integration: ZendeskIntegration,
        member_headers: dict,
    ):
        resp = client.patch(
            "/api/v1/integrations/zendesk/status-sync",
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
            "/api/v1/integrations/zendesk/status-sync",
            json={"enabled": True},
            headers=owner_headers,
        )
        assert resp.status_code == 404


# ──────────────────────────── POST /status-sync/sync ───────────────────────────


class TestPostStatusSyncTrigger:
    def test_owner_can_trigger_sync(
        self,
        client: TestClient,
        active_integration: ZendeskIntegration,
        owner_headers: dict,
    ):
        with patch("src.api.routes.zendesk_integration._get_celery_app") as mock_get_celery:
            mock_celery = MagicMock()
            mock_get_celery.return_value = mock_celery

            resp = client.post(
                "/api/v1/integrations/zendesk/status-sync/sync",
                headers=owner_headers,
            )

        assert resp.status_code == 202
        assert resp.json()["status"] == "queued"
        mock_celery.send_task.assert_called_once_with(
            "src.tasks.zendesk_status_sync.sync_zendesk_status_org",
            args=[active_integration.id],
        )

    def test_admin_can_trigger_sync(
        self,
        client: TestClient,
        active_integration: ZendeskIntegration,
        admin_headers: dict,
    ):
        with patch("src.api.routes.zendesk_integration._get_celery_app") as mock_get_celery:
            mock_celery = MagicMock()
            mock_get_celery.return_value = mock_celery

            resp = client.post(
                "/api/v1/integrations/zendesk/status-sync/sync",
                headers=admin_headers,
            )

        assert resp.status_code == 202

    def test_broker_failure_returns_502(
        self,
        client: TestClient,
        active_integration: ZendeskIntegration,
        owner_headers: dict,
    ):
        with patch("src.api.routes.zendesk_integration._get_celery_app") as mock_get_celery:
            mock_celery = MagicMock()
            mock_celery.send_task.side_effect = RuntimeError("broker unreachable")
            mock_get_celery.return_value = mock_celery

            resp = client.post(
                "/api/v1/integrations/zendesk/status-sync/sync",
                headers=owner_headers,
            )

        assert resp.status_code == 502

    def test_member_forbidden(
        self,
        client: TestClient,
        active_integration: ZendeskIntegration,
        member_headers: dict,
    ):
        resp = client.post(
            "/api/v1/integrations/zendesk/status-sync/sync",
            headers=member_headers,
        )
        assert resp.status_code == 403

    def test_no_active_integration_returns_400(
        self,
        client: TestClient,
        owner_headers: dict,
    ):
        resp = client.post(
            "/api/v1/integrations/zendesk/status-sync/sync",
            headers=owner_headers,
        )
        assert resp.status_code == 400

    def test_cross_org_has_no_active_integration(
        self,
        client: TestClient,
        active_integration: ZendeskIntegration,
        other_owner_headers: dict,
    ):
        """An org without its own Zendesk integration must never trigger another org's sync."""
        resp = client.post(
            "/api/v1/integrations/zendesk/status-sync/sync",
            headers=other_owner_headers,
        )
        assert resp.status_code == 400
