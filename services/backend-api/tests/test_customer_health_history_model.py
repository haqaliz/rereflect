"""
TDD tests for CustomerHealthHistory model and CustomerHealth model extensions.
RED phase: these tests should fail until the model is created.
"""
import pytest
from datetime import datetime
from sqlalchemy.orm import Session

from src.models.customer_health import CustomerHealth
from src.models.organization import Organization


class TestCustomerHealthNewFields:
    """Test that CustomerHealth has is_archived and confidence_level fields."""

    def test_customer_health_has_is_archived_field(self, db: Session, test_organization: Organization):
        """CustomerHealth should have is_archived boolean field defaulting to False."""
        health = CustomerHealth(
            organization_id=test_organization.id,
            customer_email="test@example.com",
            health_score=75,
        )
        db.add(health)
        db.commit()
        db.refresh(health)

        assert hasattr(health, "is_archived")
        assert health.is_archived == False

    def test_customer_health_has_confidence_level_field(self, db: Session, test_organization: Organization):
        """CustomerHealth should have confidence_level string field defaulting to 'low'."""
        health = CustomerHealth(
            organization_id=test_organization.id,
            customer_email="conf@example.com",
            health_score=50,
        )
        db.add(health)
        db.commit()
        db.refresh(health)

        assert hasattr(health, "confidence_level")
        assert health.confidence_level == "low"

    def test_can_set_is_archived_true(self, db: Session, test_organization: Organization):
        """is_archived can be set to True."""
        health = CustomerHealth(
            organization_id=test_organization.id,
            customer_email="archived@example.com",
            health_score=30,
            is_archived=True,
        )
        db.add(health)
        db.commit()
        db.refresh(health)

        assert health.is_archived == True

    def test_can_set_confidence_level(self, db: Session, test_organization: Organization):
        """confidence_level can be set to low/medium/high."""
        for level in ("low", "medium", "high"):
            health = CustomerHealth(
                organization_id=test_organization.id,
                customer_email=f"{level}@example.com",
                health_score=50,
                confidence_level=level,
            )
            db.add(health)
        db.commit()


class TestCustomerHealthHistoryModel:
    """Test that CustomerHealthHistory model exists and works correctly."""

    def test_customer_health_history_importable(self):
        """CustomerHealthHistory should be importable from models."""
        from src.models.customer_health_history import CustomerHealthHistory
        assert CustomerHealthHistory is not None

    def test_customer_health_history_in_init(self):
        """CustomerHealthHistory should be exported from models __init__."""
        from src.models import CustomerHealthHistory
        assert CustomerHealthHistory is not None

    def test_customer_health_history_has_correct_table_name(self):
        """CustomerHealthHistory table should be named 'customer_health_history'."""
        from src.models.customer_health_history import CustomerHealthHistory
        assert CustomerHealthHistory.__tablename__ == "customer_health_history"

    def test_customer_health_history_can_be_created(self, db: Session, test_organization: Organization):
        """CustomerHealthHistory record can be inserted into database."""
        from src.models.customer_health_history import CustomerHealthHistory

        # First create a CustomerHealth record
        health = CustomerHealth(
            organization_id=test_organization.id,
            customer_email="history@example.com",
            health_score=60,
        )
        db.add(health)
        db.commit()
        db.refresh(health)

        # Now create history record
        history = CustomerHealthHistory(
            customer_health_id=health.id,
            organization_id=test_organization.id,
            health_score=60,
            churn_risk_component=55,
            sentiment_component=65,
            resolution_component=60,
            frequency_component=58,
            risk_level="moderate",
        )
        db.add(history)
        db.commit()
        db.refresh(history)

        assert history.id is not None
        assert history.customer_health_id == health.id
        assert history.organization_id == test_organization.id
        assert history.health_score == 60
        assert history.churn_risk_component == 55
        assert history.sentiment_component == 65
        assert history.resolution_component == 60
        assert history.frequency_component == 58
        assert history.risk_level == "moderate"
        assert history.recorded_at is not None

    def test_customer_health_history_recorded_at_defaults_to_now(self, db: Session, test_organization: Organization):
        """recorded_at should default to current datetime."""
        from src.models.customer_health_history import CustomerHealthHistory

        health = CustomerHealth(
            organization_id=test_organization.id,
            customer_email="timing@example.com",
            health_score=50,
        )
        db.add(health)
        db.commit()
        db.refresh(health)

        before = datetime.utcnow()
        history = CustomerHealthHistory(
            customer_health_id=health.id,
            organization_id=test_organization.id,
            health_score=50,
            risk_level="moderate",
        )
        db.add(history)
        db.commit()
        db.refresh(history)
        after = datetime.utcnow()

        assert history.recorded_at is not None
        assert before <= history.recorded_at <= after

    def test_customer_health_history_cascade_delete(self, db: Session, test_organization: Organization):
        """Deleting CustomerHealth via ORM should cascade delete its history records."""
        from src.models.customer_health_history import CustomerHealthHistory

        health = CustomerHealth(
            organization_id=test_organization.id,
            customer_email="cascade@example.com",
            health_score=70,
        )
        db.add(health)
        db.commit()
        db.refresh(health)
        health_id = health.id

        history = CustomerHealthHistory(
            customer_health_id=health.id,
            organization_id=test_organization.id,
            health_score=70,
            risk_level="healthy",
        )
        db.add(history)
        db.commit()

        # Re-query health to ensure ORM relationship is loaded before delete
        health = db.query(CustomerHealth).filter(CustomerHealth.id == health_id).first()
        # Load relationship so SQLAlchemy cascade applies even in SQLite
        _ = health.history
        db.delete(health)
        db.commit()

        # History should be gone too (cascade via SQLAlchemy relationship)
        remaining = db.query(CustomerHealthHistory).filter(
            CustomerHealthHistory.customer_health_id == health_id
        ).count()
        assert remaining == 0
