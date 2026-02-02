"""
Tests for authentication endpoints.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.models.user import User
from src.models.organization import Organization


class TestSignup:
    """Tests for /api/v1/auth/signup endpoint."""

    def test_signup_success(self, client: TestClient, db: Session):
        """Test successful user signup."""
        response = client.post(
            "/api/v1/auth/signup",
            json={
                "email": "newuser@example.com",
                "password": "password123",
                "organization_name": "New Company"
            }
        )

        assert response.status_code == 201
        data = response.json()
        assert "access_token" in data
        assert isinstance(data["access_token"], str)
        assert len(data["access_token"]) > 0

        # Verify user was created in database
        user = db.query(User).filter(User.email == "newuser@example.com").first()
        assert user is not None
        assert user.email == "newuser@example.com"
        assert user.role == "owner"  # First user in org is owner

        # Verify organization was created
        org = db.query(Organization).filter(Organization.id == user.organization_id).first()
        assert org is not None
        assert org.name == "New Company"
        assert org.plan == "free"

    def test_signup_duplicate_email(self, client: TestClient, test_user: User):
        """Test signup with existing email fails."""
        response = client.post(
            "/api/v1/auth/signup",
            json={
                "email": test_user.email,
                "password": "password123",
                "organization_name": "Another Company"
            }
        )

        assert response.status_code == 400
        assert "Email already registered" in response.json()["detail"]

    def test_signup_missing_fields(self, client: TestClient):
        """Test signup with missing fields fails."""
        response = client.post(
            "/api/v1/auth/signup",
            json={
                "email": "test@example.com"
                # Missing password and organization_name
            }
        )

        assert response.status_code == 422  # Validation error

    def test_signup_invalid_email(self, client: TestClient):
        """Test signup with invalid email format fails."""
        response = client.post(
            "/api/v1/auth/signup",
            json={
                "email": "not-an-email",
                "password": "password123",
                "organization_name": "Test Company"
            }
        )

        assert response.status_code == 422  # Validation error


class TestLogin:
    """Tests for /api/v1/auth/login endpoint."""

    def test_login_success(self, client: TestClient, test_user: User):
        """Test successful login."""
        response = client.post(
            "/api/v1/auth/login",
            json={
                "email": test_user.email,
                "password": "password123"
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert isinstance(data["access_token"], str)
        assert len(data["access_token"]) > 0

    def test_login_wrong_password(self, client: TestClient, test_user: User):
        """Test login with wrong password fails."""
        response = client.post(
            "/api/v1/auth/login",
            json={
                "email": test_user.email,
                "password": "wrongpassword"
            }
        )

        assert response.status_code in [401, 403]
        assert "Invalid email or password" in response.json()["detail"]

    def test_login_nonexistent_user(self, client: TestClient):
        """Test login with non-existent user fails."""
        response = client.post(
            "/api/v1/auth/login",
            json={
                "email": "nonexistent@example.com",
                "password": "password123"
            }
        )

        assert response.status_code in [401, 403]
        assert "Invalid email or password" in response.json()["detail"]

    def test_login_missing_fields(self, client: TestClient):
        """Test login with missing fields fails."""
        response = client.post(
            "/api/v1/auth/login",
            json={
                "email": "test@example.com"
                # Missing password
            }
        )

        assert response.status_code == 422  # Validation error


class TestGetMe:
    """Tests for /api/v1/auth/me endpoint."""

    def test_get_me_success(self, client: TestClient, test_user: User, auth_headers: dict):
        """Test getting current user info."""
        response = client.get(
            "/api/v1/auth/me",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == test_user.id
        assert data["email"] == test_user.email
        assert data["role"] == test_user.role
        assert data["organization_id"] == test_user.organization_id

    def test_get_me_unauthorized(self, client: TestClient):
        """Test getting user info without authentication fails."""
        response = client.get("/api/v1/auth/me")

        # 401 or 403 - depends on how auth middleware handles missing credentials
        assert response.status_code in [401, 403]

    def test_get_me_invalid_token(self, client: TestClient):
        """Test getting user info with invalid token fails."""
        response = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer invalid-token"}
        )

        assert response.status_code in [401, 403]
