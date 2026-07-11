"""
TDD tests for the worker-owned JiraClient (src/clients/jira.py) — Phase 4 of
docs/planning/jira-status-sync/inbound-status-sync/plan_20260711.md.

No real HTTP. Uses unittest.mock.patch on httpx.Client, mirroring
test_zendesk_client.py's structure (this worker cannot import
backend-api's src/services/jira_client.py, so it's a standalone client
scoped to what the poller needs: search_issues).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


def _make_resp(status_code: int = 200, json_data: dict = None, headers: dict = None) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.headers = headers or {}
    return resp


def _client_kwargs(**overrides) -> dict:
    kwargs = dict(
        site_url="https://acme.atlassian.net",
        email="operator@acme.com",
        api_token="s3cr3t-token",
    )
    kwargs.update(overrides)
    return kwargs


def _issue(key: str, name: str = "In Progress", category: str = "indeterminate") -> dict:
    return {
        "key": key,
        "fields": {
            "status": {
                "name": name,
                "statusCategory": {"key": category},
            }
        },
    }


def _search_resp(issues: list, total: int = None, start_at: int = 0) -> MagicMock:
    return _make_resp(
        200,
        {
            "issues": issues,
            "total": total if total is not None else len(issues) + start_at,
            "startAt": start_at,
        },
    )


# ---------------------------------------------------------------------------
# TestConstruction
# ---------------------------------------------------------------------------


class TestConstruction:
    def test_basic_auth_tuple_is_email_and_api_token(self):
        from src.clients.jira import JiraClient

        with patch("httpx.Client") as MockHTTP:
            JiraClient(**_client_kwargs())

        _, kwargs = MockHTTP.call_args
        assert kwargs["auth"] == ("operator@acme.com", "s3cr3t-token")

    def test_base_url_is_site_url_plus_api_path(self):
        from src.clients.jira import JiraClient

        with patch("httpx.Client") as MockHTTP:
            JiraClient(**_client_kwargs())

        _, kwargs = MockHTTP.call_args
        assert kwargs["base_url"] == "https://acme.atlassian.net/rest/api/3"

    def test_timeout_is_15_seconds(self):
        from src.clients.jira import JiraClient

        with patch("httpx.Client") as MockHTTP:
            JiraClient(**_client_kwargs())

        _, kwargs = MockHTTP.call_args
        assert kwargs["timeout"] == 15.0

    def test_token_never_appears_in_repr(self):
        from src.clients.jira import JiraClient

        with patch("httpx.Client"):
            client = JiraClient(**_client_kwargs())

        assert "s3cr3t-token" not in repr(client)
        assert "s3cr3t-token" not in str(client)

    def test_context_manager_and_close(self):
        from src.clients.jira import JiraClient

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            with JiraClient(**_client_kwargs()) as client:
                assert client is not None
            instance.close.assert_called_once()

    def test_close_is_directly_callable(self):
        from src.clients.jira import JiraClient

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            client = JiraClient(**_client_kwargs())
            client.close()
            instance.close.assert_called_once()


# ---------------------------------------------------------------------------
# TestErrorTaxonomy — throttle mapping
# ---------------------------------------------------------------------------


class TestErrorTaxonomy:
    def test_429_with_retry_after_sleeps_and_raises_transient(self):
        from src.clients.jira import JiraClient, JiraTransientError

        resp = _make_resp(429, {}, headers={"Retry-After": "5"})

        with patch("httpx.Client") as MockHTTP, patch("src.clients.jira.time.sleep") as mock_sleep:
            instance = MockHTTP.return_value
            instance.get.return_value = resp

            client = JiraClient(**_client_kwargs())
            with pytest.raises(JiraTransientError):
                client.search_issues(["ENG-1"])

        mock_sleep.assert_called_once_with(5)

    def test_429_missing_retry_after_defaults_to_10(self):
        from src.clients.jira import JiraClient, JiraTransientError

        resp = _make_resp(429, {}, headers={})

        with patch("httpx.Client") as MockHTTP, patch("src.clients.jira.time.sleep") as mock_sleep:
            instance = MockHTTP.return_value
            instance.get.return_value = resp

            client = JiraClient(**_client_kwargs())
            with pytest.raises(JiraTransientError):
                client.search_issues(["ENG-1"])

        mock_sleep.assert_called_once_with(10)

    @pytest.mark.parametrize("status_code", [500, 502, 503])
    def test_5xx_raises_transient_without_sleep(self, status_code):
        from src.clients.jira import JiraClient, JiraTransientError

        resp = _make_resp(status_code, {})

        with patch("httpx.Client") as MockHTTP, patch("src.clients.jira.time.sleep") as mock_sleep:
            instance = MockHTTP.return_value
            instance.get.return_value = resp

            client = JiraClient(**_client_kwargs())
            with pytest.raises(JiraTransientError):
                client.search_issues(["ENG-1"])

        mock_sleep.assert_not_called()

    @pytest.mark.parametrize("status_code", [401, 403])
    def test_401_403_raises_auth_error(self, status_code):
        from src.clients.jira import JiraAuthError, JiraClient

        resp = _make_resp(status_code, {})

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.get.return_value = resp

            client = JiraClient(**_client_kwargs())
            with pytest.raises(JiraAuthError):
                client.search_issues(["ENG-1"])

    def test_404_raises_not_found_error(self):
        from src.clients.jira import JiraClient, JiraNotFoundError

        resp = _make_resp(404, {})

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.get.return_value = resp

            client = JiraClient(**_client_kwargs())
            with pytest.raises(JiraNotFoundError):
                client.search_issues(["ENG-1"])


# ---------------------------------------------------------------------------
# TestSearchIssues — JQL build / parse / chunk / page
# ---------------------------------------------------------------------------


class TestSearchIssuesEmptyKeys:
    def test_empty_list_short_circuits_no_http_call(self):
        from src.clients.jira import JiraClient

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            client = JiraClient(**_client_kwargs())
            result = client.search_issues([])

        assert result == {}
        instance.get.assert_not_called()


class TestSearchIssuesJQL:
    def test_jql_contains_issue_in_and_all_keys(self):
        from src.clients.jira import JiraClient

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.get.return_value = _search_resp([_issue("ENG-1"), _issue("ENG-2")])

            client = JiraClient(**_client_kwargs())
            client.search_issues(["ENG-1", "ENG-2"])

        instance.get.assert_called_once()
        _, kwargs = instance.get.call_args
        jql = kwargs["params"]["jql"]
        assert "issue in (" in jql
        assert "ENG-1" in jql
        assert "ENG-2" in jql

    def test_requests_status_field(self):
        from src.clients.jira import JiraClient

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.get.return_value = _search_resp([_issue("ENG-1")])

            client = JiraClient(**_client_kwargs())
            client.search_issues(["ENG-1"])

        _, kwargs = instance.get.call_args
        assert kwargs["params"]["fields"] == "status"


class TestSearchIssuesParsing:
    def test_parses_name_and_category_into_dict(self):
        from src.clients.jira import JiraClient

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.get.return_value = _search_resp([
                _issue("ENG-1", name="Done", category="done"),
                _issue("ENG-2", name="To Do", category="new"),
            ])

            client = JiraClient(**_client_kwargs())
            result = client.search_issues(["ENG-1", "ENG-2"])

        assert result == {
            "ENG-1": {"name": "Done", "category": "done"},
            "ENG-2": {"name": "To Do", "category": "new"},
        }

    def test_key_missing_from_response_is_omitted_not_raised(self):
        from src.clients.jira import JiraClient

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.get.return_value = _search_resp([_issue("ENG-1")])

            client = JiraClient(**_client_kwargs())
            result = client.search_issues(["ENG-1", "ENG-2"])

        assert "ENG-1" in result
        assert "ENG-2" not in result


class TestSearchIssuesPaging:
    def test_pages_through_startat_until_all_issues_collected(self):
        from src.clients.jira import JiraClient

        keys = [f"ENG-{i}" for i in range(1, 51)]
        page1 = _search_resp([_issue(k) for k in keys[:30]], total=50, start_at=0)
        page2 = _search_resp([_issue(k) for k in keys[30:]], total=50, start_at=30)

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.get.side_effect = [page1, page2]

            client = JiraClient(**_client_kwargs())
            result = client.search_issues(keys)

        assert instance.get.call_count == 2
        assert len(result) == 50
        assert "ENG-1" in result
        assert "ENG-50" in result


class TestSearchIssuesChunking:
    def test_more_than_50_keys_triggers_chunked_calls_and_merges(self):
        from src.clients.jira import JiraClient

        keys = [f"ENG-{i}" for i in range(1, 61)]  # 60 keys -> 2 batches

        batch1_resp = _search_resp([_issue(k) for k in keys[:50]])
        batch2_resp = _search_resp([_issue(k) for k in keys[50:]])

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.get.side_effect = [batch1_resp, batch2_resp]

            client = JiraClient(**_client_kwargs())
            result = client.search_issues(keys)

        assert instance.get.call_count == 2

        first_jql = instance.get.call_args_list[0].kwargs["params"]["jql"]
        second_jql = instance.get.call_args_list[1].kwargs["params"]["jql"]
        assert "ENG-1" in first_jql and "ENG-50" in first_jql
        assert "ENG-51" not in first_jql
        assert "ENG-51" in second_jql and "ENG-60" in second_jql

        assert len(result) == 60
        assert "ENG-1" in result
        assert "ENG-60" in result
