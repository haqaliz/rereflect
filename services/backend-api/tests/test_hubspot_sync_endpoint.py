"""
Tests for POST /api/v1/integrations/hubspot/sync (manual trigger endpoint).

Phase 5 of hubspot-sync aspect.
Mirrors pattern from test_hubspot_routes.py.
"""

import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.models.organization import Organization
from src.models.user import User
from src.models.hubspot_integration import HubSpotIntegration
from src.api.auth import hash_password, create_access_token

# Valid 32-byte Fernet key for tests (same as test_hubspot_routes.py)
TEST_FERNET_KEY = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def hs_owner_user(db: Session, test_organization: Organization) -> User:
    user = User(
        email="sync_owner@test.com",
        password_hash=hash_password("pw"),
        organization_id=test_organization.id,
        role="owner",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def hs_owner_headers(hs_owner_user: User) -> dict:
    token = create_access_token({
        "user_id": hs_owner_user.id,
        "organization_id": hs_owner_user.organization_id,
        "role": hs_owner_user.role,
    })
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def hs_admin_user(db: Session, test_organization: Organization) -> User:
    user = User(
        email="sync_admin@test.com",
        password_hash=hash_password("pw"),
        organization_id=test_organization.id,
        role="admin",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def hs_admin_headers(hs_admin_user: User) -> dict:
    token = create_access_token({
        "user_id": hs_admin_user.id,
        "organization_id": hs_admin_user.organization_id,
        "role": hs_admin_user.role,
    })
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def hs_member_user(db: Session, test_organization: Organization) -> User:
    user = User(
        email="sync_member@test.com",
        password_hash=hash_password("pw"),
        organization_id=test_organization.id,
        role="member",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def hs_member_headers(hs_member_user: User) -> dict:
    token = create_access_token({
        "user_id": hs_member_user.id,
        "organization_id": hs_member_user.organization_id,
        "role": hs_member_user.role,
    })
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def active_integration(db: Session, test_organization: Organization) -> HubSpotIntegration:
    """Create an active HubSpot integration for the test org."""
    integ = HubSpotIntegration(
        organization_id=test_organization.id,
        access_token="encrypted-token-placeholder",
        token_hint="...abcd",
        hub_id="12345678",
        portal_name="Test Portal",
        arr_property_name="annualrevenue",
        is_active=True,
        connected_at=datetime.utcnow(),
        contacts_synced=0,
        contacts_matched=0,
    )
    db.add(integ)
    db.commit()
    db.refresh(integ)
    return integ


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestHubSpotSyncEndpoint:
    def test_sync_enqueues_task_for_admin(
        self,
        client: TestClient,
        db: Session,
        test_organization: Organization,
        active_integration: HubSpotIntegration,
        hs_admin_headers: dict,
    ):
        """Admin POST /sync → 200, status=queued, delay() called with integration.id."""
        with patch(
            "src.api.routes.hubspot_integration._get_celery_app"
        ) as mock_get_celery:
            mock_celery = MagicMock()
            mock_get_celery.return_value = mock_celery

            resp = client.post(
                "/api/v1/integrations/hubspot/sync",
                headers=hs_admin_headers,
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "queued"
        assert body["integration_id"] == active_integration.id
        mock_celery.send_task.assert_called_once_with(
            "src.tasks.hubspot_sync.sync_hubspot_org",
            args=[active_integration.id],
        )

    def test_sync_enqueues_task_for_owner(
        self,
        client: TestClient,
        db: Session,
        test_organization: Organization,
        active_integration: HubSpotIntegration,
        hs_owner_headers: dict,
    ):
        """Owner POST /sync → 200, status=queued."""
        with patch(
            "src.api.routes.hubspot_integration._get_celery_app"
        ) as mock_get_celery:
            mock_celery = MagicMock()
            mock_get_celery.return_value = mock_celery

            resp = client.post(
                "/api/v1/integrations/hubspot/sync",
                headers=hs_owner_headers,
            )

        assert resp.status_code == 200
        assert resp.json()["status"] == "queued"

    def test_sync_returns_404_when_not_connected(
        self,
        client: TestClient,
        db: Session,
        test_organization: Organization,
        hs_owner_headers: dict,
    ):
        """No active integration → 404."""
        resp = client.post(
            "/api/v1/integrations/hubspot/sync",
            headers=hs_owner_headers,
        )
        assert resp.status_code == 404

    def test_sync_forbidden_for_member(
        self,
        client: TestClient,
        db: Session,
        test_organization: Organization,
        active_integration: HubSpotIntegration,
        hs_member_headers: dict,
    ):
        """Member POST /sync → 403."""
        resp = client.post(
            "/api/v1/integrations/hubspot/sync",
            headers=hs_member_headers,
        )
        assert resp.status_code == 403
