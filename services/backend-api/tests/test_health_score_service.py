"""
TDD tests for health_score_service.py updates:
- Confidence level computation (low/medium/high)
- History recording (≥2 point change)
- Sentiment trend calculation (improving/declining/stable)
- Unarchive logic
"""
import pytest
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from src.models.customer_health import CustomerHealth
from src.models.feedback import FeedbackItem
from src.models.organization import Organization
from src.services.health_score_service import (
    compute_health_score,
    update_customer_health,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_feedback(db, org_id, email, sentiment_score=0.0, created_at=None, churn_risk_score=50):
    """Create a FeedbackItem in the DB."""
    fb = FeedbackItem(
        organization_id=org_id,
        customer_email=email,
        text="test feedback",
        source="email",
        sentiment_score=sentiment_score,
        sentiment_label="neutral",
        churn_risk_score=churn_risk_score,
        is_urgent=False,
        created_at=created_at or datetime.utcnow(),
    )
    db.add(fb)
    db.commit()
    db.refresh(fb)
    return fb


# ---------------------------------------------------------------------------
# Confidence Level Tests
# ---------------------------------------------------------------------------

class TestConfidenceLevel:
    """compute_health_score should return the correct confidence_level based on feedback_count."""

    def test_one_feedback_returns_low_confidence(self, db: Session, test_organization: Organization):
        """1 feedback → confidence_level = 'low'."""
        make_feedback(db, test_organization.id, "low1@example.com")
        result = compute_health_score(test_organization.id, "low1@example.com", db)
        assert result["confidence_level"] == "low"

    def test_two_feedbacks_returns_low_confidence(self, db: Session, test_organization: Organization):
        """2 feedbacks → confidence_level = 'low'."""
        for _ in range(2):
            make_feedback(db, test_organization.id, "low2@example.com")
        result = compute_health_score(test_organization.id, "low2@example.com", db)
        assert result["confidence_level"] == "low"

    def test_three_feedbacks_returns_medium_confidence(self, db: Session, test_organization: Organization):
        """3 feedbacks → confidence_level = 'medium'."""
        for _ in range(3):
            make_feedback(db, test_organization.id, "medium3@example.com")
        result = compute_health_score(test_organization.id, "medium3@example.com", db)
        assert result["confidence_level"] == "medium"

    def test_nine_feedbacks_returns_medium_confidence(self, db: Session, test_organization: Organization):
        """9 feedbacks → confidence_level = 'medium'."""
        for _ in range(9):
            make_feedback(db, test_organization.id, "medium9@example.com")
        result = compute_health_score(test_organization.id, "medium9@example.com", db)
        assert result["confidence_level"] == "medium"

    def test_ten_feedbacks_returns_high_confidence(self, db: Session, test_organization: Organization):
        """10 feedbacks → confidence_level = 'high'."""
        for _ in range(10):
            make_feedback(db, test_organization.id, "high10@example.com")
        result = compute_health_score(test_organization.id, "high10@example.com", db)
        assert result["confidence_level"] == "high"

    def test_twenty_feedbacks_returns_high_confidence(self, db: Session, test_organization: Organization):
        """20 feedbacks → confidence_level = 'high'."""
        for _ in range(20):
            make_feedback(db, test_organization.id, "high20@example.com")
        result = compute_health_score(test_organization.id, "high20@example.com", db)
        assert result["confidence_level"] == "high"

    def test_update_customer_health_persists_confidence_level(self, db: Session, test_organization: Organization):
        """update_customer_health() should persist confidence_level on the CustomerHealth record."""
        for _ in range(5):
            make_feedback(db, test_organization.id, "persist@example.com")
        update_customer_health(test_organization.id, "persist@example.com", db)
        db.commit()

        record = db.query(CustomerHealth).filter(
            CustomerHealth.organization_id == test_organization.id,
            CustomerHealth.customer_email == "persist@example.com",
        ).first()
        assert record is not None
        assert record.confidence_level == "medium"


# ---------------------------------------------------------------------------
# History Recording Tests
# ---------------------------------------------------------------------------

class TestHistoryRecording:
    """update_customer_health() should insert a CustomerHealthHistory record when score changes ≥ 2."""

    def test_first_update_creates_history_record(self, db: Session, test_organization: Organization):
        """The first call to update_customer_health creates a history record."""
        from src.models.customer_health_history import CustomerHealthHistory

        make_feedback(db, test_organization.id, "hist1@example.com")
        update_customer_health(test_organization.id, "hist1@example.com", db)
        db.commit()

        count = db.query(CustomerHealthHistory).join(
            CustomerHealth,
            CustomerHealthHistory.customer_health_id == CustomerHealth.id,
        ).filter(
            CustomerHealth.customer_email == "hist1@example.com",
            CustomerHealth.organization_id == test_organization.id,
        ).count()
        assert count == 1

    def test_update_with_significant_score_change_creates_history(self, db: Session, test_organization: Organization):
        """Second update with ≥ 2 point score change should create a new history record."""
        from src.models.customer_health_history import CustomerHealthHistory

        # Create an existing CustomerHealth with a known score
        health = CustomerHealth(
            organization_id=test_organization.id,
            customer_email="hist2@example.com",
            health_score=50,
            risk_level="moderate",
            confidence_level="low",
        )
        db.add(health)
        db.commit()

        # Add feedback that will shift score significantly
        for _ in range(3):
            make_feedback(db, test_organization.id, "hist2@example.com",
                         sentiment_score=0.9, churn_risk_score=10)

        update_customer_health(test_organization.id, "hist2@example.com", db)
        db.commit()

        count = db.query(CustomerHealthHistory).filter(
            CustomerHealthHistory.customer_health_id == health.id,
        ).count()
        assert count >= 1

    def test_update_with_no_score_change_skips_history(self, db: Session, test_organization: Organization):
        """Second update with <2 point change should NOT create another history record."""
        from src.models.customer_health_history import CustomerHealthHistory

        make_feedback(db, test_organization.id, "hist3@example.com",
                     sentiment_score=0.5, churn_risk_score=50)
        update_customer_health(test_organization.id, "hist3@example.com", db)
        db.commit()

        health = db.query(CustomerHealth).filter(
            CustomerHealth.customer_email == "hist3@example.com",
            CustomerHealth.organization_id == test_organization.id,
        ).first()

        # Force health_score to same value so the next update doesn't trigger history
        original_score = health.health_score

        # Run update again — score won't change since feedback is the same
        update_customer_health(test_organization.id, "hist3@example.com", db)
        db.commit()

        count = db.query(CustomerHealthHistory).filter(
            CustomerHealthHistory.customer_health_id == health.id,
        ).count()
        # Should be exactly 1 (from first update), not 2
        assert count == 1

    def test_history_record_has_correct_fields(self, db: Session, test_organization: Organization):
        """History record should capture all health score components."""
        from src.models.customer_health_history import CustomerHealthHistory

        make_feedback(db, test_organization.id, "hist4@example.com",
                     sentiment_score=0.3, churn_risk_score=40)
        update_customer_health(test_organization.id, "hist4@example.com", db)
        db.commit()

        health = db.query(CustomerHealth).filter(
            CustomerHealth.customer_email == "hist4@example.com",
        ).first()

        record = db.query(CustomerHealthHistory).filter(
            CustomerHealthHistory.customer_health_id == health.id,
        ).first()

        assert record is not None
        assert record.health_score == health.health_score
        assert record.risk_level == health.risk_level
        assert record.churn_risk_component == health.churn_risk_component
        assert record.sentiment_component == health.sentiment_component
        assert record.resolution_component == health.resolution_component
        assert record.frequency_component == health.frequency_component
        assert record.organization_id == test_organization.id
        assert record.recorded_at is not None


# ---------------------------------------------------------------------------
# Sentiment Trend Tests
# ---------------------------------------------------------------------------

class TestSentimentTrend:
    """compute_sentiment_trend() should return correct direction and change_percent."""

    def test_sentiment_trend_no_feedbacks_returns_stable(self, db: Session, test_organization: Organization):
        """No feedbacks returns stable with 0 change."""
        from src.services.health_score_service import compute_sentiment_trend

        result = compute_sentiment_trend(test_organization.id, "empty@example.com", db)
        assert result["direction"] == "stable"
        assert result["change_percent"] == 0

    def test_sentiment_trend_improving(self, db: Session, test_organization: Organization):
        """Recent feedbacks more positive than previous period → improving."""
        from src.services.health_score_service import compute_sentiment_trend

        now = datetime.utcnow()
        # Previous period (8-14 days ago): negative sentiment
        for _ in range(3):
            make_feedback(db, test_organization.id, "trend1@example.com",
                         sentiment_score=-0.5,
                         created_at=now - timedelta(days=10))

        # Recent period (last 7 days): positive sentiment
        for _ in range(3):
            make_feedback(db, test_organization.id, "trend1@example.com",
                         sentiment_score=0.8,
                         created_at=now - timedelta(days=2))

        result = compute_sentiment_trend(test_organization.id, "trend1@example.com", db)
        assert result["direction"] == "improving"
        assert result["change_percent"] > 5

    def test_sentiment_trend_declining(self, db: Session, test_organization: Organization):
        """Recent feedbacks more negative than previous period → declining."""
        from src.services.health_score_service import compute_sentiment_trend

        now = datetime.utcnow()
        # Previous period: positive sentiment
        for _ in range(3):
            make_feedback(db, test_organization.id, "trend2@example.com",
                         sentiment_score=0.8,
                         created_at=now - timedelta(days=10))

        # Recent period: negative sentiment
        for _ in range(3):
            make_feedback(db, test_organization.id, "trend2@example.com",
                         sentiment_score=-0.5,
                         created_at=now - timedelta(days=2))

        result = compute_sentiment_trend(test_organization.id, "trend2@example.com", db)
        assert result["direction"] == "declining"
        assert result["change_percent"] < -5

    def test_sentiment_trend_stable(self, db: Session, test_organization: Organization):
        """Similar sentiment in both periods → stable (within ±5% change)."""
        from src.services.health_score_service import compute_sentiment_trend

        now = datetime.utcnow()
        # Use same sentiment score to get 0% change → stable
        for _ in range(3):
            make_feedback(db, test_organization.id, "trend3@example.com",
                         sentiment_score=0.5,
                         created_at=now - timedelta(days=10))
        for _ in range(3):
            make_feedback(db, test_organization.id, "trend3@example.com",
                         sentiment_score=0.5,
                         created_at=now - timedelta(days=2))

        result = compute_sentiment_trend(test_organization.id, "trend3@example.com", db)
        assert result["direction"] == "stable"
        assert -5 <= result["change_percent"] <= 5

    def test_sentiment_trend_only_recent_no_previous(self, db: Session, test_organization: Organization):
        """Only recent feedbacks with no previous period → stable."""
        from src.services.health_score_service import compute_sentiment_trend

        now = datetime.utcnow()
        make_feedback(db, test_organization.id, "trend4@example.com",
                     sentiment_score=0.5,
                     created_at=now - timedelta(days=2))

        result = compute_sentiment_trend(test_organization.id, "trend4@example.com", db)
        assert result["direction"] == "stable"
        assert result["change_percent"] == 0

    def test_sentiment_trend_change_percent_rounded(self, db: Session, test_organization: Organization):
        """change_percent should be rounded to 1 decimal place."""
        from src.services.health_score_service import compute_sentiment_trend

        now = datetime.utcnow()
        make_feedback(db, test_organization.id, "trend5@example.com",
                     sentiment_score=0.333,
                     created_at=now - timedelta(days=10))
        make_feedback(db, test_organization.id, "trend5@example.com",
                     sentiment_score=0.777,
                     created_at=now - timedelta(days=2))

        result = compute_sentiment_trend(test_organization.id, "trend5@example.com", db)
        # Check it's rounded to 1 decimal
        assert result["change_percent"] == round(result["change_percent"], 1)


# ---------------------------------------------------------------------------
# Unarchive Logic Tests
# ---------------------------------------------------------------------------

class TestUnarchiveLogic:
    """update_customer_health() should set is_archived=False when new feedback arrives."""

    def test_unarchive_on_new_feedback(self, db: Session, test_organization: Organization):
        """An archived customer should be unarchived when update_customer_health runs with feedback."""
        # Create an archived CustomerHealth record
        health = CustomerHealth(
            organization_id=test_organization.id,
            customer_email="archived@example.com",
            health_score=30,
            is_archived=True,
            confidence_level="low",
        )
        db.add(health)
        db.commit()

        # Add new feedback (simulates new feedback ingestion)
        make_feedback(db, test_organization.id, "archived@example.com",
                     sentiment_score=0.5)

        # update_customer_health should set is_archived=False
        update_customer_health(test_organization.id, "archived@example.com", db)
        db.commit()

        db.refresh(health)
        assert health.is_archived == False

    def test_new_customer_health_not_archived_by_default(self, db: Session, test_organization: Organization):
        """A new CustomerHealth record created by update_customer_health should not be archived."""
        make_feedback(db, test_organization.id, "newcust@example.com")
        update_customer_health(test_organization.id, "newcust@example.com", db)
        db.commit()

        health = db.query(CustomerHealth).filter(
            CustomerHealth.customer_email == "newcust@example.com",
            CustomerHealth.organization_id == test_organization.id,
        ).first()
        assert health is not None
        assert health.is_archived == False
