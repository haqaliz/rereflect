"""
TDD tests for the SamlConfig database model, admin CRUD route, the public
SAML status probe, and the cross-provider single-SSO guard.

Mirrors test_oidc_config.py exactly in shape/security posture. Key
differences from OIDC:
  - idp_x509_cert is a PUBLIC PEM cert, stored plaintext (not Fernet-
    encrypted) — no LLM_ENCRYPTION_KEY dependency anywhere in this file.
  - idp_x509_cert is PEM-validated on save (422 on garbage) and the
    response returns a SHA-256 cert_fingerprint, never the raw PEM.
  - idp_sso_url is SSRF + https-validated on save (422 on failure).
  - Cross-provider guard: enabling SAML 422s if OIDC (or another SAML) is
    enabled, and (characterization) enabling OIDC now 422s if SAML is
    enabled, while OIDC's own same-provider D5 behavior/message stays
    byte-stable.
"""
import pytest
from sqlalchemy.orm import Session

from src.api.auth import create_access_token, hash_password
from src.models.organization import Organization
from src.models.user import User


VALID_TEST_CERT_PEM = """-----BEGIN CERTIFICATE-----
MIICyjCCAbKgAwIBAgIUP35sxDOi+ld1iCIVBRgXwIteYMIwDQYJKoZIhvcNAQEL
BQAwHzEdMBsGA1UEAwwUdGVzdC1pZHAuZXhhbXBsZS5jb20wHhcNMjYwNzE2MjA1
NzMzWhcNMzYwNzE0MjA1NzMzWjAfMR0wGwYDVQQDDBR0ZXN0LWlkcC5leGFtcGxl
LmNvbTCCASIwDQYJKoZIhvcNAQEBBQADggEPADCCAQoCggEBAKO3jNiubUIBNVT0
TjgMD/YI5raMG3NLJ/Uy3jYF4bcfaKqJ0D9m7i/mIZxL1fSdoaIYN0UveeRd3ldF
dFOnBlEO6jSMilx/nqrrFJAZfEa7j8BW6bQoz9jb40Q76EjkW/TzXKSjgSZnzEzN
ROWvb2+fNdjlsfIRO/GOu+B+otdbgZUGiEGSoAChT9p4jxxwFOYrBd0uzwwUP+6i
1QQWhWGa1HrXOQWwZg0fs3AQr58eWdVMC+vfOgaG0msOoaChRXU7M6fkDRWyBAh3
9UgMtsNnIH7B56z4sI+Xi3WFoe+WsGMZBtYtTSYaDxuYXQRKlvaCEHWBNTLnHfWC
1o2FJv0CAwEAATANBgkqhkiG9w0BAQsFAAOCAQEAigAjNcVjOb5mtQtn38SkxqFB
+mQcqdeuW0rok83b6r4berM4UV9XpsWiPuMMVpZbINuLqN94MqjtA8LzP/Qv/8WF
hzYrL9gFMWAWYfrkzuihFtoW6lTFsMeLWvvZAvkiyTNo6Zq6mqTalndYk4xg+sqS
oql3r+JBNYYypOS/3LyTVhKCaoihVq5HF3Cx29x5oUBsQTV9LNZM/ouzVzKOaUOV
XmOXjHtXG08NrWjovlkT1NWyq9MBXifUTmjPVFoOTRdQXu5ZRv1CZZ583ruR0Zkq
c47ebzutvOs68eqstfP2f71qlj0H3gt+a009MM3TmtlvayhN4vDAT5L1ZmlgBw==
-----END CERTIFICATE-----
"""

GARBAGE_CERT_PEM = "-----BEGIN CERTIFICATE-----\nnot-base64!!!\n-----END CERTIFICATE-----\n"


class TestSamlConfigModel:

    def test_importable(self):
        from src.models.saml_config import SamlConfig
        assert SamlConfig is not None

    def test_exported_from_init(self):
        from src.models import SamlConfig
        assert SamlConfig is not None

    def test_table_name(self):
        from src.models.saml_config import SamlConfig
        assert SamlConfig.__tablename__ == "saml_configs"

    def test_columns_present(self):
        from src.models.saml_config import SamlConfig
        columns = SamlConfig.__table__.columns.keys()
        expected = {
            "id", "organization_id", "idp_entity_id", "idp_sso_url",
            "idp_x509_cert", "email_attribute", "enabled",
            "allowed_email_domains", "button_label",
            "created_at", "updated_at",
        }
        assert expected.issubset(set(columns))

    def test_unique_constraint_on_organization_id(self):
        from src.models.saml_config import SamlConfig
        constraint_names = {
            c.name for c in SamlConfig.__table__.constraints
            if hasattr(c, "name") and c.name
        }
        assert "uq_saml_configs_org_id" in constraint_names

    def test_saml_config_model_roundtrip(self, db: Session, test_organization: Organization):
        from src.models.saml_config import SamlConfig

        config = SamlConfig(
            organization_id=test_organization.id,
            idp_entity_id="https://idp.example.com/entity",
            idp_sso_url="https://idp.example.com/sso",
            idp_x509_cert=VALID_TEST_CERT_PEM,
            email_attribute="email",
            enabled=True,
            allowed_email_domains=["acme.com", "example.org"],
            button_label="Sign in with Acme SSO",
        )
        db.add(config)
        db.commit()
        db.refresh(config)

        assert config.id is not None
        assert config.organization_id == test_organization.id
        assert config.idp_entity_id == "https://idp.example.com/entity"
        assert config.idp_sso_url == "https://idp.example.com/sso"
        assert config.idp_x509_cert == VALID_TEST_CERT_PEM
        assert config.email_attribute == "email"
        assert config.enabled is True
        assert config.allowed_email_domains == ["acme.com", "example.org"]
        assert config.button_label == "Sign in with Acme SSO"
        assert config.created_at is not None
        assert config.updated_at is not None

    def test_defaults(self, db: Session, test_organization: Organization):
        from src.models.saml_config import SamlConfig

        config = SamlConfig(
            organization_id=test_organization.id,
            idp_entity_id="https://idp.example.com/entity",
            idp_sso_url="https://idp.example.com/sso",
            idp_x509_cert=VALID_TEST_CERT_PEM,
        )
        db.add(config)
        db.commit()
        db.refresh(config)

        assert config.enabled is False
        assert config.button_label == "Sign in with SSO"
        assert config.email_attribute is None
        assert config.allowed_email_domains is None


class TestUserSamlSubjectColumn:

    def test_user_has_saml_subject_column(self):
        assert "saml_subject" in User.__table__.columns
        index_names = {ix.name: ix for ix in User.__table__.indexes}
        assert "ix_users_saml_subject" in index_names
        assert index_names["ix_users_saml_subject"].unique is True


# ──────────────────────── Route fixtures ─────────────────────────────────────


@pytest.fixture(autouse=True)
def _noop_ssrf(monkeypatch):
    """Happy-path default: don't hit real DNS. Dedicated SSRF tests override this."""
    monkeypatch.setattr("src.api.routes.saml_config.assert_host_not_ssrf", lambda host: None)


@pytest.fixture
def owner_user(db: Session, test_organization: Organization) -> User:
    user = User(
        email="saml_owner@test.com",
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
        email="saml_member@test.com",
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
        email="saml_other_owner@test.com",
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
    "idp_entity_id": "https://test-idp.example.com/entity",
    "idp_sso_url": "https://test-idp.example.com/sso",
    "idp_x509_cert": VALID_TEST_CERT_PEM,
    "email_attribute": "email",
    "enabled": False,
    "allowed_email_domains": ["acme.com"],
    "button_label": "Sign in with Acme SSO",
}


class TestSamlConfigRoute:
    """CRUD route tests for /api/v1/settings/saml."""

    # ── GET when unconfigured ──────────────────────────────────────────────

    def test_get_unconfigured_returns_configured_false(self, client, owner_headers):
        resp = client.get("/api/v1/settings/saml", headers=owner_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["configured"] is False

    # ── PUT stores plaintext + returns fingerprint not PEM ──────────────────

    def test_put_creates_and_returns_fingerprint_not_pem(
        self, client, db, test_organization, owner_headers
    ):
        resp = client.put("/api/v1/settings/saml", json=VALID_PAYLOAD, headers=owner_headers)
        assert resp.status_code == 200
        body = resp.json()

        assert "idp_x509_cert" not in body
        assert body["configured"] is True
        assert body["cert_fingerprint"] is not None
        assert len(body["cert_fingerprint"].split(":")) == 32  # SHA-256, colon-hex
        assert body["idp_entity_id"] == VALID_PAYLOAD["idp_entity_id"]
        assert body["idp_sso_url"] == VALID_PAYLOAD["idp_sso_url"]
        assert body["allowed_email_domains"] == ["acme.com"]

        from src.models.saml_config import SamlConfig

        row = db.query(SamlConfig).filter(
            SamlConfig.organization_id == test_organization.id
        ).first()
        assert row is not None
        assert row.idp_x509_cert == VALID_TEST_CERT_PEM  # plaintext, NOT encrypted

    def test_put_update_preserves_cert_when_omitted(
        self, client, db, test_organization, owner_headers
    ):
        client.put("/api/v1/settings/saml", json=VALID_PAYLOAD, headers=owner_headers)

        update_payload = dict(VALID_PAYLOAD)
        update_payload.pop("idp_x509_cert")
        update_payload["idp_entity_id"] = "https://test-idp2.example.com/entity"

        resp = client.put("/api/v1/settings/saml", json=update_payload, headers=owner_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["idp_entity_id"] == "https://test-idp2.example.com/entity"

        from src.models.saml_config import SamlConfig

        row = db.query(SamlConfig).filter(
            SamlConfig.organization_id == test_organization.id
        ).first()
        assert row.idp_x509_cert == VALID_TEST_CERT_PEM

    # ── PEM validation ────────────────────────────────────────────────────

    def test_put_invalid_pem_returns_422(self, client, owner_headers):
        payload = dict(VALID_PAYLOAD)
        payload["idp_x509_cert"] = GARBAGE_CERT_PEM
        resp = client.put("/api/v1/settings/saml", json=payload, headers=owner_headers)
        assert resp.status_code == 422

    # ── SSRF / scheme validation ─────────────────────────────────────────

    def test_put_ssrf_idp_url_returns_422(self, client, owner_headers, monkeypatch):
        from src.utils.ssrf import SsrfError

        def _raise(host):
            raise SsrfError("blocked")

        monkeypatch.setattr("src.api.routes.saml_config.assert_host_not_ssrf", _raise)

        payload = dict(VALID_PAYLOAD)
        payload["idp_sso_url"] = "https://127.0.0.1/sso"
        resp = client.put("/api/v1/settings/saml", json=payload, headers=owner_headers)
        assert resp.status_code == 422

    def test_put_non_https_idp_url_returns_422(self, client, owner_headers):
        payload = dict(VALID_PAYLOAD)
        payload["idp_sso_url"] = "http://idp.example.com/sso"
        resp = client.put("/api/v1/settings/saml", json=payload, headers=owner_headers)
        assert resp.status_code == 422

    # ── Member forbidden ──────────────────────────────────────────────────

    def test_get_member_gets_403(self, client, member_headers):
        resp = client.get("/api/v1/settings/saml", headers=member_headers)
        assert resp.status_code == 403

    def test_put_member_gets_403(self, client, member_headers):
        resp = client.put("/api/v1/settings/saml", json=VALID_PAYLOAD, headers=member_headers)
        assert resp.status_code == 403

    def test_delete_member_gets_403(self, client, member_headers):
        resp = client.delete("/api/v1/settings/saml", headers=member_headers)
        assert resp.status_code == 403

    # ── DELETE happy path + 404 ──────────────────────────────────────────────

    def test_delete_happy_path(self, client, owner_headers):
        client.put("/api/v1/settings/saml", json=VALID_PAYLOAD, headers=owner_headers)

        resp = client.delete("/api/v1/settings/saml", headers=owner_headers)
        assert resp.status_code == 200

        get_resp = client.get("/api/v1/settings/saml", headers=owner_headers)
        assert get_resp.json()["configured"] is False

    def test_delete_when_none_returns_404(self, client, owner_headers):
        resp = client.delete("/api/v1/settings/saml", headers=owner_headers)
        assert resp.status_code == 404

    # ── allowed_email_domains=[] round-trips as deny-all ────────────────────

    def test_empty_allowed_domains_round_trips_as_empty_list(self, client, owner_headers):
        payload = dict(VALID_PAYLOAD)
        payload["allowed_email_domains"] = []

        resp = client.put("/api/v1/settings/saml", json=payload, headers=owner_headers)
        assert resp.status_code == 200
        assert resp.json()["allowed_email_domains"] == []

        get_resp = client.get("/api/v1/settings/saml", headers=owner_headers)
        assert get_resp.json()["allowed_email_domains"] == []

    def test_invalid_domain_entry_returns_422(self, client, owner_headers):
        payload = dict(VALID_PAYLOAD)
        payload["allowed_email_domains"] = ["not-a-domain"]

        resp = client.put("/api/v1/settings/saml", json=payload, headers=owner_headers)
        assert resp.status_code == 422

    # ── Multi-tenancy: org B cannot see org A's config ──────────────────────

    def test_other_org_cannot_see_this_org_config(self, client, owner_headers, other_owner_headers):
        resp = client.put("/api/v1/settings/saml", json=VALID_PAYLOAD, headers=owner_headers)
        assert resp.status_code == 200

        get_resp = client.get("/api/v1/settings/saml", headers=other_owner_headers)
        assert get_resp.status_code == 200
        assert get_resp.json()["configured"] is False


class TestSamlStatusEndpoint:
    """Public, unauthenticated status probe: GET /api/v1/auth/saml/status."""

    def test_unauthenticated_reachable_and_disabled_when_unconfigured(self, client):
        resp = client.get("/api/v1/auth/saml/status")
        assert resp.status_code == 200
        body = resp.json()
        assert body == {"enabled": False, "button_label": "Sign in with SSO"}

    def test_enabled_config_reports_enabled_and_custom_label(
        self, client, db, test_organization
    ):
        from src.models.saml_config import SamlConfig

        config = SamlConfig(
            organization_id=test_organization.id,
            idp_entity_id="https://idp.example.com/entity",
            idp_sso_url="https://idp.example.com/sso",
            idp_x509_cert=VALID_TEST_CERT_PEM,
            enabled=True,
            button_label="Sign in with Acme SSO",
        )
        db.add(config)
        db.commit()

        resp = client.get("/api/v1/auth/saml/status")
        assert resp.status_code == 200
        body = resp.json()
        assert body == {"enabled": True, "button_label": "Sign in with Acme SSO"}

    def test_disabled_config_still_reports_disabled(
        self, client, db, test_organization
    ):
        from src.models.saml_config import SamlConfig

        config = SamlConfig(
            organization_id=test_organization.id,
            idp_entity_id="https://idp.example.com/entity",
            idp_sso_url="https://idp.example.com/sso",
            idp_x509_cert=VALID_TEST_CERT_PEM,
            enabled=False,
            button_label="Sign in with Acme SSO",
        )
        db.add(config)
        db.commit()

        resp = client.get("/api/v1/auth/saml/status")
        assert resp.status_code == 200
        assert resp.json() == {"enabled": False, "button_label": "Sign in with SSO"}

    def test_response_leaks_exactly_two_keys(self, client, db, test_organization):
        from src.models.saml_config import SamlConfig

        config = SamlConfig(
            organization_id=test_organization.id,
            idp_entity_id="https://idp.example.com/entity",
            idp_sso_url="https://idp.example.com/sso",
            idp_x509_cert=VALID_TEST_CERT_PEM,
            enabled=True,
            allowed_email_domains=["acme.com"],
            button_label="Sign in with Acme SSO",
        )
        db.add(config)
        db.commit()

        resp = client.get("/api/v1/auth/saml/status")
        assert set(resp.json().keys()) == {"enabled", "button_label"}


class TestCrossProviderGuard:
    """Cross-provider single-SSO guard (M6): at most one SSO protocol enabled
    per deployment. Covers both directions of the 7.3 matrix in the plan."""

    def test_saml_can_enable_when_no_oidc_enabled(self, client, owner_headers):
        payload = dict(VALID_PAYLOAD)
        payload["enabled"] = True
        resp = client.put("/api/v1/settings/saml", json=payload, headers=owner_headers)
        assert resp.status_code == 200
        assert resp.json()["enabled"] is True

    def test_reenabling_own_saml_config_is_allowed(self, client, owner_headers):
        payload = dict(VALID_PAYLOAD)
        payload["enabled"] = True
        client.put("/api/v1/settings/saml", json=payload, headers=owner_headers)

        resp = client.put("/api/v1/settings/saml", json=payload, headers=owner_headers)
        assert resp.status_code == 200
        assert resp.json()["enabled"] is True

    def test_enabling_saml_while_other_saml_enabled_returns_422(
        self, client, owner_headers, other_owner_headers
    ):
        first_payload = dict(VALID_PAYLOAD)
        first_payload["enabled"] = True
        resp = client.put("/api/v1/settings/saml", json=first_payload, headers=owner_headers)
        assert resp.status_code == 200

        second_payload = dict(VALID_PAYLOAD)
        second_payload["enabled"] = True
        second_payload["idp_entity_id"] = "https://idp-other.example.com/entity"
        resp2 = client.put("/api/v1/settings/saml", json=second_payload, headers=other_owner_headers)
        assert resp2.status_code == 422

    def test_enabling_saml_while_oidc_enabled_returns_422(
        self, client, db, test_organization, owner_headers, other_owner_headers, monkeypatch
    ):
        from src.models.oidc_config import OidcConfig

        # Enable an OIDC config directly in the DB (this aspect doesn't own
        # the OIDC route's Fernet path; the DB row is what the guard checks).
        oidc_row = OidcConfig(
            organization_id=test_organization.id,
            issuer_url="https://oidc-idp.example.com",
            client_id="client-abc",
            client_secret="encrypted-value",
            enabled=True,
        )
        db.add(oidc_row)
        db.commit()

        payload = dict(VALID_PAYLOAD)
        payload["enabled"] = True
        resp = client.put("/api/v1/settings/saml", json=payload, headers=other_owner_headers)
        assert resp.status_code == 422

    def test_invalid_enabling_value_raises_value_error(self, db):
        """M-5: `enabling` must be 'oidc' or 'saml'. Without this guard, a typo
        (or any other value) silently falls into the `else` branch and is
        treated as 'saml' — checking the wrong model entirely. Assert it
        fails loudly instead."""
        from src.api.routes._sso_guard import assert_no_other_provider_enabled

        with pytest.raises(ValueError):
            assert_no_other_provider_enabled(db, enabling="oidcc")

        with pytest.raises(ValueError):
            assert_no_other_provider_enabled(db, enabling="")


class TestOidcCrossCheck:
    """Characterization tests exercising the EDITED OIDC route. Prove the
    +2-line edit is behavior-preserving except the new reciprocal
    cross-check: OIDC's own same-provider D5 behavior/message is
    byte-stable."""

    @pytest.fixture
    def valid_encryption_key(self, monkeypatch):
        from cryptography.fernet import Fernet
        key = Fernet.generate_key().decode()
        monkeypatch.setenv("LLM_ENCRYPTION_KEY", key)
        return key

    OIDC_PAYLOAD = {
        "issuer_url": "https://idp.example.com",
        "client_id": "client-abc-123",
        "client_secret": "s3cr3t-plaintext-value",
        "enabled": False,
        "allowed_email_domains": ["acme.com"],
        "button_label": "Sign in with Acme SSO",
    }

    def test_oidc_still_422s_a_second_oidc(
        self, client, owner_headers, other_owner_headers, valid_encryption_key
    ):
        first_payload = dict(self.OIDC_PAYLOAD)
        first_payload["enabled"] = True
        resp = client.put("/api/v1/settings/oidc", json=first_payload, headers=owner_headers)
        assert resp.status_code == 200
        assert resp.json()["enabled"] is True

        second_payload = dict(self.OIDC_PAYLOAD)
        second_payload["enabled"] = True
        second_payload["issuer_url"] = "https://idp-other.example.com"
        resp2 = client.put("/api/v1/settings/oidc", json=second_payload, headers=other_owner_headers)
        assert resp2.status_code == 422
        assert resp2.json()["detail"] == (
            "Another OIDC config is already enabled; only one may be active per deployment."
        )

    def test_oidc_reenable_own_still_allowed(self, client, owner_headers, valid_encryption_key):
        first_payload = dict(self.OIDC_PAYLOAD)
        first_payload["enabled"] = True
        client.put("/api/v1/settings/oidc", json=first_payload, headers=owner_headers)

        resp = client.put("/api/v1/settings/oidc", json=first_payload, headers=owner_headers)
        assert resp.status_code == 200
        assert resp.json()["enabled"] is True

    def test_enabling_oidc_while_saml_enabled_returns_422(
        self, client, db, test_organization, other_owner_headers, valid_encryption_key
    ):
        from src.models.saml_config import SamlConfig

        saml_row = SamlConfig(
            organization_id=test_organization.id,
            idp_entity_id="https://saml-idp.example.com/entity",
            idp_sso_url="https://saml-idp.example.com/sso",
            idp_x509_cert=VALID_TEST_CERT_PEM,
            enabled=True,
        )
        db.add(saml_row)
        db.commit()

        payload = dict(self.OIDC_PAYLOAD)
        payload["enabled"] = True
        resp = client.put("/api/v1/settings/oidc", json=payload, headers=other_owner_headers)
        assert resp.status_code == 422
