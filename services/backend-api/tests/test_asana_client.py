"""
TDD tests for AsanaClient (src/services/asana_client.py) — Phase 2 (backend-connection).

No real HTTP. Uses unittest.mock.patch on httpx.Client.

Covers: construction, fixed base URL, Bearer auth header, validate() /
get_workspaces() / get_projects() happy paths, and the error taxonomy
(401/403 -> AsanaAuthError, 429/5xx -> AsanaTransientError,
404 -> AsanaNotFoundError). Also asserts the PAT never leaks via
repr()/str().
"""

from unittest.mock import MagicMock, patch

import pytest

from src.services.asana_client import AsanaClient


API_TOKEN = "asana-super-secret-pat-xyz"

USERS_ME_RESPONSE = {
    "data": {
        "gid": "1204567890123",
        "name": "Jane Operator",
    }
}

WORKSPACES_RESPONSE = {
    "data": [
        {"gid": "1100000000001", "name": "Acme Workspace"},
        {"gid": "1100000000002", "name": "Acme Sandbox"},
    ]
}

PROJECTS_RESPONSE = {
    "data": [
        {"gid": "1200000000001", "name": "Engineering"},
        {"gid": "1200000000002", "name": "Support"},
    ]
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
# Construction / base URL / Bearer auth
# ---------------------------------------------------------------------------
class TestAsanaClientConstruction:
    def test_importable(self):
        from src.services.asana_client import AsanaClient
        assert AsanaClient is not None

    def test_constructs_with_api_token(self):
        with patch("httpx.Client") as MockHTTP:
            client = AsanaClient(API_TOKEN)

        assert client is not None
        MockHTTP.assert_called_once()

    def test_base_url_is_fixed_asana_host(self):
        with patch("httpx.Client") as MockHTTP:
            AsanaClient(API_TOKEN)

        _, kwargs = MockHTTP.call_args
        assert kwargs["base_url"] == "https://app.asana.com/api/1.0"

    def test_uses_bearer_auth_header(self):
        with patch("httpx.Client") as MockHTTP:
            AsanaClient(API_TOKEN)

        _, kwargs = MockHTTP.call_args
        assert kwargs["headers"]["Authorization"] == f"Bearer {API_TOKEN}"

    def test_sets_timeout(self):
        with patch("httpx.Client") as MockHTTP:
            AsanaClient(API_TOKEN)

        _, kwargs = MockHTTP.call_args
        assert kwargs["timeout"] == 15.0

    def test_client_disables_redirect_following(self):
        with patch("httpx.Client") as MockHTTP:
            AsanaClient(API_TOKEN)
            _, kwargs = MockHTTP.call_args
            assert kwargs.get("follow_redirects") is False

    def test_context_manager_closes_client(self):
        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            with AsanaClient(API_TOKEN) as client:
                assert client is not None
            instance.close.assert_called_once()

    def test_close_method(self):
        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            client = AsanaClient(API_TOKEN)
            client.close()
            instance.close.assert_called_once()


# ---------------------------------------------------------------------------
# Token never leaks via repr/str
# ---------------------------------------------------------------------------
class TestAsanaClientNoTokenLeak:
    def test_repr_excludes_token(self):
        with patch("httpx.Client"):
            client = AsanaClient(API_TOKEN)

        assert API_TOKEN not in repr(client)

    def test_str_excludes_token(self):
        with patch("httpx.Client"):
            client = AsanaClient(API_TOKEN)

        assert API_TOKEN not in str(client)


# ---------------------------------------------------------------------------
# validate() happy path
# ---------------------------------------------------------------------------
class TestAsanaClientValidate:
    def test_validate_returns_user_info(self):
        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.get.return_value = _make_resp(200, USERS_ME_RESPONSE)

            client = AsanaClient(API_TOKEN)
            result = client.validate()

        instance.get.assert_called_once_with("/users/me")

        if isinstance(result, dict):
            assert result["gid"] == USERS_ME_RESPONSE["data"]["gid"]
            assert result["name"] == USERS_ME_RESPONSE["data"]["name"]
        else:
            assert result.gid == USERS_ME_RESPONSE["data"]["gid"]
            assert result.name == USERS_ME_RESPONSE["data"]["name"]


# ---------------------------------------------------------------------------
# get_workspaces() happy path
# ---------------------------------------------------------------------------
class TestAsanaClientGetWorkspaces:
    def test_get_workspaces_returns_list(self):
        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.get.return_value = _make_resp(200, WORKSPACES_RESPONSE)

            client = AsanaClient(API_TOKEN)
            result = client.get_workspaces()

        instance.get.assert_called_once_with("/workspaces")
        assert result == [
            {"gid": "1100000000001", "name": "Acme Workspace"},
            {"gid": "1100000000002", "name": "Acme Sandbox"},
        ]


# ---------------------------------------------------------------------------
# get_projects() happy path
# ---------------------------------------------------------------------------
class TestAsanaClientGetProjects:
    def test_get_projects_calls_workspace_scoped_endpoint(self):
        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.get.return_value = _make_resp(200, PROJECTS_RESPONSE)

            client = AsanaClient(API_TOKEN)
            result = client.get_projects("1100000000001")

        instance.get.assert_called_once_with(
            "/projects", params={"workspace": "1100000000001"}
        )
        assert result == [
            {"gid": "1200000000001", "name": "Engineering"},
            {"gid": "1200000000002", "name": "Support"},
        ]


# ---------------------------------------------------------------------------
# Error taxonomy
# ---------------------------------------------------------------------------
class TestAsanaClientErrorTaxonomy:
    @pytest.mark.parametrize("status_code", [401, 403])
    def test_auth_errors_raise_asana_auth_error(self, status_code):
        from src.services.asana_client import AsanaClient, AsanaAuthError

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.get.return_value = _make_resp(status_code, {})

            client = AsanaClient(API_TOKEN)
            with pytest.raises(AsanaAuthError):
                client.validate()

    @pytest.mark.parametrize("status_code", [429, 500, 502, 503])
    def test_transient_errors_raise_asana_transient_error(self, status_code):
        from src.services.asana_client import AsanaClient, AsanaTransientError

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.get.return_value = _make_resp(status_code, {})

            client = AsanaClient(API_TOKEN)
            with pytest.raises(AsanaTransientError):
                client.validate()

    def test_not_found_raises_asana_not_found_error(self):
        from src.services.asana_client import AsanaClient, AsanaNotFoundError

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.get.return_value = _make_resp(404, {})

            client = AsanaClient(API_TOKEN)
            with pytest.raises(AsanaNotFoundError):
                client.validate()

    def test_error_classes_inherit_from_asana_error(self):
        from src.services.asana_client import (
            AsanaError,
            AsanaAuthError,
            AsanaTransientError,
            AsanaNotFoundError,
        )

        assert issubclass(AsanaAuthError, AsanaError)
        assert issubclass(AsanaTransientError, AsanaError)
        assert issubclass(AsanaNotFoundError, AsanaError)


CREATE_TASK_RESPONSE = {
    "data": {
        "gid": "1300000000001",
        "name": "Customer reports login is broken",
        "permalink_url": "https://app.asana.com/0/1200000000001/1300000000001",
    }
}

CREATE_TASK_RESPONSE_NO_PERMALINK = {
    "data": {
        "gid": "1300000000001",
        "name": "Customer reports login is broken",
    }
}

GET_TASK_RESPONSE = {
    "data": {
        "gid": "1300000000001",
        "permalink_url": "https://app.asana.com/0/1200000000001/1300000000001",
    }
}


# ---------------------------------------------------------------------------
# create_task() — backend-create-task aspect
# ---------------------------------------------------------------------------
class TestAsanaClientCreateTask:
    def test_create_task_posts_expected_body_and_opt_fields(self):
        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.post.return_value = _make_resp(200, CREATE_TASK_RESPONSE)

            client = AsanaClient(API_TOKEN)
            result = client.create_task({
                "name": "Customer reports login is broken",
                "notes": "Users cannot log in after the latest release.",
                "project_gid": "1200000000001",
                "workspace_gid": "1100000000001",
            })

        instance.post.assert_called_once_with(
            "/tasks?opt_fields=permalink_url,name,gid",
            json={
                "data": {
                    "name": "Customer reports login is broken",
                    "notes": "Users cannot log in after the latest release.",
                    "projects": ["1200000000001"],
                    "workspace": "1100000000001",
                }
            },
        )
        assert result["gid"] == "1300000000001"
        assert result["url"] == "https://app.asana.com/0/1200000000001/1300000000001"
        assert result["url"] is not None

    def test_create_task_falls_back_to_get_when_permalink_missing(self):
        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.post.return_value = _make_resp(200, CREATE_TASK_RESPONSE_NO_PERMALINK)
            instance.get.return_value = _make_resp(200, GET_TASK_RESPONSE)

            client = AsanaClient(API_TOKEN)
            result = client.create_task({
                "name": "Customer reports login is broken",
                "notes": "Users cannot log in after the latest release.",
                "project_gid": "1200000000001",
                "workspace_gid": "1100000000001",
            })

        instance.get.assert_called_once_with(
            "/tasks/1300000000001", params={"opt_fields": "permalink_url"}
        )
        assert result["gid"] == "1300000000001"
        assert result["url"] == "https://app.asana.com/0/1200000000001/1300000000001"
        assert result["url"] is not None

    def test_create_task_auth_error_raises_asana_auth_error(self):
        from src.services.asana_client import AsanaAuthError

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.post.return_value = _make_resp(401, {})

            client = AsanaClient(API_TOKEN)
            with pytest.raises(AsanaAuthError):
                client.create_task({
                    "name": "x",
                    "notes": "",
                    "project_gid": "1200000000001",
                    "workspace_gid": "1100000000001",
                })

    def test_create_task_transient_error_raises_asana_transient_error(self):
        from src.services.asana_client import AsanaTransientError

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.post.return_value = _make_resp(503, {})

            client = AsanaClient(API_TOKEN)
            with pytest.raises(AsanaTransientError):
                client.create_task({
                    "name": "x",
                    "notes": "",
                    "project_gid": "1200000000001",
                    "workspace_gid": "1100000000001",
                })


GET_TASK_COMPLETED = {
    "data": {
        "gid": "1300000000001",
        "completed": True,
        "completed_at": "2026-07-10T14:03:00.000Z",
        "memberships": [{"section": {"name": "Done"}}],
    }
}

GET_TASK_INCOMPLETE = {
    "data": {
        "gid": "1300000000001",
        "completed": False,
        "completed_at": None,
        "memberships": [{"section": {"name": "In progress"}}],
    }
}

GET_TASK_NO_MEMBERSHIPS = {
    "data": {
        "gid": "1300000000001",
        "completed": True,
    }
}


# ---------------------------------------------------------------------------
# get_task() — asana-client-get-task aspect
# ---------------------------------------------------------------------------
class TestAsanaClientGetTask:
    def test_get_task_calls_expected_endpoint_and_opt_fields(self):
        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.get.return_value = _make_resp(200, GET_TASK_COMPLETED)

            client = AsanaClient(API_TOKEN)
            client.get_task("1300000000001")

        instance.get.assert_called_once_with(
            "/tasks/1300000000001",
            params={"opt_fields": "completed,completed_at,memberships.section.name"},
        )

    def test_get_task_parses_completed_task(self):
        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.get.return_value = _make_resp(200, GET_TASK_COMPLETED)

            client = AsanaClient(API_TOKEN)
            result = client.get_task("1300000000001")

        assert result == {
            "completed": True,
            "completed_at": "2026-07-10T14:03:00.000Z",
            "memberships": [{"section": {"name": "Done"}}],
        }

    def test_get_task_incomplete_has_none_completed_at(self):
        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.get.return_value = _make_resp(200, GET_TASK_INCOMPLETE)

            client = AsanaClient(API_TOKEN)
            result = client.get_task("1300000000001")

        assert result["completed"] is False
        assert result["completed_at"] is None

    def test_get_task_missing_memberships_defaults_to_empty_list(self):
        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.get.return_value = _make_resp(200, GET_TASK_NO_MEMBERSHIPS)

            client = AsanaClient(API_TOKEN)
            result = client.get_task("1300000000001")

        assert result["memberships"] == []

    @pytest.mark.parametrize("status_code", [401, 403])
    def test_get_task_auth_errors_raise_asana_auth_error(self, status_code):
        from src.services.asana_client import AsanaAuthError

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.get.return_value = _make_resp(status_code, {})

            client = AsanaClient(API_TOKEN)
            with pytest.raises(AsanaAuthError):
                client.get_task("1300000000001")

    @pytest.mark.parametrize("status_code", [429, 500, 502, 503])
    def test_get_task_transient_errors_raise_asana_transient_error(self, status_code):
        from src.services.asana_client import AsanaTransientError

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.get.return_value = _make_resp(status_code, {})

            client = AsanaClient(API_TOKEN)
            with pytest.raises(AsanaTransientError):
                client.get_task("1300000000001")

    def test_get_task_not_found_raises_asana_not_found_error(self):
        from src.services.asana_client import AsanaNotFoundError

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.get.return_value = _make_resp(404, {})

            client = AsanaClient(API_TOKEN)
            with pytest.raises(AsanaNotFoundError):
                client.get_task("1300000000001")


class TestAsanaClientConstantHostAssertion:
    """Defense-in-depth constant scheme/host assert — Asana has a fixed host,
    so there's no per-org SSRF surface to gate (unlike Jira/Zendesk), but the
    client still asserts its own BASE_URL invariant (mirrors
    TestJiraClientSSRFGuard's behavioral structure)."""

    @pytest.mark.parametrize(
        "bad_base_url",
        [
            "http://app.asana.com/api/1.0",     # non-https scheme
            "https://evil.example.com/api/1.0",  # non-asana host
            "https://app.asana.com.evil.com/api/1.0",  # suffix-trick host
        ],
    )
    def test_rejects_unsafe_base_url(self, bad_base_url, monkeypatch):
        monkeypatch.setattr(AsanaClient, "BASE_URL", bad_base_url)
        with patch("httpx.Client"), pytest.raises(ValueError):
            AsanaClient(API_TOKEN)

    def test_allows_valid_constant_base_url(self):
        with patch("httpx.Client"):
            # Should not raise.
            AsanaClient(API_TOKEN)
