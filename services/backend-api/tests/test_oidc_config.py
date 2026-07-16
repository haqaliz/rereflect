"""
TDD tests for the OidcConfig database model.

Mirrors test_zendesk_models.py's TestZendeskIntegrationModel — one row per
org, Fernet-encrypted client_secret (encryption is a route-layer concern,
not exercised here), organization-scoped uniqueness.
"""
import pytest
from sqlalchemy.orm import Session

from src.models.organization import Organization


class TestOidcConfigModel:

    def test_importable(self):
        from src.models.oidc_config import OidcConfig
        assert OidcConfig is not None

    def test_exported_from_init(self):
        from src.models import OidcConfig
        assert OidcConfig is not None

    def test_table_name(self):
        from src.models.oidc_config import OidcConfig
        assert OidcConfig.__tablename__ == "oidc_configs"

    def test_columns_present(self):
        from src.models.oidc_config import OidcConfig
        columns = OidcConfig.__table__.columns.keys()
        expected = {
            "id", "organization_id", "issuer_url", "client_id",
            "client_secret", "secret_hint", "enabled",
            "allowed_email_domains", "button_label",
            "created_at", "updated_at",
        }
        assert expected.issubset(set(columns))

    def test_unique_constraint_on_organization_id(self):
        from src.models.oidc_config import OidcConfig
        constraint_names = {
            c.name for c in OidcConfig.__table__.constraints
            if hasattr(c, "name") and c.name
        }
        assert "uq_oidc_configs_org_id" in constraint_names

    def test_oidc_config_model_roundtrip(self, db: Session, test_organization: Organization):
        from src.models.oidc_config import OidcConfig

        config = OidcConfig(
            organization_id=test_organization.id,
            issuer_url="https://idp.example.com",
            client_id="client-abc-123",
            client_secret="encrypted_secret_value",
            secret_hint="...wxyz",
            enabled=True,
            allowed_email_domains=["acme.com", "example.org"],
            button_label="Sign in with Acme SSO",
        )
        db.add(config)
        db.commit()
        db.refresh(config)

        assert config.id is not None
        assert config.organization_id == test_organization.id
        assert config.issuer_url == "https://idp.example.com"
        assert config.client_id == "client-abc-123"
        assert config.client_secret == "encrypted_secret_value"
        assert config.secret_hint == "...wxyz"
        assert config.enabled is True
        assert config.allowed_email_domains == ["acme.com", "example.org"]
        assert config.button_label == "Sign in with Acme SSO"
        assert config.created_at is not None
        assert config.updated_at is not None

    def test_defaults(self, db: Session, test_organization: Organization):
        from src.models.oidc_config import OidcConfig

        config = OidcConfig(
            organization_id=test_organization.id,
            issuer_url="https://idp.example.com",
            client_id="client-abc-123",
            client_secret="encrypted_secret_value",
        )
        db.add(config)
        db.commit()
        db.refresh(config)

        assert config.enabled is False
        assert config.button_label == "Sign in with SSO"
        assert config.secret_hint is None
        assert config.allowed_email_domains is None
