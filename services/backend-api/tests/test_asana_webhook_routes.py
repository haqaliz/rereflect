"""
TDD tests for Phase 2 of the asana-webhook aspect (status-sync-realtime-mapping
PRD): the enable/disable control surface for the inbound real-time Asana
webhook.

Covers:
  - POST   /api/v1/integrations/asana/webhook/enable   (admin/owner)
  - DELETE /api/v1/integrations/asana/webhook           (admin/owner)
  - GET    /api/v1/integrations/asana/status            (extended: webhook_enabled,
                                                          never returns the secret)

Unlike Jira (which generates its own HMAC secret locally), Asana's webhook
must be REGISTERED with Asana via `POST /webhooks` (mocked here — no real
HTTP) targeting the operator's chosen resource (v1: a project gid, reusing
the same project wiring as task creation — see spec.md R2). The handshake
secret itself is captured later, on the first inbound delivery (Phase 3) —
so /webhook/enable never returns a secret, only `webhook_url` + `webhook_gid`.

Mirrors the fixture/test style of tests/test_jira_webhook_routes.py and
tests/test_asana_status_sync_routes.py.
"""
import os
from datetime import datetime
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.api.auth import create_access_token, hash_password
from src.models.asana_integration import AsanaIntegration
from src.models.organization import Organization
from src.models.user import User
from src.utils.encryption import decrypt_api_key, encrypt_api_key

# Valid 32-byte Fernet key for tests only. NOT used in production.
TEST_FERNET_KEY = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="

RESOURCE_GID = "1200000000001"


@pytest.fixture(autouse=True)
def _fernet_key_env():
    with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
        yield


# ──────────────────────────── Fixtures ────────────────────────────────────────


@pytest.fixture
def owner_user(db: Session, test_organization: Organization) -> User:
    user = User(
        email="awh_owner@test.com",
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
        email="awh_member@test.com",
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
def active_integration(db: Session, test_organization: Organization) -> AsanaIntegration:
    integ = AsanaIntegration(
        organization_id=test_organization.id,
        api_token=encrypt_api_key("plain-pat-token"),
        token_hint="...wxyz",
        is_active=True,
        connected_at=datetime.utcnow(),
    )
    db.add(integ)
    db.commit()
    db.refresh(integ)
    return integ


@pytest.fixture
def integration_with_webhook(db: Session, active_integration: AsanaIntegration) -> AsanaIntegration:
    active_integration.webhook_gid = "1400000000001"
    active_integration.webhook_secret = encrypt_api_key("captured-handshake-secret")
    active_integration.webhook_url_token = "existing-token-before-rotation"
    db.commit()
    db.refresh(active_integration)
    return active_integration


def _mock_asana_client(create_webhook_gid="1400000000001"):
    mock_client = MagicMock()
    mock_client.create_webhook.return_value = {"gid": create_webhook_gid}
    mock_client.delete_webhook.return_value = None
    return mock_client


# ──────────────────────────── POST /webhook/enable ─────────────────────────────


class TestAsanaWebhookEnable:
    def test_owner_can_enable_webhook_and_receives_url_and_gid(
        self, client: TestClient, active_integration: AsanaIntegration, owner_headers: dict, db: Session
    ):
        mock_client = _mock_asana_client()
        with patch("src.api.routes.asana_integration.AsanaClient", return_value=mock_client):
            resp = client.post(
                "/api/v1/integrations/asana/webhook/enable",
                headers=owner_headers,
                json={"resource_gid": RESOURCE_GID},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["webhook_gid"] == "1400000000001"
        # SECURITY: the registered URL embeds an unguessable token, NEVER
        # the integration's guessable integer id.
        assert not body["webhook_url"].endswith(
            "/api/v1/webhooks/asana/inbound/" + str(active_integration.id)
        )
        assert "webhook_secret" not in body

        mock_client.create_webhook.assert_called_once()
        args, kwargs = mock_client.create_webhook.call_args
        call = {**dict(zip(["resource_gid", "target_url"], args)), **kwargs}
        assert call["resource_gid"] == RESOURCE_GID

        db.refresh(active_integration)
        assert active_integration.webhook_gid == "1400000000001"
        assert active_integration.webhook_secret is None
        # The minted webhook_url_token is persisted and matches the URL
        # segment registered with Asana (and returned to the caller).
        assert active_integration.webhook_url_token
        assert len(active_integration.webhook_url_token) >= 32
        expected_url = (
            f"/api/v1/webhooks/asana/inbound/{active_integration.webhook_url_token}"
        )
        assert body["webhook_url"].endswith(expected_url)
        assert call["target_url"].endswith(expected_url)

    def test_admin_can_enable_webhook(
        self, client: TestClient, db: Session, test_organization: Organization, active_integration: AsanaIntegration
    ):
        admin = User(
            email="awh_admin@test.com",
            password_hash=hash_password("pw"),
            organization_id=test_organization.id,
            role="admin",
        )
        db.add(admin)
        db.commit()
        db.refresh(admin)
        token = create_access_token({
            "user_id": admin.id, "organization_id": admin.organization_id, "role": admin.role,
        })
        mock_client = _mock_asana_client()
        with patch("src.api.routes.asana_integration.AsanaClient", return_value=mock_client):
            resp = client.post(
                "/api/v1/integrations/asana/webhook/enable",
                headers={"Authorization": f"Bearer {token}"},
                json={"resource_gid": RESOURCE_GID},
            )
        assert resp.status_code == 200

    def test_member_forbidden(
        self, client: TestClient, active_integration: AsanaIntegration, member_headers: dict
    ):
        resp = client.post(
            "/api/v1/integrations/asana/webhook/enable",
            headers=member_headers,
            json={"resource_gid": RESOURCE_GID},
        )
        assert resp.status_code == 403

    def test_no_integration_returns_404(self, client: TestClient, owner_headers: dict):
        resp = client.post(
            "/api/v1/integrations/asana/webhook/enable",
            headers=owner_headers,
            json={"resource_gid": RESOURCE_GID},
        )
        assert resp.status_code == 404

    def test_missing_resource_gid_422(
        self, client: TestClient, active_integration: AsanaIntegration, owner_headers: dict
    ):
        resp = client.post(
            "/api/v1/integrations/asana/webhook/enable",
            headers=owner_headers,
            json={},
        )
        assert resp.status_code == 422

    def test_re_enable_rotates_webhook_gid(
        self, client: TestClient, integration_with_webhook: AsanaIntegration, owner_headers: dict, db: Session
    ):
        mock_client = _mock_asana_client(create_webhook_gid="1400000000099")
        with patch("src.api.routes.asana_integration.AsanaClient", return_value=mock_client):
            resp = client.post(
                "/api/v1/integrations/asana/webhook/enable",
                headers=owner_headers,
                json={"resource_gid": RESOURCE_GID},
            )
        assert resp.status_code == 200
        assert resp.json()["webhook_gid"] == "1400000000099"

        db.refresh(integration_with_webhook)
        assert integration_with_webhook.webhook_gid == "1400000000099"
        # Re-enabling clears the old handshake secret -- a fresh handshake
        # is required against the newly-created webhook.
        assert integration_with_webhook.webhook_secret is None
        # Re-enabling also rotates the webhook_url_token -- the old
        # (possibly already-known) URL must stop resolving.
        assert integration_with_webhook.webhook_url_token != "existing-token-before-rotation"
        assert integration_with_webhook.webhook_url_token
        assert resp.json()["webhook_url"].endswith(
            f"/api/v1/webhooks/asana/inbound/{integration_with_webhook.webhook_url_token}"
        )

    def test_asana_auth_error_returns_403(
        self, client: TestClient, active_integration: AsanaIntegration, owner_headers: dict
    ):
        from src.services.asana_client import AsanaAuthError

        mock_client = MagicMock()
        mock_client.create_webhook.side_effect = AsanaAuthError("bad token")
        with patch("src.api.routes.asana_integration.AsanaClient", return_value=mock_client):
            resp = client.post(
                "/api/v1/integrations/asana/webhook/enable",
                headers=owner_headers,
                json={"resource_gid": RESOURCE_GID},
            )
        assert resp.status_code == 403

    def test_asana_transient_error_returns_502(
        self, client: TestClient, active_integration: AsanaIntegration, owner_headers: dict
    ):
        from src.services.asana_client import AsanaTransientError

        mock_client = MagicMock()
        mock_client.create_webhook.side_effect = AsanaTransientError("upstream down")
        with patch("src.api.routes.asana_integration.AsanaClient", return_value=mock_client):
            resp = client.post(
                "/api/v1/integrations/asana/webhook/enable",
                headers=owner_headers,
                json={"resource_gid": RESOURCE_GID},
            )
        assert resp.status_code == 502


# ──────────────────────────── DELETE /webhook ───────────────────────────────────


class TestAsanaWebhookDisable:
    def test_owner_can_disable_webhook(
        self, client: TestClient, integration_with_webhook: AsanaIntegration, owner_headers: dict, db: Session
    ):
        mock_client = _mock_asana_client()
        with patch("src.api.routes.asana_integration.AsanaClient", return_value=mock_client):
            resp = client.delete("/api/v1/integrations/asana/webhook", headers=owner_headers)
        assert resp.status_code == 200
        assert resp.json()["success"] is True

        mock_client.delete_webhook.assert_called_once_with("1400000000001")

        db.refresh(integration_with_webhook)
        assert integration_with_webhook.webhook_gid is None
        assert integration_with_webhook.webhook_secret is None

    def test_member_forbidden(
        self, client: TestClient, integration_with_webhook: AsanaIntegration, member_headers: dict
    ):
        resp = client.delete("/api/v1/integrations/asana/webhook", headers=member_headers)
        assert resp.status_code == 403

    def test_no_integration_returns_404(self, client: TestClient, owner_headers: dict):
        resp = client.delete("/api/v1/integrations/asana/webhook", headers=owner_headers)
        assert resp.status_code == 404

    def test_disable_when_never_enabled_is_idempotent_200(
        self, client: TestClient, active_integration: AsanaIntegration, owner_headers: dict
    ):
        resp = client.delete("/api/v1/integrations/asana/webhook", headers=owner_headers)
        assert resp.status_code == 200

    def test_disable_swallows_asana_not_found(
        self, client: TestClient, integration_with_webhook: AsanaIntegration, owner_headers: dict, db: Session
    ):
        """Deleting an already-gone webhook at Asana (404) must still clear
        our local columns and return 200 -- never surfaced as an error."""
        from src.services.asana_client import AsanaNotFoundError

        mock_client = MagicMock()
        mock_client.delete_webhook.side_effect = AsanaNotFoundError("gone")
        with patch("src.api.routes.asana_integration.AsanaClient", return_value=mock_client):
            resp = client.delete("/api/v1/integrations/asana/webhook", headers=owner_headers)
        assert resp.status_code == 200

        db.refresh(integration_with_webhook)
        assert integration_with_webhook.webhook_gid is None
        assert integration_with_webhook.webhook_secret is None


# ──────────────────────────── GET /status never leaks secret ───────────────────


class TestAsanaStatusNeverLeaksWebhookSecret:
    def test_status_reports_webhook_enabled_true_without_secret(
        self, client: TestClient, integration_with_webhook: AsanaIntegration, owner_headers: dict
    ):
        resp = client.get("/api/v1/integrations/asana/status", headers=owner_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["webhook_enabled"] is True
        assert "webhook_secret" not in body
        assert "captured-handshake-secret" not in resp.text

    def test_status_reports_webhook_enabled_false_when_gid_present_but_no_secret_yet(
        self, client: TestClient, active_integration: AsanaIntegration, owner_headers: dict, db: Session
    ):
        """webhook_enabled reflects handshake completion (secret captured),
        not merely that a webhook_gid was registered -- the receiver
        fail-closes on missing secret regardless of webhook_gid."""
        active_integration.webhook_gid = "1400000000001"
        db.commit()

        resp = client.get("/api/v1/integrations/asana/status", headers=owner_headers)
        assert resp.status_code == 200
        assert resp.json()["webhook_enabled"] is False

    def test_status_reports_webhook_enabled_false_by_default(
        self, client: TestClient, active_integration: AsanaIntegration, owner_headers: dict
    ):
        resp = client.get("/api/v1/integrations/asana/status", headers=owner_headers)
        assert resp.status_code == 200
        assert resp.json()["webhook_enabled"] is False
