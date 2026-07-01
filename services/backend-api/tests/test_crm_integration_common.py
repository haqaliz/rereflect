"""
Tests for shared CRM integration helpers (Phase 2 of salesforce-connection).

- another_crm_active(db, org_id, exclude_provider): symmetric one-CRM guard.
- purge_crm_enrichment(db, org_id, provider): delete provider rows + recompute
  affected customers' health scores (locked decision 7).
"""
from datetime import datetime
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

from src.models.hubspot_integration import HubSpotIntegration
from src.models.salesforce_integration import SalesforceIntegration
from src.models.crm_enrichment import CrmEnrichment


# ─────────────────────────── another_crm_active ────────────────────────────


class TestAnotherCrmActive:
    def test_returns_none_when_nothing_connected(self, db: Session, test_organization):
        from src.services.crm_integration_common import another_crm_active
        assert another_crm_active(db, test_organization.id, exclude_provider="salesforce") is None

    def test_detects_active_hubspot(self, db: Session, test_organization):
        from src.services.crm_integration_common import another_crm_active
        db.add(HubSpotIntegration(
            organization_id=test_organization.id,
            access_token="enc",
            connected_at=datetime.utcnow(),
            is_active=True,
        ))
        db.commit()
        assert another_crm_active(db, test_organization.id, exclude_provider="salesforce") == "hubspot"

    def test_detects_active_salesforce(self, db: Session, test_organization):
        from src.services.crm_integration_common import another_crm_active
        db.add(SalesforceIntegration(
            organization_id=test_organization.id,
            refresh_token="enc",
            connected_at=datetime.utcnow(),
            is_active=True,
        ))
        db.commit()
        assert another_crm_active(db, test_organization.id, exclude_provider="hubspot") == "salesforce"

    def test_returns_none_when_only_excluded_provider_active(self, db: Session, test_organization):
        from src.services.crm_integration_common import another_crm_active
        db.add(HubSpotIntegration(
            organization_id=test_organization.id,
            access_token="enc",
            connected_at=datetime.utcnow(),
            is_active=True,
        ))
        db.commit()
        # HubSpot is active, but we exclude hubspot from the check
        assert another_crm_active(db, test_organization.id, exclude_provider="hubspot") is None

    def test_ignores_inactive_rows(self, db: Session, test_organization):
        from src.services.crm_integration_common import another_crm_active
        db.add(HubSpotIntegration(
            organization_id=test_organization.id,
            access_token="enc",
            connected_at=datetime.utcnow(),
            is_active=False,
        ))
        db.commit()
        assert another_crm_active(db, test_organization.id, exclude_provider="salesforce") is None

    def test_scoped_to_org(self, db: Session, test_organization):
        from src.models.organization import Organization
        from src.services.crm_integration_common import another_crm_active
        other_org = Organization(name="Other Org", plan="pro")
        db.add(other_org)
        db.commit()
        db.refresh(other_org)
        db.add(HubSpotIntegration(
            organization_id=other_org.id,
            access_token="enc",
            connected_at=datetime.utcnow(),
            is_active=True,
        ))
        db.commit()
        assert another_crm_active(db, test_organization.id, exclude_provider="salesforce") is None


# ─────────────────────────── purge_crm_enrichment ───────────────────────────


class TestPurgeCrmEnrichment:
    def _make_enrichment(self, db, org_id, email, provider):
        row = CrmEnrichment(
            organization_id=org_id,
            customer_email=email,
            provider=provider,
            last_synced_at=datetime.utcnow(),
        )
        db.add(row)
        return row

    def test_deletes_only_matching_provider_rows(self, db: Session, test_organization):
        from src.services.crm_integration_common import purge_crm_enrichment
        self._make_enrichment(db, test_organization.id, "a@test.com", "salesforce")
        self._make_enrichment(db, test_organization.id, "b@test.com", "hubspot")
        db.commit()

        with patch("src.services.health_score_service.update_customer_health"):
            purge_crm_enrichment(db, test_organization.id, "salesforce")

        remaining = db.query(CrmEnrichment).filter_by(
            organization_id=test_organization.id
        ).all()
        assert len(remaining) == 1
        assert remaining[0].provider == "hubspot"
        assert remaining[0].customer_email == "b@test.com"

    def test_returns_deleted_count(self, db: Session, test_organization):
        from src.services.crm_integration_common import purge_crm_enrichment
        self._make_enrichment(db, test_organization.id, "a@test.com", "salesforce")
        self._make_enrichment(db, test_organization.id, "b@test.com", "salesforce")
        db.commit()

        with patch("src.services.health_score_service.update_customer_health"):
            count = purge_crm_enrichment(db, test_organization.id, "salesforce")

        assert count == 2

    def test_triggers_health_recompute_for_each_affected_email(self, db: Session, test_organization):
        from src.services.crm_integration_common import purge_crm_enrichment
        self._make_enrichment(db, test_organization.id, "a@test.com", "salesforce")
        self._make_enrichment(db, test_organization.id, "b@test.com", "salesforce")
        db.commit()

        with patch("src.services.health_score_service.update_customer_health") as mock_update:
            purge_crm_enrichment(db, test_organization.id, "salesforce")

        assert mock_update.call_count == 2
        called_emails = {call.args[1] for call in mock_update.call_args_list}
        assert called_emails == {"a@test.com", "b@test.com"}

    def test_no_rows_is_a_noop(self, db: Session, test_organization):
        from src.services.crm_integration_common import purge_crm_enrichment
        with patch("src.services.health_score_service.update_customer_health") as mock_update:
            count = purge_crm_enrichment(db, test_organization.id, "salesforce")
        assert count == 0
        mock_update.assert_not_called()

    def test_recompute_failure_does_not_raise(self, db: Session, test_organization):
        """Health recompute is best-effort — a failure must not crash disconnect."""
        from src.services.crm_integration_common import purge_crm_enrichment
        self._make_enrichment(db, test_organization.id, "a@test.com", "salesforce")
        db.commit()

        with patch(
            "src.services.health_score_service.update_customer_health",
            side_effect=RuntimeError("boom"),
        ):
            count = purge_crm_enrichment(db, test_organization.id, "salesforce")
        assert count == 1
