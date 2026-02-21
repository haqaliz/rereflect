"""
TDD tests for churn prediction accuracy data model changes (M1.4 Phase 1):
- FeedbackItem.churn_risk_factors (JSON, nullable)
- CustomerHealth.confidence_score (Integer, default=0)
"""
import pytest
from sqlalchemy.orm import Session

from src.models.feedback import FeedbackItem
from src.models.customer_health import CustomerHealth
from src.models.organization import Organization


class TestFeedbackItemChurnRiskFactors:
    """FeedbackItem should have a churn_risk_factors JSON column that accepts factor dict data."""

    def test_feedback_item_has_churn_risk_factors_attribute(self, db: Session, test_organization: Organization):
        """FeedbackItem model should have a churn_risk_factors attribute."""
        feedback = FeedbackItem(
            organization_id=test_organization.id,
            text="Test feedback",
            source="email",
        )
        assert hasattr(feedback, "churn_risk_factors")

    def test_churn_risk_factors_defaults_to_none(self, db: Session, test_organization: Organization):
        """churn_risk_factors should default to None (nullable)."""
        feedback = FeedbackItem(
            organization_id=test_organization.id,
            text="Test feedback",
            source="email",
        )
        db.add(feedback)
        db.commit()
        db.refresh(feedback)
        assert feedback.churn_risk_factors is None

    def test_churn_risk_factors_stores_factor_dict(self, db: Session, test_organization: Organization):
        """churn_risk_factors should accept and persist a factor breakdown dictionary."""
        factors = {
            "sentiment": {"score": 15, "max": 15, "label": "Very negative sentiment"},
            "churn_keywords": {"score": 10, "max": 15, "label": "2 churn keywords found"},
            "frustration_keywords": {"score": 5, "max": 10, "label": "1 frustration keyword"},
            "urgency": {"score": 10, "max": 10, "label": "Marked as urgent"},
            "sentiment_trend": {"score": 15, "max": 15, "label": "Sentiment declining sharply"},
            "feedback_frequency": {"score": 5, "max": 10, "label": "Complaint frequency increasing"},
            "resolution_time": {"score": 10, "max": 10, "label": "Average resolution > 7 days"},
            "pain_severity": {"score": 5, "max": 10, "label": "1 critical pain point"},
            "feature_density": {"score": 0, "max": 5, "label": "Low feature request ratio"},
        }
        feedback = FeedbackItem(
            organization_id=test_organization.id,
            text="This product is terrible, I am cancelling",
            source="email",
            churn_risk_factors=factors,
        )
        db.add(feedback)
        db.commit()
        db.refresh(feedback)

        assert feedback.churn_risk_factors is not None
        assert feedback.churn_risk_factors["sentiment"]["score"] == 15
        assert feedback.churn_risk_factors["churn_keywords"]["label"] == "2 churn keywords found"

    def test_churn_risk_factors_stores_all_nine_factors(self, db: Session, test_organization: Organization):
        """churn_risk_factors should store all 9 expected factor keys."""
        expected_keys = {
            "sentiment", "churn_keywords", "frustration_keywords", "urgency",
            "sentiment_trend", "feedback_frequency", "resolution_time",
            "pain_severity", "feature_density",
        }
        factors = {key: {"score": 0, "max": 10, "label": "test"} for key in expected_keys}
        feedback = FeedbackItem(
            organization_id=test_organization.id,
            text="Test feedback",
            source="email",
            churn_risk_factors=factors,
        )
        db.add(feedback)
        db.commit()
        db.refresh(feedback)

        assert set(feedback.churn_risk_factors.keys()) == expected_keys

    def test_churn_risk_factors_can_be_updated(self, db: Session, test_organization: Organization):
        """churn_risk_factors should be updatable after initial creation."""
        feedback = FeedbackItem(
            organization_id=test_organization.id,
            text="Test feedback",
            source="email",
            churn_risk_factors=None,
        )
        db.add(feedback)
        db.commit()

        # Now update with factors
        factors = {"sentiment": {"score": 10, "max": 15, "label": "Negative sentiment"}}
        feedback.churn_risk_factors = factors
        db.commit()
        db.refresh(feedback)

        assert feedback.churn_risk_factors is not None
        assert feedback.churn_risk_factors["sentiment"]["score"] == 10


class TestCustomerHealthConfidenceScore:
    """CustomerHealth should have a confidence_score Integer column defaulting to 0."""

    def test_customer_health_has_confidence_score_attribute(self, db: Session, test_organization: Organization):
        """CustomerHealth model should have a confidence_score attribute."""
        health = CustomerHealth(
            organization_id=test_organization.id,
            customer_email="test@example.com",
        )
        assert hasattr(health, "confidence_score")

    def test_confidence_score_defaults_to_zero(self, db: Session, test_organization: Organization):
        """confidence_score should default to 0."""
        health = CustomerHealth(
            organization_id=test_organization.id,
            customer_email="test@example.com",
        )
        db.add(health)
        db.commit()
        db.refresh(health)
        assert health.confidence_score == 0

    def test_confidence_score_accepts_integer_values(self, db: Session, test_organization: Organization):
        """confidence_score should accept integer values in 0-100 range."""
        health = CustomerHealth(
            organization_id=test_organization.id,
            customer_email="score@example.com",
            confidence_score=75,
        )
        db.add(health)
        db.commit()
        db.refresh(health)
        assert health.confidence_score == 75

    def test_confidence_score_stores_max_value(self, db: Session, test_organization: Organization):
        """confidence_score should accept 100 as maximum value."""
        health = CustomerHealth(
            organization_id=test_organization.id,
            customer_email="max@example.com",
            confidence_score=100,
        )
        db.add(health)
        db.commit()
        db.refresh(health)
        assert health.confidence_score == 100

    def test_confidence_score_stores_min_value(self, db: Session, test_organization: Organization):
        """confidence_score should accept 0 as minimum value."""
        health = CustomerHealth(
            organization_id=test_organization.id,
            customer_email="min@example.com",
            confidence_score=0,
        )
        db.add(health)
        db.commit()
        db.refresh(health)
        assert health.confidence_score == 0

    def test_confidence_score_can_be_updated(self, db: Session, test_organization: Organization):
        """confidence_score should be updatable after initial creation."""
        health = CustomerHealth(
            organization_id=test_organization.id,
            customer_email="update@example.com",
            confidence_score=0,
        )
        db.add(health)
        db.commit()

        health.confidence_score = 55
        db.commit()
        db.refresh(health)

        assert health.confidence_score == 55

    def test_confidence_score_independent_of_confidence_level(self, db: Session, test_organization: Organization):
        """confidence_score (0-100 int) and confidence_level (low/medium/high str) coexist independently."""
        health = CustomerHealth(
            organization_id=test_organization.id,
            customer_email="both@example.com",
            confidence_score=72,
            confidence_level="high",
        )
        db.add(health)
        db.commit()
        db.refresh(health)

        assert health.confidence_score == 72
        assert health.confidence_level == "high"
