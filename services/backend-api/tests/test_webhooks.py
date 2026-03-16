"""
Tests for custom webhook endpoints (M3.1).

TDD approach: each test is written first, then the implementation makes it pass.
"""

import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.models.user import User
from src.models.organization import Organization
from src.models.webhook_endpoint import WebhookEndpoint
from src.models.webhook_delivery import WebhookDelivery
from src.api.auth import hash_password, create_access_token

# ---------------------------------------------------------------------------
# Set a test encryption key so Fernet works without the real env
# ---------------------------------------------------------------------------
os.environ.setdefault(
    "LLM_ENCRYPTION_KEY",
    "YWJjZGVmZ2hpamtsbW5vcHFyc3R1dnd4eXoxMjM0NTY="  # valid 32-byte Fernet key (base64)
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def member_user(db: Session, test_organization: Organization) -> User:
    user = User(
        email="member@example.com",
        password_hash=hash_password("password123"),
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
def free_org(db: Session) -> Organization:
    org = Organization(name="Free Org", plan="free")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


@pytest.fixture
def free_user(db: Session, free_org: Organization) -> User:
    user = User(
        email="free@example.com",
        password_hash=hash_password("password123"),
        organization_id=free_org.id,
        role="admin",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def free_headers(free_user: User) -> dict:
    token = create_access_token({
        "user_id": free_user.id,
        "organization_id": free_user.organization_id,
        "role": free_user.role,
    })
    return {"Authorization": f"Bearer {token}"}


# Convenience alias: the conftest `client` + `auth_headers` fixtures give us
# an admin user on a Pro org — that is our "authorized_client" equivalent.
@pytest.fixture
def authorized_client(client: TestClient, auth_headers: dict):
    """TestClient pre-loaded with admin auth headers on a Pro org."""
    client.headers.update(auth_headers)
    return client


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

VALID_WEBHOOK = {
    "name": "My Webhook",
    "url": "https://example.com/hook",
    "events": ["feedback.created"],
    "retry_mode": "fire_and_forget",
}


# ===========================================================================
# Test 1: List webhooks – empty
# ===========================================================================

class TestListWebhooks:
    def test_list_webhooks_empty(self, authorized_client: TestClient):
        response = authorized_client.get("/api/v1/webhooks")
        assert response.status_code == 200
        data = response.json()
        assert data["webhooks"] == []
        assert data["limit"] == 5   # Pro plan limit
        assert data["count"] == 0

    def test_list_webhooks_requires_auth(self, client: TestClient):
        response = client.get("/api/v1/webhooks")
        assert response.status_code == 403


# ===========================================================================
# Test 2: Create webhook
# ===========================================================================

class TestCreateWebhook:
    def test_create_webhook(self, authorized_client: TestClient):
        response = authorized_client.post("/api/v1/webhooks", json=VALID_WEBHOOK)
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "My Webhook"
        assert data["url"] == "https://example.com/hook"
        assert data["events"] == ["feedback.created"]
        assert data["retry_mode"] == "fire_and_forget"
        assert data["is_active"] is True
        # Signing secret is shown only on create
        assert "signing_secret" in data
        assert len(data["signing_secret"]) > 0

    def test_create_webhook_default_events(self, authorized_client: TestClient):
        """Events field defaults to empty list if not provided."""
        response = authorized_client.post("/api/v1/webhooks", json={
            "name": "No Events",
            "url": "https://example.com/hook2",
        })
        assert response.status_code == 201
        assert response.json()["events"] == []

    def test_create_webhook_requires_auth(self, client: TestClient):
        response = client.post("/api/v1/webhooks", json=VALID_WEBHOOK)
        assert response.status_code == 403


# ===========================================================================
# Test 3: Get webhook by ID
# ===========================================================================

class TestGetWebhook:
    def test_get_webhook(self, authorized_client: TestClient):
        create_resp = authorized_client.post("/api/v1/webhooks", json=VALID_WEBHOOK)
        assert create_resp.status_code == 201
        wh_id = create_resp.json()["id"]

        response = authorized_client.get(f"/api/v1/webhooks/{wh_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == wh_id
        assert data["name"] == "My Webhook"
        # Signing secret is masked on GET
        assert data.get("signing_secret") == "***"

    def test_get_webhook_not_found(self, authorized_client: TestClient):
        response = authorized_client.get("/api/v1/webhooks/999999")
        assert response.status_code == 404

    def test_get_webhook_cross_org_isolation(
        self, authorized_client: TestClient, client: TestClient, free_headers: dict
    ):
        """Org A cannot read Org B's webhook."""
        create_resp = authorized_client.post("/api/v1/webhooks", json=VALID_WEBHOOK)
        wh_id = create_resp.json()["id"]

        response = client.get(f"/api/v1/webhooks/{wh_id}", headers=free_headers)
        assert response.status_code == 404


# ===========================================================================
# Test 4: Update webhook
# ===========================================================================

class TestUpdateWebhook:
    def test_update_webhook(self, authorized_client: TestClient):
        create_resp = authorized_client.post("/api/v1/webhooks", json=VALID_WEBHOOK)
        wh_id = create_resp.json()["id"]

        response = authorized_client.put(f"/api/v1/webhooks/{wh_id}", json={
            "name": "Updated Name",
            "events": ["feedback.urgent"],
        })
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Name"
        assert data["events"] == ["feedback.urgent"]

    def test_update_webhook_not_found(self, authorized_client: TestClient):
        response = authorized_client.put("/api/v1/webhooks/999999", json={"name": "X"})
        assert response.status_code == 404


# ===========================================================================
# Test 5: Delete webhook
# ===========================================================================

class TestDeleteWebhook:
    def test_delete_webhook(self, authorized_client: TestClient):
        create_resp = authorized_client.post("/api/v1/webhooks", json=VALID_WEBHOOK)
        wh_id = create_resp.json()["id"]

        response = authorized_client.delete(f"/api/v1/webhooks/{wh_id}")
        assert response.status_code == 204

        # Confirm it's gone
        get_resp = authorized_client.get(f"/api/v1/webhooks/{wh_id}")
        assert get_resp.status_code == 404

    def test_delete_webhook_not_found(self, authorized_client: TestClient):
        response = authorized_client.delete("/api/v1/webhooks/999999")
        assert response.status_code == 404


# ===========================================================================
# Test 6: Test webhook (sends sample payload)
# ===========================================================================

class TestTestWebhook:
    def test_test_webhook_returns_result(
        self, authorized_client: TestClient, monkeypatch
    ):
        """POST /webhooks/{id}/test returns delivery result fields."""
        create_resp = authorized_client.post("/api/v1/webhooks", json=VALID_WEBHOOK)
        wh_id = create_resp.json()["id"]

        # Monkeypatch the HTTP call so we don't need a real server
        import src.api.routes.webhooks as wh_module

        def fake_send_test(webhook, db):
            return {"status": "sent", "response_code": 200, "latency_ms": 42, "error": None}

        monkeypatch.setattr(wh_module, "_send_test_delivery", fake_send_test)

        response = authorized_client.post(f"/api/v1/webhooks/{wh_id}/test")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "response_code" in data
        assert "latency_ms" in data

    def test_test_webhook_not_found(self, authorized_client: TestClient):
        response = authorized_client.post("/api/v1/webhooks/999999/test")
        assert response.status_code == 404


# ===========================================================================
# Test 7: Rotate signing secret
# ===========================================================================

class TestRotateSecret:
    def test_rotate_signing_secret(self, authorized_client: TestClient):
        create_resp = authorized_client.post("/api/v1/webhooks", json=VALID_WEBHOOK)
        original_secret = create_resp.json()["signing_secret"]
        wh_id = create_resp.json()["id"]

        response = authorized_client.post(f"/api/v1/webhooks/{wh_id}/rotate-secret")
        assert response.status_code == 200
        data = response.json()
        assert "signing_secret" in data
        # New secret must differ from the original
        assert data["signing_secret"] != original_secret

    def test_rotate_secret_not_found(self, authorized_client: TestClient):
        response = authorized_client.post("/api/v1/webhooks/999999/rotate-secret")
        assert response.status_code == 404


# ===========================================================================
# Test 8: List deliveries – empty
# ===========================================================================

class TestListDeliveries:
    def test_list_deliveries_empty(self, authorized_client: TestClient):
        create_resp = authorized_client.post("/api/v1/webhooks", json=VALID_WEBHOOK)
        wh_id = create_resp.json()["id"]

        response = authorized_client.get(f"/api/v1/webhooks/{wh_id}/deliveries")
        assert response.status_code == 200
        data = response.json()
        assert "deliveries" in data
        assert data["deliveries"] == []

    def test_list_deliveries_not_found(self, authorized_client: TestClient):
        response = authorized_client.get("/api/v1/webhooks/999999/deliveries")
        assert response.status_code == 404


# ===========================================================================
# Test 9: Plan limit enforcement
# ===========================================================================

class TestPlanLimitEnforcement:
    def test_reject_when_at_limit(
        self, client: TestClient, free_headers: dict, free_org: Organization, db: Session
    ):
        """Free plan allows max 2 webhooks; 3rd create must return 402."""
        # Create 2 webhooks to exhaust the free limit
        for i in range(2):
            resp = client.post(
                "/api/v1/webhooks",
                json={**VALID_WEBHOOK, "name": f"Hook {i}", "url": f"https://example.com/h{i}"},
                headers=free_headers,
            )
            assert resp.status_code == 201, f"Expected 201 on webhook {i}, got {resp.status_code}: {resp.text}"

        # 3rd create should fail
        resp = client.post(
            "/api/v1/webhooks",
            json={**VALID_WEBHOOK, "name": "Over Limit", "url": "https://example.com/over"},
            headers=free_headers,
        )
        assert resp.status_code == 402
        data = resp.json()
        assert data["detail"]["error"] == "webhook_limit_exceeded"

    def test_list_shows_correct_limit_for_plan(
        self, client: TestClient, free_headers: dict
    ):
        """Free plan list response includes limit=2."""
        response = client.get("/api/v1/webhooks", headers=free_headers)
        assert response.status_code == 200
        assert response.json()["limit"] == 2


# ===========================================================================
# Test 10: URL must be HTTPS
# ===========================================================================

class TestUrlValidation:
    def test_reject_http_url(self, authorized_client: TestClient):
        response = authorized_client.post("/api/v1/webhooks", json={
            **VALID_WEBHOOK,
            "url": "http://example.com/hook",
        })
        assert response.status_code == 422
        errors = response.json()["detail"]
        assert any("https" in str(e).lower() for e in errors)

    def test_reject_non_url(self, authorized_client: TestClient):
        response = authorized_client.post("/api/v1/webhooks", json={
            **VALID_WEBHOOK,
            "url": "not-a-url",
        })
        assert response.status_code == 422


# ===========================================================================
# Test 11: Events validation
# ===========================================================================

class TestEventsValidation:
    def test_reject_invalid_event(self, authorized_client: TestClient):
        response = authorized_client.post("/api/v1/webhooks", json={
            **VALID_WEBHOOK,
            "events": ["feedback.created", "invalid.event"],
        })
        assert response.status_code == 422

    def test_accept_all_valid_events(self, authorized_client: TestClient):
        response = authorized_client.post("/api/v1/webhooks", json={
            **VALID_WEBHOOK,
            "url": "https://example.com/all-events",
            "events": [
                "feedback.created",
                "feedback.analyzed",
                "feedback.status_changed",
                "feedback.urgent",
                "feedback.category_match",
            ],
        })
        assert response.status_code == 201


# ===========================================================================
# Test 12: category_filters only allowed with feedback.category_match
# ===========================================================================

class TestCategoryFilters:
    def test_category_filters_require_category_match_event(self, authorized_client: TestClient):
        response = authorized_client.post("/api/v1/webhooks", json={
            **VALID_WEBHOOK,
            "events": ["feedback.created"],
            "category_filters": ["billing", "auth"],
        })
        assert response.status_code == 422
        detail = str(response.json()["detail"])
        assert "category_match" in detail.lower()

    def test_category_filters_allowed_with_category_match(self, authorized_client: TestClient):
        response = authorized_client.post("/api/v1/webhooks", json={
            **VALID_WEBHOOK,
            "url": "https://example.com/cat",
            "events": ["feedback.category_match"],
            "category_filters": ["billing", "auth"],
        })
        assert response.status_code == 201


# ===========================================================================
# Test 13: Custom headers limit
# ===========================================================================

class TestCustomHeadersLimit:
    def _make_headers_payload(self, count: int) -> dict:
        return {k: f"value{k}" for k in [f"X-Header-{i}" for i in range(count)]}

    def test_free_plan_max_2_headers(
        self, client: TestClient, free_headers: dict
    ):
        """Free plan allows max 2 custom headers."""
        response = client.post("/api/v1/webhooks", json={
            **VALID_WEBHOOK,
            "custom_headers": self._make_headers_payload(3),
        }, headers=free_headers)
        assert response.status_code == 422
        detail = str(response.json()["detail"])
        assert "header" in detail.lower()

    def test_free_plan_accepts_2_headers(
        self, client: TestClient, free_headers: dict
    ):
        response = client.post("/api/v1/webhooks", json={
            **VALID_WEBHOOK,
            "url": "https://example.com/free-hdr",
            "custom_headers": self._make_headers_payload(2),
        }, headers=free_headers)
        assert response.status_code == 201

    def test_pro_plan_max_5_headers(self, authorized_client: TestClient):
        """Pro plan allows max 5 custom headers."""
        response = authorized_client.post("/api/v1/webhooks", json={
            **VALID_WEBHOOK,
            "url": "https://example.com/pro-hdr",
            "custom_headers": self._make_headers_payload(5),
        })
        assert response.status_code == 201

    def test_pro_plan_rejects_6_headers(self, authorized_client: TestClient):
        response = authorized_client.post("/api/v1/webhooks", json={
            **VALID_WEBHOOK,
            "custom_headers": self._make_headers_payload(6),
        })
        assert response.status_code == 422


# ===========================================================================
# Test 14: Admin/owner required for mutating endpoints
# ===========================================================================

class TestRBAC:
    def test_member_cannot_create_webhook(
        self, client: TestClient, member_headers: dict
    ):
        response = client.post("/api/v1/webhooks", json=VALID_WEBHOOK, headers=member_headers)
        assert response.status_code == 403

    def test_member_cannot_update_webhook(
        self, authorized_client: TestClient, client: TestClient, member_headers: dict
    ):
        create_resp = authorized_client.post("/api/v1/webhooks", json=VALID_WEBHOOK)
        wh_id = create_resp.json()["id"]

        response = client.put(
            f"/api/v1/webhooks/{wh_id}", json={"name": "Hack"}, headers=member_headers
        )
        assert response.status_code == 403

    def test_member_cannot_delete_webhook(
        self, authorized_client: TestClient, client: TestClient, member_headers: dict
    ):
        create_resp = authorized_client.post("/api/v1/webhooks", json=VALID_WEBHOOK)
        wh_id = create_resp.json()["id"]

        response = client.delete(f"/api/v1/webhooks/{wh_id}", headers=member_headers)
        assert response.status_code == 403

    def test_member_can_list_webhooks(
        self, authorized_client: TestClient, client: TestClient,
        member_headers: dict, test_organization: Organization
    ):
        """Members can read (GET) but not write."""
        # The member_user shares the same test_organization as the admin
        response = client.get("/api/v1/webhooks", headers=member_headers)
        assert response.status_code == 200

    def test_member_cannot_rotate_secret(
        self, authorized_client: TestClient, client: TestClient, member_headers: dict
    ):
        create_resp = authorized_client.post("/api/v1/webhooks", json=VALID_WEBHOOK)
        wh_id = create_resp.json()["id"]

        response = client.post(
            f"/api/v1/webhooks/{wh_id}/rotate-secret", headers=member_headers
        )
        assert response.status_code == 403
