"""
TDD tests for ZendeskClient (src/services/zendesk_client.py) — Phase 2 (backend-connection).

No real HTTP. Uses unittest.mock.patch on httpx.Client.

Covers: construction, base URL, Basic auth (email + "/token" suffix), validate()
happy path, and the error taxonomy (401/403 -> ZendeskAuthError, 429/5xx ->
ZendeskTransientError, 404 -> ZendeskNotFoundError). Also asserts the API
token never leaks via repr()/str(), and the client-side SSRF guard on the
subdomain (defense-in-depth; the route's DNS-based gate is the primary one).
"""

from unittest.mock import MagicMock, patch

import pytest

from src.services.zendesk_client import ZendeskClient


SUBDOMAIN = "acme"
EMAIL = "operator@acme.com"
API_TOKEN = "zendesk-super-secret-token-xyz"

ME_RESPONSE = {
    "user": {
        "id": 12345,
        "name": "Jane Agent",
        "email": EMAIL,
    }
}


def _make_resp(status_code: int = 200, json_data: dict = None) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    if status_code >= 400:
        from httpx import HTTPStatusError
        resp.raise_for_status.side_effect = HTTPStatusError(
            f"HTTP {status_code}",
            request=MagicMock(),
            response=MagicMock(status_code=status_code),
        )
    else:
        resp.raise_for_status = MagicMock()
    return resp


# ---------------------------------------------------------------------------
# Construction / base URL / Basic auth
# ---------------------------------------------------------------------------
class TestZendeskClientConstruction:
    def test_importable(self):
        from src.services.zendesk_client import ZendeskClient
        assert ZendeskClient is not None

    def test_constructs_with_subdomain_email_token(self):
        from src.services.zendesk_client import ZendeskClient

        with patch("httpx.Client") as MockHTTP:
            client = ZendeskClient(SUBDOMAIN, EMAIL, API_TOKEN)

        assert client is not None
        MockHTTP.assert_called_once()

    def test_base_url_is_api_v2(self):
        from src.services.zendesk_client import ZendeskClient

        with patch("httpx.Client") as MockHTTP:
            ZendeskClient(SUBDOMAIN, EMAIL, API_TOKEN)

        _, kwargs = MockHTTP.call_args
        assert kwargs["base_url"] == "https://acme.zendesk.com/api/v2"

    def test_uses_basic_auth_tuple_with_slash_token_suffix(self):
        from src.services.zendesk_client import ZendeskClient

        with patch("httpx.Client") as MockHTTP:
            ZendeskClient(SUBDOMAIN, EMAIL, API_TOKEN)

        _, kwargs = MockHTTP.call_args
        assert kwargs["auth"] == ("operator@acme.com/token", API_TOKEN)

    def test_sets_timeout(self):
        from src.services.zendesk_client import ZendeskClient

        with patch("httpx.Client") as MockHTTP:
            ZendeskClient(SUBDOMAIN, EMAIL, API_TOKEN)

        _, kwargs = MockHTTP.call_args
        assert kwargs["timeout"] == 15.0

    def test_context_manager_closes_client(self):
        from src.services.zendesk_client import ZendeskClient

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            with ZendeskClient(SUBDOMAIN, EMAIL, API_TOKEN) as client:
                assert client is not None
            instance.close.assert_called_once()

    def test_close_method(self):
        from src.services.zendesk_client import ZendeskClient

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            client = ZendeskClient(SUBDOMAIN, EMAIL, API_TOKEN)
            client.close()
            instance.close.assert_called_once()


# ---------------------------------------------------------------------------
# Token never leaks via repr/str
# ---------------------------------------------------------------------------
class TestZendeskClientNoTokenLeak:
    def test_repr_excludes_token(self):
        from src.services.zendesk_client import ZendeskClient

        with patch("httpx.Client"):
            client = ZendeskClient(SUBDOMAIN, EMAIL, API_TOKEN)

        assert API_TOKEN not in repr(client)

    def test_str_excludes_token(self):
        from src.services.zendesk_client import ZendeskClient

        with patch("httpx.Client"):
            client = ZendeskClient(SUBDOMAIN, EMAIL, API_TOKEN)

        assert API_TOKEN not in str(client)


# ---------------------------------------------------------------------------
# validate() happy path
# ---------------------------------------------------------------------------
class TestZendeskClientValidate:
    def test_validate_returns_account_info(self):
        from src.services.zendesk_client import ZendeskClient

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.get.return_value = _make_resp(200, ME_RESPONSE)

            client = ZendeskClient(SUBDOMAIN, EMAIL, API_TOKEN)
            result = client.validate()

        instance.get.assert_called_once_with("/users/me.json")

        assert result["account_user_id"] == "12345"
        assert result["display_name"] == "Jane Agent"
        assert result["email"] == "operator@acme.com"


# ---------------------------------------------------------------------------
# Error taxonomy
# ---------------------------------------------------------------------------
class TestZendeskClientErrorTaxonomy:
    @pytest.mark.parametrize("status_code", [401, 403])
    def test_auth_errors_raise_zendesk_auth_error(self, status_code):
        from src.services.zendesk_client import ZendeskClient, ZendeskAuthError

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.get.return_value = _make_resp(status_code, {})

            client = ZendeskClient(SUBDOMAIN, EMAIL, API_TOKEN)
            with pytest.raises(ZendeskAuthError):
                client.validate()

    @pytest.mark.parametrize("status_code", [429, 500, 502, 503])
    def test_transient_errors_raise_zendesk_transient_error(self, status_code):
        from src.services.zendesk_client import ZendeskClient, ZendeskTransientError

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.get.return_value = _make_resp(status_code, {})

            client = ZendeskClient(SUBDOMAIN, EMAIL, API_TOKEN)
            with pytest.raises(ZendeskTransientError):
                client.validate()

    def test_not_found_raises_zendesk_not_found_error(self):
        from src.services.zendesk_client import ZendeskClient, ZendeskNotFoundError

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.get.return_value = _make_resp(404, {})

            client = ZendeskClient(SUBDOMAIN, EMAIL, API_TOKEN)
            with pytest.raises(ZendeskNotFoundError):
                client.validate()

    def test_error_classes_inherit_from_zendesk_error(self):
        from src.services.zendesk_client import (
            ZendeskError,
            ZendeskAuthError,
            ZendeskTransientError,
            ZendeskNotFoundError,
        )

        assert issubclass(ZendeskAuthError, ZendeskError)
        assert issubclass(ZendeskTransientError, ZendeskError)
        assert issubclass(ZendeskNotFoundError, ZendeskError)


class TestZendeskClientSSRFGuard:
    """Defense-in-depth SSRF guard on the target subdomain (mirrors Jira's client-level guard)."""

    @pytest.mark.parametrize(
        "bad_subdomain",
        [
            "",
            "acme/evil",
            "acme.evil.com",       # dot in subdomain — not a bare label
            "acme:443",
            "http://acme",          # scheme sneaks into the subdomain field
            "169.254.169.254",      # raw IP as "subdomain"
        ],
    )
    def test_rejects_disallowed_subdomain(self, bad_subdomain):
        with pytest.raises(ValueError):
            ZendeskClient(bad_subdomain, EMAIL, API_TOKEN)

    def test_allows_valid_bare_subdomain(self):
        with patch("httpx.Client"):
            # Should not raise.
            ZendeskClient("acme", EMAIL, API_TOKEN)

    def test_client_disables_redirect_following(self):
        with patch("httpx.Client") as MockHTTP:
            ZendeskClient(SUBDOMAIN, EMAIL, API_TOKEN)
            _, kwargs = MockHTTP.call_args
            assert kwargs.get("follow_redirects") is False
