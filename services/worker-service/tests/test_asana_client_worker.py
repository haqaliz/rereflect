"""
TDD tests for the worker-owned AsanaClient (src/clients/asana.py) and the
pure asana_category adapter (src/services/asana_adapter.py) — the
asana-client-get-task aspect of docs/planning/asana-status-sync.

No real HTTP. Uses unittest.mock.patch on httpx.Client, mirroring
test_jira_client_worker.py's structure (this worker cannot import
backend-api's src/services/asana_client.py, so it's a standalone client
scoped to what the poller needs: get_task only).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.clients.asana import AsanaClient


API_TOKEN = "asana-super-secret-pat-xyz"

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


def _make_resp(status_code: int = 200, json_data: dict = None, headers: dict = None) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.headers = headers or {}
    return resp


# ---------------------------------------------------------------------------
# TestConstruction
# ---------------------------------------------------------------------------


class TestConstruction:
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

    def test_timeout_is_15_seconds(self):
        with patch("httpx.Client") as MockHTTP:
            AsanaClient(API_TOKEN)

        _, kwargs = MockHTTP.call_args
        assert kwargs["timeout"] == 15.0

    def test_follow_redirects_is_false(self):
        with patch("httpx.Client") as MockHTTP:
            AsanaClient(API_TOKEN)

        _, kwargs = MockHTTP.call_args
        assert kwargs["follow_redirects"] is False

    def test_token_never_appears_in_repr_or_str(self):
        with patch("httpx.Client"):
            client = AsanaClient(API_TOKEN)

        assert API_TOKEN not in repr(client)
        assert API_TOKEN not in str(client)

    def test_context_manager_and_close(self):
        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            with AsanaClient(API_TOKEN) as client:
                assert client is not None
            instance.close.assert_called_once()

    def test_close_is_directly_callable(self):
        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            client = AsanaClient(API_TOKEN)
            client.close()
            instance.close.assert_called_once()


# ---------------------------------------------------------------------------
# TestErrorTaxonomy — the critical Retry-After cases
# ---------------------------------------------------------------------------


class TestErrorTaxonomy:
    def test_429_with_retry_after_sleeps_and_raises_transient(self):
        from src.clients.asana import AsanaTransientError

        resp = _make_resp(429, {}, headers={"Retry-After": "5"})

        with patch("httpx.Client") as MockHTTP, patch("src.clients.asana.time.sleep") as mock_sleep:
            instance = MockHTTP.return_value
            instance.get.return_value = resp

            client = AsanaClient(API_TOKEN)
            with pytest.raises(AsanaTransientError):
                client.get_task("1300000000001")

        mock_sleep.assert_called_once_with(5)

    def test_429_missing_retry_after_defaults_to_10(self):
        from src.clients.asana import AsanaTransientError

        resp = _make_resp(429, {}, headers={})

        with patch("httpx.Client") as MockHTTP, patch("src.clients.asana.time.sleep") as mock_sleep:
            instance = MockHTTP.return_value
            instance.get.return_value = resp

            client = AsanaClient(API_TOKEN)
            with pytest.raises(AsanaTransientError):
                client.get_task("1300000000001")

        mock_sleep.assert_called_once_with(10)

    @pytest.mark.parametrize("status_code", [500, 502, 503])
    def test_5xx_raises_transient_without_sleep(self, status_code):
        from src.clients.asana import AsanaTransientError

        resp = _make_resp(status_code, {})

        with patch("httpx.Client") as MockHTTP, patch("src.clients.asana.time.sleep") as mock_sleep:
            instance = MockHTTP.return_value
            instance.get.return_value = resp

            client = AsanaClient(API_TOKEN)
            with pytest.raises(AsanaTransientError):
                client.get_task("1300000000001")

        mock_sleep.assert_not_called()

    @pytest.mark.parametrize("status_code", [401, 403])
    def test_401_403_raises_auth_error(self, status_code):
        from src.clients.asana import AsanaAuthError

        resp = _make_resp(status_code, {})

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.get.return_value = resp

            client = AsanaClient(API_TOKEN)
            with pytest.raises(AsanaAuthError):
                client.get_task("1300000000001")

    def test_404_raises_not_found_error(self):
        from src.clients.asana import AsanaNotFoundError

        resp = _make_resp(404, {})

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.get.return_value = resp

            client = AsanaClient(API_TOKEN)
            with pytest.raises(AsanaNotFoundError):
                client.get_task("1300000000001")

    def test_error_classes_inherit_from_asana_error(self):
        from src.clients.asana import (
            AsanaError,
            AsanaAuthError,
            AsanaTransientError,
            AsanaNotFoundError,
        )

        assert issubclass(AsanaAuthError, AsanaError)
        assert issubclass(AsanaTransientError, AsanaError)
        assert issubclass(AsanaNotFoundError, AsanaError)


# ---------------------------------------------------------------------------
# TestGetTask — endpoint + opt_fields + parsing
# ---------------------------------------------------------------------------


class TestGetTask:
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


# ---------------------------------------------------------------------------
# TestConstantHostAssertion
# ---------------------------------------------------------------------------


class TestConstantHostAssertion:
    @pytest.mark.parametrize(
        "bad_base_url",
        [
            "http://app.asana.com/api/1.0",  # non-https scheme
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


# ---------------------------------------------------------------------------
# TestAsanaCategory — pure adapter (no I/O)
# ---------------------------------------------------------------------------


class TestAsanaCategory:
    def test_completed_true_maps_to_done(self):
        from src.services.asana_adapter import asana_category

        assert asana_category(True) == "done"

    def test_completed_false_maps_to_new(self):
        from src.services.asana_adapter import asana_category

        assert asana_category(False) == "new"
