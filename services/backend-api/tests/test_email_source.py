"""Tests for email feedback source creation and plan gating."""
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.models.organization import Organization
from src.models.user import User
from src.models.feedback_source import FeedbackSource
from src.api.auth import hash_password, create_access_token


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def free_organization(db: Session) -> Organization:
    """Organization on Free plan."""
    org = Organization(name="Free Org", plan="free")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


@pytest.fixture
def free_user(db: Session, free_organization: Organization) -> User:
    user = User(
        email="free@example.com",
        password_hash=hash_password("password123"),
        organization_id=free_organization.id,
        role="admin",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def free_auth_headers(free_user: User) -> dict:
    token = create_access_token({
        "user_id": free_user.id,
        "organization_id": free_user.organization_id,
        "role": free_user.role,
    })
    return {"Authorization": f"Bearer {token}"}


# ============================================================================
# Plan Gating Tests
# ============================================================================

class TestEmailPlanGating:
    """email_integration feature should be gated to Pro+."""

    def test_email_feature_available_on_pro(self):
        from src.config.plans import has_feature
        assert has_feature("pro", "email_integration") is True

    def test_email_feature_available_on_business(self):
        from src.config.plans import has_feature
        assert has_feature("business", "email_integration") is True

    def test_email_feature_available_on_enterprise(self):
        from src.config.plans import has_feature
        assert has_feature("enterprise", "email_integration") is True

    def test_email_feature_not_available_on_free(self):
        from src.config.plans import has_feature
        assert has_feature("free", "email_integration") is False

    def test_email_feature_minimum_plan_is_pro(self):
        from src.config.plans import get_plan_for_feature
        assert get_plan_for_feature("email_integration") == "pro"


# ============================================================================
# Email Source Creation Tests
# ============================================================================

class TestEmailSourceCreation:
    """Tests for POST /api/v1/feedback-sources with type=email."""

    def test_create_email_source_on_pro_plan(
        self,
        client: TestClient,
        auth_headers: dict,
        db: Session,
        test_organization: Organization,
    ):
        """Pro plan users should be able to create an email source."""
        response = client.post(
            "/api/v1/feedback-sources/",
            json={
                "source_type": "email",
                "name": "Support Inbox Forwarding",
            },
            headers=auth_headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["source_type"] == "email"
        assert data["name"] == "Support Inbox Forwarding"
        assert "inbound_address" in data["provider_config"]
        assert data["provider_config"]["inbound_address"].endswith("@rereflect.ca")
        assert data["provider_config"]["inbound_address"].startswith("feedback-")
        assert data["is_active"] is True

    def test_inbound_address_format(
        self,
        client: TestClient,
        auth_headers: dict,
    ):
        """Inbound address should follow format: feedback-{8chars}@rereflect.ca."""
        response = client.post(
            "/api/v1/feedback-sources/",
            json={"source_type": "email", "name": "Test"},
            headers=auth_headers,
        )
        assert response.status_code == 201
        addr = response.json()["provider_config"]["inbound_address"]
        prefix, domain = addr.split("@")
        assert domain == "rereflect.ca"
        assert prefix.startswith("feedback-")
        hash_part = prefix[len("feedback-"):]
        assert len(hash_part) == 8

    def test_unique_addresses_per_source(
        self,
        client: TestClient,
        auth_headers: dict,
    ):
        """Each email source should get a unique inbound address."""
        resp1 = client.post(
            "/api/v1/feedback-sources/",
            json={"source_type": "email", "name": "Source 1"},
            headers=auth_headers,
        )
        resp2 = client.post(
            "/api/v1/feedback-sources/",
            json={"source_type": "email", "name": "Source 2"},
            headers=auth_headers,
        )
        assert resp1.status_code == 201
        assert resp2.status_code == 201
        addr1 = resp1.json()["provider_config"]["inbound_address"]
        addr2 = resp2.json()["provider_config"]["inbound_address"]
        assert addr1 != addr2

    def test_email_source_no_integration_needed(
        self,
        client: TestClient,
        auth_headers: dict,
    ):
        """Email sources should not require an integration_id."""
        response = client.post(
            "/api/v1/feedback-sources/",
            json={
                "source_type": "email",
                "name": "Email Source",
                "integration_id": None,
            },
            headers=auth_headers,
        )
        assert response.status_code == 201
        assert response.json()["integration_id"] is None

    def test_create_email_source_blocked_on_free_plan(
        self,
        client: TestClient,
        free_auth_headers: dict,
    ):
        """Free plan should be blocked from creating email sources."""
        response = client.post(
            "/api/v1/feedback-sources/",
            json={"source_type": "email", "name": "Blocked"},
            headers=free_auth_headers,
        )
        assert response.status_code == 403
        data = response.json()
        assert data["detail"]["error"] == "feature_not_available"
        assert data["detail"]["feature"] == "email_integration"


# ============================================================================
# Source Types Endpoint
# ============================================================================

class TestSourceTypes:
    """Tests for GET /api/v1/feedback-sources/types."""

    def test_email_type_is_available(self, client: TestClient, auth_headers: dict):
        """Email should be listed as an available source type."""
        response = client.get(
            "/api/v1/feedback-sources/types",
            headers=auth_headers,
        )
        assert response.status_code == 200
        types = response.json()
        email_type = next(t for t in types if t["type"] == "email")
        assert email_type["available"] is True
        assert email_type["requires_integration"] is False
