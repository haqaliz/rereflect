"""
TDD tests for ZendeskClient (src/clients/zendesk.py).

No real HTTP. Uses unittest.mock.patch on httpx.Client methods.
Mirrors test_salesforce_client.py structure (Phase 2 of ingestion-pull plan).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_resp(status_code: int = 200, json_data: dict = None, headers: dict = None) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.headers = headers or {}
    return resp


def _client_kwargs(**overrides) -> dict:
    kwargs = dict(
        subdomain="acmeco",
        email="agent@acmeco.com",
        api_token="s3cr3t-token",
    )
    kwargs.update(overrides)
    return kwargs


# ---------------------------------------------------------------------------
# TestConstruction
# ---------------------------------------------------------------------------


class TestConstruction:
    def test_basic_auth_tuple_is_email_token_and_api_token(self):
        from src.clients.zendesk import ZendeskClient

        with patch("httpx.Client") as MockHTTP:
            ZendeskClient(**_client_kwargs())

        _, kwargs = MockHTTP.call_args
        assert kwargs["auth"] == ("agent@acmeco.com/token", "s3cr3t-token")

    def test_base_url_uses_subdomain(self):
        from src.clients.zendesk import ZendeskClient

        with patch("httpx.Client") as MockHTTP:
            ZendeskClient(**_client_kwargs())

        _, kwargs = MockHTTP.call_args
        assert kwargs["base_url"] == "https://acmeco.zendesk.com/api/v2"

    def test_token_never_appears_in_repr(self):
        from src.clients.zendesk import ZendeskClient

        with patch("httpx.Client"):
            client = ZendeskClient(**_client_kwargs())

        assert "s3cr3t-token" not in repr(client)
        assert "s3cr3t-token" not in str(client)

    def test_context_manager_and_close(self):
        from src.clients.zendesk import ZendeskClient

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            with ZendeskClient(**_client_kwargs()) as client:
                assert client is not None
            instance.close.assert_called_once()

    def test_close_is_idempotently_callable_directly(self):
        from src.clients.zendesk import ZendeskClient

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            client = ZendeskClient(**_client_kwargs())
            client.close()
            instance.close.assert_called_once()


# ---------------------------------------------------------------------------
# TestIncrementalTickets
# ---------------------------------------------------------------------------


class TestIncrementalTickets:
    def test_single_page_end_of_stream_returns_all_tickets(self):
        from src.clients.zendesk import ZendeskClient

        page = {
            "tickets": [
                {"id": 1, "subject": "A", "requester_id": 10},
                {"id": 2, "subject": "B", "requester_id": 11},
            ],
            "users": [
                {"id": 10, "email": "a@example.com"},
                {"id": 11, "email": "b@example.com"},
            ],
            "end_of_stream": True,
            "end_time": 1700000100,
            "next_page": None,
        }

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.get.return_value = _make_resp(200, page)

            with ZendeskClient(**_client_kwargs()) as client:
                result = client.incremental_tickets(start_time=1700000000)

        assert instance.get.call_count == 1
        assert len(result["tickets"]) == 2
        assert result["end_time"] == 1700000100

    def test_two_pages_via_next_page_concatenates_and_uses_literal_url(self):
        from src.clients.zendesk import ZendeskClient

        page1 = {
            "tickets": [{"id": 1, "subject": "A", "requester_id": 10}],
            "users": [{"id": 10, "email": "a@example.com"}],
            "end_of_stream": False,
            "end_time": 1700000050,
            "next_page": "https://acmeco.zendesk.com/api/v2/incremental/tickets?cursor=abc",
        }
        page2 = {
            "tickets": [{"id": 2, "subject": "B", "requester_id": 11}],
            "users": [{"id": 11, "email": "b@example.com"}],
            "end_of_stream": True,
            "end_time": 1700000100,
            "next_page": None,
        }

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.get.side_effect = [_make_resp(200, page1), _make_resp(200, page2)]

            with ZendeskClient(**_client_kwargs()) as client:
                result = client.incremental_tickets(start_time=1700000000)

        assert instance.get.call_count == 2
        second_call_args = instance.get.call_args_list[1]
        assert second_call_args[0][0] == (
            "https://acmeco.zendesk.com/api/v2/incremental/tickets?cursor=abc"
        )
        assert len(result["tickets"]) == 2
        assert [t["id"] for t in result["tickets"]] == [1, 2]
        assert result["end_time"] == 1700000100

    def test_side_loaded_users_merged_onto_tickets_as_flat_requester_email(self):
        from src.clients.zendesk import ZendeskClient

        page = {
            "tickets": [{"id": 1, "subject": "A", "requester_id": 10}],
            "users": [{"id": 10, "email": "a@example.com"}],
            "end_of_stream": True,
            "end_time": 1700000100,
        }

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.get.return_value = _make_resp(200, page)

            with ZendeskClient(**_client_kwargs()) as client:
                result = client.incremental_tickets(start_time=1700000000)

        assert result["tickets"][0]["requester_email"] == "a@example.com"

    def test_requester_with_no_matching_side_loaded_user_gets_none_not_exception(self):
        from src.clients.zendesk import ZendeskClient

        page = {
            "tickets": [{"id": 1, "subject": "A", "requester_id": 999}],
            "users": [{"id": 10, "email": "a@example.com"}],
            "end_of_stream": True,
            "end_time": 1700000100,
        }

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.get.return_value = _make_resp(200, page)

            with ZendeskClient(**_client_kwargs()) as client:
                result = client.incremental_tickets(start_time=1700000000)

        assert result["tickets"][0]["requester_email"] is None

    def test_per_run_page_cap_reached_stops_and_returns_partial_results(self):
        from src.clients.zendesk import ZendeskClient

        def _page(n):
            return _make_resp(200, {
                "tickets": [{"id": n, "subject": "T", "requester_id": None}],
                "users": [],
                "end_of_stream": False,
                "end_time": 1700000000 + n,
                "next_page": f"https://acmeco.zendesk.com/api/v2/incremental/tickets?cursor={n}",
            })

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.get.side_effect = [_page(n) for n in range(1, ZendeskClient.PER_RUN_PAGE_CAP + 5)]

            with ZendeskClient(**_client_kwargs()) as client:
                result = client.incremental_tickets(start_time=1700000000)

        assert instance.get.call_count == ZendeskClient.PER_RUN_PAGE_CAP
        assert len(result["tickets"]) == ZendeskClient.PER_RUN_PAGE_CAP


# ---------------------------------------------------------------------------
# TestRateLimitAndErrors
# ---------------------------------------------------------------------------


class TestRateLimitAndErrors:
    def test_429_with_retry_after_sleeps_and_raises_transient(self):
        from src.clients.zendesk import ZendeskClient, ZendeskTransientError

        resp = _make_resp(429, {}, headers={"Retry-After": "5"})

        with patch("httpx.Client") as MockHTTP, patch("src.clients.zendesk.time.sleep") as mock_sleep:
            instance = MockHTTP.return_value
            instance.get.return_value = resp

            with ZendeskClient(**_client_kwargs()) as client:
                with pytest.raises(ZendeskTransientError):
                    client.incremental_tickets(start_time=1700000000)

        mock_sleep.assert_called_once_with(5)

    def test_429_missing_retry_after_defaults_to_10(self):
        from src.clients.zendesk import ZendeskClient, ZendeskTransientError

        resp = _make_resp(429, {}, headers={})

        with patch("httpx.Client") as MockHTTP, patch("src.clients.zendesk.time.sleep") as mock_sleep:
            instance = MockHTTP.return_value
            instance.get.return_value = resp

            with ZendeskClient(**_client_kwargs()) as client:
                with pytest.raises(ZendeskTransientError):
                    client.incremental_tickets(start_time=1700000000)

        mock_sleep.assert_called_once_with(10)

    def test_5xx_raises_transient_no_sleep(self):
        from src.clients.zendesk import ZendeskClient, ZendeskTransientError

        resp = _make_resp(500, {})

        with patch("httpx.Client") as MockHTTP, patch("src.clients.zendesk.time.sleep") as mock_sleep:
            instance = MockHTTP.return_value
            instance.get.return_value = resp

            with ZendeskClient(**_client_kwargs()) as client:
                with pytest.raises(ZendeskTransientError):
                    client.incremental_tickets(start_time=1700000000)

        mock_sleep.assert_not_called()

    def test_503_raises_transient_no_sleep(self):
        from src.clients.zendesk import ZendeskClient, ZendeskTransientError

        resp = _make_resp(503, {})

        with patch("httpx.Client") as MockHTTP, patch("src.clients.zendesk.time.sleep") as mock_sleep:
            instance = MockHTTP.return_value
            instance.get.return_value = resp

            with ZendeskClient(**_client_kwargs()) as client:
                with pytest.raises(ZendeskTransientError):
                    client.incremental_tickets(start_time=1700000000)

        mock_sleep.assert_not_called()

    def test_401_raises_auth_error(self):
        from src.clients.zendesk import ZendeskClient, ZendeskAuthError

        resp = _make_resp(401, {})

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.get.return_value = resp

            with ZendeskClient(**_client_kwargs()) as client:
                with pytest.raises(ZendeskAuthError):
                    client.incremental_tickets(start_time=1700000000)

    def test_403_raises_auth_error(self):
        from src.clients.zendesk import ZendeskClient, ZendeskAuthError

        resp = _make_resp(403, {})

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.get.return_value = resp

            with ZendeskClient(**_client_kwargs()) as client:
                with pytest.raises(ZendeskAuthError):
                    client.incremental_tickets(start_time=1700000000)

    def test_404_raises_not_found_error(self):
        from src.clients.zendesk import ZendeskClient, ZendeskNotFoundError

        resp = _make_resp(404, {})

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.get.return_value = resp

            with ZendeskClient(**_client_kwargs()) as client:
                with pytest.raises(ZendeskNotFoundError):
                    client.incremental_tickets(start_time=1700000000)
