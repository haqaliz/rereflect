"""
Tests for churn risk edge cases: NULL scores, boundary filters, mixed data.
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
        email="owner@edgetest.com",
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
def feedback_with_nulls(db: Session, test_organization: Organization):
    """Create feedback items where some have NULL churn risk scores."""
    items = [
        FeedbackItem(
            organization_id=test_organization.id,
            text="Analyzed with score",
            source="manual",
            sentiment_label="negative",
            sentiment_score=-0.5,
            churn_risk_score=60,
        ),
        FeedbackItem(
            organization_id=test_organization.id,
            text="No churn score yet",
            source="manual",
            sentiment_label="neutral",
            sentiment_score=0.1,
            churn_risk_score=None,
        ),
        FeedbackItem(
            organization_id=test_organization.id,
            text="Zero churn risk",
            source="manual",
            sentiment_label="positive",
            sentiment_score=0.9,
            churn_risk_score=0,
        ),
    ]
    for item in items:
        db.add(item)
    db.commit()
    for item in items:
        db.refresh(item)
    return items


class TestChurnRiskNullHandling:
    """Tests for churn risk with NULL values."""

    def test_filter_min_excludes_null_scores(
        self, client: TestClient, owner_headers: dict, feedback_with_nulls
    ):
        """churn_risk_min filter should exclude items with NULL churn_risk_score."""
        response = client.get(
            "/api/v1/feedback/?churn_risk_min=0",
            headers=owner_headers,
        )
        assert response.status_code == 200
        items = response.json()["items"]
        # Should get score 60 and 0, but NOT the NULL one
        assert len(items) == 2
        for item in items:
            assert item["churn_risk_score"] is not None

    def test_filter_max_excludes_null_scores(
        self, client: TestClient, owner_headers: dict, feedback_with_nulls
    ):
        """churn_risk_max filter should exclude items with NULL churn_risk_score."""
        response = client.get(
            "/api/v1/feedback/?churn_risk_max=100",
            headers=owner_headers,
        )
        assert response.status_code == 200
        items = response.json()["items"]
        # Should get score 60 and 0, but NOT the NULL one
        assert len(items) == 2

    def test_dashboard_churn_summary_ignores_nulls(
        self, client: TestClient, owner_headers: dict, feedback_with_nulls
    ):
        """Dashboard churn risk summary should not count NULL scores."""
        response = client.get("/api/v1/dashboard/", headers=owner_headers)
        assert response.status_code == 200
        summary = response.json()["churn_risk_summary"]
        # score 60 = medium, score 0 = low, NULL = ignored
        assert summary["medium_count"] == 1
        assert summary["low_count"] == 1
        assert summary["high_count"] == 0

    def test_sort_by_churn_risk_handles_nulls(
        self, client: TestClient, owner_headers: dict, feedback_with_nulls
    ):
        """Sorting by churn_risk_score should work when some items have NULL scores."""
        response = client.get(
            "/api/v1/feedback/?sort_by=churn_risk_score&sort_order=desc",
            headers=owner_headers,
        )
        assert response.status_code == 200
        items = response.json()["items"]
        assert len(items) == 3  # All items returned

    def test_single_feedback_with_null_churn(
        self, client: TestClient, owner_headers: dict, feedback_with_nulls
    ):
        """GET single feedback should return null for churn_risk_score when not set."""
        null_item = feedback_with_nulls[1]  # The one with NULL score
        response = client.get(
            f"/api/v1/feedback/{null_item.id}",
            headers=owner_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["churn_risk_score"] is None
        assert data["suggested_action"] is None


class TestChurnRiskBoundary:
    """Tests for churn risk boundary values."""

    def test_filter_exact_boundary_70(
        self, client: TestClient, owner_headers: dict, db, test_organization
    ):
        """Score of exactly 70 should be included in churn_risk_min=70."""
        db.add(FeedbackItem(
            organization_id=test_organization.id,
            text="Boundary 70",
            source="manual",
            sentiment_label="negative",
            sentiment_score=-0.6,
            churn_risk_score=70,
        ))
        db.commit()

        response = client.get(
            "/api/v1/feedback/?churn_risk_min=70",
            headers=owner_headers,
        )
        assert response.status_code == 200
        items = response.json()["items"]
        assert len(items) == 1
        assert items[0]["churn_risk_score"] == 70

    def test_filter_exact_boundary_0(
        self, client: TestClient, owner_headers: dict, db, test_organization
    ):
        """Score of exactly 0 should be included in churn_risk_max=0."""
        db.add(FeedbackItem(
            organization_id=test_organization.id,
            text="Zero risk",
            source="manual",
            sentiment_label="positive",
            sentiment_score=0.9,
            churn_risk_score=0,
        ))
        db.commit()

        response = client.get(
            "/api/v1/feedback/?churn_risk_max=0",
            headers=owner_headers,
        )
        assert response.status_code == 200
        items = response.json()["items"]
        assert len(items) == 1
        assert items[0]["churn_risk_score"] == 0
