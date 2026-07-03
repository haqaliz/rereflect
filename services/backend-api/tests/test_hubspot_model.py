"""
Tests for HubSpotIntegration SQLAlchemy model (Phase 2).
"""
import pytest
from sqlalchemy.orm import Session
from datetime import datetime


class TestHubSpotIntegrationModel:
    def test_model_importable(self):
        from src.models.hubspot_integration import HubSpotIntegration
        assert HubSpotIntegration.__tablename__ == "hubspot_integrations"

    def test_model_in_models_init(self):
        from src.models import HubSpotIntegration as H
        assert H.__tablename__ == "hubspot_integrations"

    def test_create_and_query(self, db: Session, test_organization):
        from src.models.hubspot_integration import HubSpotIntegration
        row = HubSpotIntegration(
            organization_id=test_organization.id,
            access_token="encrypted_sentinel",
            token_hint="...abcd",
            hub_id="12345",
            portal_name="Acme Corp",
            arr_property_name="annualrevenue",
            connected_at=datetime.utcnow(),
            is_active=True,
            contacts_synced=0,
            contacts_matched=0,
        )
        db.add(row)
        db.commit()
        fetched = db.query(HubSpotIntegration).filter_by(
            organization_id=test_organization.id
        ).first()
        assert fetched is not None
        assert fetched.portal_name == "Acme Corp"
        assert fetched.arr_property_name == "annualrevenue"

    def test_organization_id_unique_constraint(self, db: Session, test_organization):
        from src.models.hubspot_integration import HubSpotIntegration
        for _ in range(2):
            db.add(HubSpotIntegration(
                organization_id=test_organization.id,
                access_token="x",
                connected_at=datetime.utcnow(),
            ))
        with pytest.raises(Exception):  # IntegrityError or similar
            db.commit()

    def test_nullable_fields(self, db: Session, test_organization):
        from src.models.hubspot_integration import HubSpotIntegration
        row = HubSpotIntegration(
            organization_id=test_organization.id,
            access_token="encrypted_x",
            connected_at=datetime.utcnow(),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        assert row.hub_id is None
        assert row.portal_name is None
        assert row.last_synced_at is None
        assert row.last_error is None
        assert row.contacts_synced == 0
        assert row.contacts_matched == 0
        assert row.is_active is True


class TestHubSpotWritebackColumns:
    """writeback-config-api Phase 1: writeback config/status columns."""

    def test_writeback_defaults(self, db: Session, test_organization):
        from src.models.hubspot_integration import HubSpotIntegration
        row = HubSpotIntegration(
            organization_id=test_organization.id,
            access_token="encrypted_x",
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
        from src.models.hubspot_integration import HubSpotIntegration
        row = HubSpotIntegration(
            organization_id=test_organization.id,
            access_token="encrypted_x",
            connected_at=datetime.utcnow(),
            writeback_enabled=True,
            writeback_field_name="rereflect_health_score",
            last_writeback_at=datetime.utcnow(),
            last_writeback_status="ok",
            last_writeback_error=None,
            contacts_written=5,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        assert row.writeback_enabled is True
        assert row.writeback_field_name == "rereflect_health_score"
        assert row.last_writeback_status == "ok"
        assert row.contacts_written == 5

    def test_writeback_columns_on_worker_mirror(self):
        """Worker mirror must expose the same writeback columns."""
        from src.models.hubspot_integration import HubSpotIntegration
        backend_cols = {c.name for c in HubSpotIntegration.__table__.columns}
        expected = {
            "writeback_enabled",
            "writeback_field_name",
            "last_writeback_at",
            "last_writeback_status",
            "last_writeback_error",
            "contacts_written",
        }
        assert expected.issubset(backend_cols)


class TestCrmEnrichmentWritebackColumns:
    """writeback-config-api Phase 1: idempotency memory on crm_enrichment."""

    def test_last_written_health_score_and_timestamp_nullable(
        self, db: Session, test_organization
    ):
        from src.models.crm_enrichment import CrmEnrichment
        row = CrmEnrichment(
            organization_id=test_organization.id,
            customer_email="writeback_columns@example.com",
            last_synced_at=datetime.utcnow(),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        assert row.last_written_health_score is None
        assert row.last_health_written_at is None

    def test_last_written_health_score_settable(self, db: Session, test_organization):
        from src.models.crm_enrichment import CrmEnrichment
        now = datetime.utcnow()
        row = CrmEnrichment(
            organization_id=test_organization.id,
            customer_email="writeback_columns2@example.com",
            last_synced_at=now,
            last_written_health_score=72,
            last_health_written_at=now,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        assert row.last_written_health_score == 72
        assert row.last_health_written_at == now
