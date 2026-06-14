"""
Tests for AI settings API endpoints.
Updated for M2.1: schema expanded with provider, models, budget.
BYOK key management moved to /api/v1/settings/ai/keys.
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
        """Should return expanded AI settings with provider and models.
        OSS pivot (A6): budget field removed from AISettingsResponse."""
        response = client.get("/api/v1/settings/ai", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["ai_analysis_enabled"] is True
        assert "default_provider" in data
        assert "models" in data
        # A6: budget field removed — verify it is absent
        assert "budget" not in data

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

    def test_admin_can_update_provider(self, client: TestClient, auth_headers: dict):
        """Admin should be able to change the default provider."""
        response = client.patch(
            "/api/v1/settings/ai",
            headers=auth_headers,
            json={"default_provider": "anthropic"},
        )
        assert response.status_code == 200
        assert response.json()["default_provider"] == "anthropic"

    def test_admin_can_update_models(self, client: TestClient, auth_headers: dict):
        """Admin should be able to change model selection per task."""
        response = client.patch(
            "/api/v1/settings/ai",
            headers=auth_headers,
            json={
                "model_categorization": "claude-haiku-4-5",
                "model_analysis": "claude-haiku-4-5",
                "model_insights": "claude-haiku-4-5",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["models"]["categorization"] == "claude-haiku-4-5"
        assert data["models"]["analysis"] == "claude-haiku-4-5"
        assert data["models"]["insights"] == "claude-haiku-4-5"

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
