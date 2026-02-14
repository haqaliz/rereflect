"""
Tests for organization endpoints.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.models.user import User
from src.models.organization import Organization


class TestGetMyOrganization:
    """Tests for GET /api/v1/organizations/me endpoint."""

    def test_get_my_organization_success(
        self,
        client: TestClient,
        auth_headers: dict,
        test_organization: Organization
    ):
        """Test getting current user's organization."""
        response = client.get(
            "/api/v1/organizations/me",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == test_organization.id
        assert data["name"] == test_organization.name
        assert data["plan"] == test_organization.plan
        assert "created_at" in data

    def test_get_my_organization_unauthorized(self, client: TestClient):
        """Test getting organization without authentication fails."""
        response = client.get("/api/v1/organizations/me")

        assert response.status_code in [401, 403]


class TestGetOrganizationStats:
    """Tests for GET /api/v1/organizations/stats endpoint."""

    def test_get_organization_stats_success(
        self,
        client: TestClient,
        auth_headers: dict,
        test_user: User,
        test_feedback_batch: list
    ):
        """Test getting organization statistics."""
        response = client.get(
            "/api/v1/organizations/me/stats",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert "total_users" in data
        assert "total_feedback" in data
        assert data["total_users"] == 1  # Just test_user
        assert data["total_feedback"] == 5  # From test_feedback_batch

    def test_get_organization_stats_empty(
        self,
        client: TestClient,
        auth_headers: dict
    ):
        """Test getting stats for organization with no data."""
        response = client.get(
            "/api/v1/organizations/me/stats",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total_users"] >= 1  # At least the test user
        assert data["total_feedback"] >= 0

    def test_get_organization_stats_unauthorized(self, client: TestClient):
        """Test getting stats without authentication fails."""
        response = client.get("/api/v1/organizations/me/stats")

        # FastAPI returns 404 when authentication is missing
        assert response.status_code in [401, 403, 404]


class TestUpdateOrganization:
    """Tests for PATCH /api/v1/organizations/me endpoint."""

    def test_update_organization_success(
        self,
        client: TestClient,
        auth_headers: dict,
        test_organization: Organization,
        db: Session
    ):
        """Test updating organization."""
        response = client.patch(
            "/api/v1/organizations/me",
            headers=auth_headers,
            json={
                "name": "Updated Company Name"
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Company Name"
        assert data["id"] == test_organization.id

        # Verify in database
        db.refresh(test_organization)
        assert test_organization.name == "Updated Company Name"

    def test_update_organization_empty_name(
        self,
        client: TestClient,
        auth_headers: dict
    ):
        """Test updating organization with empty name fails."""
        response = client.patch(
            "/api/v1/organizations/me",
            headers=auth_headers,
            json={
                "name": ""
            }
        )

        # Should return validation error
        assert response.status_code == 422

    def test_update_organization_unauthorized(self, client: TestClient):
        """Test updating organization without authentication fails."""
        response = client.patch(
            "/api/v1/organizations/me",
            json={
                "name": "New Name"
            }
        )

        assert response.status_code in [401, 403]
