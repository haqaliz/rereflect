"""
TDD tests for the OidcConfig database model and admin CRUD route.

Mirrors test_zendesk_models.py's TestZendeskIntegrationModel — one row per
org, Fernet-encrypted client_secret (encryption is a route-layer concern,
not exercised here), organization-scoped uniqueness. The route tests
(TestOidcConfigRoute) mirror test_zendesk_connection.py's Fernet + RBAC
patterns.
"""
import os

import pytest
from cryptography.fernet import Fernet
from sqlalchemy.orm import Session

from src.api.auth import create_access_token, hash_password
from src.models.organization import Organization
from src.models.user import User
from src.utils.encryption import decrypt_api_key


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


# ──────────────────────── Route fixtures ─────────────────────────────────────


@pytest.fixture
def valid_encryption_key(monkeypatch):
    """Set a valid Fernet key for LLM_ENCRYPTION_KEY for the duration of the test."""
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("LLM_ENCRYPTION_KEY", key)
    return key


@pytest.fixture
def owner_user(db: Session, test_organization: Organization) -> User:
    user = User(
        email="oidc_owner@test.com",
        password_hash=hash_password("pw"),
        organization_id=test_organization.id,
        role="owner",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def owner_headers(owner_user: User) -> dict:
    token = create_access_token({
        "user_id": owner_user.id,
        "organization_id": owner_user.organization_id,
        "role": owner_user.role,
    })
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def member_user(db: Session, test_organization: Organization) -> User:
    user = User(
        email="oidc_member@test.com",
        password_hash=hash_password("pw"),
        organization_id=test_organization.id,
        role="member",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def member_headers(member_user: User) -> dict:
    token = create_access_token({
        "user_id": member_user.id,
        "organization_id": member_user.organization_id,
        "role": member_user.role,
    })
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def other_organization(db: Session) -> Organization:
    org = Organization(name="Other Org", plan="pro")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


@pytest.fixture
def other_owner_user(db: Session, other_organization: Organization) -> User:
    user = User(
        email="oidc_other_owner@test.com",
        password_hash=hash_password("pw"),
        organization_id=other_organization.id,
        role="owner",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def other_owner_headers(other_owner_user: User) -> dict:
    token = create_access_token({
        "user_id": other_owner_user.id,
        "organization_id": other_owner_user.organization_id,
        "role": other_owner_user.role,
    })
    return {"Authorization": f"Bearer {token}"}


VALID_PAYLOAD = {
    "issuer_url": "https://idp.example.com",
    "client_id": "client-abc-123",
    "client_secret": "s3cr3t-plaintext-value",
    "enabled": False,
    "allowed_email_domains": ["acme.com"],
    "button_label": "Sign in with Acme SSO",
}


class TestOidcConfigRoute:
    """CRUD route tests for /api/v1/settings/oidc (AC2-AC5)."""

    # ── GET when unconfigured ──────────────────────────────────────────────

    def test_get_unconfigured_returns_configured_false(self, client, owner_headers):
        resp = client.get("/api/v1/settings/oidc", headers=owner_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["configured"] is False

    # ── PUT stores encrypted + returns hint not secret (AC2) ───────────────

    def test_put_stores_encrypted_secret_and_hides_it_in_response(
        self, client, db, test_organization, owner_headers, valid_encryption_key
    ):
        resp = client.put("/api/v1/settings/oidc", json=VALID_PAYLOAD, headers=owner_headers)
        assert resp.status_code == 200
        body = resp.json()

        assert "client_secret" not in body
        assert body["secret_hint"] == "...alue"
        assert body["configured"] is True
        assert body["issuer_url"] == VALID_PAYLOAD["issuer_url"]
        assert body["client_id"] == VALID_PAYLOAD["client_id"]
        assert body["allowed_email_domains"] == ["acme.com"]

        from src.models.oidc_config import OidcConfig

        row = db.query(OidcConfig).filter(
            OidcConfig.organization_id == test_organization.id
        ).first()
        assert row is not None
        assert row.client_secret != VALID_PAYLOAD["client_secret"]
        assert decrypt_api_key(row.client_secret) == VALID_PAYLOAD["client_secret"]

    def test_put_update_without_secret_preserves_existing(
        self, client, db, test_organization, owner_headers, valid_encryption_key
    ):
        client.put("/api/v1/settings/oidc", json=VALID_PAYLOAD, headers=owner_headers)

        update_payload = dict(VALID_PAYLOAD)
        update_payload.pop("client_secret")
        update_payload["issuer_url"] = "https://idp2.example.com"

        resp = client.put("/api/v1/settings/oidc", json=update_payload, headers=owner_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["issuer_url"] == "https://idp2.example.com"
        assert body["secret_hint"] == "...alue"

        from src.models.oidc_config import OidcConfig

        row = db.query(OidcConfig).filter(
            OidcConfig.organization_id == test_organization.id
        ).first()
        assert decrypt_api_key(row.client_secret) == VALID_PAYLOAD["client_secret"]

    # ── Missing LLM_ENCRYPTION_KEY -> 422 (AC3) ─────────────────────────────

    def test_put_missing_encryption_key_returns_422(self, client, owner_headers, monkeypatch):
        monkeypatch.delenv("LLM_ENCRYPTION_KEY", raising=False)
        resp = client.put("/api/v1/settings/oidc", json=VALID_PAYLOAD, headers=owner_headers)
        assert resp.status_code == 422

    # ── Enabling a second org's config -> 422 (D5, AC4) ─────────────────────

    def test_enabling_second_config_returns_422(
        self, client, owner_headers, other_owner_headers, valid_encryption_key
    ):
        first_payload = dict(VALID_PAYLOAD)
        first_payload["enabled"] = True
        resp = client.put("/api/v1/settings/oidc", json=first_payload, headers=owner_headers)
        assert resp.status_code == 200
        assert resp.json()["enabled"] is True

        second_payload = dict(VALID_PAYLOAD)
        second_payload["enabled"] = True
        second_payload["issuer_url"] = "https://idp-other.example.com"
        resp2 = client.put("/api/v1/settings/oidc", json=second_payload, headers=other_owner_headers)
        assert resp2.status_code == 422

    def test_reenabling_own_config_is_allowed(self, client, owner_headers, valid_encryption_key):
        first_payload = dict(VALID_PAYLOAD)
        first_payload["enabled"] = True
        client.put("/api/v1/settings/oidc", json=first_payload, headers=owner_headers)

        resp = client.put("/api/v1/settings/oidc", json=first_payload, headers=owner_headers)
        assert resp.status_code == 200
        assert resp.json()["enabled"] is True

    # ── Member forbidden (AC5) ───────────────────────────────────────────────

    def test_get_member_gets_403(self, client, member_headers):
        resp = client.get("/api/v1/settings/oidc", headers=member_headers)
        assert resp.status_code == 403

    def test_put_member_gets_403(self, client, member_headers, valid_encryption_key):
        resp = client.put("/api/v1/settings/oidc", json=VALID_PAYLOAD, headers=member_headers)
        assert resp.status_code == 403

    def test_delete_member_gets_403(self, client, member_headers):
        resp = client.delete("/api/v1/settings/oidc", headers=member_headers)
        assert resp.status_code == 403

    # ── DELETE happy path + 404 ──────────────────────────────────────────────

    def test_delete_happy_path(self, client, owner_headers, valid_encryption_key):
        client.put("/api/v1/settings/oidc", json=VALID_PAYLOAD, headers=owner_headers)

        resp = client.delete("/api/v1/settings/oidc", headers=owner_headers)
        assert resp.status_code == 200

        get_resp = client.get("/api/v1/settings/oidc", headers=owner_headers)
        assert get_resp.json()["configured"] is False

    def test_delete_when_none_returns_404(self, client, owner_headers):
        resp = client.delete("/api/v1/settings/oidc", headers=owner_headers)
        assert resp.status_code == 404

    # ── allowed_email_domains=[] round-trips as deny-all ────────────────────

    def test_empty_allowed_domains_round_trips_as_empty_list(
        self, client, owner_headers, valid_encryption_key
    ):
        payload = dict(VALID_PAYLOAD)
        payload["allowed_email_domains"] = []

        resp = client.put("/api/v1/settings/oidc", json=payload, headers=owner_headers)
        assert resp.status_code == 200
        assert resp.json()["allowed_email_domains"] == []

        get_resp = client.get("/api/v1/settings/oidc", headers=owner_headers)
        assert get_resp.json()["allowed_email_domains"] == []

    def test_invalid_domain_entry_returns_422(self, client, owner_headers, valid_encryption_key):
        payload = dict(VALID_PAYLOAD)
        payload["allowed_email_domains"] = ["not-a-domain"]

        resp = client.put("/api/v1/settings/oidc", json=payload, headers=owner_headers)
        assert resp.status_code == 422
