"""
Tests for authentication endpoints.
"""

import pytest
from unittest.mock import patch, MagicMock
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


# Mock Google user info returned by verify_google_token
MOCK_GOOGLE_USER = {
    "google_id": "google-user-id-12345",
    "email": "googleuser@gmail.com",
    "email_verified": True,
    "name": "Google User",
    "picture": "https://example.com/photo.jpg",
    "given_name": "Google",
    "family_name": "User",
}


class TestGoogleSignup:
    """Tests for /api/v1/auth/google/signup endpoint."""

    @patch("src.api.routes.auth.verify_google_access_token")
    def test_google_signup_success(self, mock_verify: MagicMock, client: TestClient, db: Session):
        """Test successful signup with Google creates user and organization."""
        # Mock async function
        async def mock_return(*args, **kwargs):
            return MOCK_GOOGLE_USER
        mock_verify.side_effect = mock_return

        response = client.post(
            "/api/v1/auth/google/signup",
            json={
                "access_token": "valid-google-token",
                "organization_name": "Google Company"
            }
        )

        assert response.status_code == 201
        data = response.json()
        assert "access_token" in data
        assert isinstance(data["access_token"], str)

        # Verify user was created with Google info
        user = db.query(User).filter(User.email == "googleuser@gmail.com").first()
        assert user is not None
        assert user.google_id == "google-user-id-12345"
        assert user.auth_provider == "google"
        assert user.password_hash is None  # No password for Google-only users
        assert user.role == "owner"

        # Verify organization was created
        org = db.query(Organization).filter(Organization.id == user.organization_id).first()
        assert org is not None
        assert org.name == "Google Company"

    @patch("src.api.routes.auth.verify_google_access_token")
    def test_google_signup_invalid_token(self, mock_verify: MagicMock, client: TestClient):
        """Test signup with invalid Google token fails."""
        async def mock_return(*args, **kwargs):
            return None  # Invalid token returns None
        mock_verify.side_effect = mock_return

        response = client.post(
            "/api/v1/auth/google/signup",
            json={
                "access_token": "invalid-google-token",
                "organization_name": "Test Company"
            }
        )

        assert response.status_code == 401
        assert "Invalid Google token" in response.json()["detail"]

    @patch("src.api.routes.auth.verify_google_access_token")
    def test_google_signup_existing_email(self, mock_verify: MagicMock, client: TestClient, test_user: User):
        """Test Google signup with existing email fails."""
        async def mock_return(*args, **kwargs):
            return {**MOCK_GOOGLE_USER, "email": test_user.email}
        mock_verify.side_effect = mock_return

        response = client.post(
            "/api/v1/auth/google/signup",
            json={
                "access_token": "valid-google-token",
                "organization_name": "Another Company"
            }
        )

        assert response.status_code == 400
        # Should suggest signing in instead
        assert "already exists" in response.json()["detail"].lower()

    @patch("src.api.routes.auth.verify_google_access_token")
    def test_google_signup_missing_org_name(self, mock_verify: MagicMock, client: TestClient):
        """Test Google signup without organization name fails."""
        async def mock_return(*args, **kwargs):
            return MOCK_GOOGLE_USER
        mock_verify.side_effect = mock_return

        response = client.post(
            "/api/v1/auth/google/signup",
            json={
                "access_token": "valid-google-token"
                # Missing organization_name
            }
        )

        assert response.status_code == 422  # Validation error


class TestGoogleLogin:
    """Tests for /api/v1/auth/google/login endpoint."""

    @patch("src.api.routes.auth.verify_google_access_token")
    def test_google_login_existing_google_user(self, mock_verify: MagicMock, client: TestClient, db: Session):
        """Test login with existing Google user returns token."""
        # First create a Google user
        org = Organization(name="Google Org", plan="free")
        db.add(org)
        db.flush()

        user = User(
            email="existinggoogle@gmail.com",
            password_hash=None,
            google_id="existing-google-id",
            auth_provider="google",
            organization_id=org.id,
            role="owner"
        )
        db.add(user)
        db.commit()

        async def mock_return(*args, **kwargs):
            return {
                **MOCK_GOOGLE_USER,
                "email": "existinggoogle@gmail.com",
                "google_id": "existing-google-id"
            }
        mock_verify.side_effect = mock_return

        response = client.post(
            "/api/v1/auth/google/login",
            json={"access_token": "valid-google-token"}
        )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data

    @patch("src.api.routes.auth.verify_google_access_token")
    def test_google_login_links_email_account(self, mock_verify: MagicMock, client: TestClient, test_user: User, db: Session):
        """Test Google login with existing email user links accounts."""
        # test_user is an email-based user (has password_hash, no google_id)
        async def mock_return(*args, **kwargs):
            return {
                **MOCK_GOOGLE_USER,
                "email": test_user.email,
                "google_id": "new-google-id-for-existing-user"
            }
        mock_verify.side_effect = mock_return

        response = client.post(
            "/api/v1/auth/google/login",
            json={"access_token": "valid-google-token"}
        )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data

        # Verify Google ID was linked
        db.refresh(test_user)
        assert test_user.google_id == "new-google-id-for-existing-user"
        assert test_user.auth_provider == "both"  # Now has both email and Google

    @patch("src.api.routes.auth.verify_google_access_token")
    def test_google_login_no_account(self, mock_verify: MagicMock, client: TestClient):
        """Test Google login with no existing account fails."""
        async def mock_return(*args, **kwargs):
            return {
                **MOCK_GOOGLE_USER,
                "email": "nonexistent@gmail.com"
            }
        mock_verify.side_effect = mock_return

        response = client.post(
            "/api/v1/auth/google/login",
            json={"access_token": "valid-google-token"}
        )

        assert response.status_code == 404
        assert "No account found" in response.json()["detail"]

    @patch("src.api.routes.auth.verify_google_access_token")
    def test_google_login_invalid_token(self, mock_verify: MagicMock, client: TestClient):
        """Test Google login with invalid token fails."""
        async def mock_return(*args, **kwargs):
            return None
        mock_verify.side_effect = mock_return

        response = client.post(
            "/api/v1/auth/google/login",
            json={"access_token": "invalid-token"}
        )

        assert response.status_code == 401
        assert "Invalid Google token" in response.json()["detail"]

    @patch("src.api.routes.auth.verify_google_access_token")
    def test_google_login_mismatched_google_id(self, mock_verify: MagicMock, client: TestClient, db: Session):
        """Test Google login fails if email is linked to different Google account."""
        # Create user with one Google ID
        org = Organization(name="Test Org", plan="free")
        db.add(org)
        db.flush()

        user = User(
            email="linked@gmail.com",
            password_hash=None,
            google_id="original-google-id",
            auth_provider="google",
            organization_id=org.id,
            role="owner"
        )
        db.add(user)
        db.commit()

        # Try to login with different Google ID but same email
        async def mock_return(*args, **kwargs):
            return {
                **MOCK_GOOGLE_USER,
                "email": "linked@gmail.com",
                "google_id": "different-google-id"
            }
        mock_verify.side_effect = mock_return

        response = client.post(
            "/api/v1/auth/google/login",
            json={"access_token": "valid-google-token"}
        )

        assert response.status_code == 401
        assert "different Google account" in response.json()["detail"]


class TestEmailLoginWithGoogleUser:
    """Tests for email login behavior with Google-only users."""

    def test_email_login_google_only_user(self, client: TestClient, db: Session):
        """Test email login fails for Google-only user with helpful message."""
        # Create a Google-only user (no password)
        org = Organization(name="Google Org", plan="free")
        db.add(org)
        db.flush()

        user = User(
            email="googleonly@gmail.com",
            password_hash=None,  # No password
            google_id="google-only-id",
            auth_provider="google",
            organization_id=org.id,
            role="owner"
        )
        db.add(user)
        db.commit()

        response = client.post(
            "/api/v1/auth/login",
            json={
                "email": "googleonly@gmail.com",
                "password": "anypassword"
            }
        )

        assert response.status_code == 401
        assert "Google Sign-In" in response.json()["detail"]
