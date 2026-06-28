"""
Phase 1 — RED: Characterization tests for compute_health_score() score stability.
Phase 3 — Usage component math tests (wired at weight 0 by default).
Phase 4 — Health-weights API accepts 5 components summing to 100.

These tests lock the current output of compute_health_score() and _get_org_weights()
before and after the usage component is added. They must stay GREEN (byte-identical
output) through all subsequent phases, proving that health_weight_usage=0 changes nothing.
"""
import pytest
from datetime import datetime
from unittest.mock import patch
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.models.organization import Organization
from src.models.org_ai_config import OrgAIConfig
from src.models.feedback import FeedbackItem
from src.models.user import User
from src.api.auth import hash_password, create_access_token
from src.services.health_score_service import (
    compute_health_score,
    _get_org_weights,
    _compute_usage_component,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_feedback(db, org_id, email, sentiment_score, churn_risk_score):
    """Create a FeedbackItem directly in the DB."""
    fb = FeedbackItem(
        organization_id=org_id,
        customer_email=email,
        text="characterization test feedback",
        source="email",
        sentiment_score=sentiment_score,
        sentiment_label="neutral",
        churn_risk_score=churn_risk_score,
        is_urgent=False,
        created_at=datetime.utcnow(),
    )
    db.add(fb)
    db.commit()
    db.refresh(fb)
    return fb


# ---------------------------------------------------------------------------
# Score stability characterization — must pass before AND after usage columns
# ---------------------------------------------------------------------------

class TestScoreStabilityCharacterization:
    """
    Snapshot of compute_health_score() output with 3 feedbacks and default
    weights (no OrgAIConfig row, i.e. health_weight_usage effectively 0).

    Hardcoded expected values captured 2026-06-28 by running the probe script.
    These values MUST remain byte-identical after Phase 2 (migration+columns)
    and Phase 3 (usage component wired at weight 0).
    """

    # Fixture email — unique across the test suite
    EMAIL = "char_stability@example.com"

    @pytest.fixture(autouse=True)
    def seed(self, db: Session, test_organization: Organization):
        """Seed 3 feedbacks with known sentiment + churn values."""
        # (sentiment_score, churn_risk_score)
        rows = [(0.5, 30), (-0.2, 60), (0.1, 45)]
        for sentiment, churn in rows:
            _make_feedback(db, test_organization.id, self.EMAIL, sentiment, churn)

    def test_health_score_snapshot(self, db: Session, test_organization: Organization):
        """health_score must equal 47 — the captured snapshot value."""
        result = compute_health_score(test_organization.id, self.EMAIL, db)
        assert result["health_score"] == 47

    def test_churn_risk_component_snapshot(self, db: Session, test_organization: Organization):
        """churn_risk_component must equal 55."""
        result = compute_health_score(test_organization.id, self.EMAIL, db)
        assert result["churn_risk_component"] == 55

    def test_sentiment_component_snapshot(self, db: Session, test_organization: Organization):
        """sentiment_component must equal 56."""
        result = compute_health_score(test_organization.id, self.EMAIL, db)
        assert result["sentiment_component"] == 56

    def test_resolution_component_snapshot(self, db: Session, test_organization: Organization):
        """resolution_component must equal 50 (no resolution data → neutral)."""
        result = compute_health_score(test_organization.id, self.EMAIL, db)
        assert result["resolution_component"] == 50

    def test_frequency_component_snapshot(self, db: Session, test_organization: Organization):
        """frequency_component must equal 10."""
        result = compute_health_score(test_organization.id, self.EMAIL, db)
        assert result["frequency_component"] == 10

    def test_risk_level_snapshot(self, db: Session, test_organization: Organization):
        """risk_level must equal 'at_risk'."""
        result = compute_health_score(test_organization.id, self.EMAIL, db)
        assert result["risk_level"] == "at_risk"

    def test_feedback_count_snapshot(self, db: Session, test_organization: Organization):
        """feedback_count must equal 3."""
        result = compute_health_score(test_organization.id, self.EMAIL, db)
        assert result["feedback_count"] == 3

    def test_confidence_level_snapshot(self, db: Session, test_organization: Organization):
        """confidence_level must equal 'medium' (3 feedbacks)."""
        result = compute_health_score(test_organization.id, self.EMAIL, db)
        assert result["confidence_level"] == "medium"

    def test_customer_name_snapshot(self, db: Session, test_organization: Organization):
        """customer_name must be None (no source_metadata on feedbacks)."""
        result = compute_health_score(test_organization.id, self.EMAIL, db)
        assert result["customer_name"] is None

    def test_last_feedback_at_not_none(self, db: Session, test_organization: Organization):
        """last_feedback_at must be a datetime (not None)."""
        result = compute_health_score(test_organization.id, self.EMAIL, db)
        assert result["last_feedback_at"] is not None
        assert isinstance(result["last_feedback_at"], datetime)


# ---------------------------------------------------------------------------
# _get_org_weights — 4 weights summing to 1.0 when no OrgAIConfig row exists
# ---------------------------------------------------------------------------

class TestGetOrgWeightsDefaultsBeforeUsageColumn:
    """
    _get_org_weights falls back to module-level WEIGHTS dict when there is no
    OrgAIConfig row for the org.  After Phase 3, 5 keys exist (usage added at 0.0)
    and they still sum to exactly 1.0.

    NOTE: Originally written as a 4-key assertion; updated to 5 keys after Phase 3
    wires the usage component into WEIGHTS with default 0.0.
    """

    def test_returns_five_keys_with_usage_default(self, db: Session, test_organization: Organization):
        """Default weights dict has exactly 5 keys including 'usage' at 0.0."""
        weights = _get_org_weights(test_organization.id, db)
        assert set(weights.keys()) == {"churn_risk", "sentiment", "resolution", "frequency", "usage"}

    def test_default_usage_weight_is_zero(self, db: Session, test_organization: Organization):
        """Default usage weight is 0.0 (opt-in, no existing scores change)."""
        weights = _get_org_weights(test_organization.id, db)
        assert weights["usage"] == pytest.approx(0.0)

    def test_sum_equals_one(self, db: Session, test_organization: Organization):
        """Default weights sum to exactly 1.0."""
        weights = _get_org_weights(test_organization.id, db)
        assert sum(weights.values()) == pytest.approx(1.0)

    def test_default_churn_weight(self, db: Session, test_organization: Organization):
        """Default churn_risk weight is 0.35."""
        weights = _get_org_weights(test_organization.id, db)
        assert weights["churn_risk"] == pytest.approx(0.35)

    def test_default_sentiment_weight(self, db: Session, test_organization: Organization):
        """Default sentiment weight is 0.25."""
        weights = _get_org_weights(test_organization.id, db)
        assert weights["sentiment"] == pytest.approx(0.25)

    def test_default_resolution_weight(self, db: Session, test_organization: Organization):
        """Default resolution weight is 0.25."""
        weights = _get_org_weights(test_organization.id, db)
        assert weights["resolution"] == pytest.approx(0.25)

    def test_default_frequency_weight(self, db: Session, test_organization: Organization):
        """Default frequency weight is 0.15."""
        weights = _get_org_weights(test_organization.id, db)
        assert weights["frequency"] == pytest.approx(0.15)


# ---------------------------------------------------------------------------
# Phase 3 — Usage component math
# ---------------------------------------------------------------------------

class TestComputeUsageComponentFallback:
    """
    _compute_usage_component must NEVER raise, even when customer_usage table
    does not exist.  It falls back to 50 (neutral).
    """

    def test_returns_50_when_no_customer_usage_table(
        self, db: Session, test_organization: Organization
    ):
        """Missing customer_usage table (or row) returns 50, never raises."""
        result = _compute_usage_component(
            db, test_organization.id, "norollup@example.com", datetime.utcnow()
        )
        assert result == 50

    def test_never_raises_on_missing_table(
        self, db: Session, test_organization: Organization
    ):
        """_compute_usage_component is safe even on unexpected DB errors."""
        # No customer_usage table exists in the in-memory test DB — must not raise
        try:
            val = _compute_usage_component(
                db, test_organization.id, "safe@example.com", datetime.utcnow()
            )
        except Exception as exc:
            pytest.fail(f"_compute_usage_component raised unexpectedly: {exc}")
        assert isinstance(val, int)


class TestGetOrgWeightsWithUsageColumn:
    """
    After Phase 3, _get_org_weights returns 5 keys.
    With health_weight_usage=0 (default) the usage key is 0.0 and the total
    is still 1.0 (35+25+25+15+0 = 100).
    """

    def test_returns_five_keys_when_config_exists(
        self, db: Session, test_organization: Organization
    ):
        """With an OrgAIConfig row, _get_org_weights returns 5 keys."""
        config = OrgAIConfig(
            organization_id=test_organization.id,
            health_weight_churn=35,
            health_weight_sentiment=25,
            health_weight_resolution=25,
            health_weight_frequency=15,
            health_weight_usage=0,
        )
        db.add(config)
        db.commit()

        weights = _get_org_weights(test_organization.id, db)
        assert "usage" in weights
        assert len(weights) == 5

    def test_usage_weight_zero_by_default(
        self, db: Session, test_organization: Organization
    ):
        """Default usage weight is 0.0."""
        config = OrgAIConfig(
            organization_id=test_organization.id,
            health_weight_churn=35,
            health_weight_sentiment=25,
            health_weight_resolution=25,
            health_weight_frequency=15,
            health_weight_usage=0,
        )
        db.add(config)
        db.commit()

        weights = _get_org_weights(test_organization.id, db)
        assert weights["usage"] == pytest.approx(0.0)

    def test_sum_still_one_with_default_usage(
        self, db: Session, test_organization: Organization
    ):
        """35+25+25+15+0 = 100 → weights sum to 1.0."""
        config = OrgAIConfig(
            organization_id=test_organization.id,
            health_weight_churn=35,
            health_weight_sentiment=25,
            health_weight_resolution=25,
            health_weight_frequency=15,
            health_weight_usage=0,
        )
        db.add(config)
        db.commit()

        weights = _get_org_weights(test_organization.id, db)
        assert sum(weights.values()) == pytest.approx(1.0)


class TestScoreMovesWhenUsageWeightRaised:
    """
    When health_weight_usage > 0 and the usage component differs from the other
    components, compute_health_score() must produce a different score than at
    weight 0, proving the component is wired into the aggregation.
    """

    EMAIL = "usage_weight_test@example.com"

    @pytest.fixture(autouse=True)
    def seed(self, db: Session, test_organization: Organization):
        """Seed 3 feedbacks so other components have real values."""
        rows = [(0.5, 30), (-0.2, 60), (0.1, 45)]
        for sentiment, churn in rows:
            _make_feedback(db, test_organization.id, self.EMAIL, sentiment, churn)

    def test_score_differs_when_usage_weight_nonzero_and_low_usage_score(
        self, db: Session, test_organization: Organization
    ):
        """
        Set usage weight to 10, mock _compute_usage_component to return 20 (low usage).
        Score at weight 10 must differ from weight 0 baseline (47).
        """
        config = OrgAIConfig(
            organization_id=test_organization.id,
            health_weight_churn=35,
            health_weight_sentiment=20,
            health_weight_resolution=20,
            health_weight_frequency=15,
            health_weight_usage=10,
        )
        db.add(config)
        db.commit()

        # Mock usage component to return a distinctly low value
        with patch(
            "src.services.health_score_service._compute_usage_component",
            return_value=20,
        ):
            result = compute_health_score(test_organization.id, self.EMAIL, db)

        # The score must be valid but not equal to the baseline 47 since weights changed
        assert 0 <= result["health_score"] <= 100
        # With usage weight 10, sentiment/resolution each 20, and usage_score=20 (low),
        # the score must shift relative to the 35/25/25/15 baseline
        assert result["health_score"] != 47  # baseline was 47 with default weights

    def test_weight_zero_still_returns_baseline_even_with_config(
        self, db: Session, test_organization: Organization
    ):
        """
        With health_weight_usage=0 (and other weights matching defaults), the score
        must be 47 regardless of usage_component value — usage is neutralized.
        """
        config = OrgAIConfig(
            organization_id=test_organization.id,
            health_weight_churn=35,
            health_weight_sentiment=25,
            health_weight_resolution=25,
            health_weight_frequency=15,
            health_weight_usage=0,
        )
        db.add(config)
        db.commit()

        # Even with an extreme usage_component, weight=0 means it doesn't affect the total
        with patch(
            "src.services.health_score_service._compute_usage_component",
            return_value=0,  # extreme low value
        ):
            result = compute_health_score(test_organization.id, self.EMAIL, db)

        assert result["health_score"] == 47  # unchanged from baseline


# ---------------------------------------------------------------------------
# Phase 4 — Health-weights API: 5-field validation + GET/PUT
# ---------------------------------------------------------------------------

@pytest.fixture
def owner_user_p4(db: Session, test_organization: Organization) -> User:
    user = User(
        email="p4_owner@example.com",
        password_hash=hash_password("password123"),
        organization_id=test_organization.id,
        role="owner",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def owner_headers_p4(owner_user_p4: User) -> dict:
    token = create_access_token({
        "user_id": owner_user_p4.id,
        "organization_id": owner_user_p4.organization_id,
        "role": owner_user_p4.role,
    })
    return {"Authorization": f"Bearer {token}"}


class TestHealthWeightsApiPhase4:
    """
    Phase 4 — GET returns 5 keys; PUT accepts explicit usage weight; validator
    covers all 5 fields when checking sum=100.
    """

    def test_get_returns_usage_key_with_default_zero(
        self, client: TestClient, owner_headers_p4: dict
    ):
        """GET /api/v1/categories/health-weights must include 'usage': 0 in response."""
        response = client.get("/api/v1/categories/health-weights", headers=owner_headers_p4)
        assert response.status_code == 200
        data = response.json()
        assert "usage" in data
        assert data["usage"] == 0

    def test_put_with_5_fields_summing_100_returns_200(
        self, client: TestClient, owner_headers_p4: dict
    ):
        """PUT with 5 fields summing to 100 (35/25/25/15/0) returns 200."""
        response = client.put(
            "/api/v1/categories/health-weights",
            headers=owner_headers_p4,
            json={"churn": 35, "sentiment": 25, "resolution": 25, "frequency": 15, "usage": 0},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["usage"] == 0

    def test_put_with_nonzero_usage_persists_health_weight_usage(
        self, client: TestClient, owner_headers_p4: dict,
        db: Session, test_organization: Organization
    ):
        """PUT with usage=10 (35/20/20/15/10=100) persists health_weight_usage=10."""
        response = client.put(
            "/api/v1/categories/health-weights",
            headers=owner_headers_p4,
            json={"churn": 35, "sentiment": 20, "resolution": 20, "frequency": 15, "usage": 10},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["usage"] == 10

        # Verify DB persistence
        config = db.query(OrgAIConfig).filter_by(organization_id=test_organization.id).first()
        assert config is not None
        assert config.health_weight_usage == 10

    def test_put_5_fields_not_summing_100_returns_422(
        self, client: TestClient, owner_headers_p4: dict
    ):
        """PUT with 5 fields that sum to 110 returns 422."""
        response = client.put(
            "/api/v1/categories/health-weights",
            headers=owner_headers_p4,
            json={"churn": 35, "sentiment": 25, "resolution": 25, "frequency": 15, "usage": 10},
        )
        assert response.status_code == 422

    def test_put_4_fields_still_works_with_usage_defaulting_to_zero(
        self, client: TestClient, owner_headers_p4: dict
    ):
        """PUT with only 4 fields (usage omitted, defaults to 0) still returns 200 if sum=100."""
        response = client.put(
            "/api/v1/categories/health-weights",
            headers=owner_headers_p4,
            json={"churn": 35, "sentiment": 25, "resolution": 25, "frequency": 15},
        )
        assert response.status_code == 200
        assert response.json()["usage"] == 0

    def test_get_returns_configured_usage_weight(
        self, client: TestClient, owner_headers_p4: dict,
        db: Session, test_organization: Organization
    ):
        """GET returns the persisted usage weight, not zero, after PUT with usage=5."""
        # First PUT to set usage=5
        client.put(
            "/api/v1/categories/health-weights",
            headers=owner_headers_p4,
            json={"churn": 35, "sentiment": 25, "resolution": 25, "frequency": 10, "usage": 5},
        )
        response = client.get("/api/v1/categories/health-weights", headers=owner_headers_p4)
        assert response.status_code == 200
        assert response.json()["usage"] == 5
