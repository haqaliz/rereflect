"""
TDD tests for the CRM writeback enqueue hook in health_score_service.py
(writeback-task-trigger aspect, Phase 2).

Covers _maybe_enqueue_writeback() directly and through update_customer_health()
for the existing-customer branch. Mocks get_celery_app — no real Celery/Redis.
"""
from datetime import datetime

import pytest
from sqlalchemy.orm import Session
from unittest.mock import patch, MagicMock

from src.models.customer_health import CustomerHealth
from src.models.feedback import FeedbackItem
from src.models.hubspot_integration import HubSpotIntegration
from src.models.salesforce_integration import SalesforceIntegration
from src.models.organization import Organization
from src.services.health_score_service import (
    _maybe_enqueue_writeback,
    update_customer_health,
)

GET_CELERY_TARGET = "src.background.celery_client.get_celery_app"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_feedback(db, org_id, email, sentiment_score=0.0, churn_risk_score=50):
    fb = FeedbackItem(
        organization_id=org_id,
        customer_email=email,
        text="test feedback",
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


def make_integration(db, org_id, is_active=True, writeback_enabled=True):
    integ = HubSpotIntegration(
        organization_id=org_id,
        access_token="encrypted-token",
        is_active=is_active,
        writeback_enabled=writeback_enabled,
        writeback_field_name="rereflect_health_score" if writeback_enabled else None,
        connected_at=datetime.utcnow(),
    )
    db.add(integ)
    db.commit()
    db.refresh(integ)
    return integ


def make_salesforce_integration(db, org_id, is_active=True, writeback_enabled=True):
    integ = SalesforceIntegration(
        organization_id=org_id,
        refresh_token="encrypted-refresh-token",
        instance_url="https://acme.my.salesforce.com",
        is_active=is_active,
        writeback_enabled=writeback_enabled,
        writeback_field_name="Rereflect_Health_Score__c" if writeback_enabled else None,
        connected_at=datetime.utcnow(),
    )
    db.add(integ)
    db.commit()
    db.refresh(integ)
    return integ


# ---------------------------------------------------------------------------
# TestMaybeEnqueueWritebackDirect — unit tests on the helper itself
# ---------------------------------------------------------------------------


class TestMaybeEnqueueWritebackDirect:
    def test_change_ge_2_with_active_enabled_integration_enqueues(
        self, db: Session, test_organization: Organization
    ):
        make_integration(db, test_organization.id)

        with patch(GET_CELERY_TARGET) as mock_get_celery:
            mock_celery = MagicMock()
            mock_get_celery.return_value = mock_celery

            _maybe_enqueue_writeback(
                org_id=test_organization.id,
                customer_email="alice@example.com",
                old_score=50,
                new_score=80,
                db=db,
            )

        mock_celery.send_task.assert_called_once_with(
            "src.tasks.hubspot_writeback.push_health_to_hubspot",
            args=[test_organization.id, "alice@example.com"],
        )

    def test_change_under_2_does_not_enqueue(
        self, db: Session, test_organization: Organization
    ):
        make_integration(db, test_organization.id)

        with patch(GET_CELERY_TARGET) as mock_get_celery:
            mock_celery = MagicMock()
            mock_get_celery.return_value = mock_celery

            _maybe_enqueue_writeback(
                org_id=test_organization.id,
                customer_email="alice@example.com",
                old_score=50,
                new_score=51,
                db=db,
            )

        mock_celery.send_task.assert_not_called()

    def test_no_integration_does_not_enqueue(
        self, db: Session, test_organization: Organization
    ):
        with patch(GET_CELERY_TARGET) as mock_get_celery:
            mock_celery = MagicMock()
            mock_get_celery.return_value = mock_celery

            _maybe_enqueue_writeback(
                org_id=test_organization.id,
                customer_email="alice@example.com",
                old_score=50,
                new_score=80,
                db=db,
            )

        mock_get_celery.assert_not_called()

    def test_inactive_integration_does_not_enqueue(
        self, db: Session, test_organization: Organization
    ):
        make_integration(db, test_organization.id, is_active=False)

        with patch(GET_CELERY_TARGET) as mock_get_celery:
            mock_celery = MagicMock()
            mock_get_celery.return_value = mock_celery

            _maybe_enqueue_writeback(
                org_id=test_organization.id,
                customer_email="alice@example.com",
                old_score=50,
                new_score=80,
                db=db,
            )

        mock_get_celery.assert_not_called()

    def test_writeback_disabled_integration_does_not_enqueue(
        self, db: Session, test_organization: Organization
    ):
        make_integration(db, test_organization.id, writeback_enabled=False)

        with patch(GET_CELERY_TARGET) as mock_get_celery:
            mock_celery = MagicMock()
            mock_get_celery.return_value = mock_celery

            _maybe_enqueue_writeback(
                org_id=test_organization.id,
                customer_email="alice@example.com",
                old_score=50,
                new_score=80,
                db=db,
            )

        mock_get_celery.assert_not_called()

    def test_send_task_exception_does_not_raise(
        self, db: Session, test_organization: Organization
    ):
        make_integration(db, test_organization.id)

        with patch(GET_CELERY_TARGET) as mock_get_celery:
            mock_celery = MagicMock()
            mock_celery.send_task.side_effect = RuntimeError("broker down")
            mock_get_celery.return_value = mock_celery

            # Should not raise.
            _maybe_enqueue_writeback(
                org_id=test_organization.id,
                customer_email="alice@example.com",
                old_score=50,
                new_score=80,
                db=db,
            )

    def test_get_celery_app_import_error_does_not_raise(
        self, db: Session, test_organization: Organization
    ):
        """Simulates the worker environment, where the backend's celery client
        may not be importable at all."""
        make_integration(db, test_organization.id)

        with patch(GET_CELERY_TARGET, side_effect=ImportError("no celery client here")):
            # Should not raise.
            _maybe_enqueue_writeback(
                org_id=test_organization.id,
                customer_email="alice@example.com",
                old_score=50,
                new_score=80,
                db=db,
            )


# ---------------------------------------------------------------------------
# TestUpdateCustomerHealthIntegration — through the real hook site
# ---------------------------------------------------------------------------


class TestUpdateCustomerHealthEnqueuesOnScoreChange:
    def test_significant_change_enqueues_via_update_customer_health(
        self, db: Session, test_organization: Organization
    ):
        make_integration(db, test_organization.id)

        # Existing CustomerHealth with a known low score.
        health = CustomerHealth(
            organization_id=test_organization.id,
            customer_email="bob@example.com",
            health_score=50,
            risk_level="moderate",
            confidence_level="low",
        )
        db.add(health)
        db.commit()

        # Feedback that shifts the computed score significantly upward.
        for _ in range(3):
            make_feedback(
                db, test_organization.id, "bob@example.com",
                sentiment_score=0.9, churn_risk_score=10,
            )

        with patch(GET_CELERY_TARGET) as mock_get_celery:
            mock_celery = MagicMock()
            mock_get_celery.return_value = mock_celery

            update_customer_health(test_organization.id, "bob@example.com", db)
            db.commit()

        mock_celery.send_task.assert_called_once_with(
            "src.tasks.hubspot_writeback.push_health_to_hubspot",
            args=[test_organization.id, "bob@example.com"],
        )

    def test_no_integration_configured_does_not_enqueue_via_update_customer_health(
        self, db: Session, test_organization: Organization
    ):
        health = CustomerHealth(
            organization_id=test_organization.id,
            customer_email="carol@example.com",
            health_score=50,
            risk_level="moderate",
            confidence_level="low",
        )
        db.add(health)
        db.commit()

        for _ in range(3):
            make_feedback(
                db, test_organization.id, "carol@example.com",
                sentiment_score=0.9, churn_risk_score=10,
            )

        with patch(GET_CELERY_TARGET) as mock_get_celery:
            mock_celery = MagicMock()
            mock_get_celery.return_value = mock_celery

            update_customer_health(test_organization.id, "carol@example.com", db)
            db.commit()

        mock_get_celery.assert_not_called()


# ---------------------------------------------------------------------------
# TestMaybeEnqueueSalesforceWriteback — push-task-trigger Phase 3
# (generalizes _maybe_enqueue_writeback to also dispatch a Salesforce push;
#  the HubSpot-only assertions above must remain unchanged.)
# ---------------------------------------------------------------------------


class TestMaybeEnqueueSalesforceWriteback:
    def test_hubspot_only_org_still_dispatches_only_hubspot_task(
        self, db: Session, test_organization: Organization
    ):
        """No Salesforce integration exists — only the HubSpot task fires,
        exactly once, with the existing args shape (regression guard)."""
        make_integration(db, test_organization.id)

        with patch(GET_CELERY_TARGET) as mock_get_celery:
            mock_celery = MagicMock()
            mock_get_celery.return_value = mock_celery

            _maybe_enqueue_writeback(
                org_id=test_organization.id,
                customer_email="alice@example.com",
                old_score=50,
                new_score=80,
                db=db,
            )

        mock_celery.send_task.assert_called_once_with(
            "src.tasks.hubspot_writeback.push_health_to_hubspot",
            args=[test_organization.id, "alice@example.com"],
        )

    def test_salesforce_only_org_dispatches_salesforce_task(
        self, db: Session, test_organization: Organization
    ):
        make_salesforce_integration(db, test_organization.id)

        with patch(GET_CELERY_TARGET) as mock_get_celery:
            mock_celery = MagicMock()
            mock_get_celery.return_value = mock_celery

            _maybe_enqueue_writeback(
                org_id=test_organization.id,
                customer_email="alice@example.com",
                old_score=50,
                new_score=80,
                db=db,
            )

        mock_celery.send_task.assert_called_once_with(
            "src.tasks.salesforce_writeback.push_health_to_salesforce",
            args=[test_organization.id, "alice@example.com"],
        )

    def test_salesforce_inactive_integration_does_not_enqueue(
        self, db: Session, test_organization: Organization
    ):
        make_salesforce_integration(db, test_organization.id, is_active=False)

        with patch(GET_CELERY_TARGET) as mock_get_celery:
            mock_celery = MagicMock()
            mock_get_celery.return_value = mock_celery

            _maybe_enqueue_writeback(
                org_id=test_organization.id,
                customer_email="alice@example.com",
                old_score=50,
                new_score=80,
                db=db,
            )

        mock_get_celery.assert_not_called()

    def test_salesforce_writeback_disabled_does_not_enqueue(
        self, db: Session, test_organization: Organization
    ):
        make_salesforce_integration(db, test_organization.id, writeback_enabled=False)

        with patch(GET_CELERY_TARGET) as mock_get_celery:
            mock_celery = MagicMock()
            mock_get_celery.return_value = mock_celery

            _maybe_enqueue_writeback(
                org_id=test_organization.id,
                customer_email="alice@example.com",
                old_score=50,
                new_score=80,
                db=db,
            )

        mock_get_celery.assert_not_called()

    def test_salesforce_change_under_2_does_not_enqueue(
        self, db: Session, test_organization: Organization
    ):
        make_salesforce_integration(db, test_organization.id)

        with patch(GET_CELERY_TARGET) as mock_get_celery:
            mock_celery = MagicMock()
            mock_get_celery.return_value = mock_celery

            _maybe_enqueue_writeback(
                org_id=test_organization.id,
                customer_email="alice@example.com",
                old_score=50,
                new_score=51,
                db=db,
            )

        mock_get_celery.assert_not_called()

    def test_no_integration_of_either_provider_does_not_enqueue(
        self, db: Session, test_organization: Organization
    ):
        with patch(GET_CELERY_TARGET) as mock_get_celery:
            mock_celery = MagicMock()
            mock_get_celery.return_value = mock_celery

            _maybe_enqueue_writeback(
                org_id=test_organization.id,
                customer_email="alice@example.com",
                old_score=50,
                new_score=80,
                db=db,
            )

        mock_get_celery.assert_not_called()

    def test_salesforce_send_task_exception_does_not_raise(
        self, db: Session, test_organization: Organization
    ):
        make_salesforce_integration(db, test_organization.id)

        with patch(GET_CELERY_TARGET) as mock_get_celery:
            mock_celery = MagicMock()
            mock_celery.send_task.side_effect = RuntimeError("broker down")
            mock_get_celery.return_value = mock_celery

            # Should not raise.
            _maybe_enqueue_writeback(
                org_id=test_organization.id,
                customer_email="alice@example.com",
                old_score=50,
                new_score=80,
                db=db,
            )
