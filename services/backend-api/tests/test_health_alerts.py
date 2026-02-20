"""
TDD tests for Customer Sentiment Alerts (M1.3) — Phase 1.

Tests for _check_health_drop_alert() in health_score_service.py.
RED → GREEN → REFACTOR.
"""
import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock, call
from sqlalchemy.orm import Session

from src.models.customer_health import CustomerHealth
from src.models.organization import Organization


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_customer_health(
    db,
    org_id: int,
    email: str,
    health_score: int,
    risk_level: str,
    llm_analyzed_at=None,
) -> CustomerHealth:
    """Create a CustomerHealth record in the DB."""
    ch = CustomerHealth(
        organization_id=org_id,
        customer_email=email,
        customer_name="Test Customer",
        health_score=health_score,
        risk_level=risk_level,
        churn_risk_component=50,
        sentiment_component=50,
        resolution_component=50,
        frequency_component=50,
        confidence_level="medium",
        llm_analyzed_at=llm_analyzed_at,
        is_archived=False,
    )
    db.add(ch)
    db.commit()
    db.refresh(ch)
    return ch


COMPONENTS = {
    "churn_risk": 78,
    "sentiment": 35,
    "resolution": 60,
    "frequency": 45,
}


# ---------------------------------------------------------------------------
# Tests for _check_health_drop_alert()
# ---------------------------------------------------------------------------

class TestCheckHealthDropAlert:
    """Unit tests for _check_health_drop_alert() trigger logic."""

    def test_calls_dispatch_when_score_crosses_below_threshold(
        self, db: Session, test_organization: Organization
    ):
        """
        Alert fires when new_score < threshold AND old_score >= threshold.
        Default threshold is 50.
        """
        from src.services.health_score_service import _check_health_drop_alert

        with patch(
            "src.services.health_score_service.dispatch_health_drop_alert"
        ) as mock_dispatch:
            _check_health_drop_alert(
                org_id=test_organization.id,
                customer_email="drop@example.com",
                customer_name="Drop User",
                old_score=55,
                new_score=45,
                old_risk_level="moderate",
                new_risk_level="at_risk",
                components=COMPONENTS,
                db=db,
            )
            mock_dispatch.assert_called_once()

    def test_does_not_call_dispatch_when_score_already_below_threshold(
        self, db: Session, test_organization: Organization
    ):
        """
        No alert when score stays below threshold (both old and new < 50, no risk change, no large drop).
        """
        from src.services.health_score_service import _check_health_drop_alert

        with patch(
            "src.services.health_score_service.dispatch_health_drop_alert"
        ) as mock_dispatch:
            _check_health_drop_alert(
                org_id=test_organization.id,
                customer_email="below@example.com",
                customer_name="Below User",
                old_score=45,
                new_score=44,
                old_risk_level="at_risk",
                new_risk_level="at_risk",  # same risk level
                components=COMPONENTS,
                db=db,
            )
            mock_dispatch.assert_not_called()

    def test_calls_dispatch_when_score_drops_by_15_or_more(
        self, db: Session, test_organization: Organization
    ):
        """Alert fires when score drops by >= 15 points."""
        from src.services.health_score_service import _check_health_drop_alert

        with patch(
            "src.services.health_score_service.dispatch_health_drop_alert"
        ) as mock_dispatch:
            _check_health_drop_alert(
                org_id=test_organization.id,
                customer_email="bigdrop@example.com",
                customer_name="Big Drop User",
                old_score=80,
                new_score=65,  # exactly 15 point drop
                old_risk_level="healthy",
                new_risk_level="healthy",  # same risk level
                components=COMPONENTS,
                db=db,
            )
            mock_dispatch.assert_called_once()

    def test_does_not_call_dispatch_for_small_drop_same_risk_above_threshold(
        self, db: Session, test_organization: Organization
    ):
        """No alert when drop < 15 pts, same risk level, score still above threshold."""
        from src.services.health_score_service import _check_health_drop_alert

        with patch(
            "src.services.health_score_service.dispatch_health_drop_alert"
        ) as mock_dispatch:
            _check_health_drop_alert(
                org_id=test_organization.id,
                customer_email="small@example.com",
                customer_name="Small Drop User",
                old_score=80,
                new_score=74,  # 6 point drop, below 15 threshold
                old_risk_level="healthy",
                new_risk_level="healthy",
                components=COMPONENTS,
                db=db,
            )
            mock_dispatch.assert_not_called()

    def test_calls_dispatch_on_risk_level_downgrade_healthy_to_moderate(
        self, db: Session, test_organization: Organization
    ):
        """Alert fires on risk level downgrade (healthy → moderate)."""
        from src.services.health_score_service import _check_health_drop_alert

        with patch(
            "src.services.health_score_service.dispatch_health_drop_alert"
        ) as mock_dispatch:
            _check_health_drop_alert(
                org_id=test_organization.id,
                customer_email="downgrade1@example.com",
                customer_name="Downgrade User",
                old_score=72,
                new_score=68,  # small drop but risk level changes
                old_risk_level="healthy",
                new_risk_level="moderate",
                components=COMPONENTS,
                db=db,
            )
            mock_dispatch.assert_called_once()

    def test_calls_dispatch_on_risk_level_downgrade_moderate_to_at_risk(
        self, db: Session, test_organization: Organization
    ):
        """Alert fires on risk level downgrade (moderate → at_risk)."""
        from src.services.health_score_service import _check_health_drop_alert

        with patch(
            "src.services.health_score_service.dispatch_health_drop_alert"
        ) as mock_dispatch:
            _check_health_drop_alert(
                org_id=test_organization.id,
                customer_email="downgrade2@example.com",
                customer_name="Downgrade User 2",
                old_score=52,
                new_score=48,
                old_risk_level="moderate",
                new_risk_level="at_risk",
                components=COMPONENTS,
                db=db,
            )
            mock_dispatch.assert_called_once()

    def test_calls_dispatch_on_risk_level_downgrade_at_risk_to_critical(
        self, db: Session, test_organization: Organization
    ):
        """Alert fires on risk level downgrade (at_risk → critical)."""
        from src.services.health_score_service import _check_health_drop_alert

        with patch(
            "src.services.health_score_service.dispatch_health_drop_alert"
        ) as mock_dispatch:
            _check_health_drop_alert(
                org_id=test_organization.id,
                customer_email="downgrade3@example.com",
                customer_name="Downgrade User 3",
                old_score=31,
                new_score=28,
                old_risk_level="at_risk",
                new_risk_level="critical",
                components=COMPONENTS,
                db=db,
            )
            mock_dispatch.assert_called_once()

    def test_calls_dispatch_for_recovery_on_risk_level_upgrade(
        self, db: Session, test_organization: Organization
    ):
        """Recovery alert fires on risk level upgrade (at_risk → moderate)."""
        from src.services.health_score_service import _check_health_drop_alert

        with patch(
            "src.services.health_score_service.dispatch_health_drop_alert"
        ) as mock_dispatch:
            _check_health_drop_alert(
                org_id=test_organization.id,
                customer_email="recovery@example.com",
                customer_name="Recovery User",
                old_score=40,
                new_score=55,
                old_risk_level="at_risk",
                new_risk_level="moderate",
                components=COMPONENTS,
                db=db,
            )
            # Should be called with is_recovery=True
            mock_dispatch.assert_called_once()
            call_kwargs = mock_dispatch.call_args[1]
            assert call_kwargs.get("is_recovery") is True

    def test_does_not_call_dispatch_when_score_rises_but_same_risk_level(
        self, db: Session, test_organization: Organization
    ):
        """No alert when score improves but stays in same risk level (no recovery)."""
        from src.services.health_score_service import _check_health_drop_alert

        with patch(
            "src.services.health_score_service.dispatch_health_drop_alert"
        ) as mock_dispatch:
            _check_health_drop_alert(
                org_id=test_organization.id,
                customer_email="smallrise@example.com",
                customer_name="Small Rise User",
                old_score=60,
                new_score=65,
                old_risk_level="healthy",
                new_risk_level="healthy",
                components=COMPONENTS,
                db=db,
            )
            mock_dispatch.assert_not_called()

    def test_downgrade_alert_called_with_is_recovery_false(
        self, db: Session, test_organization: Organization
    ):
        """A drop alert should be called with is_recovery=False."""
        from src.services.health_score_service import _check_health_drop_alert

        with patch(
            "src.services.health_score_service.dispatch_health_drop_alert"
        ) as mock_dispatch:
            _check_health_drop_alert(
                org_id=test_organization.id,
                customer_email="norecover@example.com",
                customer_name="No Recovery",
                old_score=72,
                new_score=68,
                old_risk_level="healthy",
                new_risk_level="moderate",
                components=COMPONENTS,
                db=db,
            )
            call_kwargs = mock_dispatch.call_args[1]
            assert call_kwargs.get("is_recovery") is False


class TestCheckHealthDropAlertIntegration:
    """Integration tests: update_customer_health() triggers _check_health_drop_alert()."""

    def test_update_health_calls_check_alert_for_existing_customer(
        self, db: Session, test_organization: Organization
    ):
        """update_customer_health() calls _check_health_drop_alert() for existing customer."""
        from src.services.health_score_service import update_customer_health
        from src.models.feedback import FeedbackItem

        # Pre-create a CustomerHealth record
        ch = CustomerHealth(
            organization_id=test_organization.id,
            customer_email="existing@example.com",
            health_score=70,
            risk_level="healthy",
            confidence_level="medium",
        )
        db.add(ch)
        db.commit()

        # Add feedback so score can be computed
        fb = FeedbackItem(
            organization_id=test_organization.id,
            customer_email="existing@example.com",
            text="test feedback",
            source="email",
            sentiment_score=0.0,
            sentiment_label="neutral",
            churn_risk_score=50,
        )
        db.add(fb)
        db.commit()

        with patch(
            "src.services.health_score_service._check_health_drop_alert"
        ) as mock_check:
            update_customer_health(test_organization.id, "existing@example.com", db)
            mock_check.assert_called_once()

    def test_update_health_does_not_call_check_alert_for_new_customer(
        self, db: Session, test_organization: Organization
    ):
        """update_customer_health() does NOT call _check_health_drop_alert() for brand new customer."""
        from src.services.health_score_service import update_customer_health
        from src.models.feedback import FeedbackItem

        fb = FeedbackItem(
            organization_id=test_organization.id,
            customer_email="brandnew@example.com",
            text="first feedback",
            source="email",
            sentiment_score=0.0,
            sentiment_label="neutral",
            churn_risk_score=50,
        )
        db.add(fb)
        db.commit()

        with patch(
            "src.services.health_score_service._check_health_drop_alert"
        ) as mock_check:
            update_customer_health(test_organization.id, "brandnew@example.com", db)
            mock_check.assert_not_called()
