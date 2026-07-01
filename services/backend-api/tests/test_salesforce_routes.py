"""
Tests for Salesforce integration API routes (salesforce-connection aspect).

Role-matrix pattern mirrors tests/test_hubspot_routes.py.
Mock ALL Salesforce HTTP — no live org.
"""
import os
import urllib.parse
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.models.organization import Organization
from src.models.user import User
from src.models.hubspot_integration import HubSpotIntegration
from src.models.salesforce_integration import SalesforceIntegration
from src.api.auth import hash_password, create_access_token

TEST_FERNET_KEY = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="

SALESFORCE_ENV = {
    "SALESFORCE_CLIENT_ID": "sf-client-id",
    "SALESFORCE_CLIENT_SECRET": "sf-client-secret",
    "SALESFORCE_REDIRECT_URI": "http://localhost:8000/api/v1/integrations/salesforce/callback",
    "SALESFORCE_LOGIN_BASE": "https://login.salesforce.com",
    "SALESFORCE_API_VERSION": "v60.0",
}

TOKEN_RESPONSE = {
    "access_token": "00Dxx0000001gPF!ARsAQP0",
    "refresh_token": "5Aep861...refresh...token",
    "instance_url": "https://acme.my.salesforce.com",
    "id": "https://login.salesforce.com/id/00Dxx0000001gPFEAY/005xx000001Sv6AAAS",
    "token_type": "Bearer",
}


# ──────────────────────────── Fixtures ────────────────────────────────────────

@pytest.fixture
def owner_user(db: Session, test_organization: Organization) -> User:
    user = User(
        email="sf_owner@test.com",
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
        email="sf_admin@test.com",
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
        email="sf_member@test.com",
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
def active_integration(db: Session, test_organization: Organization) -> SalesforceIntegration:
    integ = SalesforceIntegration(
        organization_id=test_organization.id,
        refresh_token="encrypted-refresh-placeholder",
        instance_url="https://acme.my.salesforce.com",
        sf_org_id="00Dxx0000001gPFEAY",
        token_hint="...oken",
        is_active=True,
        connected_at=datetime.utcnow(),
        contacts_synced=0,
        contacts_matched=0,
    )
    db.add(integ)
    db.commit()
    db.refresh(integ)
    return integ


def _salesforce_env():
    return patch.dict(os.environ, SALESFORCE_ENV)


def token_exchange_ok():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = TOKEN_RESPONSE
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


def userinfo_ok():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"user_id": "005xx000001Sv6AAAS", "organization_id": "00Dxx0000001gPFEAY"}
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


# ──────────────────────────── connect-url ─────────────────────────────────────


class TestConnectUrlEndpoint:
    def test_connect_url_returns_well_formed_authorize_url(self, client, owner_headers):
        with _salesforce_env():
            resp = client.get(
                "/api/v1/integrations/salesforce/connect-url",
                headers=owner_headers,
            )
        assert resp.status_code == 200
        body = resp.json()
        assert "auth_url" in body
        parsed = urllib.parse.urlparse(body["auth_url"])
        assert parsed.scheme == "https"
        assert parsed.netloc == "login.salesforce.com"
        assert parsed.path == "/services/oauth2/authorize"
        qs = urllib.parse.parse_qs(parsed.query)
        assert qs["response_type"] == ["code"]
        assert qs["client_id"] == ["sf-client-id"]
        assert qs["redirect_uri"] == ["http://localhost:8000/api/v1/integrations/salesforce/callback"]
        assert qs["scope"] == ["refresh_token offline_access api"]
        assert "state" in qs and qs["state"][0]

    def test_connect_url_state_is_verifiable(self, client, owner_headers, owner_user):
        with _salesforce_env():
            resp = client.get(
                "/api/v1/integrations/salesforce/connect-url",
                headers=owner_headers,
            )
        body = resp.json()
        parsed = urllib.parse.urlparse(body["auth_url"])
        state = urllib.parse.parse_qs(parsed.query)["state"][0]
        from src.api.routes.salesforce_integration import _verify_state
        payload = _verify_state(state)
        assert payload is not None
        assert payload["org_id"] == owner_user.organization_id
        assert payload["user_id"] == owner_user.id

    def test_connect_url_member_gets_403(self, client, member_headers):
        with _salesforce_env():
            resp = client.get(
                "/api/v1/integrations/salesforce/connect-url",
                headers=member_headers,
            )
        assert resp.status_code == 403

    def test_connect_url_blocked_when_hubspot_active(
        self, client, db, test_organization, owner_headers
    ):
        db.add(HubSpotIntegration(
            organization_id=test_organization.id,
            access_token="enc",
            connected_at=datetime.utcnow(),
            is_active=True,
        ))
        db.commit()
        with _salesforce_env():
            resp = client.get(
                "/api/v1/integrations/salesforce/connect-url",
                headers=owner_headers,
            )
        assert resp.status_code == 409

    def test_connect_url_not_blocked_when_hubspot_inactive(
        self, client, db, test_organization, owner_headers
    ):
        db.add(HubSpotIntegration(
            organization_id=test_organization.id,
            access_token="enc",
            connected_at=datetime.utcnow(),
            is_active=False,
        ))
        db.commit()
        with _salesforce_env():
            resp = client.get(
                "/api/v1/integrations/salesforce/connect-url",
                headers=owner_headers,
            )
        assert resp.status_code == 200


# ──────────────────────────── status ──────────────────────────────────────────


class TestStatusEndpoint:
    def test_status_disconnected(self, client, owner_headers):
        resp = client.get(
            "/api/v1/integrations/salesforce/status",
            headers=owner_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["connected"] is False

    def test_status_connected(self, client, active_integration, owner_headers):
        resp = client.get(
            "/api/v1/integrations/salesforce/status",
            headers=owner_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["connected"] is True
        assert body["instance_url"] == "https://acme.my.salesforce.com"
        assert body["sf_org_id"] == "00Dxx0000001gPFEAY"

    def test_status_never_returns_refresh_or_access_token(
        self, client, active_integration, owner_headers
    ):
        resp = client.get(
            "/api/v1/integrations/salesforce/status",
            headers=owner_headers,
        )
        body = resp.json()
        assert "refresh_token" not in body
        assert "access_token" not in body
        assert "encrypted-refresh-placeholder" not in str(body)

    def test_status_member_gets_403(self, client, member_headers):
        resp = client.get(
            "/api/v1/integrations/salesforce/status",
            headers=member_headers,
        )
        assert resp.status_code == 403


def test_salesforce_status_route_is_registered(client, owner_headers):
    """Endpoint must be reachable — 403/200 is fine, 404 is not."""
    resp = client.get(
        "/api/v1/integrations/salesforce/status",
        headers=owner_headers,
    )
    assert resp.status_code != 404, "Route not registered in main.py"
