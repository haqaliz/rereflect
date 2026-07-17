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


# ============================================================================
# ACS shared helpers
# ============================================================================


def _post_acs(client, *, saml_response=None, relay_state="__default__", in_response_to="req-1"):
    """POST the ACS as a browser returning from the IdP (form-encoded)."""
    if relay_state == "__default__":
        relay_state = _relay_state()
    data = {
        "SAMLResponse": saml_response if saml_response is not None
        else _saml_response_b64(in_response_to),
    }
    if relay_state is not None:
        data["RelayState"] = relay_state
    return client.post(ACS_URL, data=data, follow_redirects=False)


def _acs(client, stub, **kw):
    """POST the ACS with `SamlProvider` patched to return/raise via `stub`."""
    with patch("src.api.routes.auth.SamlProvider") as MockProvider:
        MockProvider.from_config.return_value = stub
        return _post_acs(client, **kw)


# ============================================================================
# Phase B — ACS validation / RelayState / config error branches
# ============================================================================


class TestSamlAcsValidationBranches:

    def test_missing_relay_state_rejected(
        self, client, db: Session, test_organization: Organization
    ):
        _make_enabled_saml_config(db, test_organization)
        before = db.query(User).count()

        resp = _post_acs(client, relay_state=None)

        assert resp.headers["location"] == f"{FRONTEND_URL}/login?sso_error=state"
        assert db.query(User).count() == before

    def test_forged_relay_state_rejected(
        self, client, db: Session, test_organization: Organization
    ):
        _make_enabled_saml_config(db, test_organization)
        before = db.query(User).count()

        resp = _post_acs(client, relay_state="tampered.deadbeef")

        assert resp.headers["location"] == f"{FRONTEND_URL}/login?sso_error=state"
        assert db.query(User).count() == before

    def test_no_enabled_config_at_acs_rejected(self, client, db: Session):
        before = db.query(User).count()

        resp = _post_acs(client)

        assert resp.headers["location"] == f"{FRONTEND_URL}/login?sso_error=disabled"
        assert db.query(User).count() == before

    def test_malformed_response_rejected(
        self, client, db: Session, test_organization: Organization
    ):
        _make_enabled_saml_config(db, test_organization)
        before = db.query(User).count()
        stub = _StubSamlProvider(validate_exc=SamlValidationError("assertion"))

        resp = _acs(client, stub)

        assert resp.headers["location"] == f"{FRONTEND_URL}/login?sso_error=assertion"
        assert db.query(User).count() == before

    def test_invalid_signature_rejected(
        self, client, db: Session, test_organization: Organization
    ):
        _make_enabled_saml_config(db, test_organization)
        before = db.query(User).count()
        stub = _StubSamlProvider(validate_exc=SamlValidationError("signature"))

        resp = _acs(client, stub)

        assert resp.headers["location"] == f"{FRONTEND_URL}/login?sso_error=signature"
        assert db.query(User).count() == before

    def test_wrong_audience_rejected(
        self, client, db: Session, test_organization: Organization
    ):
        _make_enabled_saml_config(db, test_organization)
        stub = _StubSamlProvider(validate_exc=SamlValidationError("audience"))

        resp = _acs(client, stub)

        assert resp.headers["location"] == f"{FRONTEND_URL}/login?sso_error=audience"

    def test_wrong_recipient_rejected(
        self, client, db: Session, test_organization: Organization
    ):
        _make_enabled_saml_config(db, test_organization)
        stub = _StubSamlProvider(validate_exc=SamlValidationError("recipient"))

        resp = _acs(client, stub)

        assert resp.headers["location"] == f"{FRONTEND_URL}/login?sso_error=recipient"

    def test_expired_assertion_rejected(
        self, client, db: Session, test_organization: Organization
    ):
        _make_enabled_saml_config(db, test_organization)
        stub = _StubSamlProvider(validate_exc=SamlValidationError("expired"))

        resp = _acs(client, stub)

        assert resp.headers["location"] == f"{FRONTEND_URL}/login?sso_error=expired"

    def test_unexpected_provider_exception_is_sso_error_not_500(
        self, client, db: Session, test_organization: Organization
    ):
        """The unauthenticated ACS must never leak a 500 / stack trace. ANY
        unexpected (non-SamlValidationError) exception from the provider maps
        to a generic ?sso_error=assertion redirect."""
        _make_enabled_saml_config(db, test_organization)
        before = db.query(User).count()
        stub = _StubSamlProvider(validate_exc=RuntimeError("xmlsec segfault surrogate"))

        resp = _acs(client, stub)

        assert resp.status_code in (302, 307)
        assert resp.headers["location"] == f"{FRONTEND_URL}/login?sso_error=assertion"
        assert db.query(User).count() == before


# ============================================================================
# Phase C — replay-store branches (REAL DB-backed store)
# ============================================================================


class TestSamlAcsReplayStore:

    def test_replay_rejected(self, client, db: Session, test_organization: Organization):
        _make_enabled_saml_config(db, test_organization)
        register_request(db, request_id="req-1", organization_id=test_organization.id)
        stub = _StubSamlProvider(assertion=_assertion())

        # First POST consumes the pending request -> success (a user is minted).
        resp1 = _acs(client, stub)
        assert resp1.headers["location"].startswith(f"{FRONTEND_URL}/login/callback#token=")
        after_first = db.query(User).count()

        # Second POST re-presents the same InResponseTo -> replay, no new user.
        resp2 = _acs(client, stub)
        assert resp2.headers["location"] == f"{FRONTEND_URL}/login?sso_error=replay"
        assert db.query(User).count() == after_first

    def test_unsolicited_rejected(self, client, db: Session, test_organization: Organization):
        _make_enabled_saml_config(db, test_organization)
        before = db.query(User).count()
        # No pending row was ever issued for this InResponseTo.
        stub = _StubSamlProvider(assertion=_assertion())

        resp = _acs(client, stub, in_response_to="never-issued")

        assert resp.headers["location"] == f"{FRONTEND_URL}/login?sso_error=unsolicited"
        assert db.query(User).count() == before

    def test_expired_request_rejected(self, client, db: Session, test_organization: Organization):
        _make_enabled_saml_config(db, test_organization)
        before = db.query(User).count()
        # Pending row already past its TTL.
        register_request(
            db, request_id="req-exp", organization_id=test_organization.id, ttl_seconds=-10
        )
        stub = _StubSamlProvider(assertion=_assertion())

        resp = _acs(client, stub, in_response_to="req-exp")

        assert resp.headers["location"] == f"{FRONTEND_URL}/login?sso_error=expired"
        assert db.query(User).count() == before


# ============================================================================
# Phase D — identity resolution (provider returns a ValidatedAssertion)
# ============================================================================


def _seed_pending(db, org, request_id="req-1"):
    register_request(db, request_id=request_id, organization_id=org.id)


class TestSamlAcsIdentityResolution:

    def test_unverified_no_email_rejected(
        self, client, db: Session, test_organization: Organization
    ):
        _make_enabled_saml_config(db, test_organization)
        _seed_pending(db, test_organization)
        before = db.query(User).count()
        stub = _StubSamlProvider(assertion=_assertion(email=None))

        resp = _acs(client, stub)

        assert resp.headers["location"] == f"{FRONTEND_URL}/login?sso_error=unverified"
        assert db.query(User).count() == before

    def test_domain_denied_rejected(
        self, client, db: Session, test_organization: Organization
    ):
        _make_enabled_saml_config(db, test_organization, allowed_email_domains=["example.com"])
        _seed_pending(db, test_organization)
        before = db.query(User).count()
        stub = _StubSamlProvider(assertion=_assertion(email="user@not-allowed.com"))

        resp = _acs(client, stub)

        assert resp.headers["location"] == f"{FRONTEND_URL}/login?sso_error=domain"
        assert db.query(User).count() == before

    def test_empty_allowlist_denies_all(
        self, client, db: Session, test_organization: Organization
    ):
        _make_enabled_saml_config(db, test_organization, allowed_email_domains=[])
        _seed_pending(db, test_organization)
        before = db.query(User).count()
        stub = _StubSamlProvider(assertion=_assertion(email="user@example.com"))

        resp = _acs(client, stub)

        assert resp.headers["location"] == f"{FRONTEND_URL}/login?sso_error=domain"
        assert db.query(User).count() == before

    def test_jit_provision_new_member(
        self, client, db: Session, test_organization: Organization
    ):
        _make_enabled_saml_config(db, test_organization, allowed_email_domains=["example.com"])
        _seed_pending(db, test_organization)
        before = db.query(User).count()
        stub = _StubSamlProvider(
            assertion=_assertion(email="brand-new@example.com", subject="nameid-new")
        )

        resp = _acs(client, stub)

        assert resp.status_code in (302, 307)
        location = resp.headers["location"]
        assert location.startswith(f"{FRONTEND_URL}/login/callback#token=")
        assert db.query(User).count() == before + 1

        user = db.query(User).filter(User.email == "brand-new@example.com").first()
        assert user is not None
        assert user.saml_subject == "nameid-new"
        assert user.auth_provider == "saml"
        assert user.role == "member"
        assert user.organization_id == test_organization.id
        assert user.password_hash is None

        decoded = decode_access_token(location.split("#token=", 1)[1])
        assert decoded["user_id"] == user.id
        assert decoded["organization_id"] == user.organization_id
        assert decoded["role"] == "member"

    def test_link_existing_password_user(
        self, client, db: Session, test_organization: Organization
    ):
        _make_enabled_saml_config(db, test_organization, allowed_email_domains=["example.com"])
        existing = User(
            email="existing@example.com",
            password_hash=hash_password("password123"),
            organization_id=test_organization.id,
            role="member",
            auth_provider="email",
        )
        db.add(existing)
        db.commit()
        db.refresh(existing)
        _seed_pending(db, test_organization)
        before = db.query(User).count()
        stub = _StubSamlProvider(
            assertion=_assertion(email="existing@example.com", subject="nameid-link")
        )

        resp = _acs(client, stub)

        assert resp.status_code in (302, 307)
        assert db.query(User).count() == before  # no new row

        db.refresh(existing)
        assert existing.saml_subject == "nameid-link"
        assert existing.auth_provider == "both"
        assert existing.password_hash is not None  # password path untouched

        decoded = decode_access_token(resp.headers["location"].split("#token=", 1)[1])
        assert decoded["user_id"] == existing.id

    def test_link_case_insensitive_email(
        self, client, db: Session, test_organization: Organization
    ):
        _make_enabled_saml_config(db, test_organization, allowed_email_domains=["corp.com"])
        existing = User(
            email="Alice@corp.com",
            password_hash=hash_password("password123"),
            organization_id=test_organization.id,
            role="member",
            auth_provider="email",
        )
        db.add(existing)
        db.commit()
        db.refresh(existing)
        _seed_pending(db, test_organization)
        before = db.query(User).count()
        stub = _StubSamlProvider(
            assertion=_assertion(email="alice@corp.com", subject="nameid-mixed")
        )

        resp = _acs(client, stub)

        assert resp.status_code in (302, 307)
        assert db.query(User).count() == before  # linked, not duplicated

        db.refresh(existing)
        assert existing.saml_subject == "nameid-mixed"
        assert existing.auth_provider == "both"

        decoded = decode_access_token(resp.headers["location"].split("#token=", 1)[1])
        assert decoded["user_id"] == existing.id

    def test_returning_by_subject_with_changed_email(
        self, client, db: Session, test_organization: Organization
    ):
        _make_enabled_saml_config(db, test_organization, allowed_email_domains=["example.com"])
        existing = User(
            email="old-email@example.com",
            password_hash=None,
            organization_id=test_organization.id,
            role="member",
            auth_provider="saml",
            saml_subject="nameid-returning",
        )
        db.add(existing)
        db.commit()
        db.refresh(existing)
        _seed_pending(db, test_organization)
        before = db.query(User).count()
        stub = _StubSamlProvider(
            assertion=_assertion(email="new-email@example.com", subject="nameid-returning")
        )

        resp = _acs(client, stub)

        assert resp.status_code in (302, 307)
        assert db.query(User).count() == before  # matched by subject, not duplicated

        decoded = decode_access_token(resp.headers["location"].split("#token=", 1)[1])
        assert decoded["user_id"] == existing.id

    def test_success_fragment_on_fixed_frontend_url(
        self, client, db: Session, test_organization: Organization
    ):
        _make_enabled_saml_config(db, test_organization, allowed_email_domains=["example.com"])
        _seed_pending(db, test_organization)
        stub = _StubSamlProvider(
            assertion=_assertion(email="frag@example.com", subject="nameid-frag")
        )

        resp = _acs(client, stub)

        location = resp.headers["location"]
        assert location.startswith("http://localhost:3000/login/callback#token=")
        assert "?token=" not in location
        assert "&token=" not in location


# ============================================================================
# Phase E — security no-takeover / forgery cases (gap 2)
# ============================================================================


class TestSamlAcsSecurity:

    def test_missing_subject_no_takeover(
        self, client, db: Session, test_organization: Organization
    ):
        """A validated assertion with a null NameID subject must be rejected
        before any `User.saml_subject == subject` query. Otherwise the query
        degrades to `WHERE saml_subject IS NULL`, matching every existing
        password/Google/OIDC user, and `.first()` would mint a token for the
        lowest-id row (the org owner) — account takeover."""
        _make_enabled_saml_config(db, test_organization, allowed_email_domains=["example.com"])
        owner = User(
            email="owner@example.com",
            password_hash=hash_password("password123"),
            organization_id=test_organization.id,
            role="owner",
            auth_provider="email",
        )
        db.add(owner)
        db.commit()
        db.refresh(owner)
        _seed_pending(db, test_organization)
        before = db.query(User).count()
        stub = _StubSamlProvider(
            assertion=_assertion(email="attacker@example.com", subject=None)
        )

        resp = _acs(client, stub)

        assert resp.headers["location"] == f"{FRONTEND_URL}/login?sso_error=token"
        assert "#token=" not in resp.headers["location"]
        assert db.query(User).count() == before  # no JIT user either

        db.refresh(owner)
        assert owner.saml_subject is None  # owner untouched

    def test_forged_unsigned_post_rejected(
        self, client, db: Session, test_organization: Organization
    ):
        """The ACS is auth-exempt & CSRF-exempt by design; the trust control is
        the XML signature. A forged/unsigned assertion (modelled by the provider
        raising SamlValidationError("signature")) is rejected with
        ?sso_error=signature and mints/links no user — even with a real
        garbage SAMLResponse body that never reaches identity resolution."""
        _make_enabled_saml_config(db, test_organization)
        # Pre-seed a legitimate pending request the attacker must NOT be able to
        # burn: validation fails before the consume, so it stays pending.
        register_request(db, request_id="req-1", organization_id=test_organization.id)
        before = db.query(User).count()
        stub = _StubSamlProvider(validate_exc=SamlValidationError("signature"))

        resp = _acs(client, stub, saml_response="not-valid-base64-xml-@@@")

        assert resp.headers["location"] == f"{FRONTEND_URL}/login?sso_error=signature"
        assert db.query(User).count() == before  # no user created/linked

        # The legitimate pending request was NOT consumed by the forged POST
        # (validate-before-consume ordering) — it is still claimable.
        assert consume_request(db, request_id="req-1") == ConsumeOutcome.OK
