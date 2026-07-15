"""
TDD tests for SalesforceClient (src/clients/salesforce.py).

No real HTTP. Uses unittest.mock.patch on httpx.Client methods.
Mirrors test_hubspot_client.py structure.
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


def _make_token_resp(access_token: str = "test-access-token", instance_url: str = None) -> MagicMock:
    data = {"access_token": access_token, "token_type": "Bearer"}
    if instance_url:
        data["instance_url"] = instance_url
    return _make_resp(200, data)


def _client_kwargs(**overrides) -> dict:
    kwargs = dict(
        refresh_token="refresh-token-123",
        instance_url="https://acme.my.salesforce.com",
        client_id="client-id",
        client_secret="client-secret",
    )
    kwargs.update(overrides)
    return kwargs


# ---------------------------------------------------------------------------
# TestSalesforceClientAuth
# ---------------------------------------------------------------------------


class TestSalesforceClientAuth:
    def test_refresh_success_sets_access_token(self):
        from src.clients.salesforce import SalesforceClient

        token_resp = _make_token_resp("abc123")

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.post.return_value = token_resp

            with SalesforceClient(**_client_kwargs()) as client:
                assert client._access_token == "abc123"

    def test_refresh_posts_to_login_base_token_endpoint(self):
        from src.clients.salesforce import SalesforceClient

        token_resp = _make_token_resp()

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.post.return_value = token_resp

            with SalesforceClient(**_client_kwargs(login_base="https://login.salesforce.com")):
                pass

        call = instance.post.call_args
        url = call[0][0]
        assert url == "https://login.salesforce.com/services/oauth2/token"
        data = call[1]["data"]
        assert data["grant_type"] == "refresh_token"
        assert data["refresh_token"] == "refresh-token-123"
        assert data["client_id"] == "client-id"
        assert data["client_secret"] == "client-secret"

    def test_invalid_grant_raises_auth_error_non_retrying(self):
        from src.clients.salesforce import SalesforceClient, SalesforceAuthError

        resp = _make_resp(400, {"error": "invalid_grant", "error_description": "expired token"})

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.post.return_value = resp

            with pytest.raises(SalesforceAuthError):
                with SalesforceClient(**_client_kwargs()):
                    pass

    def test_refresh_429_raises_transient_error(self):
        from src.clients.salesforce import SalesforceClient, SalesforceTransientError

        resp = _make_resp(429, {"error": "rate_limited"})

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.post.return_value = resp

            with pytest.raises(SalesforceTransientError):
                with SalesforceClient(**_client_kwargs()):
                    pass

    def test_refresh_5xx_raises_transient_error(self):
        from src.clients.salesforce import SalesforceClient, SalesforceTransientError

        resp = _make_resp(500, {})

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.post.return_value = resp

            with pytest.raises(SalesforceTransientError):
                with SalesforceClient(**_client_kwargs()):
                    pass

    def test_refresh_updates_instance_url_if_returned(self):
        from src.clients.salesforce import SalesforceClient

        token_resp = _make_token_resp(
            "abc123", instance_url="https://new-instance.my.salesforce.com"
        )

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.post.return_value = token_resp

            with SalesforceClient(**_client_kwargs()) as client:
                assert client._instance_url == "https://new-instance.my.salesforce.com"


# ---------------------------------------------------------------------------
# TestSalesforceClientQueryPagination
# ---------------------------------------------------------------------------


class TestSalesforceClientQueryPagination:
    def test_query_single_page(self):
        from src.clients.salesforce import SalesforceClient

        token_resp = _make_token_resp()
        page = {
            "records": [{"Id": "003xx", "Email": "a@test.com"}],
            "done": True,
        }
        page_resp = _make_resp(200, page)

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.post.return_value = token_resp
            instance.get.return_value = page_resp

            with SalesforceClient(**_client_kwargs()) as client:
                records = client.query("SELECT Id, Email FROM Contact")

        assert len(records) == 1
        assert records[0]["Id"] == "003xx"

    def test_query_follows_next_records_url(self):
        from src.clients.salesforce import SalesforceClient

        token_resp = _make_token_resp()
        page1 = {
            "records": [{"Id": "003xx1"}],
            "done": False,
            "nextRecordsUrl": "/services/data/v60.0/query/01g-2000",
        }
        page2 = {
            "records": [{"Id": "003xx2"}],
            "done": True,
        }
        resp1 = _make_resp(200, page1)
        resp2 = _make_resp(200, page2)

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.post.return_value = token_resp
            instance.get.side_effect = [resp1, resp2]

            with SalesforceClient(**_client_kwargs()) as client:
                records = client.query("SELECT Id FROM Contact")

        assert len(records) == 2
        ids = {r["Id"] for r in records}
        assert ids == {"003xx1", "003xx2"}

        # Second GET call must use the nextRecordsUrl (prefixed with instance_url)
        second_call_url = instance.get.call_args_list[1][0][0]
        assert second_call_url == (
            "https://acme.my.salesforce.com/services/data/v60.0/query/01g-2000"
        )

    def test_query_respects_per_run_page_cap(self, caplog):
        from src.clients.salesforce import SalesforceClient

        original_cap = SalesforceClient.PER_RUN_PAGE_CAP
        SalesforceClient.PER_RUN_PAGE_CAP = 2

        def _page(cursor, has_next=True):
            data = {"records": [{"Id": cursor}], "done": not has_next}
            if has_next:
                data["nextRecordsUrl"] = f"/services/data/v60.0/query/{cursor}"
            return _make_resp(200, data)

        token_resp = _make_token_resp()
        resp1 = _page("c1")
        resp2 = _page("c2")
        resp3 = _page("c3", has_next=False)  # should never be fetched

        try:
            with patch("httpx.Client") as MockHTTP, caplog.at_level("WARNING"):
                instance = MockHTTP.return_value
                instance.post.return_value = token_resp
                instance.get.side_effect = [resp1, resp2, resp3]

                with SalesforceClient(**_client_kwargs()) as client:
                    records = client.query("SELECT Id FROM Contact")

            assert len(records) == 2
            warnings = [r.message for r in caplog.records if r.levelname == "WARNING"]
            assert any("cap" in msg.lower() or "per-run" in msg.lower() for msg in warnings)
        finally:
            SalesforceClient.PER_RUN_PAGE_CAP = original_cap

    def test_query_429_raises_transient_error(self):
        from src.clients.salesforce import SalesforceClient, SalesforceTransientError

        token_resp = _make_token_resp()
        resp_429 = _make_resp(429, {}, headers={"Retry-After": "1"})

        with patch("httpx.Client") as MockHTTP, patch("time.sleep"):
            instance = MockHTTP.return_value
            instance.post.return_value = token_resp
            instance.get.return_value = resp_429

            with pytest.raises(SalesforceTransientError):
                with SalesforceClient(**_client_kwargs()) as client:
                    client.query("SELECT Id FROM Contact")

    def test_query_5xx_raises_transient_error(self):
        from src.clients.salesforce import SalesforceClient, SalesforceTransientError

        token_resp = _make_token_resp()
        resp_500 = _make_resp(500, {})

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.post.return_value = token_resp
            instance.get.return_value = resp_500

            with pytest.raises(SalesforceTransientError):
                with SalesforceClient(**_client_kwargs()) as client:
                    client.query("SELECT Id FROM Contact")

    def test_query_other_error_raises_query_error(self):
        from src.clients.salesforce import SalesforceClient, SalesforceQueryError

        token_resp = _make_token_resp()
        resp_400 = _make_resp(400, [{"message": "malformed query", "errorCode": "MALFORMED_QUERY"}])

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.post.return_value = token_resp
            instance.get.return_value = resp_400

            with pytest.raises(SalesforceQueryError):
                with SalesforceClient(**_client_kwargs()) as client:
                    client.query("SELECT Id FROM Contact WHERE bad syntax")


# ---------------------------------------------------------------------------
# TestSalesforceClientLimitInfo
# ---------------------------------------------------------------------------


class TestSalesforceClientLimitInfo:
    def test_limit_info_logged(self, caplog):
        from src.clients.salesforce import SalesforceClient

        token_resp = _make_token_resp()
        page = _make_resp(
            200,
            {"records": [{"Id": "1"}], "done": True},
            headers={"Sforce-Limit-Info": "api-usage=18000/20000"},
        )

        with patch("httpx.Client") as MockHTTP, caplog.at_level("INFO"):
            instance = MockHTTP.return_value
            instance.post.return_value = token_resp
            instance.get.return_value = page

            with SalesforceClient(**_client_kwargs()) as client:
                client.query("SELECT Id FROM Contact")

        infos = [r.message for r in caplog.records if r.levelname == "INFO"]
        assert any("2000" in msg or "remaining" in msg.lower() for msg in infos)

    def test_limit_near_exhaustion_stops_pagination(self, caplog):
        from src.clients.salesforce import SalesforceClient

        token_resp = _make_token_resp()
        page1 = _make_resp(
            200,
            {
                "records": [{"Id": "1"}],
                "done": False,
                "nextRecordsUrl": "/services/data/v60.0/query/next",
            },
            headers={"Sforce-Limit-Info": "api-usage=19980/20000"},  # remaining=20 <= threshold
        )
        page2 = _make_resp(200, {"records": [{"Id": "2"}], "done": True})

        with patch("httpx.Client") as MockHTTP, caplog.at_level("WARNING"):
            instance = MockHTTP.return_value
            instance.post.return_value = token_resp
            instance.get.side_effect = [page1, page2]

            with SalesforceClient(**_client_kwargs()) as client:
                records = client.query("SELECT Id FROM Contact")

        # Should stop after page1 despite nextRecordsUrl being present.
        assert len(records) == 1
        instance.get.assert_called_once()
        warnings = [r.message for r in caplog.records if r.levelname == "WARNING"]
        assert any("exhaust" in msg.lower() or "limit" in msg.lower() for msg in warnings)


# ---------------------------------------------------------------------------
# TestSalesforceClientTypedHelpers
# ---------------------------------------------------------------------------


class TestSalesforceClientTypedHelpers:
    def test_list_contacts_queries_expected_fields(self):
        from src.clients.salesforce import SalesforceClient

        token_resp = _make_token_resp()
        page = _make_resp(200, {"records": [], "done": True})

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.post.return_value = token_resp
            instance.get.return_value = page

            with SalesforceClient(**_client_kwargs()) as client:
                client.list_contacts()

        params = instance.get.call_args[1]["params"]
        soql = params["q"]
        assert "Contact" in soql
        assert "Email" in soql
        assert "AccountId" in soql

    def test_get_account_returns_first_record(self):
        from src.clients.salesforce import SalesforceClient

        token_resp = _make_token_resp()
        page = _make_resp(
            200,
            {
                "records": [
                    {"Id": "001XX000003DHViQAG", "Name": "Acme Corp", "AnnualRevenue": 100000, "Type": "Customer"}
                ],
                "done": True,
            },
        )

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.post.return_value = token_resp
            instance.get.return_value = page

            with SalesforceClient(**_client_kwargs()) as client:
                account = client.get_account("001XX000003DHViQAG")

        assert account["Name"] == "Acme Corp"
        assert account["AnnualRevenue"] == 100000

    def test_get_account_not_found_returns_none(self):
        from src.clients.salesforce import SalesforceClient

        token_resp = _make_token_resp()
        page = _make_resp(200, {"records": [], "done": True})

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.post.return_value = token_resp
            instance.get.return_value = page

            with SalesforceClient(**_client_kwargs()) as client:
                account = client.get_account("001XX000003NOTFND1")

        assert account is None

    def test_get_open_opportunities_queries_account_id_and_is_closed_filter(self):
        from src.clients.salesforce import SalesforceClient

        token_resp = _make_token_resp()
        page = _make_resp(200, {"records": [], "done": True})

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.post.return_value = token_resp
            instance.get.return_value = page

            with SalesforceClient(**_client_kwargs()) as client:
                client.get_open_opportunities("001XX000003DHViQAG")

        soql = instance.get.call_args[1]["params"]["q"]
        assert "Opportunity" in soql
        assert "001XX000003DHViQAG" in soql
        assert "IsClosed = false" in soql

    def test_get_account_rejects_malformed_id_no_http_call(self):
        """
        SOQL-injection defense-in-depth: a malformed id must be rejected
        BEFORE any HTTP request is made (no query issued at all).
        """
        from src.clients.salesforce import SalesforceClient, SalesforceQueryError

        token_resp = _make_token_resp()

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.post.return_value = token_resp

            with SalesforceClient(**_client_kwargs()) as client:
                with pytest.raises(SalesforceQueryError):
                    client.get_account("x' OR Name!='")

        instance.get.assert_not_called()

    def test_get_open_opportunities_rejects_malformed_id_no_http_call(self):
        """
        SOQL-injection defense-in-depth: a malformed AccountId must be
        rejected BEFORE any HTTP request is made.
        """
        from src.clients.salesforce import SalesforceClient, SalesforceQueryError

        token_resp = _make_token_resp()

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.post.return_value = token_resp

            with SalesforceClient(**_client_kwargs()) as client:
                with pytest.raises(SalesforceQueryError):
                    client.get_open_opportunities("x' OR Name!='")

        instance.get.assert_not_called()


# ---------------------------------------------------------------------------
# Phase 1 (provider-churn-fetch): characterization lock — pins the EXISTING
# get_open_opportunities SOQL + returned records byte-identical before any
# client edit in this aspect.
# ---------------------------------------------------------------------------


class TestOpenOppsCharacterizationLock:
    def test_soql_and_records_unchanged(self):
        from src.clients.salesforce import SalesforceClient

        token_resp = _make_token_resp()
        stub_records = [
            {
                "Id": "006o1",
                "Name": "Open High",
                "StageName": "Negotiation",
                "Amount": 900,
                "CloseDate": "2026-09-01",
                "IsClosed": False,
            }
        ]
        page = _make_resp(200, {"records": stub_records, "done": True})

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.post.return_value = token_resp
            instance.get.return_value = page

            with SalesforceClient(**_client_kwargs()) as client:
                records = client.get_open_opportunities("001xxxxxxxxxxxxxxx")

        soql = instance.get.call_args.kwargs["params"]["q"]
        assert soql == (
            "SELECT Id, Name, StageName, Amount, CloseDate, IsClosed "
            "FROM Opportunity WHERE AccountId = '001xxxxxxxxxxxxxxx' AND IsClosed = false"
        )
        assert records == stub_records
