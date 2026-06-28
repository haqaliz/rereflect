"""
Phase 1 — RED: Characterization tests for compute_health_score() score stability.

These tests lock the current output of compute_health_score() and _get_org_weights()
before the usage component is added. They must stay GREEN (byte-identical output)
through all subsequent phases, proving that health_weight_usage=0 changes nothing.
"""
import pytest
from datetime import datetime
from sqlalchemy.orm import Session

from src.models.organization import Organization
from src.models.feedback import FeedbackItem
from src.services.health_score_service import compute_health_score, _get_org_weights


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
    OrgAIConfig row for the org.  Before Phase 3, only 4 keys exist and they
    sum to exactly 1.0.
    """

    def test_returns_four_keys(self, db: Session, test_organization: Organization):
        """Default weights dict has exactly 4 keys."""
        weights = _get_org_weights(test_organization.id, db)
        assert set(weights.keys()) == {"churn_risk", "sentiment", "resolution", "frequency"}

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
