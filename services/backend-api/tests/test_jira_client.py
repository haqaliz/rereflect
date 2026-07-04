"""
TDD tests for JiraClient (src/services/jira_client.py) — Phase 2 (backend-connection).

No real HTTP. Uses unittest.mock.patch on httpx.Client.

Covers: construction, base URL, Basic auth, validate() happy path, and the
error taxonomy (401/403 -> JiraAuthError, 429/5xx -> JiraTransientError,
404 -> JiraNotFoundError). Also asserts the API token never leaks via
repr()/str().
"""

from unittest.mock import MagicMock, patch

import pytest


SITE_URL = "https://acme.atlassian.net"
EMAIL = "operator@acme.com"
API_TOKEN = "atlassian-super-secret-token-xyz"

MYSELF_RESPONSE = {
    "accountId": "5b10a2844c20165700ede21g",
    "displayName": "Jane Operator",
    "emailAddress": EMAIL,
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
class TestJiraClientConstruction:
    def test_importable(self):
        from src.services.jira_client import JiraClient
        assert JiraClient is not None

    def test_constructs_with_site_email_token(self):
        from src.services.jira_client import JiraClient

        with patch("httpx.Client") as MockHTTP:
            client = JiraClient(SITE_URL, EMAIL, API_TOKEN)

        assert client is not None
        MockHTTP.assert_called_once()

    def test_base_url_is_rest_api_v3(self):
        from src.services.jira_client import JiraClient

        with patch("httpx.Client") as MockHTTP:
            JiraClient(SITE_URL, EMAIL, API_TOKEN)

        _, kwargs = MockHTTP.call_args
        assert kwargs["base_url"] == "https://acme.atlassian.net/rest/api/3"

    def test_uses_basic_auth_tuple(self):
        from src.services.jira_client import JiraClient

        with patch("httpx.Client") as MockHTTP:
            JiraClient(SITE_URL, EMAIL, API_TOKEN)

        _, kwargs = MockHTTP.call_args
        assert kwargs["auth"] == (EMAIL, API_TOKEN)

    def test_sets_timeout(self):
        from src.services.jira_client import JiraClient

        with patch("httpx.Client") as MockHTTP:
            JiraClient(SITE_URL, EMAIL, API_TOKEN)

        _, kwargs = MockHTTP.call_args
        assert kwargs["timeout"] == 15.0

    def test_context_manager_closes_client(self):
        from src.services.jira_client import JiraClient

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            with JiraClient(SITE_URL, EMAIL, API_TOKEN) as client:
                assert client is not None
            instance.close.assert_called_once()

    def test_close_method(self):
        from src.services.jira_client import JiraClient

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            client = JiraClient(SITE_URL, EMAIL, API_TOKEN)
            client.close()
            instance.close.assert_called_once()


# ---------------------------------------------------------------------------
# Token never leaks via repr/str
# ---------------------------------------------------------------------------
class TestJiraClientNoTokenLeak:
    def test_repr_excludes_token(self):
        from src.services.jira_client import JiraClient

        with patch("httpx.Client"):
            client = JiraClient(SITE_URL, EMAIL, API_TOKEN)

        assert API_TOKEN not in repr(client)

    def test_str_excludes_token(self):
        from src.services.jira_client import JiraClient

        with patch("httpx.Client"):
            client = JiraClient(SITE_URL, EMAIL, API_TOKEN)

        assert API_TOKEN not in str(client)


# ---------------------------------------------------------------------------
# validate() happy path
# ---------------------------------------------------------------------------
class TestJiraClientValidate:
    def test_validate_returns_account_info(self):
        from src.services.jira_client import JiraClient

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.get.return_value = _make_resp(200, MYSELF_RESPONSE)

            client = JiraClient(SITE_URL, EMAIL, API_TOKEN)
            result = client.validate()

        instance.get.assert_called_once_with("/myself")

        # Accept either an object with attributes or a dict — must expose
        # account_id + display_name in snake_case.
        if isinstance(result, dict):
            assert result["account_id"] == MYSELF_RESPONSE["accountId"]
            assert result["display_name"] == MYSELF_RESPONSE["displayName"]
        else:
            assert result.account_id == MYSELF_RESPONSE["accountId"]
            assert result.display_name == MYSELF_RESPONSE["displayName"]


# ---------------------------------------------------------------------------
# Error taxonomy
# ---------------------------------------------------------------------------
class TestJiraClientErrorTaxonomy:
    @pytest.mark.parametrize("status_code", [401, 403])
    def test_auth_errors_raise_jira_auth_error(self, status_code):
        from src.services.jira_client import JiraClient, JiraAuthError

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.get.return_value = _make_resp(status_code, {})

            client = JiraClient(SITE_URL, EMAIL, API_TOKEN)
            with pytest.raises(JiraAuthError):
                client.validate()

    @pytest.mark.parametrize("status_code", [429, 500, 502, 503])
    def test_transient_errors_raise_jira_transient_error(self, status_code):
        from src.services.jira_client import JiraClient, JiraTransientError

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.get.return_value = _make_resp(status_code, {})

            client = JiraClient(SITE_URL, EMAIL, API_TOKEN)
            with pytest.raises(JiraTransientError):
                client.validate()

    def test_not_found_raises_jira_not_found_error(self):
        from src.services.jira_client import JiraClient, JiraNotFoundError

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.get.return_value = _make_resp(404, {})

            client = JiraClient(SITE_URL, EMAIL, API_TOKEN)
            with pytest.raises(JiraNotFoundError):
                client.validate()

    def test_error_classes_inherit_from_jira_error(self):
        from src.services.jira_client import (
            JiraError,
            JiraAuthError,
            JiraTransientError,
            JiraNotFoundError,
        )

        assert issubclass(JiraAuthError, JiraError)
        assert issubclass(JiraTransientError, JiraError)
        assert issubclass(JiraNotFoundError, JiraError)
