"""
Tests for main API endpoints.
"""

import pytest
from fastapi.testclient import TestClient


class TestRootEndpoint:
    """Tests for root endpoint."""

    def test_root_endpoint(self, client: TestClient):
        """Test root endpoint returns API info."""
        response = client.get("/")

        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "version" in data
        assert "status" in data
        assert data["message"] == "Customer Feedback Analyzer API"
        assert data["version"] == "1.0.0"
        assert data["status"] == "running"


class TestHealthEndpoint:
    """Tests for health check endpoint."""

    def test_health_endpoint(self, client: TestClient):
        """Test health check endpoint."""
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert data["status"] == "healthy"
