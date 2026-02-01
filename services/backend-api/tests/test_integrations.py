"""
Tests for integrations endpoints.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.models.integration import Integration
from src.models.user import User
from src.models.organization import Organization


@pytest.fixture
def test_integration(db: Session, test_organization: Organization) -> Integration:
    """Create a test Slack integration."""
    integration = Integration(
        organization_id=test_organization.id,
        type="slack",
        name="Test Slack Channel",
        config={
            "webhook_url": "https://hooks.slack.com/services/TEST/WEBHOOK/URL",
            "integration_type": "webhook"
        },
        triggers=["urgent", "negative"],
        included_fields=["text", "sentiment"],
        is_active=True,
    )
    db.add(integration)
    db.commit()
    db.refresh(integration)
    return integration


class TestListIntegrations:
    """Tests for GET /api/v1/integrations endpoint."""

    def test_list_integrations_empty(
        self,
        client: TestClient,
        auth_headers: dict
    ):
        """Test listing integrations when none exist."""
        response = client.get(
            "/api/v1/integrations/",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert "integrations" in data
        assert "total" in data
        assert data["total"] == 0
        assert len(data["integrations"]) == 0

    def test_list_integrations_success(
        self,
        client: TestClient,
        auth_headers: dict,
        test_integration: Integration
    ):
        """Test listing integrations when one exists."""
        response = client.get(
            "/api/v1/integrations/",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["integrations"]) == 1
        assert data["integrations"][0]["name"] == "Test Slack Channel"
        assert data["integrations"][0]["type"] == "slack"

    def test_list_integrations_unauthorized(self, client: TestClient):
        """Test listing integrations without authentication fails."""
        response = client.get("/api/v1/integrations/")
        assert response.status_code == 403  # Returns 403 Forbidden


class TestCreateSlackWebhook:
    """Tests for POST /api/v1/integrations/slack/webhook endpoint."""

    def test_create_slack_webhook_success(
        self,
        client: TestClient,
        auth_headers: dict,
        db: Session
    ):
        """Test creating a Slack webhook integration."""
        response = client.post(
            "/api/v1/integrations/slack/webhook",
            headers=auth_headers,
            json={
                "name": "My Alerts Channel",
                "webhook_url": "https://hooks.slack.com/services/T123/B456/xyz789",
                "triggers": ["urgent"],
                "included_fields": ["text", "sentiment", "pain_point_category"],
                "digest_time": "09:00"
            }
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "My Alerts Channel"
        assert data["type"] == "slack"
        assert data["is_active"] is True
        assert "urgent" in data["triggers"]
        assert "text" in data["included_fields"]

    def test_create_slack_webhook_invalid_url(
        self,
        client: TestClient,
        auth_headers: dict
    ):
        """Test creating webhook with invalid URL fails."""
        response = client.post(
            "/api/v1/integrations/slack/webhook",
            headers=auth_headers,
            json={
                "name": "Invalid Webhook",
                "webhook_url": "https://example.com/not-slack",
                "triggers": ["urgent"]
            }
        )

        assert response.status_code == 422  # Validation error

    def test_create_slack_webhook_invalid_trigger(
        self,
        client: TestClient,
        auth_headers: dict
    ):
        """Test creating webhook with invalid trigger fails."""
        response = client.post(
            "/api/v1/integrations/slack/webhook",
            headers=auth_headers,
            json={
                "name": "Invalid Trigger",
                "webhook_url": "https://hooks.slack.com/services/T123/B456/xyz789",
                "triggers": ["invalid_trigger"]
            }
        )

        assert response.status_code == 422  # Validation error

    def test_create_slack_webhook_unauthorized(self, client: TestClient):
        """Test creating webhook without authentication fails."""
        response = client.post(
            "/api/v1/integrations/slack/webhook",
            json={
                "name": "Test",
                "webhook_url": "https://hooks.slack.com/services/T123/B456/xyz789"
            }
        )
        assert response.status_code == 403  # Returns 403 Forbidden


class TestGetIntegration:
    """Tests for GET /api/v1/integrations/{id} endpoint."""

    def test_get_integration_success(
        self,
        client: TestClient,
        auth_headers: dict,
        test_integration: Integration
    ):
        """Test getting a single integration."""
        response = client.get(
            f"/api/v1/integrations/{test_integration.id}",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == test_integration.id
        assert data["name"] == test_integration.name

    def test_get_integration_not_found(
        self,
        client: TestClient,
        auth_headers: dict
    ):
        """Test getting non-existent integration fails."""
        response = client.get(
            "/api/v1/integrations/99999",
            headers=auth_headers
        )
        assert response.status_code == 404


class TestUpdateIntegration:
    """Tests for PATCH /api/v1/integrations/{id} endpoint."""

    def test_update_integration_success(
        self,
        client: TestClient,
        auth_headers: dict,
        test_integration: Integration
    ):
        """Test updating an integration."""
        response = client.patch(
            f"/api/v1/integrations/{test_integration.id}",
            headers=auth_headers,
            json={
                "name": "Updated Channel Name",
                "triggers": ["all"],
                "is_active": False
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Channel Name"
        assert data["triggers"] == ["all"]
        assert data["is_active"] is False

    def test_update_integration_not_found(
        self,
        client: TestClient,
        auth_headers: dict
    ):
        """Test updating non-existent integration fails."""
        response = client.patch(
            "/api/v1/integrations/99999",
            headers=auth_headers,
            json={"name": "Updated"}
        )
        assert response.status_code == 404


class TestDeleteIntegration:
    """Tests for DELETE /api/v1/integrations/{id} endpoint."""

    def test_delete_integration_success(
        self,
        client: TestClient,
        auth_headers: dict,
        test_integration: Integration,
        db: Session
    ):
        """Test deleting an integration."""
        integration_id = test_integration.id
        response = client.delete(
            f"/api/v1/integrations/{integration_id}",
            headers=auth_headers
        )

        assert response.status_code == 204

        # Verify deleted from database
        integration = db.query(Integration).filter(Integration.id == integration_id).first()
        assert integration is None

    def test_delete_integration_not_found(
        self,
        client: TestClient,
        auth_headers: dict
    ):
        """Test deleting non-existent integration fails."""
        response = client.delete(
            "/api/v1/integrations/99999",
            headers=auth_headers
        )
        assert response.status_code == 404
