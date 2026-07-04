"""
TDD tests for the Jira connection routes (backend-connection aspect, Phase 3).

Covers: POST /connect, GET /status, DELETE /disconnect, POST /test.

Mocks JiraClient at the route module (`src.api.routes.jira_integration.JiraClient`)
per the repo's Linear/HubSpot test pattern — never hits the network.

DNS resolution (the SSRF gate) is also mocked at the route module
(`src.api.routes.jira_integration.socket.getaddrinfo`), scoped tightly
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
from src.models.jira_integration import JiraIntegration, FeedbackJiraIssue
from src.api.auth import hash_password, create_access_token


# Valid 32-byte Fernet key for tests only. NOT used in production.
TEST_FERNET_KEY = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="

SITE_URL = "https://acme.atlassian.net"
EMAIL = "operator@acme.com"
API_TOKEN = "atlassian-super-secret-token-xyz"

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
        "src.api.routes.jira_integration.socket.getaddrinfo",
        return_value=_addrinfo(ip),
    ):
        yield


def jira_client_ok(account_id="5b10a2844c20165700ede21g", display_name="Jane Operator"):
    """A JiraClient mock instance whose validate() succeeds."""
    mock_instance = MagicMock()
    mock_instance.validate.return_value = {
        "account_id": account_id,
        "display_name": display_name,
        "email": EMAIL,
    }
    mock_instance.close = MagicMock()
    return mock_instance


def jira_client_auth_fail():
    """A JiraClient mock instance whose validate() raises JiraAuthError."""
    from src.services.jira_client import JiraAuthError

    mock_instance = MagicMock()
    mock_instance.validate.side_effect = JiraAuthError("401 invalid token")
    mock_instance.close = MagicMock()
    return mock_instance


def jira_client_transient_fail():
    """A JiraClient mock instance whose validate() raises JiraTransientError."""
    from src.services.jira_client import JiraTransientError

    mock_instance = MagicMock()
    mock_instance.validate.side_effect = JiraTransientError("503 upstream error")
    mock_instance.close = MagicMock()
    return mock_instance


# ──────────────────────────── Fixtures ────────────────────────────────────────

@pytest.fixture
def owner_user(db: Session, test_organization: Organization) -> User:
    user = User(
        email="jira_owner@test.com",
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
        email="jira_member@test.com",
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
    """An organization on the Free plan — the jira_integration feature must be unlocked here."""
    org = Organization(name="Free Jira Co", plan="free")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


@pytest.fixture
def free_owner_user(db: Session, free_organization: Organization) -> User:
    user = User(
        email="free_jira_owner@test.com",
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
    payload = {"site_url": SITE_URL, "email": EMAIL, "api_token": API_TOKEN}
    payload.update(overrides)
    return payload


# ──────────────────────────── POST /connect ───────────────────────────────────

class TestConnectEndpoint:
    def test_connect_valid_token_returns_200_with_expected_fields(self, client, owner_headers):
        with _dns(), patch("src.api.routes.jira_integration.JiraClient", return_value=jira_client_ok()):
            with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
                resp = client.post(
                    "/api/v1/integrations/jira/connect",
                    json=_connect_payload(),
                    headers=owner_headers,
                )
        assert resp.status_code == 200
        body = resp.json()
        assert body["connected"] is True
        assert body["site_url"] == SITE_URL
        assert body["email"] == EMAIL
        assert body["token_hint"] is not None
        assert body["account_id"] == "5b10a2844c20165700ede21g"
        assert body["display_name"] == "Jane Operator"

    def test_connect_response_never_contains_api_token(self, client, owner_headers):
        with _dns(), patch("src.api.routes.jira_integration.JiraClient", return_value=jira_client_ok()):
            with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
                resp = client.post(
                    "/api/v1/integrations/jira/connect",
                    json=_connect_payload(),
                    headers=owner_headers,
                )
        body = resp.json()
        assert "api_token" not in body
        assert API_TOKEN not in str(body)

    def test_connect_stores_encrypted_token_not_plaintext(
        self, client, db, test_organization, owner_headers
    ):
        with _dns(), patch("src.api.routes.jira_integration.JiraClient", return_value=jira_client_ok()):
            with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
                resp = client.post(
                    "/api/v1/integrations/jira/connect",
                    json=_connect_payload(),
                    headers=owner_headers,
                )
        assert resp.status_code == 200
        db.expire_all()
        row = db.query(JiraIntegration).filter_by(organization_id=test_organization.id).first()
        assert row is not None
        assert row.api_token != API_TOKEN, "Token must be encrypted at rest"
        with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
            from src.utils.encryption import decrypt_api_key
            assert decrypt_api_key(row.api_token) == API_TOKEN

    def test_connect_invalid_token_returns_422_and_persists_no_row(
        self, client, db, test_organization, owner_headers
    ):
        with _dns(), patch("src.api.routes.jira_integration.JiraClient", return_value=jira_client_auth_fail()):
            with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
                resp = client.post(
                    "/api/v1/integrations/jira/connect",
                    json=_connect_payload(),
                    headers=owner_headers,
                )
        assert resp.status_code == 422
        db.expire_all()
        row = db.query(JiraIntegration).filter_by(organization_id=test_organization.id).first()
        assert row is None

    def test_connect_transient_error_returns_502(self, client, owner_headers):
        with _dns(), patch("src.api.routes.jira_integration.JiraClient", return_value=jira_client_transient_fail()):
            with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
                resp = client.post(
                    "/api/v1/integrations/jira/connect",
                    json=_connect_payload(),
                    headers=owner_headers,
                )
        assert resp.status_code == 502

    def test_connect_missing_encryption_key_returns_422_not_500(self, client, owner_headers):
        with (
            _dns(),
            patch("src.api.routes.jira_integration.JiraClient", return_value=jira_client_ok()),
            patch(
                "src.api.routes.jira_integration.encrypt_api_key",
                side_effect=ValueError("LLM_ENCRYPTION_KEY environment variable is not set"),
            ),
        ):
            resp = client.post(
                "/api/v1/integrations/jira/connect",
                json=_connect_payload(),
                headers=owner_headers,
            )
        assert resp.status_code == 422
        assert "LLM_ENCRYPTION_KEY" in resp.json()["detail"]

    @pytest.mark.parametrize(
        "raw_site_url",
        ["acme", "acme.atlassian.net", "https://acme.atlassian.net", "https://acme.atlassian.net/"],
    )
    def test_connect_normalizes_site_url_variants_to_canonical(
        self, client, db, test_organization, owner_headers, raw_site_url
    ):
        with _dns(), patch("src.api.routes.jira_integration.JiraClient", return_value=jira_client_ok()):
            with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
                resp = client.post(
                    "/api/v1/integrations/jira/connect",
                    json=_connect_payload(site_url=raw_site_url),
                    headers=owner_headers,
                )
        assert resp.status_code == 200
        assert resp.json()["site_url"] == SITE_URL
        db.expire_all()
        row = db.query(JiraIntegration).filter_by(organization_id=test_organization.id).first()
        assert row.site_url == SITE_URL

    def test_connect_rejects_non_atlassian_host(self, client, owner_headers):
        with _dns(), patch("src.api.routes.jira_integration.JiraClient", return_value=jira_client_ok()):
            with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
                resp = client.post(
                    "/api/v1/integrations/jira/connect",
                    json=_connect_payload(site_url="https://acme.example.com"),
                    headers=owner_headers,
                )
        assert resp.status_code == 422

    @pytest.mark.parametrize("private_ip", ["169.254.169.254", "10.0.0.1", "127.0.0.1"])
    def test_connect_ssrf_gate_rejects_private_resolving_host(
        self, client, owner_headers, private_ip
    ):
        with _dns(private_ip):
            with patch("src.api.routes.jira_integration.JiraClient", return_value=jira_client_ok()):
                with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
                    resp = client.post(
                        "/api/v1/integrations/jira/connect",
                        json=_connect_payload(),
                        headers=owner_headers,
                    )
        assert resp.status_code == 422

    def test_connect_ssrf_gate_allows_public_resolving_host(self, client, owner_headers):
        with _dns(PUBLIC_IP):
            with patch("src.api.routes.jira_integration.JiraClient", return_value=jira_client_ok()):
                with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
                    resp = client.post(
                        "/api/v1/integrations/jira/connect",
                        json=_connect_payload(),
                        headers=owner_headers,
                    )
        assert resp.status_code == 200

    def test_connect_reconnect_reuses_row_and_rotates_token(
        self, client, db, test_organization, owner_headers
    ):
        with _dns(), patch("src.api.routes.jira_integration.JiraClient", return_value=jira_client_ok()):
            with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
                first_resp = client.post(
                    "/api/v1/integrations/jira/connect",
                    json=_connect_payload(),
                    headers=owner_headers,
                )
        assert first_resp.status_code == 200
        db.expire_all()
        first_row = db.query(JiraIntegration).filter_by(organization_id=test_organization.id).first()
        first_id = first_row.id
        first_token_hint = first_row.token_hint

        new_token = "atlassian-rotated-token-9999"
        with _dns(), patch(
            "src.api.routes.jira_integration.JiraClient",
            return_value=jira_client_ok(account_id="new-account-id", display_name="New Name"),
        ):
            with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
                second_resp = client.post(
                    "/api/v1/integrations/jira/connect",
                    json=_connect_payload(api_token=new_token),
                    headers=owner_headers,
                )
        assert second_resp.status_code == 200

        db.expire_all()
        rows = db.query(JiraIntegration).filter_by(organization_id=test_organization.id).all()
        assert len(rows) == 1, "Unique constraint must hold — reconnect must not create a 2nd row"
        row = rows[0]
        assert row.id == first_id
        assert row.is_active is True
        assert row.token_hint != first_token_hint
        assert row.token_hint == "...9999"
        from src.utils.encryption import decrypt_api_key
        with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
            assert decrypt_api_key(row.api_token) == new_token


# ──────────────────────────── GET /status ──────────────────────────────────────

class TestStatusEndpoint:
    def test_status_disconnected_when_no_integration(self, client, owner_headers):
        resp = client.get("/api/v1/integrations/jira/status", headers=owner_headers)
        assert resp.status_code == 200
        assert resp.json()["connected"] is False

    def test_status_connected_returns_full_status(
        self, client, db, test_organization, owner_headers
    ):
        from datetime import datetime
        db.add(JiraIntegration(
            organization_id=test_organization.id,
            site_url=SITE_URL,
            email=EMAIL,
            api_token="encrypted-blob",
            token_hint="...wxyz",
            account_id="acc-1",
            display_name="Display Name",
            is_active=True,
            connected_at=datetime.utcnow(),
        ))
        db.commit()

        resp = client.get("/api/v1/integrations/jira/status", headers=owner_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["connected"] is True
        assert body["site_url"] == SITE_URL
        assert body["email"] == EMAIL
        assert body["token_hint"] == "...wxyz"
        assert body["account_id"] == "acc-1"
        assert body["display_name"] == "Display Name"
        assert "api_token" not in body
        assert "encrypted-blob" not in str(body)

    def test_status_requires_auth(self, client):
        resp = client.get("/api/v1/integrations/jira/status")
        assert resp.status_code == 403


# ──────────────────────────── DELETE /disconnect ───────────────────────────────

class TestDisconnectEndpoint:
    def test_disconnect_sets_inactive(self, client, db, test_organization, owner_headers):
        from datetime import datetime
        db.add(JiraIntegration(
            organization_id=test_organization.id,
            site_url=SITE_URL,
            email=EMAIL,
            api_token="encrypted-blob",
            is_active=True,
            connected_at=datetime.utcnow(),
        ))
        db.commit()

        resp = client.delete("/api/v1/integrations/jira/disconnect", headers=owner_headers)
        assert resp.status_code == 200
        db.expire_all()
        row = db.query(JiraIntegration).filter_by(organization_id=test_organization.id).first()
        assert row.is_active is False

    def test_disconnect_preserves_feedback_jira_issue_rows(
        self, client, db, test_organization, owner_headers, test_feedback
    ):
        from datetime import datetime
        db.add(JiraIntegration(
            organization_id=test_organization.id,
            site_url=SITE_URL,
            email=EMAIL,
            api_token="encrypted-blob",
            is_active=True,
            connected_at=datetime.utcnow(),
        ))
        issue = FeedbackJiraIssue(
            organization_id=test_organization.id,
            feedback_id=test_feedback.id,
            jira_issue_id="10001",
            jira_issue_key="ENG-142",
            jira_issue_url="https://acme.atlassian.net/browse/ENG-142",
            jira_issue_title="Some bug",
        )
        db.add(issue)
        db.commit()
        issue_id = issue.id

        resp = client.delete("/api/v1/integrations/jira/disconnect", headers=owner_headers)
        assert resp.status_code == 200

        db.expire_all()
        preserved = db.query(FeedbackJiraIssue).filter_by(id=issue_id).first()
        assert preserved is not None, "FeedbackJiraIssue rows must be preserved on disconnect"

    def test_disconnect_nonexistent_returns_404(self, client, owner_headers):
        resp = client.delete("/api/v1/integrations/jira/disconnect", headers=owner_headers)
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
        db.add(JiraIntegration(
            organization_id=test_organization.id,
            site_url=SITE_URL,
            email=EMAIL,
            api_token=encrypted,
            is_active=True,
            connected_at=datetime.utcnow(),
        ))
        db.commit()

        with patch("src.api.routes.jira_integration.JiraClient", return_value=jira_client_ok()):
            with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
                resp = client.post("/api/v1/integrations/jira/test", headers=owner_headers)
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_test_with_invalid_stored_token_returns_failure_never_500(
        self, client, db, test_organization, owner_headers
    ):
        from datetime import datetime
        # Malformed ciphertext -> decrypt_api_key raises; route must swallow it.
        db.add(JiraIntegration(
            organization_id=test_organization.id,
            site_url=SITE_URL,
            email=EMAIL,
            api_token="not-a-valid-fernet-token",
            is_active=True,
            connected_at=datetime.utcnow(),
        ))
        db.commit()

        with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
            resp = client.post("/api/v1/integrations/jira/test", headers=owner_headers)
        assert resp.status_code == 200
        assert resp.json()["success"] is False

    def test_test_with_auth_error_returns_failure_never_500(
        self, client, db, test_organization, owner_headers
    ):
        from datetime import datetime
        with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
            from src.utils.encryption import encrypt_api_key
            encrypted = encrypt_api_key(API_TOKEN)
        db.add(JiraIntegration(
            organization_id=test_organization.id,
            site_url=SITE_URL,
            email=EMAIL,
            api_token=encrypted,
            is_active=True,
            connected_at=datetime.utcnow(),
        ))
        db.commit()

        with patch("src.api.routes.jira_integration.JiraClient", return_value=jira_client_auth_fail()):
            with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
                resp = client.post("/api/v1/integrations/jira/test", headers=owner_headers)
        assert resp.status_code == 200
        assert resp.json()["success"] is False

    def test_test_without_connection_returns_400(self, client, owner_headers):
        resp = client.post("/api/v1/integrations/jira/test", headers=owner_headers)
        assert resp.status_code == 400


# ──────────────────────────── RBAC ─────────────────────────────────────────────

class TestRBAC:
    def test_connect_member_gets_403(self, client, member_headers):
        resp = client.post(
            "/api/v1/integrations/jira/connect",
            json=_connect_payload(),
            headers=member_headers,
        )
        assert resp.status_code == 403

    def test_status_member_gets_403(self, client, member_headers):
        resp = client.get("/api/v1/integrations/jira/status", headers=member_headers)
        assert resp.status_code == 403

    def test_disconnect_member_gets_403(self, client, member_headers):
        resp = client.delete("/api/v1/integrations/jira/disconnect", headers=member_headers)
        assert resp.status_code == 403

    def test_test_member_gets_403(self, client, member_headers):
        resp = client.post("/api/v1/integrations/jira/test", headers=member_headers)
        assert resp.status_code == 403


# ──────────────────────────── Free-plan unlocked ───────────────────────────────

class TestFreePlanUnlocked:
    """jira_integration must work end-to-end for an org on the Free plan."""

    def test_connect_status_disconnect_test_all_work_on_free_plan(
        self, client, db, free_organization, free_owner_headers
    ):
        # connect
        with _dns(), patch("src.api.routes.jira_integration.JiraClient", return_value=jira_client_ok()):
            with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
                connect_resp = client.post(
                    "/api/v1/integrations/jira/connect",
                    json=_connect_payload(),
                    headers=free_owner_headers,
                )
        assert connect_resp.status_code == 200
        assert connect_resp.json()["connected"] is True

        # status
        status_resp = client.get("/api/v1/integrations/jira/status", headers=free_owner_headers)
        assert status_resp.status_code == 200
        assert status_resp.json()["connected"] is True

        # test
        with patch("src.api.routes.jira_integration.JiraClient", return_value=jira_client_ok()):
            with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
                test_resp = client.post("/api/v1/integrations/jira/test", headers=free_owner_headers)
        assert test_resp.status_code == 200
        assert test_resp.json()["success"] is True

        # disconnect
        disconnect_resp = client.delete(
            "/api/v1/integrations/jira/disconnect", headers=free_owner_headers
        )
        assert disconnect_resp.status_code == 200

        db.expire_all()
        row = db.query(JiraIntegration).filter_by(organization_id=free_organization.id).first()
        assert row.is_active is False


def test_jira_status_route_is_registered(client, owner_headers):
    """Endpoint must be reachable — 403/200 is fine, 404 is not."""
    resp = client.get("/api/v1/integrations/jira/status", headers=owner_headers)
    assert resp.status_code != 404, "Route not registered in main.py"
