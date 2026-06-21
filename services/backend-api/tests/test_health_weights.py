"""
TDD tests for Feature B2: Configurable health-score weights.

Tests cover:
- GET /api/v1/categories/health-weights — returns defaults when no OrgAIConfig
- PUT /api/v1/categories/health-weights — persists valid weights
- PUT with sum ≠ 100 returns 422
- health_score_service uses org's configured weights (different weights → different score)
- Category type 'urgency' accepted by POST /api/v1/categories/custom

RED phase: all tests must fail before production code is written.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.models.organization import Organization
from src.models.user import User
from src.models.org_ai_config import OrgAIConfig
from src.api.auth import hash_password, create_access_token


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def owner_user(db: Session, test_organization: Organization) -> User:
    user = User(
        email="hw_owner@test.com",
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
def member_user(db: Session, test_organization: Organization) -> User:
    user = User(
        email="hw_member@test.com",
        password_hash=hash_password("password123"),
        organization_id=test_organization.id,
        role="member",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def member_headers(member_user: User) -> dict:
    token = create_access_token({
        "user_id": member_user.id,
        "organization_id": member_user.organization_id,
        "role": member_user.role,
    })
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# B2 — GET health-weights
# ---------------------------------------------------------------------------

class TestGetHealthWeights:
    def test_returns_defaults_when_no_config(self, client: TestClient, auth_headers: dict):
        """With no OrgAIConfig row, defaults (35/25/25/15) are returned."""
        response = client.get("/api/v1/categories/health-weights", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["churn"] == 35
        assert data["sentiment"] == 25
        assert data["resolution"] == 25
        assert data["frequency"] == 15

    def test_returns_configured_weights(self, client: TestClient, auth_headers: dict,
                                        db: Session, test_organization: Organization):
        """When OrgAIConfig row exists, the stored weights are returned."""
        config = OrgAIConfig(
            organization_id=test_organization.id,
            health_weight_churn=40,
            health_weight_sentiment=30,
            health_weight_resolution=20,
            health_weight_frequency=10,
        )
        db.add(config)
        db.commit()

        response = client.get("/api/v1/categories/health-weights", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["churn"] == 40
        assert data["sentiment"] == 30
        assert data["resolution"] == 20
        assert data["frequency"] == 10

    def test_requires_auth(self, client: TestClient):
        response = client.get("/api/v1/categories/health-weights")
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# B2 — PUT health-weights
# ---------------------------------------------------------------------------

class TestPutHealthWeights:
    def test_creates_config_and_persists_weights(self, client: TestClient, owner_headers: dict,
                                                   db: Session, test_organization: Organization):
        """PUT with valid sum=100 should create/update OrgAIConfig and return the weights."""
        response = client.put(
            "/api/v1/categories/health-weights",
            headers=owner_headers,
            json={"churn": 40, "sentiment": 20, "resolution": 25, "frequency": 15},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["churn"] == 40
        assert data["sentiment"] == 20
        assert data["resolution"] == 25
        assert data["frequency"] == 15

        # Verify persisted in DB
        config = db.query(OrgAIConfig).filter_by(
            organization_id=test_organization.id
        ).first()
        assert config is not None
        assert config.health_weight_churn == 40
        assert config.health_weight_frequency == 15

    def test_updates_existing_config(self, client: TestClient, owner_headers: dict,
                                      db: Session, test_organization: Organization):
        """PUT should update an existing OrgAIConfig row."""
        config = OrgAIConfig(
            organization_id=test_organization.id,
            health_weight_churn=35,
            health_weight_sentiment=25,
            health_weight_resolution=25,
            health_weight_frequency=15,
        )
        db.add(config)
        db.commit()

        response = client.put(
            "/api/v1/categories/health-weights",
            headers=owner_headers,
            json={"churn": 50, "sentiment": 20, "resolution": 20, "frequency": 10},
        )
        assert response.status_code == 200
        assert response.json()["churn"] == 50

        db.refresh(config)
        assert config.health_weight_churn == 50

    def test_rejects_sum_not_100(self, client: TestClient, owner_headers: dict):
        """PUT with weights that do not sum to 100 must return 422."""
        response = client.put(
            "/api/v1/categories/health-weights",
            headers=owner_headers,
            json={"churn": 40, "sentiment": 30, "resolution": 20, "frequency": 20},
        )
        assert response.status_code == 422

    def test_rejects_sum_less_than_100(self, client: TestClient, owner_headers: dict):
        """PUT with weights summing to 95 must return 422."""
        response = client.put(
            "/api/v1/categories/health-weights",
            headers=owner_headers,
            json={"churn": 30, "sentiment": 25, "resolution": 25, "frequency": 15},
        )
        assert response.status_code == 422

    def test_rejects_negative_weight(self, client: TestClient, owner_headers: dict):
        """PUT with a negative weight must return 422."""
        response = client.put(
            "/api/v1/categories/health-weights",
            headers=owner_headers,
            json={"churn": -10, "sentiment": 50, "resolution": 40, "frequency": 20},
        )
        assert response.status_code == 422

    def test_member_cannot_update_weights(self, client: TestClient, member_headers: dict):
        """Members must not update health weights (admin/owner only)."""
        response = client.put(
            "/api/v1/categories/health-weights",
            headers=member_headers,
            json={"churn": 35, "sentiment": 25, "resolution": 25, "frequency": 15},
        )
        assert response.status_code == 403

    def test_requires_auth(self, client: TestClient):
        response = client.put(
            "/api/v1/categories/health-weights",
            json={"churn": 35, "sentiment": 25, "resolution": 25, "frequency": 15},
        )
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# B2 — health_score_service uses org weights
# ---------------------------------------------------------------------------

class TestHealthScoreServiceUsesOrgWeights:
    """health_score_service.compute_health_score() must use per-org weights."""

    def _make_feedback(self, db, org_id, email, churn_score=50, sentiment=0.0):
        from src.models.feedback import FeedbackItem
        from datetime import datetime
        fb = FeedbackItem(
            organization_id=org_id,
            customer_email=email,
            text="test feedback",
            source="email",
            sentiment_score=sentiment,
            sentiment_label="neutral",
            churn_risk_score=churn_score,
            is_urgent=False,
            created_at=datetime.utcnow(),
        )
        db.add(fb)
        db.commit()
        db.refresh(fb)
        return fb

    def test_default_weights_produce_expected_score(self, db: Session, test_organization: Organization):
        """With no OrgAIConfig, defaults (35/25/25/15) are used."""
        from src.services.health_score_service import compute_health_score

        email = "defaults@example.com"
        self._make_feedback(db, test_organization.id, email, churn_score=0, sentiment=1.0)

        result = compute_health_score(test_organization.id, email, db)
        assert result["health_score"] > 0  # Sanity

    def test_different_weights_produce_different_score(self, db: Session, test_organization: Organization):
        """Changing weights must produce a different final score."""
        from src.services.health_score_service import compute_health_score

        email = "weights@example.com"
        # churn_risk_score=0 (inverted → churn_component=100), sentiment=0 (→50)
        self._make_feedback(db, test_organization.id, email, churn_score=0, sentiment=0.0)

        # Default weights: 35% churn, 25% sentiment, 25% resolution, 15% frequency
        score_default = compute_health_score(test_organization.id, email, db)["health_score"]

        # Now set a churn-heavy config: 70% churn, 10% sentiment, 10% resolution, 10% frequency
        config = OrgAIConfig(
            organization_id=test_organization.id,
            health_weight_churn=70,
            health_weight_sentiment=10,
            health_weight_resolution=10,
            health_weight_frequency=10,
        )
        db.add(config)
        db.commit()

        score_custom = compute_health_score(test_organization.id, email, db)["health_score"]

        # With churn_component=100 and 70% weight, custom score must be higher
        assert score_custom != score_default
        assert score_custom > score_default

    def test_weights_are_read_from_org_ai_config(self, db: Session, test_organization: Organization):
        """compute_health_score reads weights from OrgAIConfig, not hard-coded constants."""
        from src.services.health_score_service import compute_health_score

        email = "orgweights@example.com"
        # Create feedback with churn_score=0 (churn_component=100) but bad sentiment
        self._make_feedback(db, test_organization.id, email, churn_score=0, sentiment=-1.0)

        # Sentiment-heavy config: churn=10, sentiment=80, resolution=5, frequency=5
        config = OrgAIConfig(
            organization_id=test_organization.id,
            health_weight_churn=10,
            health_weight_sentiment=80,
            health_weight_resolution=5,
            health_weight_frequency=5,
        )
        db.add(config)
        db.commit()

        result = compute_health_score(test_organization.id, email, db)
        # sentiment_component for -1.0 = int((-1+1)*50) = 0
        # With 80% weight on bad sentiment, score should be low
        assert result["health_score"] < 50


# ---------------------------------------------------------------------------
# B1 — categories.py: urgency type accepted in create/update
# ---------------------------------------------------------------------------

class TestUrgencyCategoryType:
    """POST /api/v1/categories/custom must accept category_type='urgency'."""

    @pytest.fixture
    def owner_user_b1(self, db: Session, test_organization: Organization) -> User:
        user = User(
            email="b1owner@test.com",
            password_hash=hash_password("password123"),
            organization_id=test_organization.id,
            role="owner",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    @pytest.fixture
    def owner_headers_b1(self, owner_user_b1: User) -> dict:
        token = create_access_token({
            "user_id": owner_user_b1.id,
            "organization_id": owner_user_b1.organization_id,
            "role": owner_user_b1.role,
        })
        return {"Authorization": f"Bearer {token}"}

    def test_create_urgency_category(self, client: TestClient, owner_headers_b1: dict):
        """Creating a category with category_type='urgency' should return 201."""
        response = client.post(
            "/api/v1/categories/custom",
            headers=owner_headers_b1,
            json={
                "name": "gdpr_breach",
                "description": "GDPR data breach requiring immediate response",
                "category_type": "urgency",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "gdpr_breach"
        assert data["category_type"] == "urgency"

    def test_list_urgency_categories(self, client: TestClient, auth_headers: dict,
                                      db: Session, test_organization: Organization):
        """GET /api/v1/categories/custom?category_type=urgency should return urgency categories."""
        from src.models.custom_category import CustomCategory
        cat = CustomCategory(
            organization_id=test_organization.id,
            name="regulatory_alert",
            description="Regulatory compliance alerts",
            category_type="urgency",
        )
        db.add(cat)
        db.commit()

        response = client.get(
            "/api/v1/categories/custom?category_type=urgency",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == "regulatory_alert"
        assert data[0]["category_type"] == "urgency"
