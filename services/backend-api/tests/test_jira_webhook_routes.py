"""
TDD tests for Phase 2 of the jira-webhook aspect (status-sync-realtime-mapping
PRD): the enable/disable/secret-reveal control surface for the inbound
real-time Jira webhook.

Covers:
  - POST   /api/v1/integrations/jira/webhook/enable   (admin/owner)
  - DELETE /api/v1/integrations/jira/webhook           (admin/owner)
  - GET    /api/v1/integrations/jira/status            (extended: webhook_enabled,
                                                          never returns the secret)

Mirrors the fixture/test style of tests/test_jira_status_sync_routes.py
(admin/owner/member/other-org fixtures) and the R6 fail-closed pattern of
zendesk_integration.py's connect route (missing LLM_ENCRYPTION_KEY -> 422,
never a 500).
"""
import os
from datetime import datetime
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.api.auth import create_access_token, hash_password
from src.models.jira_integration import JiraIntegration
from src.models.organization import Organization
from src.models.user import User
from src.utils.encryption import decrypt_api_key, encrypt_api_key

SITE_URL = "https://acme.atlassian.net"
EMAIL = "operator@acme.com"

# Valid 32-byte Fernet key for tests only. NOT used in production.
TEST_FERNET_KEY = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="


@pytest.fixture(autouse=True)
def _fernet_key_env():
    with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
        yield


# ──────────────────────────── Fixtures ────────────────────────────────────────


@pytest.fixture
def owner_user(db: Session, test_organization: Organization) -> User:
    user = User(
        email="jwh_owner@test.com",
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
        email="jwh_member@test.com",
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
def active_integration(db: Session, test_organization: Organization) -> JiraIntegration:
    integ = JiraIntegration(
        organization_id=test_organization.id,
        site_url=SITE_URL,
        email=EMAIL,
        api_token=encrypt_api_key("plain-api-token"),
        token_hint="...wxyz",
        is_active=True,
        connected_at=datetime.utcnow(),
    )
    db.add(integ)
    db.commit()
    db.refresh(integ)
    return integ


@pytest.fixture
def integration_with_webhook(db: Session, active_integration: JiraIntegration) -> JiraIntegration:
    active_integration.webhook_secret = encrypt_api_key("existing-plaintext-secret")
    db.commit()
    db.refresh(active_integration)
    return active_integration


# ──────────────────────────── POST /webhook/enable ─────────────────────────────


class TestJiraWebhookEnable:
    def test_owner_can_enable_webhook_and_receives_secret_once(
        self, client: TestClient, active_integration: JiraIntegration, owner_headers: dict, db: Session
    ):
        resp = client.post("/api/v1/integrations/jira/webhook/enable", headers=owner_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert "webhook_secret" in body
        assert isinstance(body["webhook_secret"], str)
        assert len(body["webhook_secret"]) > 0
        assert body["webhook_url"].endswith("/api/v1/webhooks/jira/inbound")

        db.refresh(active_integration)
        assert active_integration.webhook_secret is not None
        assert decrypt_api_key(active_integration.webhook_secret) == body["webhook_secret"]

    def test_admin_can_enable_webhook(
        self, client: TestClient, db: Session, test_organization: Organization, active_integration: JiraIntegration
    ):
        admin = User(
            email="jwh_admin@test.com",
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
        resp = client.post(
            "/api/v1/integrations/jira/webhook/enable",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200

    def test_member_forbidden(
        self, client: TestClient, active_integration: JiraIntegration, member_headers: dict
    ):
        resp = client.post("/api/v1/integrations/jira/webhook/enable", headers=member_headers)
        assert resp.status_code == 403

    def test_no_integration_returns_404(self, client: TestClient, owner_headers: dict):
        resp = client.post("/api/v1/integrations/jira/webhook/enable", headers=owner_headers)
        assert resp.status_code == 404

    def test_re_enable_rotates_secret(
        self, client: TestClient, integration_with_webhook: JiraIntegration, owner_headers: dict, db: Session
    ):
        old_encrypted = integration_with_webhook.webhook_secret

        resp = client.post("/api/v1/integrations/jira/webhook/enable", headers=owner_headers)
        assert resp.status_code == 200
        new_secret = resp.json()["webhook_secret"]
        assert new_secret != "existing-plaintext-secret"

        db.refresh(integration_with_webhook)
        assert integration_with_webhook.webhook_secret != old_encrypted
        assert decrypt_api_key(integration_with_webhook.webhook_secret) == new_secret

    def test_missing_encryption_key_fails_closed_422(
        self, client: TestClient, active_integration: JiraIntegration, owner_headers: dict
    ):
        with patch.dict(os.environ, {}, clear=True):
            resp = client.post("/api/v1/integrations/jira/webhook/enable", headers=owner_headers)
        assert resp.status_code == 422
        assert resp.status_code != 500


# ──────────────────────────── DELETE /webhook ───────────────────────────────────


class TestJiraWebhookDisable:
    def test_owner_can_disable_webhook(
        self, client: TestClient, integration_with_webhook: JiraIntegration, owner_headers: dict, db: Session
    ):
        resp = client.delete("/api/v1/integrations/jira/webhook", headers=owner_headers)
        assert resp.status_code == 200
        assert resp.json()["success"] is True

        db.refresh(integration_with_webhook)
        assert integration_with_webhook.webhook_secret is None

    def test_member_forbidden(
        self, client: TestClient, integration_with_webhook: JiraIntegration, member_headers: dict
    ):
        resp = client.delete("/api/v1/integrations/jira/webhook", headers=member_headers)
        assert resp.status_code == 403

    def test_no_integration_returns_404(self, client: TestClient, owner_headers: dict):
        resp = client.delete("/api/v1/integrations/jira/webhook", headers=owner_headers)
        assert resp.status_code == 404

    def test_disable_when_never_enabled_is_idempotent_200(
        self, client: TestClient, active_integration: JiraIntegration, owner_headers: dict
    ):
        resp = client.delete("/api/v1/integrations/jira/webhook", headers=owner_headers)
        assert resp.status_code == 200


# ──────────────────────────── GET /status never leaks secret ───────────────────


class TestJiraStatusNeverLeaksWebhookSecret:
    def test_status_reports_webhook_enabled_true_without_secret(
        self, client: TestClient, integration_with_webhook: JiraIntegration, owner_headers: dict
    ):
        resp = client.get("/api/v1/integrations/jira/status", headers=owner_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["webhook_enabled"] is True
        assert "webhook_secret" not in body
        assert "existing-plaintext-secret" not in resp.text

    def test_status_reports_webhook_enabled_false_by_default(
        self, client: TestClient, active_integration: JiraIntegration, owner_headers: dict
    ):
        resp = client.get("/api/v1/integrations/jira/status", headers=owner_headers)
        assert resp.status_code == 200
        assert resp.json()["webhook_enabled"] is False

    def test_enable_response_never_leaks_secret_via_status_afterward(
        self, client: TestClient, active_integration: JiraIntegration, owner_headers: dict
    ):
        enable_resp = client.post("/api/v1/integrations/jira/webhook/enable", headers=owner_headers)
        secret = enable_resp.json()["webhook_secret"]

        status_resp = client.get("/api/v1/integrations/jira/status", headers=owner_headers)
        assert secret not in status_resp.text
