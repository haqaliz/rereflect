"""
Tests for HubSpot integration API routes (Phase 3 + Phase 4).

Role-matrix pattern mirrors tests/test_health_weights.py.
R6 test: POST /connect with missing LLM_ENCRYPTION_KEY returns 422 with
actionable message (patch encrypt_api_key — do not mutate env).
"""
import os
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from src.models.organization import Organization
from src.models.user import User
from src.models.hubspot_integration import HubSpotIntegration
from src.api.auth import hash_password, create_access_token

# Valid 32-byte Fernet key for tests only. NOT used in production.
# Note: plan specified "dGhpcyBpcyBhIHRlc3Qga2V5IGZvciBmZXJuZXQ=" but that
# decodes to 29 bytes and is invalid for Fernet (must be exactly 32 bytes).
# Using a proper 32-byte key (44 url-safe base64 chars) instead.
TEST_FERNET_KEY = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="

VALID_TOKEN = "pat-na1-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
PORTAL_RESPONSE = {
    "portalId": 12345678,
    "timeZone": "America/New_York",
    "companyCurrency": "USD",
    "additionalCurrencies": [],
    "utcOffset": "-05:00",
}


# ──────────────────────────── Fixtures ────────────────────────────────────────

@pytest.fixture
def owner_user(db: Session, test_organization: Organization) -> User:
    user = User(
        email="hs_owner@test.com",
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
        email="hs_admin@test.com",
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
        email="hs_member@test.com",
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
def second_org(db: Session) -> Organization:
    org = Organization(name="Other Corp", plan="pro")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


@pytest.fixture
def second_org_owner(db: Session, second_org: Organization) -> User:
    user = User(
        email="other_owner@test.com",
        password_hash=hash_password("pw"),
        organization_id=second_org.id,
        role="owner",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def second_org_headers(second_org_owner: User) -> dict:
    token = create_access_token({
        "user_id": second_org_owner.id,
        "organization_id": second_org_owner.organization_id,
        "role": second_org_owner.role,
    })
    return {"Authorization": f"Bearer {token}"}


# Context manager helpers

def hubspot_ping_ok():
    """Mock httpx.Client returning 200 from HubSpot account-info endpoint."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = PORTAL_RESPONSE
    mock_resp.raise_for_status = MagicMock()
    mock = MagicMock()
    mock.__enter__ = MagicMock(return_value=mock)
    mock.__exit__ = MagicMock(return_value=False)
    mock.get = MagicMock(return_value=mock_resp)
    return mock


def hubspot_ping_fail():
    """Mock httpx.Client raising 401 HTTPStatusError."""
    import httpx
    mock = MagicMock()
    mock.__enter__ = MagicMock(return_value=mock)
    mock.__exit__ = MagicMock(return_value=False)
    mock.get = MagicMock(side_effect=httpx.HTTPStatusError(
        "401", request=MagicMock(), response=MagicMock(status_code=401)
    ))
    return mock


# ──────────────────────────── Tests ───────────────────────────────────────────

class TestConnectEndpoint:
    def test_connect_valid_token_returns_200(self, client, owner_headers):
        with patch("src.api.routes.hubspot_integration.httpx.Client",
                   return_value=hubspot_ping_ok()):
            with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
                resp = client.post(
                    "/api/v1/integrations/hubspot/connect",
                    json={"access_token": VALID_TOKEN},
                    headers=owner_headers,
                )
        assert resp.status_code == 200

    def test_connect_response_does_not_contain_access_token(self, client, owner_headers):
        with patch("src.api.routes.hubspot_integration.httpx.Client",
                   return_value=hubspot_ping_ok()):
            with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
                resp = client.post(
                    "/api/v1/integrations/hubspot/connect",
                    json={"access_token": VALID_TOKEN},
                    headers=owner_headers,
                )
        body = resp.json()
        assert "access_token" not in body
        assert VALID_TOKEN not in str(body)

    def test_connect_stores_encrypted_token_not_plaintext(
        self, client, db, test_organization, owner_headers
    ):
        with patch("src.api.routes.hubspot_integration.httpx.Client",
                   return_value=hubspot_ping_ok()):
            with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
                resp = client.post(
                    "/api/v1/integrations/hubspot/connect",
                    json={"access_token": VALID_TOKEN},
                    headers=owner_headers,
                )
        assert resp.status_code == 200
        db.expire_all()
        row = db.query(HubSpotIntegration).filter_by(
            organization_id=test_organization.id
        ).first()
        assert row is not None
        assert row.access_token != VALID_TOKEN, "Token must be encrypted at rest"
        with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
            from src.utils.encryption import decrypt_api_key
            assert decrypt_api_key(row.access_token) == VALID_TOKEN

    def test_connect_token_hint_is_last_4_chars(
        self, client, db, test_organization, owner_headers
    ):
        with patch("src.api.routes.hubspot_integration.httpx.Client",
                   return_value=hubspot_ping_ok()):
            with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
                client.post(
                    "/api/v1/integrations/hubspot/connect",
                    json={"access_token": "pat-na1-ABCDEFG1234"},
                    headers=owner_headers,
                )
        db.expire_all()
        row = db.query(HubSpotIntegration).filter_by(
            organization_id=test_organization.id
        ).first()
        assert row.token_hint == "...1234"

    def test_connect_decrypt_round_trips(
        self, client, db, test_organization, owner_headers
    ):
        with patch("src.api.routes.hubspot_integration.httpx.Client",
                   return_value=hubspot_ping_ok()):
            with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
                client.post(
                    "/api/v1/integrations/hubspot/connect",
                    json={"access_token": VALID_TOKEN},
                    headers=owner_headers,
                )
        db.expire_all()
        row = db.query(HubSpotIntegration).filter_by(
            organization_id=test_organization.id
        ).first()
        with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
            from src.utils.encryption import decrypt_api_key
            assert decrypt_api_key(row.access_token) == VALID_TOKEN

    def test_connect_sets_hub_id(
        self, client, db, test_organization, owner_headers
    ):
        with patch("src.api.routes.hubspot_integration.httpx.Client",
                   return_value=hubspot_ping_ok()):
            with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
                client.post(
                    "/api/v1/integrations/hubspot/connect",
                    json={"access_token": VALID_TOKEN},
                    headers=owner_headers,
                )
        db.expire_all()
        row = db.query(HubSpotIntegration).filter_by(
            organization_id=test_organization.id
        ).first()
        assert row.hub_id == "12345678"

    def test_connect_invalid_token_returns_4xx(self, client, owner_headers):
        with patch("src.api.routes.hubspot_integration.httpx.Client",
                   return_value=hubspot_ping_fail()):
            resp = client.post(
                "/api/v1/integrations/hubspot/connect",
                json={"access_token": "invalid-token"},
                headers=owner_headers,
            )
        assert resp.status_code in (400, 401, 422)

    def test_connect_missing_encryption_key_returns_422(self, client, owner_headers):
        with (
            patch("src.api.routes.hubspot_integration.httpx.Client",
                  return_value=hubspot_ping_ok()),
            patch(
                "src.api.routes.hubspot_integration.encrypt_api_key",
                side_effect=ValueError("LLM_ENCRYPTION_KEY environment variable is not set"),
            ),
        ):
            resp = client.post(
                "/api/v1/integrations/hubspot/connect",
                json={"access_token": VALID_TOKEN},
                headers=owner_headers,
            )
        assert resp.status_code == 422
        assert "LLM_ENCRYPTION_KEY" in resp.json()["detail"]

    def test_connect_missing_encryption_key_message_is_actionable(self, client, owner_headers):
        with (
            patch("src.api.routes.hubspot_integration.httpx.Client",
                  return_value=hubspot_ping_ok()),
            patch(
                "src.api.routes.hubspot_integration.encrypt_api_key",
                side_effect=ValueError("LLM_ENCRYPTION_KEY environment variable is not set"),
            ),
        ):
            resp = client.post(
                "/api/v1/integrations/hubspot/connect",
                json={"access_token": VALID_TOKEN},
                headers=owner_headers,
            )
        detail = resp.json()["detail"]
        assert "LLM_ENCRYPTION_KEY" in detail

    def test_connect_second_connect_upserts(
        self, client, db, test_organization, owner_headers
    ):
        # First connect
        with patch("src.api.routes.hubspot_integration.httpx.Client",
                   return_value=hubspot_ping_ok()):
            with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
                client.post(
                    "/api/v1/integrations/hubspot/connect",
                    json={"access_token": VALID_TOKEN},
                    headers=owner_headers,
                )
        # Second connect — should not create a duplicate
        with patch("src.api.routes.hubspot_integration.httpx.Client",
                   return_value=hubspot_ping_ok()):
            with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
                resp = client.post(
                    "/api/v1/integrations/hubspot/connect",
                    json={"access_token": "pat-na1-newtoken1234"},
                    headers=owner_headers,
                )
        assert resp.status_code == 200
        db.expire_all()
        count = db.query(HubSpotIntegration).filter_by(
            organization_id=test_organization.id
        ).count()
        assert count == 1

    def test_connect_arr_property_name_default(
        self, client, db, test_organization, owner_headers
    ):
        with patch("src.api.routes.hubspot_integration.httpx.Client",
                   return_value=hubspot_ping_ok()):
            with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
                client.post(
                    "/api/v1/integrations/hubspot/connect",
                    json={"access_token": VALID_TOKEN},
                    headers=owner_headers,
                )
        db.expire_all()
        row = db.query(HubSpotIntegration).filter_by(
            organization_id=test_organization.id
        ).first()
        assert row.arr_property_name == "annualrevenue"

    def test_connect_arr_property_name_custom(
        self, client, db, test_organization, owner_headers
    ):
        with patch("src.api.routes.hubspot_integration.httpx.Client",
                   return_value=hubspot_ping_ok()):
            with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
                client.post(
                    "/api/v1/integrations/hubspot/connect",
                    json={"access_token": VALID_TOKEN, "arr_property_name": "mrr"},
                    headers=owner_headers,
                )
        db.expire_all()
        row = db.query(HubSpotIntegration).filter_by(
            organization_id=test_organization.id
        ).first()
        assert row.arr_property_name == "mrr"


class TestStatusEndpoint:
    def test_status_disconnected(self, client, owner_headers):
        resp = client.get(
            "/api/v1/integrations/hubspot/status",
            headers=owner_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["connected"] is False

    def test_status_connected(self, client, db, test_organization, owner_headers):
        from datetime import datetime
        db.add(HubSpotIntegration(
            organization_id=test_organization.id,
            access_token="encrypted_x",
            token_hint="...abcd",
            hub_id="99999",
            portal_name="Test Portal",
            arr_property_name="annualrevenue",
            connected_at=datetime.utcnow(),
            is_active=True,
        ))
        db.commit()
        resp = client.get(
            "/api/v1/integrations/hubspot/status",
            headers=owner_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["connected"] is True
        assert body["portal_name"] == "Test Portal"

    def test_status_never_returns_access_token(
        self, client, db, test_organization, owner_headers
    ):
        from datetime import datetime
        db.add(HubSpotIntegration(
            organization_id=test_organization.id,
            access_token="super_secret_token",
            connected_at=datetime.utcnow(),
            is_active=True,
        ))
        db.commit()
        resp = client.get(
            "/api/v1/integrations/hubspot/status",
            headers=owner_headers,
        )
        body = resp.json()
        assert "access_token" not in body
        assert "super_secret_token" not in str(body)

    def test_status_shows_token_hint(
        self, client, db, test_organization, owner_headers
    ):
        from datetime import datetime
        db.add(HubSpotIntegration(
            organization_id=test_organization.id,
            access_token="encrypted_y",
            token_hint="...wxyz",
            connected_at=datetime.utcnow(),
            is_active=True,
        ))
        db.commit()
        resp = client.get(
            "/api/v1/integrations/hubspot/status",
            headers=owner_headers,
        )
        assert resp.json()["token_hint"] == "...wxyz"

    def test_status_shows_portal_name(
        self, client, db, test_organization, owner_headers
    ):
        from datetime import datetime
        db.add(HubSpotIntegration(
            organization_id=test_organization.id,
            access_token="x",
            portal_name="My Portal",
            connected_at=datetime.utcnow(),
            is_active=True,
        ))
        db.commit()
        resp = client.get(
            "/api/v1/integrations/hubspot/status",
            headers=owner_headers,
        )
        assert resp.json()["portal_name"] == "My Portal"

    def test_status_after_disconnect_is_disconnected(
        self, client, db, test_organization, owner_headers
    ):
        from datetime import datetime
        db.add(HubSpotIntegration(
            organization_id=test_organization.id,
            access_token="z",
            connected_at=datetime.utcnow(),
            is_active=True,
        ))
        db.commit()
        # Disconnect
        client.delete(
            "/api/v1/integrations/hubspot/disconnect",
            headers=owner_headers,
        )
        # Status should be disconnected
        resp = client.get(
            "/api/v1/integrations/hubspot/status",
            headers=owner_headers,
        )
        assert resp.json()["connected"] is False


class TestDisconnectEndpoint:
    def test_disconnect_sets_inactive(
        self, client, db, test_organization, owner_headers
    ):
        from datetime import datetime
        db.add(HubSpotIntegration(
            organization_id=test_organization.id,
            access_token="enc",
            connected_at=datetime.utcnow(),
            is_active=True,
        ))
        db.commit()
        resp = client.delete(
            "/api/v1/integrations/hubspot/disconnect",
            headers=owner_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        db.expire_all()
        row = db.query(HubSpotIntegration).filter_by(
            organization_id=test_organization.id
        ).first()
        assert row.is_active is False

    def test_disconnect_nonexistent_returns_404(self, client, owner_headers):
        resp = client.delete(
            "/api/v1/integrations/hubspot/disconnect",
            headers=owner_headers,
        )
        assert resp.status_code == 404


class TestTestEndpoint:
    def test_test_with_valid_token_returns_success(
        self, client, db, test_organization, owner_headers
    ):
        from datetime import datetime
        with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
            from src.utils.encryption import encrypt_api_key
            encrypted = encrypt_api_key(VALID_TOKEN)
        db.add(HubSpotIntegration(
            organization_id=test_organization.id,
            access_token=encrypted,
            connected_at=datetime.utcnow(),
            is_active=True,
        ))
        db.commit()

        with patch("src.api.routes.hubspot_integration.httpx.Client",
                   return_value=hubspot_ping_ok()):
            with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
                resp = client.post(
                    "/api/v1/integrations/hubspot/test",
                    headers=owner_headers,
                )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_test_with_invalid_stored_token_returns_failure(
        self, client, db, test_organization, owner_headers
    ):
        from datetime import datetime
        # Store deliberately malformed ciphertext
        db.add(HubSpotIntegration(
            organization_id=test_organization.id,
            access_token="not-valid-fernet-token",
            connected_at=datetime.utcnow(),
            is_active=True,
        ))
        db.commit()
        with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
            resp = client.post(
                "/api/v1/integrations/hubspot/test",
                headers=owner_headers,
            )
        assert resp.status_code == 200
        assert resp.json()["success"] is False

    def test_test_without_connection_returns_400(self, client, owner_headers):
        resp = client.post(
            "/api/v1/integrations/hubspot/test",
            headers=owner_headers,
        )
        assert resp.status_code == 400


class TestRBAC:
    def test_connect_member_gets_403(self, client, member_headers):
        resp = client.post(
            "/api/v1/integrations/hubspot/connect",
            json={"access_token": VALID_TOKEN},
            headers=member_headers,
        )
        assert resp.status_code == 403

    def test_disconnect_member_gets_403(self, client, member_headers):
        resp = client.delete(
            "/api/v1/integrations/hubspot/disconnect",
            headers=member_headers,
        )
        assert resp.status_code == 403

    def test_status_member_gets_403(self, client, member_headers):
        resp = client.get(
            "/api/v1/integrations/hubspot/status",
            headers=member_headers,
        )
        assert resp.status_code == 403

    def test_test_member_gets_403(self, client, member_headers):
        resp = client.post(
            "/api/v1/integrations/hubspot/test",
            headers=member_headers,
        )
        assert resp.status_code == 403

    def test_connect_admin_succeeds(self, client, admin_headers):
        with patch("src.api.routes.hubspot_integration.httpx.Client",
                   return_value=hubspot_ping_ok()):
            with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
                resp = client.post(
                    "/api/v1/integrations/hubspot/connect",
                    json={"access_token": VALID_TOKEN},
                    headers=admin_headers,
                )
        assert resp.status_code == 200

    def test_connect_owner_succeeds(self, client, owner_headers):
        with patch("src.api.routes.hubspot_integration.httpx.Client",
                   return_value=hubspot_ping_ok()):
            with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
                resp = client.post(
                    "/api/v1/integrations/hubspot/connect",
                    json={"access_token": VALID_TOKEN},
                    headers=owner_headers,
                )
        assert resp.status_code == 200


class TestOrgIsolation:
    def test_status_for_second_org_sees_nothing(
        self,
        client,
        db,
        test_organization,
        owner_headers,
        second_org,
        second_org_headers,
    ):
        # Connect first org
        with patch("src.api.routes.hubspot_integration.httpx.Client",
                   return_value=hubspot_ping_ok()):
            with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
                client.post(
                    "/api/v1/integrations/hubspot/connect",
                    json={"access_token": VALID_TOKEN},
                    headers=owner_headers,
                )
        # Second org should see disconnected
        resp = client.get(
            "/api/v1/integrations/hubspot/status",
            headers=second_org_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["connected"] is False

    def test_disconnect_cannot_touch_other_org(
        self,
        client,
        db,
        test_organization,
        owner_headers,
        second_org,
        second_org_headers,
    ):
        # Connect first org
        with patch("src.api.routes.hubspot_integration.httpx.Client",
                   return_value=hubspot_ping_ok()):
            with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
                client.post(
                    "/api/v1/integrations/hubspot/connect",
                    json={"access_token": VALID_TOKEN},
                    headers=owner_headers,
                )
        # Second org tries to disconnect — should 404 (no integration for it)
        resp = client.delete(
            "/api/v1/integrations/hubspot/disconnect",
            headers=second_org_headers,
        )
        assert resp.status_code == 404
        # First org's integration should still be active
        db.expire_all()
        row = db.query(HubSpotIntegration).filter_by(
            organization_id=test_organization.id
        ).first()
        assert row is not None
        assert row.is_active is True


def test_hubspot_status_route_is_registered(client, owner_headers):
    """Endpoint must be reachable — 403/200 is fine, 404 is not."""
    resp = client.get(
        "/api/v1/integrations/hubspot/status",
        headers=owner_headers,
    )
    assert resp.status_code != 404, "Route not registered in main.py"
