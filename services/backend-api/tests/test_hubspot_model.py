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
