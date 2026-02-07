"""
Tests for AI settings API endpoints.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.models.organization import Organization
from src.models.user import User
from src.api.auth import hash_password, create_access_token


@pytest.fixture
def owner_user(db: Session, test_organization: Organization) -> User:
    """Create an owner user."""
    user = User(
        email="owner@test.com",
        password_hash=hash_password("password123"),
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
    """Create a member user."""
    user = User(
        email="member@test.com",
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


class TestGetAISettings:
    def test_get_default_settings(self, client: TestClient, auth_headers: dict):
        """Should return default AI settings (enabled, no custom key)."""
        response = client.get("/api/v1/settings/ai", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["ai_analysis_enabled"] is True
        assert data["has_custom_key"] is False

    def test_requires_auth(self, client: TestClient):
        """Should require authentication."""
        response = client.get("/api/v1/settings/ai")
        assert response.status_code == 403


class TestUpdateAISettings:
    def test_toggle_ai_analysis(self, client: TestClient, owner_headers: dict):
        """Should toggle AI analysis on/off."""
        # Disable
        response = client.patch(
            "/api/v1/settings/ai",
            headers=owner_headers,
            json={"ai_analysis_enabled": False},
        )
        assert response.status_code == 200
        assert response.json()["ai_analysis_enabled"] is False

        # Enable
        response = client.patch(
            "/api/v1/settings/ai",
            headers=owner_headers,
            json={"ai_analysis_enabled": True},
        )
        assert response.status_code == 200
        assert response.json()["ai_analysis_enabled"] is True

    def test_admin_can_toggle(self, client: TestClient, auth_headers: dict):
        """Admin should be able to toggle AI analysis."""
        response = client.patch(
            "/api/v1/settings/ai",
            headers=auth_headers,
            json={"ai_analysis_enabled": False},
        )
        assert response.status_code == 200

    def test_member_cannot_update(self, client: TestClient, member_headers: dict):
        """Members should not be able to update AI settings."""
        response = client.patch(
            "/api/v1/settings/ai",
            headers=member_headers,
            json={"ai_analysis_enabled": False},
        )
        assert response.status_code == 403

    def test_owner_can_set_api_key(self, client: TestClient, owner_headers: dict):
        """Owner should be able to set BYOK API key."""
        response = client.patch(
            "/api/v1/settings/ai",
            headers=owner_headers,
            json={"openai_api_key": "sk-test-key-123"},
        )
        assert response.status_code == 200
        assert response.json()["has_custom_key"] is True

    def test_owner_can_remove_api_key(self, client: TestClient, owner_headers: dict, db, test_organization):
        """Owner should be able to remove BYOK API key."""
        # Set key first
        test_organization.openai_api_key = "sk-existing-key"
        db.commit()

        response = client.patch(
            "/api/v1/settings/ai",
            headers=owner_headers,
            json={"openai_api_key": ""},
        )
        assert response.status_code == 200
        assert response.json()["has_custom_key"] is False

    def test_admin_cannot_set_api_key(self, client: TestClient, auth_headers: dict):
        """Admin should NOT be able to set BYOK API key (owner only)."""
        response = client.patch(
            "/api/v1/settings/ai",
            headers=auth_headers,
            json={"openai_api_key": "sk-test-key"},
        )
        assert response.status_code == 403

    def test_persists_settings(self, client: TestClient, owner_headers: dict):
        """Settings should persist across GET requests."""
        # Update
        client.patch(
            "/api/v1/settings/ai",
            headers=owner_headers,
            json={"ai_analysis_enabled": False},
        )

        # Verify
        response = client.get("/api/v1/settings/ai", headers=owner_headers)
        assert response.json()["ai_analysis_enabled"] is False
