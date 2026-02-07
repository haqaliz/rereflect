"""
Tests for user preferences endpoints.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.models.user import User
from src.models.organization import Organization
from src.api.auth import hash_password, create_access_token


class TestGetPreferences:
    """Tests for GET /api/v1/auth/me/preferences endpoint."""

    def test_get_preferences_returns_default_enabled(self, client: TestClient, auth_headers: dict):
        """New users should have weekly_digest_enabled=True by default."""
        response = client.get("/api/v1/auth/me/preferences", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["weekly_digest_enabled"] is True

    def test_get_preferences_unauthorized(self, client: TestClient):
        """Should return 401/403 without authentication."""
        response = client.get("/api/v1/auth/me/preferences")

        assert response.status_code in [401, 403]

    def test_get_preferences_reflects_saved_state(self, client: TestClient, db: Session, test_user: User, auth_headers: dict):
        """Should return the actual saved preference value."""
        test_user.weekly_digest_enabled = False
        db.commit()

        response = client.get("/api/v1/auth/me/preferences", headers=auth_headers)

        assert response.status_code == 200
        assert response.json()["weekly_digest_enabled"] is False


class TestUpdatePreferences:
    """Tests for PATCH /api/v1/auth/me/preferences endpoint."""

    def test_disable_weekly_digest(self, client: TestClient, db: Session, test_user: User, auth_headers: dict):
        """Should be able to disable weekly digest."""
        response = client.patch(
            "/api/v1/auth/me/preferences",
            headers=auth_headers,
            json={"weekly_digest_enabled": False},
        )

        assert response.status_code == 200
        assert response.json()["weekly_digest_enabled"] is False

        # Verify persisted in database
        db.refresh(test_user)
        assert test_user.weekly_digest_enabled is False

    def test_enable_weekly_digest(self, client: TestClient, db: Session, test_user: User, auth_headers: dict):
        """Should be able to re-enable weekly digest after disabling."""
        test_user.weekly_digest_enabled = False
        db.commit()

        response = client.patch(
            "/api/v1/auth/me/preferences",
            headers=auth_headers,
            json={"weekly_digest_enabled": True},
        )

        assert response.status_code == 200
        assert response.json()["weekly_digest_enabled"] is True

        db.refresh(test_user)
        assert test_user.weekly_digest_enabled is True

    def test_update_preferences_unauthorized(self, client: TestClient):
        """Should return 401/403 without authentication."""
        response = client.patch(
            "/api/v1/auth/me/preferences",
            json={"weekly_digest_enabled": False},
        )

        assert response.status_code in [401, 403]

    def test_empty_update_preserves_value(self, client: TestClient, db: Session, test_user: User, auth_headers: dict):
        """Sending empty body should not change existing preference."""
        response = client.patch(
            "/api/v1/auth/me/preferences",
            headers=auth_headers,
            json={},
        )

        assert response.status_code == 200
        assert response.json()["weekly_digest_enabled"] is True

        db.refresh(test_user)
        assert test_user.weekly_digest_enabled is True


class TestUserResponseIncludesDigestField:
    """Tests that GET /api/v1/auth/me includes weekly_digest_enabled."""

    def test_me_includes_weekly_digest_enabled(self, client: TestClient, auth_headers: dict):
        """GET /me response should include weekly_digest_enabled field."""
        response = client.get("/api/v1/auth/me", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert "weekly_digest_enabled" in data
        assert data["weekly_digest_enabled"] is True

    def test_signup_creates_user_with_digest_enabled(self, client: TestClient, db: Session):
        """New signups should have weekly_digest_enabled=True."""
        response = client.post(
            "/api/v1/auth/signup",
            json={
                "email": "newdigest@example.com",
                "password": "password123",
                "organization_name": "Digest Test Co",
            },
        )

        assert response.status_code == 201

        user = db.query(User).filter(User.email == "newdigest@example.com").first()
        assert user is not None
        assert user.weekly_digest_enabled is True
