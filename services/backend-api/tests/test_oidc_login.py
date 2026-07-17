"""
TDD tests for the `oidc-login-flow` aspect of `oidc-sso`.

Task 1: `users.oidc_sub` column (additive, unique, nullable) that OIDC login
will populate on JIT-provision/link.

Task 3: `GET /auth/oidc/start` — the authorize redirect. `OidcProvider` is
mocked at the `src.api.routes.auth.OidcProvider` boundary (no network); only
`authorization_url()` runs for real (via a stub provider) so the query-param
assertions exercise real URL-building logic, not a canned string.

Subsequent tasks (/callback) grow this file further.
"""
import json
import urllib.parse
from unittest.mock import patch

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.api.auth import hash_password, decode_access_token
from src.api.routes._oidc_state import sign_state, hash_nonce
from src.api.routes.auth import OIDC_SESSION_COOKIE
from src.models.organization import Organization
from src.models.user import User
from src.models.oidc_config import OidcConfig
from src.services.oidc_provider import OidcValidationError
from src.utils.ssrf import SsrfError


class TestUserOidcSubColumn:

    def test_user_oidc_sub_column(self, db: Session, test_organization: Organization):
        """A User can be created with oidc_sub set and it persists on readback."""
        user = User(
            email="sso-user@example.com",
            password_hash=hash_password("password123"),
            organization_id=test_organization.id,
            role="member",
            auth_provider="oidc",
            oidc_sub="sub-123",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        fetched = db.query(User).filter(User.id == user.id).first()
        assert fetched.oidc_sub == "sub-123"

    def test_user_oidc_sub_unique_constraint_blocks_duplicate(
        self, db: Session, test_organization: Organization
    ):
        """Two users with the same oidc_sub violate the unique constraint."""
        user1 = User(
            email="sso-user-1@example.com",
            password_hash=hash_password("password123"),
            organization_id=test_organization.id,
            role="member",
            auth_provider="oidc",
            oidc_sub="dup-sub",
        )
        db.add(user1)
        db.commit()

        user2 = User(
            email="sso-user-2@example.com",
            password_hash=hash_password("password123"),
            organization_id=test_organization.id,
            role="member",
            auth_provider="oidc",
            oidc_sub="dup-sub",
        )
        db.add(user2)

        with pytest.raises(IntegrityError):
            db.commit()


# ============================================================================
# Task 3 — GET /auth/oidc/start
# ============================================================================

AUTHORIZATION_ENDPOINT = "https://idp.example.com/authorize"


class _StubOidcProvider:
    """Stands in for a real `OidcProvider` — only `authorization_url()` runs
    for real (the actual query-string-building logic under test); no network."""

    def __init__(self, client_id="test-client-id"):
        self.client_id = client_id

    def authorization_url(self, state, nonce, code_challenge, redirect_uri):
        params = {
            "response_type": "code",
            "scope": "openid email profile",
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "state": state,
            "nonce": nonce,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
        return f"{AUTHORIZATION_ENDPOINT}?{urllib.parse.urlencode(params)}"


def _make_enabled_oidc_config(db: Session, org: Organization, **overrides) -> OidcConfig:
    defaults = dict(
        organization_id=org.id,
        issuer_url="https://idp.example.com",
        client_id="test-client-id",
        client_secret="irrelevant-because-OidcProvider-is-mocked",
        enabled=True,
        allowed_email_domains=["example.com"],
    )
    defaults.update(overrides)
    config = OidcConfig(**defaults)
    db.add(config)
    db.commit()
    db.refresh(config)
    return config


class TestOidcStart:

    def test_enabled_config_redirects_to_idp_with_expected_params(
        self, client, db: Session, test_organization: Organization
    ):
        _make_enabled_oidc_config(db, test_organization)

        with patch("src.api.routes.auth.OidcProvider") as MockProvider:
            MockProvider.from_config.return_value = _StubOidcProvider()
            resp = client.get("/api/v1/auth/oidc/start", follow_redirects=False)

        assert resp.status_code in (302, 307)
        location = resp.headers["location"]
        assert location.startswith(f"{AUTHORIZATION_ENDPOINT}?")

        query = urllib.parse.parse_qs(urllib.parse.urlparse(location).query)
        assert query["response_type"] == ["code"]
        assert "openid" in query["scope"][0]
        assert query["client_id"] == ["test-client-id"]
        assert "code_challenge" in query
        assert query["code_challenge_method"] == ["S256"]
        assert "state" in query
        assert "nonce" in query

        set_cookie_headers = resp.headers.get_list("set-cookie")
        session_cookie_headers = [
            h for h in set_cookie_headers if h.startswith("oidc_session=")
        ]
        assert len(session_cookie_headers) == 1
        cookie_header = session_cookie_headers[0]
        assert "HttpOnly" in cookie_header
        assert "Secure" in cookie_header
        assert "/api/v1/auth/oidc/callback" in cookie_header
        assert "samesite=lax" in cookie_header.lower()

    def test_no_enabled_config_redirects_to_disabled_error(self, client, db: Session):
        resp = client.get("/api/v1/auth/oidc/start", follow_redirects=False)

        assert resp.status_code in (302, 307)
        location = resp.headers["location"]
        assert location == "http://localhost:3000/login?sso_error=disabled"

    def test_disabled_config_row_is_ignored(
        self, client, db: Session, test_organization: Organization
    ):
        """An existing OidcConfig row with enabled=False must not be used."""
        _make_enabled_oidc_config(db, test_organization, enabled=False)

        resp = client.get("/api/v1/auth/oidc/start", follow_redirects=False)

        assert resp.status_code in (302, 307)
        assert "sso_error=disabled" in resp.headers["location"]

    def test_provider_failure_redirects_to_config_error(
        self, client, db: Session, test_organization: Organization
    ):
        from src.utils.ssrf import SsrfError

        _make_enabled_oidc_config(db, test_organization)

        with patch("src.api.routes.auth.OidcProvider") as MockProvider:
            MockProvider.from_config.side_effect = SsrfError("blocked host")
            resp = client.get("/api/v1/auth/oidc/start", follow_redirects=False)

        assert resp.status_code in (302, 307)
        location = resp.headers["location"]
        assert location == "http://localhost:3000/login?sso_error=config"


# ============================================================================
# Task 4 — GET /auth/oidc/callback
# ============================================================================

FRONTEND_URL = "http://localhost:3000"
CALLBACK_URL = "/api/v1/auth/oidc/callback"


class _StubCallbackProvider:
    """Stands in for `OidcProvider` at the exchange/validate boundary — no
    network. `exchange_code`/`validate_id_token` return canned values (or
    raise canned exceptions) per test so the callback's own branching logic
    is what's under test."""

    def __init__(self, tokens=None, claims=None, exchange_exc=None, validate_exc=None):
        self._tokens = tokens if tokens is not None else {"id_token": "fake-id-token"}
        self._claims = claims if claims is not None else {}
        self._exchange_exc = exchange_exc
        self._validate_exc = validate_exc

    def exchange_code(self, code, code_verifier, redirect_uri):
        if self._exchange_exc:
            raise self._exchange_exc
        return self._tokens

    def validate_id_token(self, id_token, nonce):
        if self._validate_exc:
            raise self._validate_exc
        return self._claims


def _session_cookie_and_state(
    session_nonce="session-nonce-abc",
    code_verifier="verifier-abc",
    oidc_nonce="oidc-nonce-abc",
    state_nonce=None,
):
    """Build a valid `oidc_session` cookie value + a `state` param signed to
    match it (mirrors what `/start` sets). Pass a different `state_nonce` to
    produce a state that fails the CSRF nonce-binding check."""
    cookie_value = json.dumps({
        "session_nonce": session_nonce,
        "code_verifier": code_verifier,
        "oidc_nonce": oidc_nonce,
    })
    state = sign_state(hash_nonce(state_nonce if state_nonce is not None else session_nonce))
    return cookie_value, state


def _verified_claims(email="user@example.com", sub="idp-sub-1", email_verified=True):
    claims = {"sub": sub, "email": email}
    if email_verified is not None:
        claims["email_verified"] = email_verified
    return claims


class TestOidcCallback:

    def test_idp_denied_redirects_generic_no_user(self, client, db: Session, test_organization: Organization):
        _make_enabled_oidc_config(db, test_organization)
        before = db.query(User).count()

        resp = client.get(CALLBACK_URL, params={"error": "access_denied"}, follow_redirects=False)

        assert resp.status_code in (302, 307)
        assert resp.headers["location"] == f"{FRONTEND_URL}/login?sso_error=denied"
        assert db.query(User).count() == before

    def test_missing_session_cookie_rejected(self, client, db: Session, test_organization: Organization):
        _make_enabled_oidc_config(db, test_organization)
        before = db.query(User).count()
        _, state = _session_cookie_and_state()

        resp = client.get(
            CALLBACK_URL,
            params={"code": "auth-code", "state": state},
            follow_redirects=False,
        )

        assert resp.headers["location"] == f"{FRONTEND_URL}/login?sso_error=state"
        assert db.query(User).count() == before

    def test_malformed_state_rejected(self, client, db: Session, test_organization: Organization):
        _make_enabled_oidc_config(db, test_organization)
        before = db.query(User).count()
        cookie_value, _ = _session_cookie_and_state()

        resp = client.get(
            CALLBACK_URL,
            params={"code": "auth-code", "state": "not-a-valid-signed-state"},
            cookies={OIDC_SESSION_COOKIE: cookie_value},
            follow_redirects=False,
        )

        assert resp.headers["location"] == f"{FRONTEND_URL}/login?sso_error=state"
        assert db.query(User).count() == before

    def test_nonce_mismatch_rejected(self, client, db: Session, test_organization: Organization):
        """state signed to a DIFFERENT session_nonce than the cookie carries."""
        _make_enabled_oidc_config(db, test_organization)
        before = db.query(User).count()
        cookie_value, state = _session_cookie_and_state(
            session_nonce="session-nonce-abc", state_nonce="a-different-nonce"
        )

        resp = client.get(
            CALLBACK_URL,
            params={"code": "auth-code", "state": state},
            cookies={OIDC_SESSION_COOKIE: cookie_value},
            follow_redirects=False,
        )

        assert resp.headers["location"] == f"{FRONTEND_URL}/login?sso_error=state"
        assert db.query(User).count() == before

    def test_no_enabled_config_rejected(self, client, db: Session):
        before = db.query(User).count()
        cookie_value, state = _session_cookie_and_state()

        resp = client.get(
            CALLBACK_URL,
            params={"code": "auth-code", "state": state},
            cookies={OIDC_SESSION_COOKIE: cookie_value},
            follow_redirects=False,
        )

        assert resp.headers["location"] == f"{FRONTEND_URL}/login?sso_error=disabled"
        assert db.query(User).count() == before

    def test_exchange_failure_rejected(self, client, db: Session, test_organization: Organization):
        _make_enabled_oidc_config(db, test_organization)
        before = db.query(User).count()
        cookie_value, state = _session_cookie_and_state()

        with patch("src.api.routes.auth.OidcProvider") as MockProvider:
            MockProvider.from_config.return_value = _StubCallbackProvider(
                exchange_exc=SsrfError("token endpoint host blocked")
            )
            resp = client.get(
                CALLBACK_URL,
                params={"code": "auth-code", "state": state},
                cookies={OIDC_SESSION_COOKIE: cookie_value},
                follow_redirects=False,
            )

        assert resp.headers["location"] == f"{FRONTEND_URL}/login?sso_error=exchange"
        assert db.query(User).count() == before

    def test_id_token_validation_failure_rejected(self, client, db: Session, test_organization: Organization):
        _make_enabled_oidc_config(db, test_organization)
        before = db.query(User).count()
        cookie_value, state = _session_cookie_and_state()

        with patch("src.api.routes.auth.OidcProvider") as MockProvider:
            MockProvider.from_config.return_value = _StubCallbackProvider(
                validate_exc=OidcValidationError("bad nonce")
            )
            resp = client.get(
                CALLBACK_URL,
                params={"code": "auth-code", "state": state},
                cookies={OIDC_SESSION_COOKIE: cookie_value},
                follow_redirects=False,
            )

        assert resp.headers["location"] == f"{FRONTEND_URL}/login?sso_error=token"
        assert db.query(User).count() == before

    def test_unverified_email_rejected_no_user(self, client, db: Session, test_organization: Organization):
        _make_enabled_oidc_config(db, test_organization)
        before = db.query(User).count()
        cookie_value, state = _session_cookie_and_state()
        claims = _verified_claims(email_verified=False)

        with patch("src.api.routes.auth.OidcProvider") as MockProvider:
            MockProvider.from_config.return_value = _StubCallbackProvider(claims=claims)
            resp = client.get(
                CALLBACK_URL,
                params={"code": "auth-code", "state": state},
                cookies={OIDC_SESSION_COOKIE: cookie_value},
                follow_redirects=False,
            )

        assert resp.headers["location"] == f"{FRONTEND_URL}/login?sso_error=unverified"
        assert db.query(User).count() == before

    def test_missing_email_claim_rejected_no_user(self, client, db: Session, test_organization: Organization):
        _make_enabled_oidc_config(db, test_organization)
        before = db.query(User).count()
        cookie_value, state = _session_cookie_and_state()
        claims = {"sub": "idp-sub-1", "email_verified": True}  # no email

        with patch("src.api.routes.auth.OidcProvider") as MockProvider:
            MockProvider.from_config.return_value = _StubCallbackProvider(claims=claims)
            resp = client.get(
                CALLBACK_URL,
                params={"code": "auth-code", "state": state},
                cookies={OIDC_SESSION_COOKIE: cookie_value},
                follow_redirects=False,
            )

        assert resp.headers["location"] == f"{FRONTEND_URL}/login?sso_error=unverified"
        assert db.query(User).count() == before

    def test_domain_not_in_allowlist_rejected_no_user(self, client, db: Session, test_organization: Organization):
        _make_enabled_oidc_config(db, test_organization, allowed_email_domains=["example.com"])
        before = db.query(User).count()
        cookie_value, state = _session_cookie_and_state()
        claims = _verified_claims(email="user@not-allowed.com")

        with patch("src.api.routes.auth.OidcProvider") as MockProvider:
            MockProvider.from_config.return_value = _StubCallbackProvider(claims=claims)
            resp = client.get(
                CALLBACK_URL,
                params={"code": "auth-code", "state": state},
                cookies={OIDC_SESSION_COOKIE: cookie_value},
                follow_redirects=False,
            )

        assert resp.headers["location"] == f"{FRONTEND_URL}/login?sso_error=domain"
        assert db.query(User).count() == before

    def test_empty_allowlist_denies_all(self, client, db: Session, test_organization: Organization):
        _make_enabled_oidc_config(db, test_organization, allowed_email_domains=[])
        before = db.query(User).count()
        cookie_value, state = _session_cookie_and_state()
        claims = _verified_claims(email="user@example.com")

        with patch("src.api.routes.auth.OidcProvider") as MockProvider:
            MockProvider.from_config.return_value = _StubCallbackProvider(claims=claims)
            resp = client.get(
                CALLBACK_URL,
                params={"code": "auth-code", "state": state},
                cookies={OIDC_SESSION_COOKIE: cookie_value},
                follow_redirects=False,
            )

        assert resp.headers["location"] == f"{FRONTEND_URL}/login?sso_error=domain"
        assert db.query(User).count() == before

    def test_jit_provision_new_member(self, client, db: Session, test_organization: Organization):
        """AC6 — unknown in-list verified identity is JIT-provisioned."""
        _make_enabled_oidc_config(db, test_organization, allowed_email_domains=["example.com"])
        before = db.query(User).count()
        cookie_value, state = _session_cookie_and_state()
        claims = _verified_claims(email="brand-new-user@example.com", sub="idp-sub-new")

        with patch("src.api.routes.auth.OidcProvider") as MockProvider:
            MockProvider.from_config.return_value = _StubCallbackProvider(claims=claims)
            resp = client.get(
                CALLBACK_URL,
                params={"code": "auth-code", "state": state},
                cookies={OIDC_SESSION_COOKIE: cookie_value},
                follow_redirects=False,
            )

        assert resp.status_code in (302, 307)
        location = resp.headers["location"]
        assert location.startswith(f"{FRONTEND_URL}/login/callback#token=")
        assert db.query(User).count() == before + 1

        user = db.query(User).filter(User.email == "brand-new-user@example.com").first()
        assert user is not None
        assert user.oidc_sub == "idp-sub-new"
        assert user.auth_provider == "oidc"
        assert user.role == "member"
        assert user.organization_id == test_organization.id

        token = location.split("#token=", 1)[1]
        decoded = decode_access_token(token)
        assert decoded["user_id"] == user.id
        assert decoded["organization_id"] == user.organization_id
        assert decoded["role"] == "member"

    def test_link_existing_password_user(self, client, db: Session, test_organization: Organization):
        """AC7 — existing password user with matching verified email is linked."""
        _make_enabled_oidc_config(db, test_organization, allowed_email_domains=["example.com"])
        existing = User(
            email="existing-password-user@example.com",
            password_hash=hash_password("password123"),
            organization_id=test_organization.id,
            role="member",
            auth_provider="email",
        )
        db.add(existing)
        db.commit()
        db.refresh(existing)
        before = db.query(User).count()

        cookie_value, state = _session_cookie_and_state()
        claims = _verified_claims(email="existing-password-user@example.com", sub="idp-sub-link")

        with patch("src.api.routes.auth.OidcProvider") as MockProvider:
            MockProvider.from_config.return_value = _StubCallbackProvider(claims=claims)
            resp = client.get(
                CALLBACK_URL,
                params={"code": "auth-code", "state": state},
                cookies={OIDC_SESSION_COOKIE: cookie_value},
                follow_redirects=False,
            )

        assert resp.status_code in (302, 307)
        assert db.query(User).count() == before  # no new user row

        db.refresh(existing)
        assert existing.oidc_sub == "idp-sub-link"
        assert existing.auth_provider == "both"
        assert existing.password_hash is not None  # password path untouched

        token = resp.headers["location"].split("#token=", 1)[1]
        decoded = decode_access_token(token)
        assert decoded["user_id"] == existing.id

    def test_returning_by_sub_with_changed_email(self, client, db: Session, test_organization: Organization):
        """AC8 — matched by oidc_sub even though the IdP-reported email changed."""
        _make_enabled_oidc_config(db, test_organization, allowed_email_domains=["example.com"])
        existing = User(
            email="old-email@example.com",
            password_hash=None,
            organization_id=test_organization.id,
            role="member",
            auth_provider="oidc",
            oidc_sub="idp-sub-returning",
        )
        db.add(existing)
        db.commit()
        db.refresh(existing)
        before = db.query(User).count()

        cookie_value, state = _session_cookie_and_state()
        claims = _verified_claims(email="new-email@example.com", sub="idp-sub-returning")

        with patch("src.api.routes.auth.OidcProvider") as MockProvider:
            MockProvider.from_config.return_value = _StubCallbackProvider(claims=claims)
            resp = client.get(
                CALLBACK_URL,
                params={"code": "auth-code", "state": state},
                cookies={OIDC_SESSION_COOKIE: cookie_value},
                follow_redirects=False,
            )

        assert resp.status_code in (302, 307)
        assert db.query(User).count() == before  # matched, not duplicated

        token = resp.headers["location"].split("#token=", 1)[1]
        decoded = decode_access_token(token)
        assert decoded["user_id"] == existing.id

    def test_success_redirect_uses_fragment_on_fixed_frontend_url(
        self, client, db: Session, test_organization: Organization
    ):
        """AC10 — token is delivered via URL fragment on the fixed FRONTEND_URL, never a query param."""
        _make_enabled_oidc_config(db, test_organization, allowed_email_domains=["example.com"])
        cookie_value, state = _session_cookie_and_state()
        claims = _verified_claims(email="fragment-check@example.com", sub="idp-sub-fragment")

        with patch("src.api.routes.auth.OidcProvider") as MockProvider:
            MockProvider.from_config.return_value = _StubCallbackProvider(claims=claims)
            resp = client.get(
                CALLBACK_URL,
                params={"code": "auth-code", "state": state},
                cookies={OIDC_SESSION_COOKIE: cookie_value},
                follow_redirects=False,
            )

        location = resp.headers["location"]
        assert location.startswith("http://localhost:3000/login/callback#token=")
        assert "?token=" not in location
        assert "&token=" not in location
