"""
TDD tests for Phase 3 (segment-engine): on-ingest segment assignment.

`update_customer_health` must compute and persist `CustomerHealth.segment`
via `health_score_service.resolve_segment`, on BOTH the existing-row update
branch and the new-row creation branch. This is additive — health_score /
components must remain byte-stable regardless of segment resolution
succeeding or failing.
"""
import pytest
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from src.models.customer_health import CustomerHealth
from src.models.feedback import FeedbackItem
from src.models.organization import Organization
from src.services.segment_service import SEGMENT_SLUGS
from src.services.health_score_service import update_customer_health


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


def get_health(db, org_id, email):
    return db.query(CustomerHealth).filter(
        CustomerHealth.organization_id == org_id,
        CustomerHealth.customer_email == email,
    ).first()


class TestSegmentOnIngestNewRow:
    """New CustomerHealth row (first update_customer_health call for a customer)."""

    def test_at_risk_customer_no_usage_row_gets_at_risk_segment(
        self, db: Session, test_organization: Organization
    ):
        """
        High churn_risk_score feedback -> low churn component -> critical/at_risk
        risk_level. No CustomerUsage row exists for this customer at all — this
        must not crash and must not fall back to a false "dormant" classification.
        """
        email = "atrisk@example.com"
        for _ in range(3):
            make_feedback(
                db, test_organization.id, email,
                sentiment_score=-0.9, churn_risk_score=95,
            )

        update_customer_health(test_organization.id, email, db)
        db.commit()

        record = get_health(db, test_organization.id, email)
        assert record is not None
        assert record.health_score is not None  # health computation unaffected
        assert record.risk_level in ("at_risk", "critical")
        assert record.segment == "at_risk"

    def test_positive_customer_no_usage_row_gets_valid_non_usage_gated_segment(
        self, db: Session, test_organization: Organization
    ):
        """
        A brand-new, very positive customer with no CustomerUsage row: segment
        must be a valid slug and must NOT be a usage-gated segment
        (power_user / silent_churner), since usage is None.
        """
        email = "happy@example.com"
        make_feedback(
            db, test_organization.id, email,
            sentiment_score=0.9, churn_risk_score=5,
        )

        update_customer_health(test_organization.id, email, db)
        db.commit()

        record = get_health(db, test_organization.id, email)
        assert record is not None
        assert record.segment in SEGMENT_SLUGS
        assert record.segment not in ("power_user", "silent_churner")


class TestSegmentOnIngestExistingRow:
    """Existing CustomerHealth row (second+ update_customer_health call)."""

    def test_existing_row_segment_updates_on_second_call(
        self, db: Session, test_organization: Organization
    ):
        email = "existing@example.com"
        make_feedback(db, test_organization.id, email, sentiment_score=0.9, churn_risk_score=5)
        update_customer_health(test_organization.id, email, db)
        db.commit()

        first = get_health(db, test_organization.id, email)
        assert first.segment in SEGMENT_SLUGS

        # Drive the same customer into at_risk territory with more negative feedback.
        for _ in range(3):
            make_feedback(
                db, test_organization.id, email,
                sentiment_score=-0.9, churn_risk_score=95,
            )
        update_customer_health(test_organization.id, email, db)
        db.commit()

        second = get_health(db, test_organization.id, email)
        assert second.segment == "at_risk"
        assert second.health_score is not None


class TestSegmentResolutionRobustness:
    """Segment resolution failures must never break the health upsert."""

    def test_classify_segment_exception_does_not_break_health_upsert(
        self, db: Session, test_organization: Organization, monkeypatch
    ):
        """
        If classify_segment raises, update_customer_health must still commit
        the health row with health_score/components computed correctly, and
        leave segment as None (unset) rather than propagating the exception.
        """
        import src.services.segment_service as segment_service

        def _boom(**kwargs):
            raise RuntimeError("boom")

        monkeypatch.setattr(segment_service, "classify_segment", _boom)

        email = "robust@example.com"
        make_feedback(db, test_organization.id, email, sentiment_score=0.5, churn_risk_score=20)

        # Must not raise.
        update_customer_health(test_organization.id, email, db)
        db.commit()

        record = get_health(db, test_organization.id, email)
        assert record is not None
        assert record.health_score is not None
        assert record.segment is None

    def test_existing_row_classify_segment_exception_leaves_segment_unchanged(
        self, db: Session, test_organization: Organization, monkeypatch
    ):
        """On the update branch, a resolve_segment failure must leave the
        previously-persisted segment value unchanged (not overwritten/reset)."""
        email = "robust2@example.com"
        make_feedback(db, test_organization.id, email, sentiment_score=0.9, churn_risk_score=5)
        update_customer_health(test_organization.id, email, db)
        db.commit()

        first = get_health(db, test_organization.id, email)
        original_segment = first.segment
        assert original_segment in SEGMENT_SLUGS

        import src.services.segment_service as segment_service

        def _boom(**kwargs):
            raise RuntimeError("boom")

        monkeypatch.setattr(segment_service, "classify_segment", _boom)

        make_feedback(db, test_organization.id, email, sentiment_score=0.8, churn_risk_score=10)
        update_customer_health(test_organization.id, email, db)
        db.commit()

        second = get_health(db, test_organization.id, email)
        assert second.health_score is not None
        assert second.segment == original_segment


class TestHealthComputationUnaffected:
    """Segment write must be additive — health_score/components unchanged."""

    def test_health_components_still_computed_alongside_segment(
        self, db: Session, test_organization: Organization
    ):
        email = "additive@example.com"
        for _ in range(5):
            make_feedback(db, test_organization.id, email, sentiment_score=0.2, churn_risk_score=40)

        update_customer_health(test_organization.id, email, db)
        db.commit()

        record = get_health(db, test_organization.id, email)
        assert record.health_score is not None
        assert record.churn_risk_component is not None
        assert record.sentiment_component is not None
        assert record.resolution_component is not None
        assert record.frequency_component is not None
        assert record.feedback_count == 5
        assert record.segment in SEGMENT_SLUGS
