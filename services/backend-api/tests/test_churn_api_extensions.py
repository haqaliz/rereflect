"""
TDD tests for churn prediction API extensions (M1.4 Phase 4):
- Feedback detail includes churn_risk_factors in response
- Customer health response includes confidence_score and confidence_level
- GET /api/v1/customers/{email}/churn-factors endpoint
- POST /api/v1/admin/backtest endpoint
"""
import pytest
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

from src.models.customer_health import CustomerHealth
from src.models.feedback import FeedbackItem
from src.models.organization import Organization
from src.models.user import User
from src.api.auth import hash_password, create_access_token


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def pro_org(db: Session) -> Organization:
    org = Organization(name="Pro Corp API", plan="pro")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


@pytest.fixture
def pro_user(db: Session, pro_org: Organization) -> User:
    user = User(
        email="proapi@example.com",
        password_hash=hash_password("password123"),
        organization_id=pro_org.id,
        role="admin",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def pro_headers(pro_user: User) -> dict:
    token = create_access_token({
        "user_id": pro_user.id,
        "organization_id": pro_user.organization_id,
        "role": pro_user.role,
    })
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def free_org(db: Session) -> Organization:
    org = Organization(name="Free Corp API", plan="free")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


@pytest.fixture
def free_user(db: Session, free_org: Organization) -> User:
    user = User(
        email="freeapi@example.com",
        password_hash=hash_password("password123"),
        organization_id=free_org.id,
        role="admin",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def free_headers(free_user: User) -> dict:
    token = create_access_token({
        "user_id": free_user.id,
        "organization_id": free_user.organization_id,
        "role": free_user.role,
    })
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def system_admin_user(db: Session, pro_org: Organization) -> User:
    user = User(
        email="sysadmin@rereflect.io",
        password_hash=hash_password("password123"),
        organization_id=pro_org.id,
        role="admin",
        is_system_admin=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def admin_headers(system_admin_user: User) -> dict:
    token = create_access_token({
        "user_id": system_admin_user.id,
        "organization_id": system_admin_user.organization_id,
        "role": system_admin_user.role,
    })
    return {"Authorization": f"Bearer {token}"}


def make_feedback(db, org_id, email=None, churn_risk_factors=None, churn_risk_score=50):
    fb = FeedbackItem(
        organization_id=org_id,
        customer_email=email,
        text="Test feedback text",
        source="email",
        sentiment_score=-0.5,
        sentiment_label="negative",
        is_urgent=False,
        churn_risk_score=churn_risk_score,
        churn_risk_factors=churn_risk_factors,
        created_at=datetime.utcnow(),
    )
    db.add(fb)
    db.commit()
    db.refresh(fb)
    return fb


def make_customer_health(db, org_id, email, confidence_score=75, confidence_level="high"):
    health = CustomerHealth(
        organization_id=org_id,
        customer_email=email,
        health_score=70,
        risk_level="healthy",
        churn_risk_component=70,
        sentiment_component=70,
        resolution_component=50,
        frequency_component=50,
        feedback_count=10,
        confidence_level=confidence_level,
        confidence_score=confidence_score,
    )
    db.add(health)
    db.commit()
    db.refresh(health)
    return health


# ---------------------------------------------------------------------------
# Tests: Feedback Detail includes churn_risk_factors
# ---------------------------------------------------------------------------

class TestFeedbackDetailChurnFactors:
    """GET /api/v1/feedback/{id} should include churn_risk_factors in response."""

    def test_feedback_detail_includes_churn_risk_factors_when_present(
        self, client: TestClient, db: Session, test_organization: Organization, auth_headers: dict
    ):
        """Feedback detail response should include churn_risk_factors when column is set."""
        factors = {
            "sentiment": {"score": 15, "max": 15, "label": "Very negative sentiment"},
            "churn_keywords": {"score": 10, "max": 15, "label": "2 churn keywords found"},
            "frustration_keywords": {"score": 5, "max": 10, "label": "1 frustration keyword"},
            "urgency": {"score": 10, "max": 10, "label": "Marked as urgent"},
            "sentiment_trend": {"score": 0, "max": 15, "label": "Insufficient data"},
            "feedback_frequency": {"score": 0, "max": 10, "label": "Normal frequency"},
            "resolution_time": {"score": 0, "max": 10, "label": "No data"},
            "pain_severity": {"score": 0, "max": 10, "label": "No critical pain points"},
            "feature_density": {"score": 0, "max": 5, "label": "Low feature request ratio"},
        }
        fb = make_feedback(db, test_organization.id, churn_risk_factors=factors)

        response = client.get(f"/api/v1/feedback/{fb.id}", headers=auth_headers)
        assert response.status_code == 200

        data = response.json()
        assert "churn_risk_factors" in data
        assert data["churn_risk_factors"] is not None
        assert data["churn_risk_factors"]["sentiment"]["score"] == 15

    def test_feedback_detail_churn_risk_factors_is_none_when_not_set(
        self, client: TestClient, db: Session, test_organization: Organization, auth_headers: dict
    ):
        """Feedback detail response should return null for churn_risk_factors when not computed."""
        fb = make_feedback(db, test_organization.id, churn_risk_factors=None)

        response = client.get(f"/api/v1/feedback/{fb.id}", headers=auth_headers)
        assert response.status_code == 200

        data = response.json()
        assert "churn_risk_factors" in data
        assert data["churn_risk_factors"] is None

    def test_feedback_detail_returns_all_nine_factor_keys(
        self, client: TestClient, db: Session, test_organization: Organization, auth_headers: dict
    ):
        """churn_risk_factors should have all 9 keys when present."""
        factors = {
            "sentiment": {"score": 5, "max": 15, "label": "Slightly negative"},
            "churn_keywords": {"score": 0, "max": 15, "label": "No churn keywords"},
            "frustration_keywords": {"score": 0, "max": 10, "label": "No frustration keywords"},
            "urgency": {"score": 0, "max": 10, "label": "Not urgent"},
            "sentiment_trend": {"score": 0, "max": 15, "label": "Stable"},
            "feedback_frequency": {"score": 0, "max": 10, "label": "Normal"},
            "resolution_time": {"score": 0, "max": 10, "label": "No data"},
            "pain_severity": {"score": 0, "max": 10, "label": "No critical issues"},
            "feature_density": {"score": 0, "max": 5, "label": "Low"},
        }
        fb = make_feedback(db, test_organization.id, churn_risk_factors=factors)

        response = client.get(f"/api/v1/feedback/{fb.id}", headers=auth_headers)
        assert response.status_code == 200

        data = response.json()
        factor_keys = set(data["churn_risk_factors"].keys())
        assert factor_keys == {
            "sentiment", "churn_keywords", "frustration_keywords", "urgency",
            "sentiment_trend", "feedback_frequency", "resolution_time",
            "pain_severity", "feature_density",
        }


# ---------------------------------------------------------------------------
# Tests: Customer Health response includes confidence_score
# ---------------------------------------------------------------------------

class TestCustomerHealthConfidenceResponse:
    """GET /api/v1/customer-health/{email} should include confidence_score and confidence_level."""

    def test_customer_health_response_includes_confidence_score(
        self, client: TestClient, db: Session, pro_org: Organization, pro_headers: dict
    ):
        """Customer health response should include confidence_score field."""
        make_customer_health(db, pro_org.id, "customer@example.com", confidence_score=78)

        response = client.get("/api/v1/customer-health/customer@example.com", headers=pro_headers)
        assert response.status_code == 200

        data = response.json()
        assert "confidence_score" in data
        assert data["confidence_score"] == 78

    def test_customer_health_response_includes_confidence_level(
        self, client: TestClient, db: Session, pro_org: Organization, pro_headers: dict
    ):
        """Customer health response should include confidence_level field."""
        make_customer_health(db, pro_org.id, "custo2@example.com", confidence_level="medium")

        response = client.get("/api/v1/customer-health/custo2@example.com", headers=pro_headers)
        assert response.status_code == 200

        data = response.json()
        assert "confidence_level" in data
        assert data["confidence_level"] == "medium"

    def test_customer_health_confidence_score_is_integer(
        self, client: TestClient, db: Session, pro_org: Organization, pro_headers: dict
    ):
        """confidence_score in response should be an integer."""
        make_customer_health(db, pro_org.id, "custo3@example.com", confidence_score=45)

        response = client.get("/api/v1/customer-health/custo3@example.com", headers=pro_headers)
        assert response.status_code == 200

        data = response.json()
        assert isinstance(data["confidence_score"], int)


# ---------------------------------------------------------------------------
# Tests: GET /api/v1/customers/{email}/churn-factors
# ---------------------------------------------------------------------------

class TestChurnFactorsEndpoint:
    """GET /api/v1/customers/{email}/churn-factors — aggregated factors for last 30 days."""

    def test_churn_factors_returns_200_for_pro_user(
        self, client: TestClient, db: Session, pro_org: Organization, pro_headers: dict
    ):
        """Pro user should be able to access churn-factors endpoint."""
        now = datetime.utcnow()
        factors = {
            "sentiment": {"score": 10, "max": 15, "label": "Moderately negative"},
            "churn_keywords": {"score": 5, "max": 15, "label": "1 keyword"},
            "frustration_keywords": {"score": 0, "max": 10, "label": "None"},
            "urgency": {"score": 0, "max": 10, "label": "Not urgent"},
            "sentiment_trend": {"score": 5, "max": 15, "label": "Declining slightly"},
            "feedback_frequency": {"score": 0, "max": 10, "label": "Normal"},
            "resolution_time": {"score": 0, "max": 10, "label": "No data"},
            "pain_severity": {"score": 0, "max": 10, "label": "No critical"},
            "feature_density": {"score": 0, "max": 5, "label": "Low"},
        }
        for i in range(3):
            fb = FeedbackItem(
                organization_id=pro_org.id,
                customer_email="churn@example.com",
                text="Test feedback",
                source="email",
                sentiment_score=-0.5,
                sentiment_label="negative",
                is_urgent=False,
                churn_risk_score=30,
                churn_risk_factors=factors,
                created_at=now - timedelta(days=i),
            )
            db.add(fb)
        db.commit()

        response = client.get("/api/v1/customers/churn@example.com/churn-factors", headers=pro_headers)
        assert response.status_code == 200

    def test_churn_factors_returns_403_for_free_user(
        self, client: TestClient, db: Session, free_org: Organization, free_headers: dict
    ):
        """Free plan users should not be able to access churn-factors endpoint."""
        response = client.get("/api/v1/customers/anyone@example.com/churn-factors", headers=free_headers)
        assert response.status_code == 403

    def test_churn_factors_response_has_customer_email(
        self, client: TestClient, db: Session, pro_org: Organization, pro_headers: dict
    ):
        """Response should include customer_email field."""
        now = datetime.utcnow()
        factors = {k: {"score": 0, "max": 10, "label": "none"} for k in [
            "sentiment", "churn_keywords", "frustration_keywords", "urgency",
            "sentiment_trend", "feedback_frequency", "resolution_time",
            "pain_severity", "feature_density",
        ]}
        fb = FeedbackItem(
            organization_id=pro_org.id,
            customer_email="detail@example.com",
            text="Test",
            source="email",
            sentiment_score=-0.3,
            sentiment_label="negative",
            is_urgent=False,
            churn_risk_score=20,
            churn_risk_factors=factors,
            created_at=now - timedelta(days=5),
        )
        db.add(fb)
        db.commit()

        response = client.get("/api/v1/customers/detail@example.com/churn-factors", headers=pro_headers)
        assert response.status_code == 200

        data = response.json()
        assert data["customer_email"] == "detail@example.com"

    def test_churn_factors_response_has_aggregated_factors(
        self, client: TestClient, db: Session, pro_org: Organization, pro_headers: dict
    ):
        """Response should include aggregated_factors with all 9 factor keys."""
        now = datetime.utcnow()
        factors = {
            "sentiment": {"score": 10, "max": 15, "label": "Moderately negative"},
            "churn_keywords": {"score": 5, "max": 15, "label": "1 churn keyword"},
            "frustration_keywords": {"score": 0, "max": 10, "label": "None"},
            "urgency": {"score": 0, "max": 10, "label": "Not urgent"},
            "sentiment_trend": {"score": 5, "max": 15, "label": "Declining"},
            "feedback_frequency": {"score": 0, "max": 10, "label": "Normal"},
            "resolution_time": {"score": 0, "max": 10, "label": "No data"},
            "pain_severity": {"score": 0, "max": 10, "label": "None"},
            "feature_density": {"score": 0, "max": 5, "label": "Low"},
        }
        for i in range(2):
            fb = FeedbackItem(
                organization_id=pro_org.id,
                customer_email="agg@example.com",
                text="Test feedback",
                source="email",
                sentiment_score=-0.5,
                sentiment_label="negative",
                is_urgent=False,
                churn_risk_score=20,
                churn_risk_factors=factors,
                created_at=now - timedelta(days=i + 1),
            )
            db.add(fb)
        db.commit()

        response = client.get("/api/v1/customers/agg@example.com/churn-factors", headers=pro_headers)
        assert response.status_code == 200

        data = response.json()
        assert "aggregated_factors" in data
        agg = data["aggregated_factors"]
        expected_keys = {
            "sentiment", "churn_keywords", "frustration_keywords", "urgency",
            "sentiment_trend", "feedback_frequency", "resolution_time",
            "pain_severity", "feature_density",
        }
        assert set(agg.keys()) == expected_keys

    def test_churn_factors_response_has_period_days(
        self, client: TestClient, db: Session, pro_org: Organization, pro_headers: dict
    ):
        """Response should include period_days field."""
        fb = FeedbackItem(
            organization_id=pro_org.id,
            customer_email="period@example.com",
            text="Test",
            source="email",
            sentiment_score=-0.3,
            sentiment_label="negative",
            is_urgent=False,
            churn_risk_score=20,
            churn_risk_factors={"sentiment": {"score": 5, "max": 15, "label": "test"}},
            created_at=datetime.utcnow() - timedelta(days=5),
        )
        db.add(fb)
        db.commit()

        response = client.get("/api/v1/customers/period@example.com/churn-factors", headers=pro_headers)
        assert response.status_code == 200

        data = response.json()
        assert "period_days" in data
        assert data["period_days"] == 30

    def test_churn_factors_returns_404_for_unknown_customer(
        self, client: TestClient, db: Session, pro_org: Organization, pro_headers: dict
    ):
        """Should return 404 when no feedback found for this customer in the org."""
        response = client.get("/api/v1/customers/nobody@example.com/churn-factors", headers=pro_headers)
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Tests: POST /api/v1/admin/backtest
# ---------------------------------------------------------------------------

class TestBacktestEndpoint:
    """POST /api/v1/admin/backtest — system_admin only backtest endpoint."""

    def test_backtest_requires_system_admin(
        self, client: TestClient, db: Session, pro_org: Organization, pro_headers: dict
    ):
        """Non-system-admin user should get 403."""
        response = client.post("/api/v1/admin/backtest", headers=pro_headers, json={"churn_days": 30})
        assert response.status_code == 403

    def test_backtest_accessible_by_system_admin(
        self, client: TestClient, db: Session, pro_org: Organization, admin_headers: dict
    ):
        """System admin should be able to access the backtest endpoint."""
        response = client.post("/api/v1/admin/backtest", headers=admin_headers, json={"churn_days": 30})
        # Should not be 403 or 401
        assert response.status_code not in (401, 403)

    def test_backtest_returns_period_days(
        self, client: TestClient, db: Session, pro_org: Organization, admin_headers: dict
    ):
        """Backtest response should include period_days."""
        response = client.post("/api/v1/admin/backtest", headers=admin_headers, json={"churn_days": 30})
        assert response.status_code == 200

        data = response.json()
        assert "period_days" in data
        assert data["period_days"] == 30

    def test_backtest_returns_customers_evaluated(
        self, client: TestClient, db: Session, pro_org: Organization, admin_headers: dict
    ):
        """Backtest response should include customers_evaluated count."""
        response = client.post("/api/v1/admin/backtest", headers=admin_headers, json={"churn_days": 30})
        assert response.status_code == 200

        data = response.json()
        assert "customers_evaluated" in data
        assert isinstance(data["customers_evaluated"], int)

    def test_backtest_returns_churn_risk_metrics(
        self, client: TestClient, db: Session, pro_org: Organization, admin_headers: dict
    ):
        """Backtest response should include churn_risk_metrics with precision/recall/F1."""
        response = client.post("/api/v1/admin/backtest", headers=admin_headers, json={"churn_days": 30})
        assert response.status_code == 200

        data = response.json()
        assert "churn_risk_metrics" in data
        metrics = data["churn_risk_metrics"]
        assert "precision" in metrics
        assert "recall" in metrics
        assert "f1" in metrics
        assert "accuracy" in metrics
        assert "threshold" in metrics

    def test_backtest_returns_health_score_metrics(
        self, client: TestClient, db: Session, pro_org: Organization, admin_headers: dict
    ):
        """Backtest response should include health_score_metrics with precision/recall/F1."""
        response = client.post("/api/v1/admin/backtest", headers=admin_headers, json={"churn_days": 30})
        assert response.status_code == 200

        data = response.json()
        assert "health_score_metrics" in data
        metrics = data["health_score_metrics"]
        assert "precision" in metrics
        assert "recall" in metrics
        assert "f1" in metrics
        assert "accuracy" in metrics

    def test_backtest_default_churn_days_is_30(
        self, client: TestClient, db: Session, pro_org: Organization, admin_headers: dict
    ):
        """Default churn_days should be 30 when not specified."""
        response = client.post("/api/v1/admin/backtest", headers=admin_headers, json={})
        assert response.status_code == 200

        data = response.json()
        assert data["period_days"] == 30

    def test_backtest_custom_churn_days(
        self, client: TestClient, db: Session, pro_org: Organization, admin_headers: dict
    ):
        """Custom churn_days should be reflected in response."""
        response = client.post("/api/v1/admin/backtest", headers=admin_headers, json={"churn_days": 60})
        assert response.status_code == 200

        data = response.json()
        assert data["period_days"] == 60
