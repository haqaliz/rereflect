"""
Tests for Salesforce OAuth callback + test + disconnect + manual sync
(Phase 4 of salesforce-connection aspect).

Mocks ALL Salesforce HTTP — no live org.
"""
import os
import urllib.parse
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime

from sqlalchemy.orm import Session

from src.models.organization import Organization
from src.models.user import User
from src.models.hubspot_integration import HubSpotIntegration
from src.models.salesforce_integration import SalesforceIntegration
from src.models.crm_enrichment import CrmEnrichment
from src.api.auth import hash_password, create_access_token

TEST_FERNET_KEY = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="

SALESFORCE_ENV = {
    "SALESFORCE_CLIENT_ID": "sf-client-id",
    "SALESFORCE_CLIENT_SECRET": "sf-client-secret",
    "SALESFORCE_REDIRECT_URI": "http://localhost:8000/api/v1/integrations/salesforce/callback",
    "SALESFORCE_LOGIN_BASE": "https://login.salesforce.com",
    "SALESFORCE_API_VERSION": "v60.0",
}

TOKEN_RESPONSE = {
    "access_token": "00Dxx0000001gPF!ARsAQP0",
    "refresh_token": "5Aep861...refresh...token",
    "instance_url": "https://acme.my.salesforce.com",
    "id": "https://login.salesforce.com/id/00Dxx0000001gPFEAY/005xx000001Sv6AAAS",
    "token_type": "Bearer",
}


def _salesforce_env(**overrides):
    env = dict(SALESFORCE_ENV)
    env.update(overrides)
    return patch.dict(os.environ, env)


def _mock_client(post_return=None, post_side_effect=None, get_return=None, get_side_effect=None):
    mock = MagicMock()
    mock.__enter__ = MagicMock(return_value=mock)
    mock.__exit__ = MagicMock(return_value=False)
    if post_side_effect is not None:
        mock.post = MagicMock(side_effect=post_side_effect)
    else:
        mock.post = MagicMock(return_value=post_return)
    if get_side_effect is not None:
        mock.get = MagicMock(side_effect=get_side_effect)
    else:
        mock.get = MagicMock(return_value=get_return)
    return mock


def token_exchange_ok_resp():
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = TOKEN_RESPONSE
    resp.raise_for_status = MagicMock()
    return resp


def userinfo_ok_resp():
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {
        "user_id": "005xx000001Sv6AAAS",
        "organization_id": "00Dxx0000001gPFEAY",
    }
    resp.raise_for_status = MagicMock()
    return resp


# ──────────────────────────── Fixtures ────────────────────────────────────────

@pytest.fixture
def owner_user(db: Session, test_organization: Organization) -> User:
    user = User(
        email="sfoauth_owner@test.com",
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
        email="sfoauth_member@test.com",
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
def admin_user(db: Session, test_organization: Organization) -> User:
    user = User(
        email="sfoauth_admin@test.com",
        password_hash=hash_password("pw"),
        organization_id=test_organization.id,
        role="admin",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def admin_headers(admin_user: User) -> dict:
    token = create_access_token({
        "user_id": admin_user.id,
        "organization_id": admin_user.organization_id,
        "role": admin_user.role,
    })
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def oauth_nonce() -> str:
    """The raw session nonce the /connect-url endpoint would set as a cookie."""
    import secrets
    return secrets.token_urlsafe(32)


@pytest.fixture
def oauth_cookies(oauth_nonce: str) -> dict:
    """The cookie jar /connect-url would have set on the initiating browser."""
    from src.api.routes.salesforce_integration import SF_OAUTH_NONCE_COOKIE
    return {SF_OAUTH_NONCE_COOKIE: oauth_nonce}


@pytest.fixture
def signed_state(owner_user: User, oauth_nonce: str):
    with _salesforce_env():
        from src.api.routes.salesforce_integration import _sign_state, _hash_nonce
        return _sign_state(owner_user.organization_id, owner_user.id, _hash_nonce(oauth_nonce))


@pytest.fixture
def active_integration(db: Session, test_organization: Organization) -> SalesforceIntegration:
    with _salesforce_env(), patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
        from src.utils.encryption import encrypt_api_key
        encrypted = encrypt_api_key("plain-refresh-token")
    integ = SalesforceIntegration(
        organization_id=test_organization.id,
        refresh_token=encrypted,
        instance_url="https://acme.my.salesforce.com",
        sf_org_id="00Dxx0000001gPFEAY",
        token_hint="...oken",
        is_active=True,
        connected_at=datetime.utcnow(),
        contacts_synced=0,
        contacts_matched=0,
    )
    db.add(integ)
    db.commit()
    db.refresh(integ)
    return integ


# ──────────────────────────── /callback ───────────────────────────────────────


class TestCallbackEndpoint:
    def test_callback_persists_encrypted_refresh_token(
        self, client, db, test_organization, signed_state, oauth_cookies
    ):
        mock_client = _mock_client(
            post_return=token_exchange_ok_resp(),
            get_return=userinfo_ok_resp(),
        )
        with _salesforce_env(), patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
            with patch("src.api.routes.salesforce_integration.httpx.Client", return_value=mock_client):
                resp = client.get(
                    "/api/v1/integrations/salesforce/callback",
                    params={"code": "auth-code-123", "state": signed_state},
                    cookies=oauth_cookies,
                    follow_redirects=False,
                )
        assert resp.status_code in (302, 307)
        db.expire_all()
        row = db.query(SalesforceIntegration).filter_by(
            organization_id=test_organization.id
        ).first()
        assert row is not None
        assert row.refresh_token != TOKEN_RESPONSE["refresh_token"]
        assert row.instance_url == "https://acme.my.salesforce.com"
        assert row.sf_org_id == "00Dxx0000001gPFEAY"
        with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
            from src.utils.encryption import decrypt_api_key
            assert decrypt_api_key(row.refresh_token) == TOKEN_RESPONSE["refresh_token"]

    def test_callback_redirects_to_connected_on_success(
        self, client, db, test_organization, signed_state, oauth_cookies
    ):
        mock_client = _mock_client(
            post_return=token_exchange_ok_resp(),
            get_return=userinfo_ok_resp(),
        )
        with _salesforce_env(), patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
            with patch("src.api.routes.salesforce_integration.httpx.Client", return_value=mock_client):
                resp = client.get(
                    "/api/v1/integrations/salesforce/callback",
                    params={"code": "auth-code-123", "state": signed_state},
                    cookies=oauth_cookies,
                    follow_redirects=False,
                )
        location = resp.headers["location"]
        assert "connected=1" in location

    def test_callback_never_returns_tokens_in_body(
        self, client, db, test_organization, signed_state, oauth_cookies
    ):
        mock_client = _mock_client(
            post_return=token_exchange_ok_resp(),
            get_return=userinfo_ok_resp(),
        )
        with _salesforce_env(), patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
            with patch("src.api.routes.salesforce_integration.httpx.Client", return_value=mock_client):
                resp = client.get(
                    "/api/v1/integrations/salesforce/callback",
                    params={"code": "auth-code-123", "state": signed_state},
                    cookies=oauth_cookies,
                    follow_redirects=False,
                )
        body = resp.text
        assert TOKEN_RESPONSE["refresh_token"] not in body
        assert TOKEN_RESPONSE["access_token"] not in body

    def test_callback_invalid_state_redirects_with_error(self, client, db, test_organization):
        with _salesforce_env():
            resp = client.get(
                "/api/v1/integrations/salesforce/callback",
                params={"code": "auth-code-123", "state": "garbage-state"},
                follow_redirects=False,
            )
        assert resp.status_code in (302, 307)
        assert "oauth_error" in resp.headers["location"]

    def test_callback_rejected_without_nonce_cookie(
        self, client, db, test_organization, signed_state
    ):
        """SEC-1: a validly-signed state with NO matching session-nonce cookie
        must be rejected before any token exchange or DB write — otherwise an
        attacker-minted state completed by a victim's browser would link the
        victim's Salesforce token into the attacker's org."""
        mock_client = _mock_client(
            post_return=token_exchange_ok_resp(),
            get_return=userinfo_ok_resp(),
        )
        with _salesforce_env(), patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
            with patch(
                "src.api.routes.salesforce_integration.httpx.Client", return_value=mock_client
            ) as mock_httpx_client:
                resp = client.get(
                    "/api/v1/integrations/salesforce/callback",
                    params={"code": "auth-code-123", "state": signed_state},
                    # deliberately NOT setting the sf_oauth_nonce cookie
                    follow_redirects=False,
                )
        assert resp.status_code in (302, 307)
        assert "oauth_error=invalid_state" in resp.headers["location"]
        mock_httpx_client.assert_not_called()
        db.expire_all()
        row = db.query(SalesforceIntegration).filter_by(
            organization_id=test_organization.id
        ).first()
        assert row is None

    def test_callback_rejected_with_wrong_nonce_cookie(
        self, client, db, test_organization, signed_state
    ):
        """SEC-1: a validly-signed state with a WRONG session-nonce cookie
        (e.g. the attacker's own browser session) must be rejected."""
        from src.api.routes.salesforce_integration import SF_OAUTH_NONCE_COOKIE

        mock_client = _mock_client(
            post_return=token_exchange_ok_resp(),
            get_return=userinfo_ok_resp(),
        )
        with _salesforce_env(), patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
            with patch(
                "src.api.routes.salesforce_integration.httpx.Client", return_value=mock_client
            ) as mock_httpx_client:
                resp = client.get(
                    "/api/v1/integrations/salesforce/callback",
                    params={"code": "auth-code-123", "state": signed_state},
                    cookies={SF_OAUTH_NONCE_COOKIE: "attacker-controlled-wrong-nonce"},
                    follow_redirects=False,
                )
        assert resp.status_code in (302, 307)
        assert "oauth_error=invalid_state" in resp.headers["location"]
        mock_httpx_client.assert_not_called()
        db.expire_all()
        row = db.query(SalesforceIntegration).filter_by(
            organization_id=test_organization.id
        ).first()
        assert row is None

    def test_callback_missing_code_redirects_with_error(self, client, signed_state):
        with _salesforce_env():
            resp = client.get(
                "/api/v1/integrations/salesforce/callback",
                params={"state": signed_state},
                follow_redirects=False,
            )
        assert resp.status_code in (302, 307)
        assert "oauth_error" in resp.headers["location"]

    def test_callback_invalid_grant_redirects_with_error(
        self, client, db, signed_state, oauth_cookies
    ):
        import httpx
        error_resp = MagicMock()
        error_resp.status_code = 400
        error_resp.json.return_value = {"error": "invalid_grant", "error_description": "expired"}
        http_err = httpx.HTTPStatusError("400", request=MagicMock(), response=error_resp)
        mock_client = _mock_client(post_side_effect=http_err)
        with _salesforce_env(), patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
            with patch("src.api.routes.salesforce_integration.httpx.Client", return_value=mock_client):
                resp = client.get(
                    "/api/v1/integrations/salesforce/callback",
                    params={"code": "bad-code", "state": signed_state},
                    cookies=oauth_cookies,
                    follow_redirects=False,
                )
        assert resp.status_code in (302, 307)
        assert "oauth_error" in resp.headers["location"]

    def test_callback_token_exchange_failure_clears_nonce_cookie(
        self, client, db, signed_state, oauth_cookies
    ):
        """M3: the one-time session-nonce cookie must be cleared on EVERY
        failure redirect, not just success/invalid_state — otherwise a stale
        cookie lingers in the browser after a failed OAuth attempt."""
        import httpx
        from src.api.routes.salesforce_integration import SF_OAUTH_NONCE_COOKIE

        error_resp = MagicMock()
        error_resp.status_code = 400
        error_resp.json.return_value = {"error": "invalid_grant", "error_description": "expired"}
        http_err = httpx.HTTPStatusError("400", request=MagicMock(), response=error_resp)
        mock_client = _mock_client(post_side_effect=http_err)
        with _salesforce_env(), patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
            with patch("src.api.routes.salesforce_integration.httpx.Client", return_value=mock_client):
                resp = client.get(
                    "/api/v1/integrations/salesforce/callback",
                    params={"code": "bad-code", "state": signed_state},
                    cookies=oauth_cookies,
                    follow_redirects=False,
                )
        assert resp.status_code in (302, 307)
        set_cookie_headers = resp.headers.get_list("set-cookie")
        nonce_cookie_headers = [h for h in set_cookie_headers if h.startswith(f"{SF_OAUTH_NONCE_COOKIE}=")]
        assert nonce_cookie_headers, "sf_oauth_nonce cookie was not cleared on token-exchange failure"
        assert "Max-Age=0" in nonce_cookie_headers[0] or "max-age=0" in nonce_cookie_headers[0].lower()

    def test_callback_blocked_when_hubspot_active(
        self, client, db, test_organization, signed_state, oauth_cookies
    ):
        db.add(HubSpotIntegration(
            organization_id=test_organization.id,
            access_token="enc",
            connected_at=datetime.utcnow(),
            is_active=True,
        ))
        db.commit()
        mock_client = _mock_client(
            post_return=token_exchange_ok_resp(),
            get_return=userinfo_ok_resp(),
        )
        with _salesforce_env(), patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
            with patch("src.api.routes.salesforce_integration.httpx.Client", return_value=mock_client):
                resp = client.get(
                    "/api/v1/integrations/salesforce/callback",
                    params={"code": "auth-code-123", "state": signed_state},
                    cookies=oauth_cookies,
                    follow_redirects=False,
                )
        assert resp.status_code in (302, 307)
        assert "oauth_error" in resp.headers["location"]
        db.expire_all()
        row = db.query(SalesforceIntegration).filter_by(
            organization_id=test_organization.id
        ).first()
        assert row is None

    def test_callback_missing_encryption_key_returns_422(
        self, client, db, test_organization, signed_state, oauth_cookies
    ):
        mock_client = _mock_client(
            post_return=token_exchange_ok_resp(),
            get_return=userinfo_ok_resp(),
        )
        with _salesforce_env():
            with (
                patch("src.api.routes.salesforce_integration.httpx.Client", return_value=mock_client),
                patch(
                    "src.api.routes.salesforce_integration.encrypt_api_key",
                    side_effect=ValueError("LLM_ENCRYPTION_KEY environment variable is not set"),
                ),
            ):
                resp = client.get(
                    "/api/v1/integrations/salesforce/callback",
                    params={"code": "auth-code-123", "state": signed_state},
                    cookies=oauth_cookies,
                    follow_redirects=False,
                )
        assert resp.status_code == 422
        assert "LLM_ENCRYPTION_KEY" in resp.json()["detail"]


# ──────────────────────────── /test ───────────────────────────────────────────


class TestTestEndpoint:
    def test_test_with_valid_refresh_token_returns_success(
        self, client, active_integration, owner_headers
    ):
        refresh_ok = _mock_client(post_return=token_exchange_ok_resp(), get_return=userinfo_ok_resp())
        with _salesforce_env(), patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
            with patch("src.api.routes.salesforce_integration.httpx.Client", return_value=refresh_ok):
                resp = client.post(
                    "/api/v1/integrations/salesforce/test",
                    headers=owner_headers,
                )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_test_with_refresh_failure_returns_success_false(
        self, client, active_integration, owner_headers
    ):
        import httpx
        error_resp = MagicMock()
        error_resp.status_code = 400
        error_resp.json.return_value = {"error": "invalid_grant"}
        http_err = httpx.HTTPStatusError("400", request=MagicMock(), response=error_resp)
        mock_client = _mock_client(post_side_effect=http_err)
        with _salesforce_env(), patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
            with patch("src.api.routes.salesforce_integration.httpx.Client", return_value=mock_client):
                resp = client.post(
                    "/api/v1/integrations/salesforce/test",
                    headers=owner_headers,
                )
        assert resp.status_code == 200
        assert resp.json()["success"] is False

    def test_test_without_connection_returns_400(self, client, owner_headers):
        with _salesforce_env():
            resp = client.post(
                "/api/v1/integrations/salesforce/test",
                headers=owner_headers,
            )
        assert resp.status_code == 400

    def test_test_never_returns_500_on_unexpected_error(
        self, client, active_integration, owner_headers
    ):
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(side_effect=RuntimeError("boom"))
        with _salesforce_env(), patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
            with patch("src.api.routes.salesforce_integration.httpx.Client", return_value=mock_client):
                resp = client.post(
                    "/api/v1/integrations/salesforce/test",
                    headers=owner_headers,
                )
        assert resp.status_code == 200
        assert resp.json()["success"] is False

    def test_test_member_gets_403(self, client, active_integration, member_headers):
        with _salesforce_env():
            resp = client.post(
                "/api/v1/integrations/salesforce/test",
                headers=member_headers,
            )
        assert resp.status_code == 403


# ──────────────────────────── /disconnect ─────────────────────────────────────


class TestDisconnectEndpoint:
    def test_disconnect_sets_inactive(self, client, db, active_integration, owner_headers):
        with _salesforce_env():
            resp = client.delete(
                "/api/v1/integrations/salesforce/disconnect",
                headers=owner_headers,
            )
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        db.expire_all()
        row = db.query(SalesforceIntegration).filter_by(id=active_integration.id).first()
        assert row.is_active is False

    def test_disconnect_nonexistent_returns_404(self, client, owner_headers):
        with _salesforce_env():
            resp = client.delete(
                "/api/v1/integrations/salesforce/disconnect",
                headers=owner_headers,
            )
        assert resp.status_code == 404

    def test_disconnect_purges_salesforce_rows_only(
        self, client, db, test_organization, active_integration, owner_headers
    ):
        db.add(CrmEnrichment(
            organization_id=test_organization.id,
            customer_email="sf-customer@test.com",
            provider="salesforce",
            last_synced_at=datetime.utcnow(),
        ))
        db.add(CrmEnrichment(
            organization_id=test_organization.id,
            customer_email="hs-customer@test.com",
            provider="hubspot",
            last_synced_at=datetime.utcnow(),
        ))
        db.commit()

        with _salesforce_env(), patch(
            "src.services.health_score_service.update_customer_health"
        ) as mock_update:
            resp = client.delete(
                "/api/v1/integrations/salesforce/disconnect",
                headers=owner_headers,
            )
        assert resp.status_code == 200

        db.expire_all()
        remaining = db.query(CrmEnrichment).filter_by(
            organization_id=test_organization.id
        ).all()
        assert len(remaining) == 1
        assert remaining[0].provider == "hubspot"
        mock_update.assert_called_once()
        assert mock_update.call_args.args[1] == "sf-customer@test.com"

    def test_disconnect_member_gets_403(self, client, active_integration, member_headers):
        with _salesforce_env():
            resp = client.delete(
                "/api/v1/integrations/salesforce/disconnect",
                headers=member_headers,
            )
        assert resp.status_code == 403


# ──────────────────────────── /sync ───────────────────────────────────────────


class TestSyncEndpoint:
    def test_sync_enqueues_task_with_exact_name(
        self, client, active_integration, admin_headers
    ):
        with _salesforce_env(), patch(
            "src.api.routes.salesforce_integration._get_celery_app"
        ) as mock_get_celery:
            mock_celery = MagicMock()
            mock_get_celery.return_value = mock_celery
            resp = client.post(
                "/api/v1/integrations/salesforce/sync",
                headers=admin_headers,
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "queued"
        assert body["integration_id"] == active_integration.id
        mock_celery.send_task.assert_called_once_with(
            "src.tasks.salesforce_sync.sync_salesforce_org",
            args=[active_integration.id],
        )

    def test_sync_returns_404_when_not_connected(self, client, owner_headers):
        with _salesforce_env():
            resp = client.post(
                "/api/v1/integrations/salesforce/sync",
                headers=owner_headers,
            )
        assert resp.status_code == 404

    def test_sync_forbidden_for_member(self, client, active_integration, member_headers):
        with _salesforce_env():
            resp = client.post(
                "/api/v1/integrations/salesforce/sync",
                headers=member_headers,
            )
        assert resp.status_code == 403
