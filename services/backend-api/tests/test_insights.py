"""
Tests for weekly insights API endpoints.
"""

import pytest
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.models.organization import Organization
from src.models.weekly_insight import WeeklyInsight
from src.models.user import User
from src.api.auth import hash_password, create_access_token


@pytest.fixture
def owner_user(db: Session, test_organization: Organization) -> User:
    user = User(
        email="owner@insights.com",
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
def weekly_insights(db: Session, test_organization: Organization):
    """Create multiple weekly insights for testing."""
    now = datetime.utcnow()
    insights = [
        WeeklyInsight(
            organization_id=test_organization.id,
            week_start=now - timedelta(days=7),
            week_end=now,
            insights=[
                {"title": "Login issues increasing", "description": "20% more login complaints", "category": "pain_point", "priority": "high"},
                {"title": "Dark mode popular", "description": "Multiple requests for dark mode", "category": "feature_request", "priority": "medium"},
            ],
            generated_at=now,
        ),
        WeeklyInsight(
            organization_id=test_organization.id,
            week_start=now - timedelta(days=14),
            week_end=now - timedelta(days=7),
            insights=[
                {"title": "Performance improving", "description": "Fewer performance complaints", "category": "positive_trend", "priority": "low"},
            ],
            generated_at=now - timedelta(days=7),
        ),
    ]
    for item in insights:
        db.add(item)
    db.commit()
    for item in insights:
        db.refresh(item)
    return insights


class TestWeeklyInsightsLatest:
    """Tests for GET /api/v1/insights/weekly."""

    def test_get_latest_returns_most_recent(
        self, client: TestClient, owner_headers: dict, weekly_insights
    ):
        """Should return the most recently generated insight."""
        response = client.get("/api/v1/insights/weekly", headers=owner_headers)
        assert response.status_code == 200
        data = response.json()
        assert data is not None
        assert data["insights"][0]["title"] == "Login issues increasing"
        assert len(data["insights"]) == 2

    def test_get_latest_returns_null_when_none(
        self, client: TestClient, owner_headers: dict
    ):
        """Should return null when no insights exist."""
        response = client.get("/api/v1/insights/weekly", headers=owner_headers)
        assert response.status_code == 200
        assert response.json() is None

    def test_get_latest_requires_auth(
        self, client: TestClient
    ):
        """Should return 403 without auth."""
        response = client.get("/api/v1/insights/weekly")
        assert response.status_code == 403

    def test_get_latest_org_isolation(
        self, client: TestClient, db: Session, weekly_insights
    ):
        """Should not see insights from another organization."""
        # Create another org + user
        org_b = Organization(name="Other Corp", plan="pro")
        db.add(org_b)
        db.commit()
        db.refresh(org_b)

        user_b = User(
            email="other@test.com",
            password_hash=hash_password("password123"),
            organization_id=org_b.id,
            role="owner",
        )
        db.add(user_b)
        db.commit()
        db.refresh(user_b)

        token = create_access_token({
            "user_id": user_b.id,
            "organization_id": org_b.id,
            "role": user_b.role,
        })
        headers = {"Authorization": f"Bearer {token}"}

        response = client.get("/api/v1/insights/weekly", headers=headers)
        assert response.status_code == 200
        assert response.json() is None  # No insights for org B


class TestWeeklyInsightsHistory:
    """Tests for GET /api/v1/insights/weekly/history."""

    def test_get_history_returns_all(
        self, client: TestClient, owner_headers: dict, weekly_insights
    ):
        """Should return all insights for the org."""
        response = client.get(
            "/api/v1/insights/weekly/history", headers=owner_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2
        # Most recent first
        assert data["items"][0]["insights"][0]["title"] == "Login issues increasing"

    def test_get_history_with_limit(
        self, client: TestClient, owner_headers: dict, weekly_insights
    ):
        """Should respect limit parameter."""
        response = client.get(
            "/api/v1/insights/weekly/history?limit=1", headers=owner_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2  # Total is still 2
        assert len(data["items"]) == 1  # But only 1 returned

    def test_get_history_empty(
        self, client: TestClient, owner_headers: dict
    ):
        """Should return empty list when no insights exist."""
        response = client.get(
            "/api/v1/insights/weekly/history", headers=owner_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert len(data["items"]) == 0

    def test_get_history_requires_auth(
        self, client: TestClient
    ):
        """Should return 403 without auth."""
        response = client.get("/api/v1/insights/weekly/history")
        assert response.status_code == 403

    def test_insight_response_shape(
        self, client: TestClient, owner_headers: dict, weekly_insights
    ):
        """Should return properly shaped insight objects."""
        response = client.get("/api/v1/insights/weekly", headers=owner_headers)
        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert "organization_id" in data
        assert "week_start" in data
        assert "week_end" in data
        assert "generated_at" in data
        assert "insights" in data

        insight = data["insights"][0]
        assert "title" in insight
        assert "description" in insight
        assert "category" in insight
        assert "priority" in insight
