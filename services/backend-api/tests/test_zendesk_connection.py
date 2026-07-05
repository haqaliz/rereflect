"""
TDD tests for the Zendesk connection routes (backend-connection aspect, Phase 3).

Covers: POST /connect, GET /status, DELETE /disconnect, POST /test.

Mocks ZendeskClient at the route module
(`src.api.routes.zendesk_integration.ZendeskClient`) per the repo's Jira/
Linear/HubSpot test pattern — never hits the network.

DNS resolution (the SSRF gate) is also mocked at the route module
(`src.api.routes.zendesk_integration.socket.getaddrinfo`), scoped tightly
around each individual `client.post(".../connect")` call via `_dns()` below
— NOT autouse. `socket.getaddrinfo` is a single process-global function, so
patching it for the lifetime of an entire test (autouse, wrapping fixture
setup too) would also hijack the real DNS the app's TestClient lifespan
performs on startup (e.g. changelog sync), causing multi-minute hangs as
those calls try to connect to the wrong (fake) IP. Keeping the patch scoped
to just the request under test avoids that entirely.
"""
import os
import pytest
from contextlib import contextmanager
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.models.organization import Organization
from src.models.user import User
from src.models.zendesk_integration import ZendeskIntegration
from src.models.feedback_source import FeedbackSource
from src.api.auth import hash_password, create_access_token


# Valid 32-byte Fernet key for tests only. NOT used in production.
TEST_FERNET_KEY = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="

SUBDOMAIN = "acme"
EMAIL = "operator@acme.com"
API_TOKEN = "zendesk-super-secret-token-xyz"

PUBLIC_IP = "93.184.216.34"


def _addrinfo(ip: str):
    """Shape of socket.getaddrinfo's return value (family, type, proto, canonname, sockaddr)."""
    return [(2, 1, 6, "", (ip, 443))]


@contextmanager
def _dns(ip: str = PUBLIC_IP):
    """Scope a DNS resolution mock tightly around a single request.

    Intentionally NOT autouse/session-wide — see module docstring.
    """
    with patch(
        "src.api.routes.zendesk_integration.socket.getaddrinfo",
        return_value=_addrinfo(ip),
    ):
        yield


def zendesk_client_ok(account_user_id="12345", display_name="Jane Agent"):
    """A ZendeskClient mock instance whose validate() succeeds."""
    mock_instance = MagicMock()
    mock_instance.validate.return_value = {
        "account_user_id": account_user_id,
        "display_name": display_name,
        "email": EMAIL,
    }
    mock_instance.close = MagicMock()
    return mock_instance


def zendesk_client_auth_fail():
    """A ZendeskClient mock instance whose validate() raises ZendeskAuthError."""
    from src.services.zendesk_client import ZendeskAuthError

    mock_instance = MagicMock()
    mock_instance.validate.side_effect = ZendeskAuthError("401 invalid token")
    mock_instance.close = MagicMock()
    return mock_instance


def zendesk_client_transient_fail():
    """A ZendeskClient mock instance whose validate() raises ZendeskTransientError."""
    from src.services.zendesk_client import ZendeskTransientError

    mock_instance = MagicMock()
    mock_instance.validate.side_effect = ZendeskTransientError("503 upstream error")
    mock_instance.close = MagicMock()
    return mock_instance


# ──────────────────────────── Fixtures ────────────────────────────────────────

@pytest.fixture
def owner_user(db: Session, test_organization: Organization) -> User:
    user = User(
        email="zendesk_owner@test.com",
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
def member_user(db: Session, test_organization: Organization) -> User:
    user = User(
        email="zendesk_member@test.com",
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
def free_organization(db: Session) -> Organization:
    """An organization on the Free plan — zendesk_integration must be unlocked here."""
    org = Organization(name="Free Zendesk Co", plan="free")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


@pytest.fixture
def free_owner_user(db: Session, free_organization: Organization) -> User:
    user = User(
        email="free_zendesk_owner@test.com",
        password_hash=hash_password("pw"),
        organization_id=free_organization.id,
        role="owner",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def free_owner_headers(free_owner_user: User) -> dict:
    token = create_access_token({
        "user_id": free_owner_user.id,
        "organization_id": free_owner_user.organization_id,
        "role": free_owner_user.role,
    })
    return {"Authorization": f"Bearer {token}"}


def _connect_payload(**overrides) -> dict:
    payload = {"subdomain": SUBDOMAIN, "email": EMAIL, "api_token": API_TOKEN}
    payload.update(overrides)
    return payload


# ──────────────────────────── POST /connect ───────────────────────────────────

class TestConnectEndpoint:
    def test_connect_valid_token_returns_200_with_expected_fields(self, client, owner_headers):
        with _dns(), patch("src.api.routes.zendesk_integration.ZendeskClient", return_value=zendesk_client_ok()):
            with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
                resp = client.post(
                    "/api/v1/integrations/zendesk/connect",
                    json=_connect_payload(),
                    headers=owner_headers,
                )
        assert resp.status_code == 200
        body = resp.json()
        assert body["connected"] is True
        assert body["subdomain"] == SUBDOMAIN
        assert body["email"] == EMAIL
        assert body["token_hint"] is not None
        assert body["account_user_id"] == "12345"
        assert body["display_name"] == "Jane Agent"
        assert isinstance(body["webhook_secret"], str) and len(body["webhook_secret"]) > 0

    def test_connect_response_never_contains_api_token(self, client, owner_headers):
        with _dns(), patch("src.api.routes.zendesk_integration.ZendeskClient", return_value=zendesk_client_ok()):
            with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
                resp = client.post(
                    "/api/v1/integrations/zendesk/connect",
                    json=_connect_payload(),
                    headers=owner_headers,
                )
        body = resp.json()
        assert "api_token" not in body
        assert API_TOKEN not in str(body)

    def test_connect_stores_encrypted_token_and_webhook_secret_not_plaintext(
        self, client, db, test_organization, owner_headers
    ):
        with _dns(), patch("src.api.routes.zendesk_integration.ZendeskClient", return_value=zendesk_client_ok()):
            with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
                resp = client.post(
                    "/api/v1/integrations/zendesk/connect",
                    json=_connect_payload(),
                    headers=owner_headers,
                )
        assert resp.status_code == 200
        body = resp.json()
        db.expire_all()
        row = db.query(ZendeskIntegration).filter_by(organization_id=test_organization.id).first()
        assert row is not None
        assert row.api_token != API_TOKEN, "Token must be encrypted at rest"
        assert row.webhook_secret is not None
        assert row.webhook_secret != body["webhook_secret"], "webhook_secret must be encrypted at rest"
        with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
            from src.utils.encryption import decrypt_api_key
            assert decrypt_api_key(row.api_token) == API_TOKEN
            assert decrypt_api_key(row.webhook_secret) == body["webhook_secret"]

    def test_connect_invalid_token_returns_422_and_persists_no_row(
        self, client, db, test_organization, owner_headers
    ):
        with _dns(), patch("src.api.routes.zendesk_integration.ZendeskClient", return_value=zendesk_client_auth_fail()):
            with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
                resp = client.post(
                    "/api/v1/integrations/zendesk/connect",
                    json=_connect_payload(),
                    headers=owner_headers,
                )
        assert resp.status_code == 422
        db.expire_all()
        row = db.query(ZendeskIntegration).filter_by(organization_id=test_organization.id).first()
        assert row is None

    def test_connect_transient_error_returns_502(self, client, owner_headers):
        with _dns(), patch("src.api.routes.zendesk_integration.ZendeskClient", return_value=zendesk_client_transient_fail()):
            with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
                resp = client.post(
                    "/api/v1/integrations/zendesk/connect",
                    json=_connect_payload(),
                    headers=owner_headers,
                )
        assert resp.status_code == 502

    def test_connect_missing_encryption_key_returns_422_not_500(self, client, owner_headers):
        with (
            _dns(),
            patch("src.api.routes.zendesk_integration.ZendeskClient", return_value=zendesk_client_ok()),
            patch(
                "src.api.routes.zendesk_integration.encrypt_api_key",
                side_effect=ValueError("LLM_ENCRYPTION_KEY environment variable is not set"),
            ),
        ):
            resp = client.post(
                "/api/v1/integrations/zendesk/connect",
                json=_connect_payload(),
                headers=owner_headers,
            )
        assert resp.status_code == 422
        assert "LLM_ENCRYPTION_KEY" in resp.json()["detail"]

    def test_connect_missing_encryption_key_returns_422_when_webhook_secret_encrypt_fails(
        self, client, owner_headers
    ):
        """Covers the R6 edge case where encrypt_api_key succeeds for api_token
        but then raises on the webhook_secret encrypt call (second invocation)."""
        real_encrypt = None

        def _side_effect(value):
            # First call (api_token) succeeds; second call (webhook_secret) raises.
            if _side_effect.calls == 0:
                _side_effect.calls += 1
                return "encrypted-api-token-blob"
            raise ValueError("LLM_ENCRYPTION_KEY environment variable is not set")

        _side_effect.calls = 0

        with (
            _dns(),
            patch("src.api.routes.zendesk_integration.ZendeskClient", return_value=zendesk_client_ok()),
            patch(
                "src.api.routes.zendesk_integration.encrypt_api_key",
                side_effect=_side_effect,
            ),
        ):
            resp = client.post(
                "/api/v1/integrations/zendesk/connect",
                json=_connect_payload(),
                headers=owner_headers,
            )
        assert resp.status_code == 422
        assert resp.status_code != 500

    @pytest.mark.parametrize(
        "raw_subdomain",
        ["acme", "acme.zendesk.com", "https://acme.zendesk.com", "https://acme.zendesk.com/"],
    )
    def test_connect_normalizes_subdomain_variants_to_canonical(
        self, client, db, test_organization, owner_headers, raw_subdomain
    ):
        with _dns(), patch("src.api.routes.zendesk_integration.ZendeskClient", return_value=zendesk_client_ok()):
            with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
                resp = client.post(
                    "/api/v1/integrations/zendesk/connect",
                    json=_connect_payload(subdomain=raw_subdomain),
                    headers=owner_headers,
                )
        assert resp.status_code == 200
        assert resp.json()["subdomain"] == SUBDOMAIN
        db.expire_all()
        row = db.query(ZendeskIntegration).filter_by(organization_id=test_organization.id).first()
        assert row.subdomain == SUBDOMAIN

    def test_connect_rejects_non_zendesk_host(self, client, owner_headers):
        with _dns(), patch("src.api.routes.zendesk_integration.ZendeskClient", return_value=zendesk_client_ok()):
            with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
                resp = client.post(
                    "/api/v1/integrations/zendesk/connect",
                    json=_connect_payload(subdomain="https://acme.example.com"),
                    headers=owner_headers,
                )
        assert resp.status_code == 422

    def test_connect_rejects_suffix_trick_host(self, client, owner_headers):
        with _dns(), patch("src.api.routes.zendesk_integration.ZendeskClient", return_value=zendesk_client_ok()):
            with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
                resp = client.post(
                    "/api/v1/integrations/zendesk/connect",
                    json=_connect_payload(subdomain="https://acme.zendesk.com.evil.com"),
                    headers=owner_headers,
                )
        assert resp.status_code == 422

    @pytest.mark.parametrize("private_ip", ["169.254.169.254", "10.0.0.1", "127.0.0.1"])
    def test_connect_ssrf_gate_rejects_private_resolving_host(
        self, client, owner_headers, private_ip
    ):
        with _dns(private_ip):
            with patch("src.api.routes.zendesk_integration.ZendeskClient", return_value=zendesk_client_ok()):
                with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
                    resp = client.post(
                        "/api/v1/integrations/zendesk/connect",
                        json=_connect_payload(),
                        headers=owner_headers,
                    )
        assert resp.status_code == 422

    def test_connect_ssrf_gate_allows_public_resolving_host(self, client, owner_headers):
        with _dns(PUBLIC_IP):
            with patch("src.api.routes.zendesk_integration.ZendeskClient", return_value=zendesk_client_ok()):
                with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
                    resp = client.post(
                        "/api/v1/integrations/zendesk/connect",
                        json=_connect_payload(),
                        headers=owner_headers,
                    )
        assert resp.status_code == 200

    def test_connect_reconnect_reuses_row_and_rotates_api_token_only(
        self, client, db, test_organization, owner_headers
    ):
        with _dns(), patch("src.api.routes.zendesk_integration.ZendeskClient", return_value=zendesk_client_ok()):
            with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
                first_resp = client.post(
                    "/api/v1/integrations/zendesk/connect",
                    json=_connect_payload(),
                    headers=owner_headers,
                )
        assert first_resp.status_code == 200
        first_body = first_resp.json()
        db.expire_all()
        first_row = db.query(ZendeskIntegration).filter_by(organization_id=test_organization.id).first()
        first_id = first_row.id
        first_token_hint = first_row.token_hint

        new_token = "zendesk-rotated-token-9999"
        with _dns(), patch(
            "src.api.routes.zendesk_integration.ZendeskClient",
            return_value=zendesk_client_ok(account_user_id="99999", display_name="New Name"),
        ):
            with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
                second_resp = client.post(
                    "/api/v1/integrations/zendesk/connect",
                    json=_connect_payload(api_token=new_token),
                    headers=owner_headers,
                )
        assert second_resp.status_code == 200
        second_body = second_resp.json()

        db.expire_all()
        rows = db.query(ZendeskIntegration).filter_by(organization_id=test_organization.id).all()
        assert len(rows) == 1, "Unique constraint must hold — reconnect must not create a 2nd row"
        row = rows[0]
        assert row.id == first_id
        assert row.is_active is True
        assert row.token_hint != first_token_hint
        assert row.token_hint == "...9999"
        from src.utils.encryption import decrypt_api_key
        with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
            assert decrypt_api_key(row.api_token) == new_token

        # webhook_secret must be preserved across reconnect (locked design decision)
        assert second_body["webhook_secret"] == first_body["webhook_secret"]

    def test_connect_auto_provisions_default_feedback_source(
        self, client, db, test_organization, owner_headers
    ):
        with _dns(), patch("src.api.routes.zendesk_integration.ZendeskClient", return_value=zendesk_client_ok()):
            with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
                resp = client.post(
                    "/api/v1/integrations/zendesk/connect",
                    json=_connect_payload(),
                    headers=owner_headers,
                )
        assert resp.status_code == 200
        db.expire_all()
        source = (
            db.query(FeedbackSource)
            .filter_by(organization_id=test_organization.id, source_type="zendesk")
            .first()
        )
        assert source is not None
        assert source.provider_config["subdomain"] == SUBDOMAIN
        assert source.auto_import is True

    def test_connect_does_not_duplicate_feedback_source_on_reconnect(
        self, client, db, test_organization, owner_headers
    ):
        with _dns(), patch("src.api.routes.zendesk_integration.ZendeskClient", return_value=zendesk_client_ok()):
            with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
                client.post(
                    "/api/v1/integrations/zendesk/connect",
                    json=_connect_payload(),
                    headers=owner_headers,
                )
        with _dns(), patch("src.api.routes.zendesk_integration.ZendeskClient", return_value=zendesk_client_ok()):
            with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
                client.post(
                    "/api/v1/integrations/zendesk/connect",
                    json=_connect_payload(api_token="zendesk-rotated-token-2222"),
                    headers=owner_headers,
                )
        db.expire_all()
        sources = (
            db.query(FeedbackSource)
            .filter_by(organization_id=test_organization.id, source_type="zendesk")
            .all()
        )
        assert len(sources) == 1

    def test_connect_does_not_duplicate_feedback_source_if_already_exists(
        self, client, db, test_organization, owner_headers
    ):
        pre_existing = FeedbackSource(
            organization_id=test_organization.id,
            integration_id=None,
            source_type="zendesk",
            name="My Custom Zendesk Source",
            provider_config={"subdomain": SUBDOMAIN},
            triggers={},
            field_mapping={},
            auto_import=True,
        )
        db.add(pre_existing)
        db.commit()
        db.refresh(pre_existing)
        pre_existing_id = pre_existing.id

        with _dns(), patch("src.api.routes.zendesk_integration.ZendeskClient", return_value=zendesk_client_ok()):
            with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
                resp = client.post(
                    "/api/v1/integrations/zendesk/connect",
                    json=_connect_payload(),
                    headers=owner_headers,
                )
        assert resp.status_code == 200

        db.expire_all()
        sources = (
            db.query(FeedbackSource)
            .filter_by(organization_id=test_organization.id, source_type="zendesk")
            .all()
        )
        assert len(sources) == 1
        assert sources[0].id == pre_existing_id
        assert sources[0].name == "My Custom Zendesk Source"


# ──────────────────────────── GET /status ──────────────────────────────────────

class TestStatusEndpoint:
    def test_status_disconnected_when_no_integration(self, client, owner_headers):
        resp = client.get("/api/v1/integrations/zendesk/status", headers=owner_headers)
        assert resp.status_code == 200
        assert resp.json()["connected"] is False

    def test_status_connected_returns_full_status(
        self, client, db, test_organization, owner_headers
    ):
        from datetime import datetime
        db.add(ZendeskIntegration(
            organization_id=test_organization.id,
            subdomain=SUBDOMAIN,
            email=EMAIL,
            api_token="encrypted-blob",
            token_hint="...wxyz",
            webhook_secret="encrypted-webhook-blob",
            account_user_id="acc-1",
            display_name="Display Name",
            is_active=True,
            connected_at=datetime.utcnow(),
        ))
        db.add(FeedbackSource(
            organization_id=test_organization.id,
            integration_id=None,
            source_type="zendesk",
            name="Zendesk",
            provider_config={"subdomain": SUBDOMAIN},
            triggers={},
            field_mapping={},
            auto_import=True,
        ))
        db.commit()

        resp = client.get("/api/v1/integrations/zendesk/status", headers=owner_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["connected"] is True
        assert body["subdomain"] == SUBDOMAIN
        assert body["email"] == EMAIL
        assert body["token_hint"] == "...wxyz"
        assert body["account_user_id"] == "acc-1"
        assert body["display_name"] == "Display Name"
        assert body["has_feedback_source"] is True
        assert "api_token" not in body
        assert "webhook_secret" not in body
        assert "encrypted-blob" not in str(body)
        assert "encrypted-webhook-blob" not in str(body)

    def test_status_has_feedback_source_false_when_no_source_provisioned(
        self, client, db, test_organization, owner_headers
    ):
        from datetime import datetime
        db.add(ZendeskIntegration(
            organization_id=test_organization.id,
            subdomain=SUBDOMAIN,
            email=EMAIL,
            api_token="encrypted-blob",
            is_active=True,
            connected_at=datetime.utcnow(),
        ))
        db.commit()

        resp = client.get("/api/v1/integrations/zendesk/status", headers=owner_headers)
        assert resp.status_code == 200
        assert resp.json()["has_feedback_source"] is False

    def test_status_requires_auth(self, client):
        resp = client.get("/api/v1/integrations/zendesk/status")
        assert resp.status_code == 403


# ──────────────────────────── DELETE /disconnect ───────────────────────────────

class TestDisconnectEndpoint:
    def test_disconnect_sets_inactive(self, client, db, test_organization, owner_headers):
        from datetime import datetime
        db.add(ZendeskIntegration(
            organization_id=test_organization.id,
            subdomain=SUBDOMAIN,
            email=EMAIL,
            api_token="encrypted-blob",
            is_active=True,
            connected_at=datetime.utcnow(),
        ))
        db.commit()

        resp = client.delete("/api/v1/integrations/zendesk/disconnect", headers=owner_headers)
        assert resp.status_code == 200
        db.expire_all()
        row = db.query(ZendeskIntegration).filter_by(organization_id=test_organization.id).first()
        assert row.is_active is False

    def test_disconnect_does_not_touch_feedback_source(
        self, client, db, test_organization, owner_headers
    ):
        from datetime import datetime
        db.add(ZendeskIntegration(
            organization_id=test_organization.id,
            subdomain=SUBDOMAIN,
            email=EMAIL,
            api_token="encrypted-blob",
            is_active=True,
            connected_at=datetime.utcnow(),
        ))
        source = FeedbackSource(
            organization_id=test_organization.id,
            integration_id=None,
            source_type="zendesk",
            name="Zendesk",
            provider_config={"subdomain": SUBDOMAIN},
            triggers={},
            field_mapping={},
            auto_import=True,
        )
        db.add(source)
        db.commit()
        source_id = source.id

        resp = client.delete("/api/v1/integrations/zendesk/disconnect", headers=owner_headers)
        assert resp.status_code == 200

        db.expire_all()
        preserved = db.query(FeedbackSource).filter_by(id=source_id).first()
        assert preserved is not None
        assert preserved.is_active is True

    def test_disconnect_nonexistent_returns_404(self, client, owner_headers):
        resp = client.delete("/api/v1/integrations/zendesk/disconnect", headers=owner_headers)
        assert resp.status_code == 404


# ──────────────────────────── POST /test ───────────────────────────────────────

class TestTestEndpoint:
    def test_test_with_valid_token_returns_success(
        self, client, db, test_organization, owner_headers
    ):
        from datetime import datetime
        with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
            from src.utils.encryption import encrypt_api_key
            encrypted = encrypt_api_key(API_TOKEN)
        db.add(ZendeskIntegration(
            organization_id=test_organization.id,
            subdomain=SUBDOMAIN,
            email=EMAIL,
            api_token=encrypted,
            is_active=True,
            connected_at=datetime.utcnow(),
        ))
        db.commit()

        with patch("src.api.routes.zendesk_integration.ZendeskClient", return_value=zendesk_client_ok()):
            with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
                resp = client.post("/api/v1/integrations/zendesk/test", headers=owner_headers)
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_test_with_invalid_stored_token_returns_failure_never_500(
        self, client, db, test_organization, owner_headers
    ):
        from datetime import datetime
        # Malformed ciphertext -> decrypt_api_key raises; route must swallow it.
        db.add(ZendeskIntegration(
            organization_id=test_organization.id,
            subdomain=SUBDOMAIN,
            email=EMAIL,
            api_token="not-a-valid-fernet-token",
            is_active=True,
            connected_at=datetime.utcnow(),
        ))
        db.commit()

        with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
            resp = client.post("/api/v1/integrations/zendesk/test", headers=owner_headers)
        assert resp.status_code == 200
        assert resp.json()["success"] is False

    def test_test_with_auth_error_returns_failure_never_500(
        self, client, db, test_organization, owner_headers
    ):
        from datetime import datetime
        with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
            from src.utils.encryption import encrypt_api_key
            encrypted = encrypt_api_key(API_TOKEN)
        db.add(ZendeskIntegration(
            organization_id=test_organization.id,
            subdomain=SUBDOMAIN,
            email=EMAIL,
            api_token=encrypted,
            is_active=True,
            connected_at=datetime.utcnow(),
        ))
        db.commit()

        with patch("src.api.routes.zendesk_integration.ZendeskClient", return_value=zendesk_client_auth_fail()):
            with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
                resp = client.post("/api/v1/integrations/zendesk/test", headers=owner_headers)
        assert resp.status_code == 200
        assert resp.json()["success"] is False

    def test_test_without_connection_returns_400(self, client, owner_headers):
        resp = client.post("/api/v1/integrations/zendesk/test", headers=owner_headers)
        assert resp.status_code == 400


# ──────────────────────────── RBAC ─────────────────────────────────────────────

class TestRBAC:
    def test_connect_member_gets_403(self, client, member_headers):
        resp = client.post(
            "/api/v1/integrations/zendesk/connect",
            json=_connect_payload(),
            headers=member_headers,
        )
        assert resp.status_code == 403

    def test_status_member_gets_403(self, client, member_headers):
        resp = client.get("/api/v1/integrations/zendesk/status", headers=member_headers)
        assert resp.status_code == 403

    def test_disconnect_member_gets_403(self, client, member_headers):
        resp = client.delete("/api/v1/integrations/zendesk/disconnect", headers=member_headers)
        assert resp.status_code == 403

    def test_test_member_gets_403(self, client, member_headers):
        resp = client.post("/api/v1/integrations/zendesk/test", headers=member_headers)
        assert resp.status_code == 403


# ──────────────────────────── Free-plan unlocked ───────────────────────────────

class TestFreePlanUnlocked:
    """zendesk_integration must work end-to-end for an org on the Free plan."""

    def test_connect_status_disconnect_test_all_work_on_free_plan(
        self, client, db, free_organization, free_owner_headers
    ):
        # connect
        with _dns(), patch("src.api.routes.zendesk_integration.ZendeskClient", return_value=zendesk_client_ok()):
            with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
                connect_resp = client.post(
                    "/api/v1/integrations/zendesk/connect",
                    json=_connect_payload(),
                    headers=free_owner_headers,
                )
        assert connect_resp.status_code == 200
        assert connect_resp.json()["connected"] is True

        # status
        status_resp = client.get("/api/v1/integrations/zendesk/status", headers=free_owner_headers)
        assert status_resp.status_code == 200
        assert status_resp.json()["connected"] is True

        # test
        with patch("src.api.routes.zendesk_integration.ZendeskClient", return_value=zendesk_client_ok()):
            with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
                test_resp = client.post("/api/v1/integrations/zendesk/test", headers=free_owner_headers)
        assert test_resp.status_code == 200
        assert test_resp.json()["success"] is True

        # disconnect
        disconnect_resp = client.delete(
            "/api/v1/integrations/zendesk/disconnect", headers=free_owner_headers
        )
        assert disconnect_resp.status_code == 200

        db.expire_all()
        row = db.query(ZendeskIntegration).filter_by(organization_id=free_organization.id).first()
        assert row.is_active is False


def test_zendesk_status_route_is_registered(client, owner_headers):
    """Endpoint must be reachable — 403/200 is fine, 404 is not."""
    resp = client.get("/api/v1/integrations/zendesk/status", headers=owner_headers)
    assert resp.status_code != 404, "Route not registered in main.py"
