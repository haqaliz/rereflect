"""
Tests for POST /api/v1/integrations/zendesk/sync (manual "Sync now" trigger).

Phase 6 (should-have) of ingestion-pull aspect.
Mirrors tests/test_hubspot_sync_endpoint.py — but per plan D7 (PRD:
open-source, all features unlocked) this endpoint has NO require_feature
dependency, only require_admin_or_owner.
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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def zs_owner_user(db: Session, test_organization: Organization) -> User:
    user = User(
        email="zsync_owner@test.com",
        password_hash=hash_password("pw"),
        organization_id=test_organization.id,
        role="owner",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def zs_owner_headers(zs_owner_user: User) -> dict:
    token = create_access_token({
        "user_id": zs_owner_user.id,
        "organization_id": zs_owner_user.organization_id,
        "role": zs_owner_user.role,
    })
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def zs_admin_user(db: Session, test_organization: Organization) -> User:
    user = User(
        email="zsync_admin@test.com",
        password_hash=hash_password("pw"),
        organization_id=test_organization.id,
        role="admin",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def zs_admin_headers(zs_admin_user: User) -> dict:
    token = create_access_token({
        "user_id": zs_admin_user.id,
        "organization_id": zs_admin_user.organization_id,
        "role": zs_admin_user.role,
    })
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def zs_member_user(db: Session, test_organization: Organization) -> User:
    user = User(
        email="zsync_member@test.com",
        password_hash=hash_password("pw"),
        organization_id=test_organization.id,
        role="member",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def zs_member_headers(zs_member_user: User) -> dict:
    token = create_access_token({
        "user_id": zs_member_user.id,
        "organization_id": zs_member_user.organization_id,
        "role": zs_member_user.role,
    })
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def active_zendesk_integration(db: Session, test_organization: Organization) -> ZendeskIntegration:
    """Create an active Zendesk integration for the test org."""
    integ = ZendeskIntegration(
        organization_id=test_organization.id,
        subdomain="acmeco",
        email="agent@acmeco.com",
        api_token="encrypted-token-placeholder",
        token_hint="...abcd",
        is_active=True,
        connected_at=datetime.utcnow(),
    )
    db.add(integ)
    db.commit()
    db.refresh(integ)
    return integ


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestZendeskSyncEndpoint:
    def test_owner_can_trigger_sync(
        self,
        client: TestClient,
        db: Session,
        test_organization: Organization,
        active_zendesk_integration: ZendeskIntegration,
        zs_owner_headers: dict,
    ):
        with patch(
            "src.api.routes.zendesk_integration._get_celery_app"
        ) as mock_get_celery:
            mock_celery = MagicMock()
            mock_get_celery.return_value = mock_celery

            resp = client.post(
                "/api/v1/integrations/zendesk/sync",
                headers=zs_owner_headers,
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "queued"
        assert body["integration_id"] == active_zendesk_integration.id
        mock_celery.send_task.assert_called_once_with(
            "src.tasks.zendesk_sync.sync_zendesk_org",
            args=[active_zendesk_integration.id],
        )

    def test_admin_can_trigger_sync(
        self,
        client: TestClient,
        db: Session,
        test_organization: Organization,
        active_zendesk_integration: ZendeskIntegration,
        zs_admin_headers: dict,
    ):
        with patch(
            "src.api.routes.zendesk_integration._get_celery_app"
        ) as mock_get_celery:
            mock_celery = MagicMock()
            mock_get_celery.return_value = mock_celery

            resp = client.post(
                "/api/v1/integrations/zendesk/sync",
                headers=zs_admin_headers,
            )

        assert resp.status_code == 200
        assert resp.json()["status"] == "queued"

    def test_member_forbidden(
        self,
        client: TestClient,
        db: Session,
        test_organization: Organization,
        active_zendesk_integration: ZendeskIntegration,
        zs_member_headers: dict,
    ):
        resp = client.post(
            "/api/v1/integrations/zendesk/sync",
            headers=zs_member_headers,
        )
        assert resp.status_code == 403

    def test_no_active_integration_404s(
        self,
        client: TestClient,
        db: Session,
        test_organization: Organization,
        zs_owner_headers: dict,
    ):
        resp = client.post(
            "/api/v1/integrations/zendesk/sync",
            headers=zs_owner_headers,
        )
        assert resp.status_code == 404

    def test_never_500s_on_celery_dispatch_error(
        self,
        client: TestClient,
        db: Session,
        test_organization: Organization,
        active_zendesk_integration: ZendeskIntegration,
        zs_owner_headers: dict,
    ):
        with patch(
            "src.api.routes.zendesk_integration._get_celery_app"
        ) as mock_get_celery:
            mock_celery = MagicMock()
            mock_celery.send_task.side_effect = RuntimeError("broker unreachable")
            mock_get_celery.return_value = mock_celery

            resp = client.post(
                "/api/v1/integrations/zendesk/sync",
                headers=zs_owner_headers,
            )

        assert resp.status_code != 500
        assert resp.status_code == 502
        assert resp.json()["detail"]
