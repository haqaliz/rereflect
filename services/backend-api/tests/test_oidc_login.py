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
import urllib.parse
from unittest.mock import patch

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.api.auth import hash_password
from src.models.organization import Organization
from src.models.user import User
from src.models.oidc_config import OidcConfig


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
