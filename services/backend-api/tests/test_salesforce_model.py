"""
Tests for SalesforceIntegration SQLAlchemy model (Phase 1).

Mirrors tests/test_hubspot_model.py.
"""
import pytest
from sqlalchemy.orm import Session
from datetime import datetime


class TestSalesforceIntegrationModel:
    def test_model_importable(self):
        from src.models.salesforce_integration import SalesforceIntegration
        assert SalesforceIntegration.__tablename__ == "salesforce_integrations"

    def test_model_in_models_init(self):
        from src.models import SalesforceIntegration as S
        assert S.__tablename__ == "salesforce_integrations"

    def test_create_and_query(self, db: Session, test_organization):
        from src.models.salesforce_integration import SalesforceIntegration
        row = SalesforceIntegration(
            organization_id=test_organization.id,
            refresh_token="encrypted_sentinel",
            instance_url="https://acme.my.salesforce.com",
            sf_org_id="00Dxx0000001gPFEAY",
            token_hint="...abcd",
            connected_at=datetime.utcnow(),
            is_active=True,
            contacts_synced=0,
            contacts_matched=0,
        )
        db.add(row)
        db.commit()
        fetched = db.query(SalesforceIntegration).filter_by(
            organization_id=test_organization.id
        ).first()
        assert fetched is not None
        assert fetched.instance_url == "https://acme.my.salesforce.com"
        assert fetched.sf_org_id == "00Dxx0000001gPFEAY"

    def test_organization_id_unique_constraint(self, db: Session, test_organization):
        from src.models.salesforce_integration import SalesforceIntegration
        for _ in range(2):
            db.add(SalesforceIntegration(
                organization_id=test_organization.id,
                refresh_token="x",
                connected_at=datetime.utcnow(),
            ))
        with pytest.raises(Exception):  # IntegrityError or similar
            db.commit()

    def test_nullable_fields(self, db: Session, test_organization):
        from src.models.salesforce_integration import SalesforceIntegration
        row = SalesforceIntegration(
            organization_id=test_organization.id,
            refresh_token="encrypted_x",
            connected_at=datetime.utcnow(),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        assert row.instance_url is None
        assert row.sf_org_id is None
        assert row.last_synced_at is None
        assert row.last_error is None
        assert row.contacts_synced == 0
        assert row.contacts_matched == 0
        assert row.is_active is True


class TestSalesforceWritebackColumns:
    """model-migrations Phase 1: writeback config/status columns, mirroring
    HubSpot's TestHubSpotWritebackColumns in tests/test_hubspot_model.py."""

    def test_writeback_defaults(self, db: Session, test_organization):
        from src.models.salesforce_integration import SalesforceIntegration
        row = SalesforceIntegration(
            organization_id=test_organization.id,
            refresh_token="encrypted_x",
            connected_at=datetime.utcnow(),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        assert row.writeback_enabled is False
        assert row.writeback_field_name is None
        assert row.last_writeback_at is None
        assert row.last_writeback_status is None
        assert row.last_writeback_error is None
        assert row.contacts_written == 0

    def test_writeback_fields_settable(self, db: Session, test_organization):
        from src.models.salesforce_integration import SalesforceIntegration
        row = SalesforceIntegration(
            organization_id=test_organization.id,
            refresh_token="encrypted_x",
            connected_at=datetime.utcnow(),
            writeback_enabled=True,
            writeback_field_name="Rereflect_Health_Score__c",
            last_writeback_at=datetime.utcnow(),
            last_writeback_status="ok",
            last_writeback_error=None,
            contacts_written=5,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        assert row.writeback_enabled is True
        assert row.writeback_field_name == "Rereflect_Health_Score__c"
        assert row.last_writeback_status == "ok"
        assert row.contacts_written == 5


class TestCrmEnrichmentSalesforceContactId:
    """model-migrations Phase 1: salesforce_contact_id round-trips and
    defaults null, mirroring hubspot_contact_id."""

    def test_salesforce_contact_id_defaults_none(self, db: Session, test_organization):
        from src.models.crm_enrichment import CrmEnrichment
        row = CrmEnrichment(
            organization_id=test_organization.id,
            customer_email="sf_contact_id_default@example.com",
            last_synced_at=datetime.utcnow(),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        assert row.salesforce_contact_id is None

    def test_salesforce_contact_id_settable_and_roundtrips(self, db: Session, test_organization):
        from src.models.crm_enrichment import CrmEnrichment
        row = CrmEnrichment(
            organization_id=test_organization.id,
            customer_email="sf_contact_id_set@example.com",
            last_synced_at=datetime.utcnow(),
            salesforce_contact_id="003xx000004TmiQAAS",
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        assert row.salesforce_contact_id == "003xx000004TmiQAAS"
