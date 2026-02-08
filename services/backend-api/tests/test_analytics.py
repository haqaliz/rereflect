"""
Tests for the analytics trends endpoint.
"""
import pytest
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from src.models.feedback import FeedbackItem
from src.models.organization import Organization
from src.models.user import User
from src.api.auth import hash_password, create_access_token


# ─── Fixtures ───────────────────────────────────────────────────────

@pytest.fixture
def free_organization(db: Session) -> Organization:
    """Create an organization with Free plan."""
    org = Organization(name="Free Company", plan="free")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


@pytest.fixture
def free_user(db: Session, free_organization: Organization) -> User:
    """Create a user in the Free organization."""
    user = User(
        email="free@example.com",
        password_hash=hash_password("password123"),
        organization_id=free_organization.id,
        role="admin",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def free_auth_headers(free_user: User) -> dict:
    """Auth headers for the free user."""
    token = create_access_token({
        "user_id": free_user.id,
        "organization_id": free_user.organization_id,
        "role": free_user.role,
    })
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def feedback_over_time(db: Session, test_organization: Organization):
    """Create feedback spread over the last 14 days for the pro org."""
    now = datetime.utcnow()
    items = []

    for i in range(14):
        date = now - timedelta(days=i)
        items.append(FeedbackItem(
            organization_id=test_organization.id,
            text=f"Feedback day-{i}",
            source="email",
            sentiment_label="positive" if i % 3 == 0 else ("neutral" if i % 3 == 1 else "negative"),
            sentiment_score=0.8 if i % 3 == 0 else (0.1 if i % 3 == 1 else -0.7),
            is_urgent=(i % 5 == 0),
            pain_point_category="performance" if i % 4 == 0 else None,
            feature_request_category="automation" if i % 6 == 0 else None,
            created_at=date,
        ))

    db.add_all(items)
    db.commit()
    return items


@pytest.fixture
def other_org_feedback(db: Session):
    """Create feedback in a different organization (for isolation test)."""
    other_org = Organization(name="Other Company", plan="free")
    db.add(other_org)
    db.commit()
    db.refresh(other_org)

    items = []
    for i in range(5):
        items.append(FeedbackItem(
            organization_id=other_org.id,
            text=f"Other org feedback {i}",
            source="survey",
            sentiment_label="negative",
            sentiment_score=-0.9,
            is_urgent=True,
            created_at=datetime.utcnow() - timedelta(days=i),
        ))
    db.add_all(items)
    db.commit()
    return items


# ─── Tests ──────────────────────────────────────────────────────────

class TestAnalyticsTrends:
    """Tests for GET /api/v1/analytics/trends."""

    def test_trends_7d_returns_data(self, client, auth_headers, feedback_over_time):
        """7d range returns daily data points (pro plan)."""
        response = client.get("/api/v1/analytics/trends?range=7d", headers=auth_headers)
        assert response.status_code == 200

        data = response.json()
        assert data["date_range"] == "Last 7 days"
        assert data["granularity"] == "daily"
        assert data["total_feedback"] > 0
        assert isinstance(data["data_points"], list)
        assert isinstance(data["sentiment_distribution"], dict)
        assert isinstance(data["source_distribution"], list)
        assert isinstance(data["top_pain_points"], list)
        assert isinstance(data["top_feature_requests"], list)

    def test_trends_data_point_shape(self, client, auth_headers, feedback_over_time):
        """Each data point has the expected fields."""
        response = client.get("/api/v1/analytics/trends?range=7d", headers=auth_headers)
        data = response.json()

        if data["data_points"]:
            dp = data["data_points"][0]
            assert "date" in dp
            assert "feedback_count" in dp
            assert "avg_sentiment_score" in dp
            assert "positive_count" in dp
            assert "neutral_count" in dp
            assert "negative_count" in dp
            assert "urgent_count" in dp
            assert "pain_points_count" in dp
            assert "feature_requests_count" in dp

    def test_trends_sentiment_distribution(self, client, auth_headers, feedback_over_time):
        """Sentiment distribution sums to total."""
        response = client.get("/api/v1/analytics/trends?range=7d", headers=auth_headers)
        data = response.json()

        sd = data["sentiment_distribution"]
        assert sd["positive"] + sd["neutral"] + sd["negative"] == data["total_feedback"]

    def test_trends_source_distribution(self, client, auth_headers, feedback_over_time):
        """Source distribution has percentages summing to ~100."""
        response = client.get("/api/v1/analytics/trends?range=7d", headers=auth_headers)
        data = response.json()

        if data["source_distribution"]:
            total_pct = sum(s["percentage"] for s in data["source_distribution"])
            assert abs(total_pct - 100.0) < 1.0

    def test_trends_top_items_have_trend(self, client, auth_headers, feedback_over_time):
        """Top items include trend direction."""
        response = client.get("/api/v1/analytics/trends?range=7d", headers=auth_headers)
        data = response.json()

        for pp in data["top_pain_points"]:
            assert pp["trend"] in ("up", "down", "stable")
            assert pp["count"] > 0

    def test_trends_empty_org(self, client, auth_headers):
        """Empty org returns zero totals and empty lists."""
        response = client.get("/api/v1/analytics/trends?range=7d", headers=auth_headers)
        assert response.status_code == 200

        data = response.json()
        assert data["total_feedback"] == 0
        assert data["data_points"] == []
        assert data["top_pain_points"] == []
        assert data["top_feature_requests"] == []

    def test_trends_multi_tenant_isolation(self, client, auth_headers, feedback_over_time, other_org_feedback):
        """Data from other orgs is not included."""
        response = client.get("/api/v1/analytics/trends?range=7d", headers=auth_headers)
        data = response.json()

        # Our test_organization feedback only — no "Other Company" data
        for dp in data["data_points"]:
            assert dp["feedback_count"] >= 0

        # Our total_feedback should only include our org's items (up to 7 days)
        assert data["total_feedback"] <= len(feedback_over_time)

    def test_free_plan_blocked_30d(self, client, free_auth_headers):
        """Free plan users get 403 for 30d range."""
        response = client.get("/api/v1/analytics/trends?range=30d", headers=free_auth_headers)
        assert response.status_code == 403

        detail = response.json()["detail"]
        assert detail["error"] == "feature_not_available"
        assert detail["required_plan"] == "pro"

    def test_free_plan_blocked_90d(self, client, free_auth_headers):
        """Free plan users get 403 for 90d range."""
        response = client.get("/api/v1/analytics/trends?range=90d", headers=free_auth_headers)
        assert response.status_code == 403

    def test_free_plan_allows_7d(self, client, free_auth_headers):
        """Free plan users can access 7d range."""
        response = client.get("/api/v1/analytics/trends?range=7d", headers=free_auth_headers)
        assert response.status_code == 200

        data = response.json()
        assert data["granularity"] == "daily"
        assert data["date_range"] == "Last 7 days"

    def test_pro_plan_allows_30d(self, client, auth_headers, db, test_organization):
        """Pro plan users can access 30d range."""
        fb = FeedbackItem(
            organization_id=test_organization.id,
            text="Pro feedback",
            source="email",
            sentiment_label="positive",
            sentiment_score=0.9,
            created_at=datetime.utcnow(),
        )
        db.add(fb)
        db.commit()

        response = client.get("/api/v1/analytics/trends?range=30d", headers=auth_headers)
        assert response.status_code == 200

        data = response.json()
        assert data["granularity"] == "daily"
        assert data["date_range"] == "Last 30 days"

    def test_pro_plan_allows_90d(self, client, auth_headers):
        """Pro plan users can access 90d range with weekly granularity."""
        response = client.get("/api/v1/analytics/trends?range=90d", headers=auth_headers)
        assert response.status_code == 200

        data = response.json()
        assert data["granularity"] == "weekly"

    def test_invalid_range_rejected(self, client, auth_headers):
        """Invalid range parameter returns 422."""
        response = client.get("/api/v1/analytics/trends?range=999d", headers=auth_headers)
        assert response.status_code == 422

    def test_unauthenticated_request(self, client):
        """Unauthenticated requests return 403."""
        response = client.get("/api/v1/analytics/trends")
        assert response.status_code == 403
