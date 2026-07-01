"""
TDD tests for crm-provider-generalization aspect (aspect 1 of 4,
salesforce-crm-enrichment feature).

Phase 1 (RED characterization): locks the health-score + serializer output for
a fixture HubSpot-enriched org+customer BEFORE any provider-generalization
code changes.  Must PASS before AND after Phases 2-4 (provider column,
migration, provider-driven timeline, crm_provider on serializer/API) — proving
zero regression for existing HubSpot-enriched orgs.

Mirrors the fixture patterns in tests/test_health_crm_component.py (health
score) and tests/test_customer_profile.py (serializer).
"""
from datetime import date, datetime, timedelta

import pytest

from src.models.crm_enrichment import CrmEnrichment
from src.models.customer_health import CustomerHealth
from src.models.feedback import FeedbackItem
from src.services.health_score_service import compute_health_score
from src.services.customer_profile_serializer import serialize_customer_profile


def _make_feedback(db, org_id, email, sentiment_score, churn_risk_score):
    fb = FeedbackItem(
        organization_id=org_id,
        customer_email=email,
        text="crm provider generalization characterization feedback",
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


class TestHealthScoreStabilityCharacterization:
    """
    Fixture: org + customer with 3 feedbacks (sentiment=[0.5,-0.2,0.1],
    churn=[30,60,45]) — same baseline as test_health_crm_component.py — plus a
    CrmEnrichment row (provider left unset so it defaults) with a renewal_date
    10 days out (HIGH band, crm_component == 25.0).

    Default health_weight_crm is 0, so crm_component does not move the final
    health_score (still 47), but it IS present in the returned dict. This
    snapshot was captured by running compute_health_score() against this
    exact fixture prior to any provider-generalization code changes.
    """

    EMAIL = "crm_generalization_stability@example.com"

    @pytest.fixture(autouse=True)
    def seed(self, db, test_organization):
        for sentiment, churn in [(0.5, 30), (-0.2, 60), (0.1, 45)]:
            _make_feedback(db, test_organization.id, self.EMAIL, sentiment, churn)

        renewal_date_obj = date.today() + timedelta(days=10)
        renewal_dt = datetime(
            renewal_date_obj.year, renewal_date_obj.month, renewal_date_obj.day
        )
        db.add(CrmEnrichment(
            organization_id=test_organization.id,
            customer_email=self.EMAIL,
            company_name="HubSpot Characterization Co",
            lifecycle_stage="customer",
            arr=50000.0,
            renewal_date=renewal_dt,
            deal_name="Characterization Renewal Deal",
            deal_stage="negotiation",
            deal_amount=25000.0,
            last_synced_at=datetime.utcnow(),
        ))
        db.commit()

    def test_health_score_snapshot_unchanged(self, db, test_organization):
        """Captured snapshot — must be byte-for-byte identical before/after
        the provider generalization (Phases 2-4)."""
        result = compute_health_score(test_organization.id, self.EMAIL, db)

        assert result["health_score"] == 47
        assert result["churn_risk_component"] == 55
        assert result["sentiment_component"] == 56
        assert result["resolution_component"] == 50
        assert result["frequency_component"] == 10
        assert result["usage_component"] == pytest.approx(50.0)
        assert result["crm_component"] == pytest.approx(25.0)
        assert result["risk_level"] == "at_risk"
        assert result["confidence_level"] == "medium"
        assert result["feedback_count"] == 3


class TestSerializerFieldsStabilityCharacterization:
    """
    Fixture: CustomerHealth row + CrmEnrichment row (provider left unset so
    it defaults to 'hubspot') mirroring
    test_customer_profile.py::test_profile_includes_crm_fields_when_row_exists.

    Asserts serialize_customer_profile() returns the 7 crm_* fields with the
    expected values — must remain unchanged through Phases 2-4 (an 8th
    optional crm_provider field may be ADDED in Phase 4, but these 7 must not
    change).
    """

    EMAIL = "crm_serializer_stability@example.com"

    @pytest.fixture(autouse=True)
    def seed(self, db, test_organization):
        self.health = CustomerHealth(
            organization_id=test_organization.id,
            customer_email=self.EMAIL,
            customer_name="Serializer Stability Customer",
            health_score=60,
            risk_level="moderate",
            feedback_count=5,
            confidence_level="medium",
            churn_risk_component=50,
            sentiment_component=60,
            resolution_component=70,
            frequency_component=55,
            last_feedback_at=datetime.utcnow(),
            is_archived=False,
        )
        db.add(self.health)
        db.commit()
        db.refresh(self.health)

        db.add(CrmEnrichment(
            organization_id=test_organization.id,
            customer_email=self.EMAIL,
            company_name="HubSpot Serializer Co",
            lifecycle_stage="customer",
            arr=50000.0,
            renewal_date=datetime(2026, 12, 31),
            deal_name="Serializer Renewal Deal",
            deal_stage="negotiation",
            deal_amount=25000.0,
            last_synced_at=datetime(2026, 6, 30, 10, 0, 0),
        ))
        db.commit()

    def test_serialized_crm_fields_snapshot_unchanged(self, db, test_organization):
        result = serialize_customer_profile(self.health, db)

        assert result["crm_company_name"] == "HubSpot Serializer Co"
        assert result["crm_lifecycle_stage"] == "customer"
        assert result["crm_arr"] == pytest.approx(50000.0)
        assert result["crm_renewal_date"] == datetime(2026, 12, 31)
        assert result["crm_deal_name"] == "Serializer Renewal Deal"
        assert result["crm_deal_stage"] == "negotiation"
        assert result["crm_deal_amount"] == pytest.approx(25000.0)
