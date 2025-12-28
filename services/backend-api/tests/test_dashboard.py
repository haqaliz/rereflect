"""
Tests for dashboard endpoints.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.models.feedback import FeedbackItem


class TestGetDashboard:
    """Tests for GET /api/v1/dashboard endpoint."""

    def test_get_dashboard_success(
        self,
        client: TestClient,
        auth_headers: dict,
        test_feedback_batch: list[FeedbackItem]
    ):
        """Test getting dashboard data."""
        response = client.get(
            "/api/v1/dashboard",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()

        # Check structure
        assert "total_feedback" in data
        assert "sentiment" in data
        assert "pain_points" in data
        assert "feature_requests" in data
        assert "urgent_items" in data

        # Check values
        assert data["total_feedback"] == 5

        # Check sentiment breakdown
        sentiment = data["sentiment"]
        assert "positive_count" in sentiment
        assert "neutral_count" in sentiment
        assert "negative_count" in sentiment
        assert sentiment["positive_count"] == 1
        assert sentiment["neutral_count"] == 2
        assert sentiment["negative_count"] == 2

    def test_get_dashboard_with_days_filter(
        self,
        client: TestClient,
        auth_headers: dict,
        test_feedback_batch: list[FeedbackItem]
    ):
        """Test dashboard with days parameter."""
        response = client.get(
            "/api/v1/dashboard?days=7",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert "total_feedback" in data

    def test_get_dashboard_empty(
        self,
        client: TestClient,
        auth_headers: dict
    ):
        """Test dashboard with no feedback."""
        response = client.get(
            "/api/v1/dashboard",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total_feedback"] == 0
        assert data["sentiment"]["positive_count"] == 0
        assert data["sentiment"]["neutral_count"] == 0
        assert data["sentiment"]["negative_count"] == 0
        assert data["pain_points"] == []
        assert data["feature_requests"] == []
        assert data["urgent_items"] == []

    def test_get_dashboard_pain_points(
        self,
        client: TestClient,
        auth_headers: dict,
        test_feedback_batch: list[FeedbackItem]
    ):
        """Test dashboard pain points aggregation."""
        response = client.get(
            "/api/v1/dashboard",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()

        pain_points = data["pain_points"]
        assert isinstance(pain_points, list)
        assert len(pain_points) > 0

        # Check pain point structure
        for point in pain_points:
            assert "issue" in point
            assert "count" in point
            assert isinstance(point["count"], int)

    def test_get_dashboard_urgent_items(
        self,
        client: TestClient,
        auth_headers: dict,
        test_feedback_batch: list[FeedbackItem]
    ):
        """Test dashboard urgent items."""
        response = client.get(
            "/api/v1/dashboard",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()

        urgent_items = data["urgent_items"]
        assert isinstance(urgent_items, list)
        assert len(urgent_items) == 2  # We have 2 urgent items in test data

        # Check urgent item structure
        for item in urgent_items:
            assert "id" in item
            assert "text" in item
            assert "created_at" in item
            assert item["is_urgent"] is True

    def test_get_dashboard_unauthorized(self, client: TestClient):
        """Test getting dashboard without authentication fails."""
        response = client.get("/api/v1/dashboard")

        assert response.status_code == 401

    def test_get_dashboard_invalid_days(
        self,
        client: TestClient,
        auth_headers: dict
    ):
        """Test dashboard with invalid days parameter."""
        response = client.get(
            "/api/v1/dashboard?days=-1",
            headers=auth_headers
        )

        # Should still work or return validation error
        assert response.status_code in [200, 422]
