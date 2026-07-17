"""
TDD tests for the `login-routes-and-identity` aspect of `saml-sso` (aspect 4).

Wires the SP-initiated SAML flow into HTTP routes on `src/api/routes/auth.py`:

    GET  /api/v1/auth/saml/login     -> 302 to IdP (AuthnRequest + pending row)
    POST /api/v1/auth/saml/callback  -> ACS: validate -> consume -> resolve -> JWT

`SamlProvider` is stubbed at the `src.api.routes.auth.SamlProvider` boundary
(exactly as the OIDC tests patch `src.api.routes.auth.OidcProvider`) so the
route's own branching — not real xmlsec crypto — is under test. The DB-backed
replay store (`saml_auth_requests`) runs for REAL on SQLite, so the
replay/unsolicited/expired branches are genuinely exercised. Real signed
assertion crypto lives in `test_saml_provider.py` (aspect 3).

Mirrors `tests/test_oidc_login.py`.
"""
import base64
from unittest.mock import patch

from sqlalchemy.orm import Session

from src.api.auth import hash_password, decode_access_token
from src.api.routes._oidc_state import sign_state, hash_nonce
from src.models.organization import Organization
from src.models.user import User
from src.models.saml_config import SamlConfig
from src.models.saml_auth_request import SamlAuthRequest
from src.services.saml_provider import SamlValidationError, ValidatedAssertion
from src.services.saml_replay import register_request, consume_request, ConsumeOutcome
from src.utils.ssrf import SsrfError

FRONTEND_URL = "http://localhost:3000"
LOGIN_URL = "/api/v1/auth/saml/login"
ACS_URL = "/api/v1/auth/saml/callback"
IDP_REDIRECT = "https://idp.example.com/sso?SAMLRequest=abc&RelayState=def"


# ── Test doubles / builders ─────────────────────────────────────────────────


class _StubSamlProvider:
    """Stands in for a real `SamlProvider` at the route boundary — no xmlsec.
    `build_authn_request` returns a canned (redirect, request_id);
    `validate_response` returns a canned `ValidatedAssertion` or raises."""

    def __init__(self, redirect_url=IDP_REDIRECT, request_id="req-1",
                 assertion=None, validate_exc=None):
        self._redirect_url = redirect_url
        self._request_id = request_id
        self._assertion = assertion
        self._validate_exc = validate_exc
        self.acs_url = "http://localhost:8000/api/v1/auth/saml/callback"

    def build_authn_request(self, relay_state):
        return (self._redirect_url, self._request_id)

    def validate_response(self, saml_response_b64, *, expected_in_response_to, acs_url):
        if self._validate_exc:
            raise self._validate_exc
        return self._assertion


def _make_enabled_saml_config(db: Session, org: Organization, **overrides) -> SamlConfig:
    defaults = dict(
        organization_id=org.id,
        idp_entity_id="https://idp.example.com/entity",
        idp_sso_url="https://idp.example.com/sso",
        idp_x509_cert="-----BEGIN CERTIFICATE-----\nMIIabc\n-----END CERTIFICATE-----",
        enabled=True,
        allowed_email_domains=["example.com"],
    )
    defaults.update(overrides)
    config = SamlConfig(**defaults)
    db.add(config)
    db.commit()
    db.refresh(config)
    return config


def _assertion(email="user@example.com", subject="nameid-1") -> ValidatedAssertion:
    return ValidatedAssertion(subject=subject, email=email, attributes={})


def _saml_response_b64(in_response_to="req-1") -> str:
    """A minimal, UNSIGNED SAML Response envelope carrying an @InResponseTo.
    The provider is stubbed, so no signature is needed; the route's own
    InResponseTo extraction runs against this real XML."""
    xml = (
        '<samlp:Response xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol" '
        'ID="_resp1" Version="2.0" IssueInstant="2026-07-17T00:00:00Z" '
        f'InResponseTo="{in_response_to}"></samlp:Response>'
    )
    return base64.b64encode(xml.encode()).decode()


def _relay_state() -> str:
    """A valid signed RelayState (HMAC-signed nonce hash, mirrors /saml/login)."""
    return sign_state(hash_nonce("saml-nonce-abc"))


# ============================================================================
# Phase A — GET /api/v1/auth/saml/login  (SP-initiated start)
# ============================================================================


class TestSamlLoginStart:

    def test_enabled_config_redirects_to_idp(
        self, client, db: Session, test_organization: Organization
    ):
        _make_enabled_saml_config(db, test_organization)

        with patch("src.api.routes.auth.SamlProvider") as MockProvider:
            MockProvider.from_config.return_value = _StubSamlProvider(request_id="req-1")
            resp = client.get(LOGIN_URL, follow_redirects=False)

        assert resp.status_code in (302, 307)
        assert resp.headers["location"] == IDP_REDIRECT

        # A pending replay-store row was recorded for the issued request_id.
        assert consume_request(db, request_id="req-1") == ConsumeOutcome.OK

    def test_no_enabled_config_redirects_disabled(self, client, db: Session):
        resp = client.get(LOGIN_URL, follow_redirects=False)

        assert resp.status_code in (302, 307)
        assert resp.headers["location"] == f"{FRONTEND_URL}/login?sso_error=disabled"

    def test_disabled_config_row_ignored(
        self, client, db: Session, test_organization: Organization
    ):
        _make_enabled_saml_config(db, test_organization, enabled=False)

        resp = client.get(LOGIN_URL, follow_redirects=False)

        assert resp.status_code in (302, 307)
        assert "sso_error=disabled" in resp.headers["location"]

    def test_provider_failure_redirects_config_no_pending_row(
        self, client, db: Session, test_organization: Organization
    ):
        _make_enabled_saml_config(db, test_organization)

        with patch("src.api.routes.auth.SamlProvider") as MockProvider:
            MockProvider.from_config.side_effect = SsrfError("blocked host")
            resp = client.get(LOGIN_URL, follow_redirects=False)

        assert resp.status_code in (302, 307)
        assert resp.headers["location"] == f"{FRONTEND_URL}/login?sso_error=config"
        # No pending row must have been persisted on the failure path.
        assert db.query(SamlAuthRequest).count() == 0

    def test_login_route_is_registered_not_404(self, client, db: Session):
        """Router wiring: the route resolves (redirects), never 404."""
        resp = client.get(LOGIN_URL, follow_redirects=False)
        assert resp.status_code != 404
