"""
TDD tests for ZendeskClient.show_many (src/clients/zendesk.py).

No real HTTP. Uses unittest.mock.patch on httpx.Client methods.
Mirrors test_zendesk_client.py structure (client-batch-status aspect).
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
# TestShowMany
# ---------------------------------------------------------------------------


class TestShowMany:
    def test_two_ids_happy_path_issues_expected_get_and_parses_dict(self):
        from src.clients.zendesk import ZendeskClient

        page = {
            "tickets": [
                {"id": 1, "status": "open"},
                {"id": 2, "status": "solved"},
            ]
        }

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.get.return_value = _make_resp(200, page)

            with ZendeskClient(**_client_kwargs()) as client:
                result = client.show_many(["1", "2"])

        assert instance.get.call_count == 1
        call_args = instance.get.call_args
        assert call_args[0][0] == "/tickets/show_many.json"
        assert call_args[1]["params"] == {"ids": "1,2"}
        assert result == {"1": "open", "2": "solved"}

    def test_250_ids_chunked_into_3_requests_and_merged(self):
        from src.clients.zendesk import ZendeskClient

        all_ids = [str(i) for i in range(1, 251)]  # 250 ids

        def _page_for(chunk_ids):
            return _make_resp(
                200,
                {"tickets": [{"id": int(i), "status": "open"} for i in chunk_ids]},
            )

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.get.side_effect = [
                _page_for(all_ids[0:100]),
                _page_for(all_ids[100:200]),
                _page_for(all_ids[200:250]),
            ]

            with ZendeskClient(**_client_kwargs()) as client:
                result = client.show_many(all_ids)

        assert instance.get.call_count == 3

        call_1_params = instance.get.call_args_list[0][1]["params"]
        call_2_params = instance.get.call_args_list[1][1]["params"]
        call_3_params = instance.get.call_args_list[2][1]["params"]
        assert call_1_params["ids"] == ",".join(all_ids[0:100])
        assert call_2_params["ids"] == ",".join(all_ids[100:200])
        assert call_3_params["ids"] == ",".join(all_ids[200:250])

        assert len(result) == 250
        assert result["1"] == "open"
        assert result["250"] == "open"

    def test_id_present_in_request_absent_in_response_is_omitted(self):
        from src.clients.zendesk import ZendeskClient

        page = {
            "tickets": [
                {"id": 1, "status": "open"},
                # id 2 requested but not returned (deleted/archived) — no KeyError.
            ]
        }

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.get.return_value = _make_resp(200, page)

            with ZendeskClient(**_client_kwargs()) as client:
                result = client.show_many(["1", "2"])

        assert result == {"1": "open"}
        assert "2" not in result

    def test_429_with_retry_after_sleeps_then_raises_transient(self):
        from src.clients.zendesk import ZendeskClient, ZendeskTransientError

        resp = _make_resp(429, {}, headers={"Retry-After": "3"})

        with patch("httpx.Client") as MockHTTP, patch("src.clients.zendesk.time.sleep") as mock_sleep:
            instance = MockHTTP.return_value
            instance.get.return_value = resp

            with ZendeskClient(**_client_kwargs()) as client:
                with pytest.raises(ZendeskTransientError):
                    client.show_many(["1", "2"])

        mock_sleep.assert_called_once_with(3)

    def test_401_raises_auth_error(self):
        from src.clients.zendesk import ZendeskClient, ZendeskAuthError

        resp = _make_resp(401, {})

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.get.return_value = resp

            with ZendeskClient(**_client_kwargs()) as client:
                with pytest.raises(ZendeskAuthError):
                    client.show_many(["1", "2"])

    def test_empty_ids_makes_zero_http_calls_and_returns_empty_dict(self):
        from src.clients.zendesk import ZendeskClient

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value

            with ZendeskClient(**_client_kwargs()) as client:
                result = client.show_many([])

        instance.get.assert_not_called()
        assert result == {}
