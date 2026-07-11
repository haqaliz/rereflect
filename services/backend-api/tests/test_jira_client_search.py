"""
TDD tests for JiraClient.search_issues (src/services/jira_client.py) —
Phase 3 (backend Jira status-fetch read method, jira-status-sync/inbound-status-sync).

No real HTTP. Uses unittest.mock.patch on httpx.Client, mirroring the mocking
style of tests/test_jira_client.py.

Covers: empty-keys short-circuit (no HTTP call), JQL string construction,
name+category parsing, a key missing from the response is simply omitted,
paging within a batch, and chunking when given >50 keys.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.services.jira_client import JiraClient


SITE_URL = "https://acme.atlassian.net"
EMAIL = "operator@acme.com"
API_TOKEN = "atlassian-super-secret-token-xyz"


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


def _search_resp(issues: list[dict], total: int | None = None, start_at: int = 0) -> MagicMock:
    return _make_resp(
        200,
        {
            "issues": issues,
            "total": total if total is not None else len(issues) + start_at,
            "startAt": start_at,
        },
    )


class TestSearchIssuesEmptyKeys:
    def test_empty_list_short_circuits_no_http_call(self):
        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            client = JiraClient(SITE_URL, EMAIL, API_TOKEN)
            result = client.search_issues([])

        assert result == {}
        instance.get.assert_not_called()


class TestSearchIssuesJQL:
    def test_jql_contains_issue_in_and_all_keys(self):
        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.get.return_value = _search_resp(
                [_issue("ENG-1"), _issue("ENG-2")]
            )

            client = JiraClient(SITE_URL, EMAIL, API_TOKEN)
            client.search_issues(["ENG-1", "ENG-2"])

        instance.get.assert_called_once()
        args, kwargs = instance.get.call_args
        params = kwargs.get("params", {})
        jql = params.get("jql", "")
        assert "issue in (" in jql
        assert "ENG-1" in jql
        assert "ENG-2" in jql

    def test_requests_status_field(self):
        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.get.return_value = _search_resp([_issue("ENG-1")])

            client = JiraClient(SITE_URL, EMAIL, API_TOKEN)
            client.search_issues(["ENG-1"])

        _, kwargs = instance.get.call_args
        params = kwargs.get("params", {})
        assert "status" in str(params.get("fields", ""))


class TestSearchIssuesParsing:
    def test_parses_name_and_category_into_dict(self):
        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.get.return_value = _search_resp(
                [
                    _issue("ENG-1", name="Done", category="done"),
                    _issue("ENG-2", name="To Do", category="new"),
                ]
            )

            client = JiraClient(SITE_URL, EMAIL, API_TOKEN)
            result = client.search_issues(["ENG-1", "ENG-2"])

        assert result == {
            "ENG-1": {"name": "Done", "category": "done"},
            "ENG-2": {"name": "To Do", "category": "new"},
        }

    def test_key_missing_from_response_is_omitted_not_raised(self):
        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            # Only ENG-1 comes back — ENG-2 was deleted/moved in Jira.
            instance.get.return_value = _search_resp([_issue("ENG-1")])

            client = JiraClient(SITE_URL, EMAIL, API_TOKEN)
            result = client.search_issues(["ENG-1", "ENG-2"])

        assert "ENG-1" in result
        assert "ENG-2" not in result


class TestSearchIssuesPaging:
    def test_pages_through_startat_until_all_issues_collected(self):
        # A single batch (<=50 keys) whose server response is split across
        # two pages (simulating the server returning fewer issues than the
        # requested maxResults on the first page) — search_issues must keep
        # paging via startAt until `total` issues have been collected.
        keys = [f"ENG-{i}" for i in range(1, 51)]  # 50 keys, one batch
        page1 = _search_resp(
            [_issue(k) for k in keys[:30]], total=50, start_at=0
        )
        page2 = _search_resp(
            [_issue(k) for k in keys[30:]], total=50, start_at=30
        )

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.get.side_effect = [page1, page2]

            client = JiraClient(SITE_URL, EMAIL, API_TOKEN)
            result = client.search_issues(keys)

        assert instance.get.call_count == 2
        assert len(result) == 50
        assert "ENG-1" in result
        assert "ENG-50" in result


class TestSearchIssuesChunking:
    def test_more_than_50_keys_triggers_chunked_calls_and_merges(self):
        keys = [f"ENG-{i}" for i in range(1, 61)]  # 60 keys -> 2 batches (50 + 10)

        batch1_resp = _search_resp([_issue(k) for k in keys[:50]])
        batch2_resp = _search_resp([_issue(k) for k in keys[50:]])

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.get.side_effect = [batch1_resp, batch2_resp]

            client = JiraClient(SITE_URL, EMAIL, API_TOKEN)
            result = client.search_issues(keys)

        assert instance.get.call_count == 2

        first_call_jql = instance.get.call_args_list[0].kwargs["params"]["jql"]
        second_call_jql = instance.get.call_args_list[1].kwargs["params"]["jql"]
        assert "ENG-1" in first_call_jql and "ENG-50" in first_call_jql
        assert "ENG-51" not in first_call_jql
        assert "ENG-51" in second_call_jql and "ENG-60" in second_call_jql

        assert len(result) == 60
        assert "ENG-1" in result
        assert "ENG-60" in result


class TestSearchIssuesErrorTaxonomy:
    @pytest.mark.parametrize("status_code", [401, 403])
    def test_auth_errors_propagate(self, status_code):
        from src.services.jira_client import JiraAuthError

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.get.return_value = _make_resp(status_code, {})

            client = JiraClient(SITE_URL, EMAIL, API_TOKEN)
            with pytest.raises(JiraAuthError):
                client.search_issues(["ENG-1"])

    @pytest.mark.parametrize("status_code", [429, 500, 502, 503])
    def test_transient_errors_propagate(self, status_code):
        from src.services.jira_client import JiraTransientError

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.get.return_value = _make_resp(status_code, {})

            client = JiraClient(SITE_URL, EMAIL, API_TOKEN)
            with pytest.raises(JiraTransientError):
                client.search_issues(["ENG-1"])
