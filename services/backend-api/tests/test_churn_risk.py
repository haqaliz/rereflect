"""
Tests for churn risk features: dashboard summary, feedback filters/sorting.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.models.organization import Organization
from src.models.feedback import FeedbackItem
from src.models.user import User
from src.api.auth import hash_password, create_access_token


@pytest.fixture
def owner_user(db: Session, test_organization: Organization) -> User:
    user = User(
        email="owner@churntest.com",
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
def feedback_with_churn_scores(db: Session, test_organization: Organization):
    """Create feedback items with various churn risk scores."""
    items = [
        FeedbackItem(
            organization_id=test_organization.id,
            text="I'm canceling my subscription",
            source="support",
            sentiment_label="negative",
            sentiment_score=-0.9,
            is_urgent=True,
            churn_risk_score=85,
            suggested_action="Immediate outreach needed",
        ),
        FeedbackItem(
            organization_id=test_organization.id,
            text="Considering switching to competitor",
            source="email",
            sentiment_label="negative",
            sentiment_score=-0.5,
            is_urgent=False,
            churn_risk_score=55,
            suggested_action="Monitor and follow up",
        ),
        FeedbackItem(
            organization_id=test_organization.id,
            text="Minor issue with export",
            source="manual",
            sentiment_label="neutral",
            sentiment_score=0.1,
            is_urgent=False,
            churn_risk_score=15,
            suggested_action=None,
        ),
        FeedbackItem(
            organization_id=test_organization.id,
            text="Love this product!",
            source="email",
            sentiment_label="positive",
            sentiment_score=0.9,
            is_urgent=False,
            churn_risk_score=0,
            suggested_action=None,
        ),
        FeedbackItem(
            organization_id=test_organization.id,
            text="No score yet",
            source="manual",
            sentiment_label="neutral",
            sentiment_score=0.0,
            is_urgent=False,
            churn_risk_score=None,
            suggested_action=None,
        ),
    ]
    for item in items:
        db.add(item)
    db.commit()
    for item in items:
        db.refresh(item)
    return items


class TestDashboardChurnRisk:
    """Tests for churn risk summary on dashboard."""

    def test_dashboard_includes_churn_risk_summary(
        self, client: TestClient, owner_headers: dict, feedback_with_churn_scores
    ):
        response = client.get("/api/v1/dashboard/", headers=owner_headers)
        assert response.status_code == 200
        data = response.json()
        assert "churn_risk_summary" in data
        summary = data["churn_risk_summary"]
        assert summary["high_count"] == 1  # score 85
        assert summary["medium_count"] == 1  # score 55
        assert summary["low_count"] == 2  # score 15 and 0
        assert summary["total_at_risk"] == 2  # high + medium

    def test_dashboard_includes_top_churn_risks(
        self, client: TestClient, owner_headers: dict, feedback_with_churn_scores
    ):
        response = client.get("/api/v1/dashboard/", headers=owner_headers)
        assert response.status_code == 200
        data = response.json()
        assert "top_churn_risks" in data
        risks = data["top_churn_risks"]
        # Should be sorted by score desc, exclude 0 and None
        assert len(risks) == 3
        assert risks[0]["churn_risk_score"] == 85
        assert risks[1]["churn_risk_score"] == 55
        assert risks[2]["churn_risk_score"] == 15

    def test_dashboard_churn_risk_item_fields(
        self, client: TestClient, owner_headers: dict, feedback_with_churn_scores
    ):
        response = client.get("/api/v1/dashboard/", headers=owner_headers)
        data = response.json()
        top_risk = data["top_churn_risks"][0]
        assert "id" in top_risk
        assert "text" in top_risk
        assert "churn_risk_score" in top_risk
        assert "sentiment_label" in top_risk
        assert "suggested_action" in top_risk
        assert "created_at" in top_risk
        assert top_risk["suggested_action"] == "Immediate outreach needed"

    def test_dashboard_empty_churn_data(
        self, client: TestClient, owner_headers: dict
    ):
        response = client.get("/api/v1/dashboard/", headers=owner_headers)
        assert response.status_code == 200
        data = response.json()
        summary = data["churn_risk_summary"]
        assert summary["high_count"] == 0
        assert summary["medium_count"] == 0
        assert summary["low_count"] == 0
        assert summary["total_at_risk"] == 0
        assert data["top_churn_risks"] == []


class TestFeedbackChurnFilters:
    """Tests for churn risk filters on feedback list endpoint."""

    def test_filter_by_churn_risk_min(
        self, client: TestClient, owner_headers: dict, feedback_with_churn_scores
    ):
        response = client.get(
            "/api/v1/feedback/?churn_risk_min=50",
            headers=owner_headers,
        )
        assert response.status_code == 200
        items = response.json()["items"]
        # Should get score 85 and 55
        assert len(items) == 2
        scores = {item["churn_risk_score"] for item in items}
        assert scores == {85, 55}

    def test_filter_by_churn_risk_max(
        self, client: TestClient, owner_headers: dict, feedback_with_churn_scores
    ):
        response = client.get(
            "/api/v1/feedback/?churn_risk_max=20",
            headers=owner_headers,
        )
        assert response.status_code == 200
        items = response.json()["items"]
        # Should get score 15 and 0
        assert len(items) == 2

    def test_filter_by_churn_risk_range(
        self, client: TestClient, owner_headers: dict, feedback_with_churn_scores
    ):
        response = client.get(
            "/api/v1/feedback/?churn_risk_min=40&churn_risk_max=70",
            headers=owner_headers,
        )
        assert response.status_code == 200
        items = response.json()["items"]
        # Should only get score 55
        assert len(items) == 1
        assert items[0]["churn_risk_score"] == 55

    def test_sort_by_churn_risk_score(
        self, client: TestClient, owner_headers: dict, feedback_with_churn_scores
    ):
        response = client.get(
            "/api/v1/feedback/?sort_by=churn_risk_score&sort_order=desc",
            headers=owner_headers,
        )
        assert response.status_code == 200
        items = response.json()["items"]
        # Items with churn scores should come first (desc)
        scores = [item["churn_risk_score"] for item in items if item["churn_risk_score"] is not None]
        assert scores == sorted(scores, reverse=True)

    def test_feedback_response_includes_churn_fields(
        self, client: TestClient, owner_headers: dict, feedback_with_churn_scores
    ):
        response = client.get(
            "/api/v1/feedback/?churn_risk_min=80",
            headers=owner_headers,
        )
        assert response.status_code == 200
        items = response.json()["items"]
        assert len(items) == 1
        item = items[0]
        assert "churn_risk_score" in item
        assert "suggested_action" in item
        assert item["churn_risk_score"] == 85
        assert item["suggested_action"] == "Immediate outreach needed"

    def test_single_feedback_includes_churn_fields(
        self, client: TestClient, owner_headers: dict, feedback_with_churn_scores
    ):
        item_id = feedback_with_churn_scores[0].id
        response = client.get(
            f"/api/v1/feedback/{item_id}",
            headers=owner_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["churn_risk_score"] == 85
        assert data["suggested_action"] == "Immediate outreach needed"
