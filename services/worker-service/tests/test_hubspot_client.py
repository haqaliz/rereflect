"""
TDD tests for HubSpotClient (src/clients/hubspot.py).

No real HTTP. Uses unittest.mock.patch on httpx.Client methods.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_resp(status_code: int = 200, json_data: dict = None, headers: dict = None) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.headers = headers or {}
    if status_code >= 400:
        from httpx import HTTPStatusError, Request, Response
        resp.raise_for_status.side_effect = HTTPStatusError(
            f"HTTP {status_code}",
            request=MagicMock(),
            response=MagicMock(status_code=status_code),
        )
    else:
        resp.raise_for_status = MagicMock()
    return resp


# ---------------------------------------------------------------------------
# TestHubSpotClientPagination
# ---------------------------------------------------------------------------


class TestHubSpotClientPagination:
    def test_list_contacts_single_page(self):
        """Single-page response (no paging key) returns that page's contacts."""
        from src.clients.hubspot import HubSpotClient

        page_data = {
            "results": [
                {"id": "1", "properties": {"email": "a@test.com"}},
            ],
            # no "paging" key → no next page
        }
        mock_resp = _make_resp(200, page_data)

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.get.return_value = mock_resp

            with HubSpotClient("test-token") as client:
                contacts = client.list_contacts()

        assert len(contacts) == 1
        assert contacts[0]["id"] == "1"

    def test_list_contacts_multi_page(self):
        """Multi-page response accumulates contacts from all pages."""
        from src.clients.hubspot import HubSpotClient

        page1 = {
            "results": [{"id": "1", "properties": {"email": "a@test.com"}}],
            "paging": {"next": {"after": "cursor-abc"}},
        }
        page2 = {
            "results": [{"id": "2", "properties": {"email": "b@test.com"}}],
            # no next page
        }

        resp1 = _make_resp(200, page1)
        resp2 = _make_resp(200, page2)

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.get.side_effect = [resp1, resp2]

            with HubSpotClient("test-token") as client:
                contacts = client.list_contacts()

        assert len(contacts) == 2
        ids = {c["id"] for c in contacts}
        assert ids == {"1", "2"}

    def test_list_contacts_respects_per_run_cap(self, caplog):
        """Pagination stops at PER_RUN_PAGE_CAP and emits a WARNING."""
        from src.clients.hubspot import HubSpotClient

        original_cap = HubSpotClient.PER_RUN_PAGE_CAP
        HubSpotClient.PER_RUN_PAGE_CAP = 2

        def _page_with_cursor(cursor="next"):
            return {
                "results": [{"id": cursor, "properties": {"email": f"{cursor}@test.com"}}],
                "paging": {"next": {"after": f"cursor-{cursor}"}},
            }

        page1 = _page_with_cursor("1")
        page2 = _page_with_cursor("2")
        page3 = _page_with_cursor("3")  # should never be fetched

        resp1 = _make_resp(200, page1)
        resp2 = _make_resp(200, page2)
        resp3 = _make_resp(200, page3)

        try:
            with patch("httpx.Client") as MockHTTP, \
                 caplog.at_level("WARNING"):
                instance = MockHTTP.return_value
                instance.get.side_effect = [resp1, resp2, resp3]

                with HubSpotClient("test-token") as client:
                    contacts = client.list_contacts()

            # Should have stopped after 2 pages (cap=2)
            assert len(contacts) == 2
            # Warning must be emitted
            warning_msgs = [r.message for r in caplog.records if r.levelname == "WARNING"]
            assert any("cap" in msg.lower() or "per-run" in msg.lower() for msg in warning_msgs)
        finally:
            HubSpotClient.PER_RUN_PAGE_CAP = original_cap


# ---------------------------------------------------------------------------
# TestHubSpotClient429
# ---------------------------------------------------------------------------


class TestHubSpotClient429:
    def test_429_raises_transient_error(self):
        """HTTP 429 causes HubSpotTransientError to be raised."""
        from src.clients.hubspot import HubSpotClient, HubSpotTransientError

        resp_429 = MagicMock()
        resp_429.status_code = 429
        resp_429.headers = {"Retry-After": "1"}

        with patch("httpx.Client") as MockHTTP, \
             patch("time.sleep"):
            instance = MockHTTP.return_value
            instance.get.return_value = resp_429

            with pytest.raises(HubSpotTransientError):
                with HubSpotClient("test-token") as client:
                    client.list_contacts()

    def test_429_honors_retry_after_header(self):
        """time.sleep is called with the Retry-After value."""
        from src.clients.hubspot import HubSpotClient, HubSpotTransientError

        resp_429 = MagicMock()
        resp_429.status_code = 429
        resp_429.headers = {"Retry-After": "7"}

        with patch("httpx.Client") as MockHTTP, \
             patch("time.sleep") as mock_sleep:
            instance = MockHTTP.return_value
            instance.get.return_value = resp_429

            with pytest.raises(HubSpotTransientError):
                with HubSpotClient("test-token") as client:
                    client.list_contacts()

        mock_sleep.assert_called_once_with(7)

    def test_5xx_raises_transient_error(self):
        """HTTP 5xx raises HubSpotTransientError."""
        from src.clients.hubspot import HubSpotClient, HubSpotTransientError

        resp_500 = MagicMock()
        resp_500.status_code = 500
        resp_500.headers = {}

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.get.return_value = resp_500

            with pytest.raises(HubSpotTransientError):
                with HubSpotClient("test-token") as client:
                    client.list_contacts()


# ---------------------------------------------------------------------------
# TestHubSpotClientGetCompany
# ---------------------------------------------------------------------------


class TestHubSpotClientGetCompany:
    def test_get_company_returns_name_and_arr(self):
        """Company dict contains name and annualrevenue."""
        from src.clients.hubspot import HubSpotClient

        company_data = {
            "id": "co1",
            "properties": {
                "name": "Acme Corp",
                "annualrevenue": "100000",
            },
        }
        resp = _make_resp(200, company_data)

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.get.return_value = resp

            with HubSpotClient("test-token") as client:
                result = client.get_company("co1")

        assert result["name"] == "Acme Corp"
        assert result["annualrevenue"] == "100000"

    def test_get_company_custom_arr_property(self):
        """Client initialized with custom arr_property_name requests that property."""
        from src.clients.hubspot import HubSpotClient

        company_data = {
            "id": "co1",
            "properties": {
                "name": "Acme Corp",
                "mrr": "5000",
            },
        }
        resp = _make_resp(200, company_data)

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.get.return_value = resp

            with HubSpotClient("test-token", arr_property_name="mrr") as client:
                result = client.get_company("co1")

        # Verify the correct property was requested in the URL
        call_kwargs = instance.get.call_args
        url = call_kwargs[0][0] if call_kwargs[0] else call_kwargs[1].get("url", "")
        params = call_kwargs[1].get("params", {}) if call_kwargs[1] else {}
        assert "mrr" in str(params) or "mrr" in str(url)

    def test_get_company_not_found_returns_none(self):
        """HTTP 404 returns None (no raise)."""
        from src.clients.hubspot import HubSpotClient

        resp_404 = MagicMock()
        resp_404.status_code = 404
        resp_404.headers = {}

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.get.return_value = resp_404

            with HubSpotClient("test-token") as client:
                result = client.get_company("missing-id")

        assert result is None


# ---------------------------------------------------------------------------
# TestHubSpotClientGetDeals
# ---------------------------------------------------------------------------


class TestHubSpotClientGetDeals:
    """
    Tests for get_open_deals_for_company.

    The correct implementation MUST:
      1. Call GET /crm/v3/objects/companies/{company_id}/associations/deals
         so that company_id scopes the request (not a global deal scan).
      2. Fetch deal properties only for the associated IDs
         (POST /crm/v3/objects/deals/batch/read).
      3. Filter open stages client-side (exclude closedwon / closedlost).
    """

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _assoc_resp(self, deal_ids: list, next_after: str = None):
        """Build a mock associations-endpoint response."""
        data = {
            "results": [{"id": did, "type": "company_to_deal"} for did in deal_ids]
        }
        if next_after:
            data["paging"] = {"next": {"after": next_after}}
        return _make_resp(200, data)

    def _batch_resp(self, deals: list):
        """Build a mock batch/read response."""
        return _make_resp(200, {"results": deals, "status": "COMPLETE"})

    # ------------------------------------------------------------------
    # RED-first: must fail against the old buggy code which calls
    # GET /crm/v3/objects/deals (all portal deals) instead of the
    # company-scoped associations endpoint.
    # ------------------------------------------------------------------

    def test_associations_endpoint_called_with_company_id(self):
        """
        company_id MUST appear in the GET request path via the associations
        endpoint (/crm/v3/objects/companies/{company_id}/associations/deals).

        FAILS against old code which calls /crm/v3/objects/deals with no
        company scoping at all.
        """
        from src.clients.hubspot import HubSpotClient

        # Associations endpoint returns no deals — short-circuit after step 1.
        assoc_resp = self._assoc_resp([])

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.get.return_value = assoc_resp

            with HubSpotClient("test-token") as client:
                client.get_open_deals_for_company("co1")

        get_calls = instance.get.call_args_list
        called_urls = [str(c[0][0]) for c in get_calls]
        assert any("companies/co1/associations/deals" in url for url in called_urls), (
            f"Expected 'companies/co1/associations/deals' in a GET URL, got: {called_urls}"
        )

    def test_get_open_deals_returns_only_open(self):
        """Closed deals (closedwon/closedlost) are not returned."""
        from src.clients.hubspot import HubSpotClient

        assoc_resp = self._assoc_resp(["d1", "d2", "d3"])
        batch_resp = self._batch_resp([
            {
                "id": "d1",
                "properties": {
                    "dealstage": "closedwon",
                    "amount": "10000",
                    "closedate": "2026-01-01T00:00:00Z",
                    "dealname": "Won Deal",
                },
            },
            {
                "id": "d2",
                "properties": {
                    "dealstage": "contractsent",
                    "amount": "5000",
                    "closedate": "2026-09-01T00:00:00Z",
                    "dealname": "Open Deal",
                },
            },
            {
                "id": "d3",
                "properties": {
                    "dealstage": "closedlost",
                    "amount": "3000",
                    "closedate": "2026-02-01T00:00:00Z",
                    "dealname": "Lost Deal",
                },
            },
        ])

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.get.return_value = assoc_resp
            instance.post.return_value = batch_resp

            with HubSpotClient("test-token") as client:
                deals = client.get_open_deals_for_company("co1")

        assert len(deals) == 1
        assert deals[0]["id"] == "d2"

    def test_get_open_deals_empty(self):
        """No associated deals returns an empty list; batch read is never called."""
        from src.clients.hubspot import HubSpotClient

        assoc_resp = self._assoc_resp([])

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.get.return_value = assoc_resp

            with HubSpotClient("test-token") as client:
                deals = client.get_open_deals_for_company("co1")

        assert deals == []
        # No POST (batch read) should be issued when there are no deal IDs.
        instance.post.assert_not_called()

    def test_different_company_deals_not_returned(self):
        """
        Only deals associated with company 'co1' are returned.
        Deal 'd2' (belonging to co2) is never requested and must not appear.

        FAILS against old code which fetches all portal deals and would
        include d2 if co2's deals happened to be open.
        """
        from src.clients.hubspot import HubSpotClient

        # co1's associations: only deal "d1"
        co1_assoc_resp = self._assoc_resp(["d1"])
        batch_resp = self._batch_resp([
            {
                "id": "d1",
                "properties": {
                    "dealstage": "contractsent",
                    "amount": "5000",
                    "closedate": "2026-09-01T00:00:00Z",
                    "dealname": "co1 Deal",
                },
            },
        ])

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.get.return_value = co1_assoc_resp
            instance.post.return_value = batch_resp

            with HubSpotClient("test-token") as client:
                deals = client.get_open_deals_for_company("co1")

        # Only co1's deal is returned.
        assert len(deals) == 1
        assert deals[0]["id"] == "d1"

        # Batch read only requested "d1", not "d2" (co2's deal).
        post_call = instance.post.call_args
        assert post_call is not None, "Expected a batch/read POST call"
        # Support both positional and keyword json arg
        body = (
            post_call[1].get("json")
            or (post_call[0][1] if len(post_call[0]) > 1 else {})
        ) or {}
        requested_ids = {inp["id"] for inp in body.get("inputs", [])}
        assert "d1" in requested_ids
        assert "d2" not in requested_ids


# ---------------------------------------------------------------------------
# Phase 1 (provider-churn-fetch): characterization lock — pins the EXISTING
# get_open_deals_for_company output byte-identical before any client edit.
# ---------------------------------------------------------------------------


class TestOpenDealsCharacterizationLock:
    def test_get_open_deals_returns_exact_list_same_order(self):
        """Fixed 4-deal payload (open-high, open-low, closedwon, closedlost):
        get_open_deals_for_company must return exactly [d1, d2], in order,
        with the same dicts — untouched by this aspect's later phases."""
        from src.clients.hubspot import HubSpotClient

        d1 = {
            "id": "d1",
            "properties": {
                "dealname": "Open High",
                "dealstage": "contractsent",
                "amount": "900",
                "closedate": "2026-09-01T00:00:00Z",
            },
        }
        d2 = {
            "id": "d2",
            "properties": {
                "dealname": "Open Low",
                "dealstage": "appointmentscheduled",
                "amount": "100",
                "closedate": "2026-08-01T00:00:00Z",
            },
        }
        d3 = {
            "id": "d3",
            "properties": {
                "dealname": "Won Big",
                "dealstage": "closedwon",
                "amount": "5000",
                "closedate": "2026-05-01T00:00:00Z",
            },
        }
        d4 = {
            "id": "d4",
            "properties": {
                "dealname": "Lost Big",
                "dealstage": "closedlost",
                "amount": "4000",
                "closedate": "2026-01-15T00:00:00Z",
            },
        }

        assoc_resp = _make_resp(
            200,
            {"results": [{"id": did, "type": "company_to_deal"} for did in ["d1", "d2", "d3", "d4"]]},
        )
        batch_resp = _make_resp(200, {"results": [d1, d2, d3, d4], "status": "COMPLETE"})

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.get.return_value = assoc_resp
            instance.post.return_value = batch_resp

            with HubSpotClient("test-token") as client:
                deals = client.get_open_deals_for_company("c1")

        assert deals == [d1, d2]


# ---------------------------------------------------------------------------
# Phase 5 (provider-churn-fetch): HubSpotClient.get_closed_lost_deals_for_company
# ---------------------------------------------------------------------------


class TestGetClosedLostDealsForCompany:
    _D1 = {
        "id": "d1",
        "properties": {
            "dealname": "Open High",
            "dealstage": "contractsent",
            "amount": "900",
            "closedate": "2026-09-01T00:00:00Z",
        },
    }
    _D2 = {
        "id": "d2",
        "properties": {
            "dealname": "Open Low",
            "dealstage": "appointmentscheduled",
            "amount": "100",
            "closedate": "2026-08-01T00:00:00Z",
        },
    }
    _D3 = {
        "id": "d3",
        "properties": {
            "dealname": "Won Big",
            "dealstage": "closedwon",
            "amount": "5000",
            "closedate": "2026-05-01T00:00:00Z",
        },
    }
    _D4 = {
        "id": "d4",
        "properties": {
            "dealname": "Lost Big",
            "dealstage": "closedlost",
            "amount": "4000",
            "closedate": "2026-01-15T00:00:00Z",
        },
    }

    def _mock_transport(self, deals):
        assoc_resp = _make_resp(
            200,
            {"results": [{"id": d["id"], "type": "company_to_deal"} for d in deals]},
        )
        batch_resp = _make_resp(200, {"results": deals, "status": "COMPLETE"})
        return assoc_resp, batch_resp

    def test_returns_only_closedlost_deals(self):
        from src.clients.hubspot import HubSpotClient

        deals = [self._D1, self._D2, self._D3, self._D4]
        assoc_resp, batch_resp = self._mock_transport(deals)

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.get.return_value = assoc_resp
            instance.post.return_value = batch_resp

            with HubSpotClient("test-token") as client:
                lost = client.get_closed_lost_deals_for_company("c1")

        assert lost == [self._D4]

    def test_disjoint_with_open_deals(self):
        from src.clients.hubspot import HubSpotClient

        deals = [self._D1, self._D2, self._D3, self._D4]
        assoc_resp, batch_resp = self._mock_transport(deals)

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.get.return_value = assoc_resp
            instance.post.return_value = batch_resp

            with HubSpotClient("test-token") as client:
                open_deals = client.get_open_deals_for_company("c1")

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.get.return_value = assoc_resp
            instance.post.return_value = batch_resp

            with HubSpotClient("test-token") as client:
                lost_deals = client.get_closed_lost_deals_for_company("c1")

        open_ids = {d["id"] for d in open_deals}
        lost_ids = {d["id"] for d in lost_deals}
        assert open_ids & lost_ids == set()
        assert "d4" in lost_ids

    def test_404_on_associations_returns_empty_list(self):
        from src.clients.hubspot import HubSpotClient

        assoc_404 = MagicMock()
        assoc_404.status_code = 404
        assoc_404.headers = {}

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.get.return_value = assoc_404

            with HubSpotClient("test-token") as client:
                lost = client.get_closed_lost_deals_for_company("c1")

        assert lost == []
        instance.post.assert_not_called()

    def test_429_on_associations_raises_transient(self):
        from src.clients.hubspot import HubSpotClient, HubSpotTransientError

        resp_429 = MagicMock()
        resp_429.status_code = 429
        resp_429.headers = {"Retry-After": "1"}

        with patch("httpx.Client") as MockHTTP, patch("time.sleep"):
            instance = MockHTTP.return_value
            instance.get.return_value = resp_429

            with pytest.raises(HubSpotTransientError):
                with HubSpotClient("test-token") as client:
                    client.get_closed_lost_deals_for_company("c1")

    def test_429_on_batch_read_raises_transient(self):
        from src.clients.hubspot import HubSpotClient, HubSpotTransientError

        assoc_resp = self._mock_transport([self._D4])[0]
        resp_429 = MagicMock()
        resp_429.status_code = 429
        resp_429.headers = {"Retry-After": "1"}

        with patch("httpx.Client") as MockHTTP, patch("time.sleep"):
            instance = MockHTTP.return_value
            instance.get.return_value = assoc_resp
            instance.post.return_value = resp_429

            with pytest.raises(HubSpotTransientError):
                with HubSpotClient("test-token") as client:
                    client.get_closed_lost_deals_for_company("c1")


# ---------------------------------------------------------------------------
# Phase 2 (historical-backfill): since-floor on get_closed_lost_deals_for_company
# ---------------------------------------------------------------------------


class TestGetClosedLostDealsSinceFloor:
    _OLD = {
        "id": "d-old",
        "properties": {
            "dealname": "Old Lost",
            "dealstage": "closedlost",
            "amount": "500",
            "closedate": "2024-01-15T00:00:00Z",
        },
    }
    _NEW = {
        "id": "d-new",
        "properties": {
            "dealname": "New Lost",
            "dealstage": "closedlost",
            "amount": "700",
            "closedate": "2026-06-15T00:00:00Z",
        },
    }

    def _mock_transport(self, deals):
        assoc_resp = _make_resp(
            200,
            {"results": [{"id": d["id"], "type": "company_to_deal"} for d in deals]},
        )
        batch_resp = _make_resp(200, {"results": deals, "status": "COMPLETE"})
        return assoc_resp, batch_resp

    def test_since_none_returns_all_closed_lost_deals(self):
        """Default (since=None) preserves today's behavior — no filtering."""
        from src.clients.hubspot import HubSpotClient

        deals = [self._OLD, self._NEW]
        assoc_resp, batch_resp = self._mock_transport(deals)

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.get.return_value = assoc_resp
            instance.post.return_value = batch_resp

            with HubSpotClient("test-token") as client:
                lost = client.get_closed_lost_deals_for_company("c1")

        assert {d["id"] for d in lost} == {"d-old", "d-new"}

    def test_since_floor_excludes_deals_closed_before_floor(self):
        from datetime import datetime

        from src.clients.hubspot import HubSpotClient

        deals = [self._OLD, self._NEW]
        assoc_resp, batch_resp = self._mock_transport(deals)

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.get.return_value = assoc_resp
            instance.post.return_value = batch_resp

            with HubSpotClient("test-token") as client:
                lost = client.get_closed_lost_deals_for_company(
                    "c1", since=datetime(2025, 1, 1)
                )

        assert {d["id"] for d in lost} == {"d-new"}

    def test_since_floor_includes_deal_closed_exactly_at_floor(self):
        from datetime import datetime

        from src.clients.hubspot import HubSpotClient

        deals = [self._NEW]
        assoc_resp, batch_resp = self._mock_transport(deals)

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.get.return_value = assoc_resp
            instance.post.return_value = batch_resp

            with HubSpotClient("test-token") as client:
                lost = client.get_closed_lost_deals_for_company(
                    "c1", since=datetime(2026, 6, 15, 0, 0, 0)
                )

        assert {d["id"] for d in lost} == {"d-new"}


# ---------------------------------------------------------------------------
# Phase 6 (provider-churn-fetch): request `pipeline` on both deal accessors
# ---------------------------------------------------------------------------


class TestDealPipelineProperty:
    def test_open_deals_batch_read_requests_pipeline(self):
        from src.clients.hubspot import HubSpotClient

        assoc_resp = _make_resp(200, {"results": [{"id": "d1"}]})
        batch_resp = _make_resp(200, {"results": [], "status": "COMPLETE"})

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.get.return_value = assoc_resp
            instance.post.return_value = batch_resp

            with HubSpotClient("test-token") as client:
                client.get_open_deals_for_company("c1")

        body = instance.post.call_args.kwargs["json"]
        assert body["properties"] == ["dealname", "dealstage", "amount", "closedate", "pipeline"]

    def test_closed_lost_deals_batch_read_requests_pipeline(self):
        from src.clients.hubspot import HubSpotClient

        assoc_resp = _make_resp(200, {"results": [{"id": "d1"}]})
        batch_resp = _make_resp(200, {"results": [], "status": "COMPLETE"})

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.get.return_value = assoc_resp
            instance.post.return_value = batch_resp

            with HubSpotClient("test-token") as client:
                client.get_closed_lost_deals_for_company("c1")

        body = instance.post.call_args.kwargs["json"]
        assert body["properties"] == ["dealname", "dealstage", "amount", "closedate", "pipeline"]

    def test_deal_with_none_pipeline_returned_unaltered(self):
        from src.clients.hubspot import HubSpotClient

        deal = {
            "id": "d1",
            "properties": {
                "dealname": "Open High",
                "dealstage": "contractsent",
                "amount": "900",
                "closedate": "2026-09-01T00:00:00Z",
                "pipeline": None,
            },
        }
        assoc_resp = _make_resp(200, {"results": [{"id": "d1"}]})
        batch_resp = _make_resp(200, {"results": [deal], "status": "COMPLETE"})

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.get.return_value = assoc_resp
            instance.post.return_value = batch_resp

            with HubSpotClient("test-token") as client:
                deals = client.get_open_deals_for_company("c1")

        assert deals == [deal]

    def test_deal_with_pipeline_key_absent_returned_unaltered(self):
        from src.clients.hubspot import HubSpotClient

        deal = {
            "id": "d1",
            "properties": {
                "dealname": "Open High",
                "dealstage": "contractsent",
                "amount": "900",
                "closedate": "2026-09-01T00:00:00Z",
                # no "pipeline" key at all
            },
        }
        assoc_resp = _make_resp(200, {"results": [{"id": "d1"}]})
        batch_resp = _make_resp(200, {"results": [deal], "status": "COMPLETE"})

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.get.return_value = assoc_resp
            instance.post.return_value = batch_resp

            with HubSpotClient("test-token") as client:
                deals = client.get_open_deals_for_company("c1")

        assert deals == [deal]


# ---------------------------------------------------------------------------
# Phase 7 (provider-churn-fetch): HubSpotClient.list_deal_pipelines
# ---------------------------------------------------------------------------


class TestListDealPipelines:
    def test_returns_parsed_results(self):
        from src.clients.hubspot import HubSpotClient

        pipelines_data = {
            "results": [
                {
                    "id": "default",
                    "label": "Sales Pipeline",
                    "stages": [{"id": "appointmentscheduled", "label": "Appointment Scheduled"}],
                }
            ]
        }
        resp = _make_resp(200, pipelines_data)

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.get.return_value = resp

            with HubSpotClient("test-token") as client:
                pipelines = client.list_deal_pipelines()

        assert pipelines == pipelines_data["results"]
        called_url = instance.get.call_args[0][0]
        assert called_url == "/crm/v3/pipelines/deals"

    def test_404_returns_empty_list(self):
        from src.clients.hubspot import HubSpotClient

        resp_404 = MagicMock()
        resp_404.status_code = 404
        resp_404.headers = {}

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.get.return_value = resp_404

            with HubSpotClient("test-token") as client:
                pipelines = client.list_deal_pipelines()

        assert pipelines == []

    def test_403_raises_scope_error(self):
        from src.clients.hubspot import HubSpotClient, HubSpotScopeError

        resp_403 = MagicMock()
        resp_403.status_code = 403
        resp_403.headers = {}

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.get.return_value = resp_403

            with pytest.raises(HubSpotScopeError):
                with HubSpotClient("test-token") as client:
                    client.list_deal_pipelines()

    def test_429_with_retry_after_sleeps_and_raises_transient(self):
        from src.clients.hubspot import HubSpotClient, HubSpotTransientError

        resp_429 = MagicMock()
        resp_429.status_code = 429
        resp_429.headers = {"Retry-After": "7"}

        with patch("httpx.Client") as MockHTTP, patch("time.sleep") as mock_sleep:
            instance = MockHTTP.return_value
            instance.get.return_value = resp_429

            with pytest.raises(HubSpotTransientError):
                with HubSpotClient("test-token") as client:
                    client.list_deal_pipelines()

        mock_sleep.assert_called_once_with(7)

    def test_429_without_retry_after_defaults_to_10(self):
        from src.clients.hubspot import HubSpotClient, HubSpotTransientError

        resp_429 = MagicMock()
        resp_429.status_code = 429
        resp_429.headers = {}

        with patch("httpx.Client") as MockHTTP, patch("time.sleep") as mock_sleep:
            instance = MockHTTP.return_value
            instance.get.return_value = resp_429

            with pytest.raises(HubSpotTransientError):
                with HubSpotClient("test-token") as client:
                    client.list_deal_pipelines()

        mock_sleep.assert_called_once_with(10)

    @pytest.mark.parametrize("status", [500, 503])
    def test_5xx_raises_transient_without_sleep(self, status):
        from src.clients.hubspot import HubSpotClient, HubSpotTransientError

        resp = MagicMock()
        resp.status_code = status
        resp.headers = {}

        with patch("httpx.Client") as MockHTTP, patch("time.sleep") as mock_sleep:
            instance = MockHTTP.return_value
            instance.get.return_value = resp

            with pytest.raises(HubSpotTransientError):
                with HubSpotClient("test-token") as client:
                    client.list_deal_pipelines()

        mock_sleep.assert_not_called()


# ---------------------------------------------------------------------------
# Phase 8 (provider-churn-fetch): token & is_active safety sweep
# ---------------------------------------------------------------------------


class TestNewClientCallsNeverLeakTokenOrTouchIsActive:
    TOKEN = "s3cr3t"

    def _drive_all_new_methods(self, resp):
        from src.clients.hubspot import HubSpotClient

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.get.return_value = resp
            instance.post.return_value = resp

            with HubSpotClient(self.TOKEN) as client:
                for fn in (
                    lambda: client.get_closed_lost_deals_for_company("c1"),
                    lambda: client.list_deal_pipelines(),
                ):
                    try:
                        fn()
                    except Exception:
                        pass

    @pytest.mark.parametrize("status", [200, 429, 403, 404, 500])
    def test_token_never_appears_in_logs(self, status, caplog):
        resp = MagicMock()
        resp.status_code = status
        resp.headers = {"Retry-After": "1"} if status == 429 else {}
        resp.json.return_value = {"results": []}

        with caplog.at_level(logging.DEBUG), patch("time.sleep"):
            self._drive_all_new_methods(resp)

        assert self.TOKEN not in caplog.text

    def test_token_never_in_repr_or_str(self):
        from src.clients.hubspot import HubSpotClient

        with patch("httpx.Client"):
            client = HubSpotClient(self.TOKEN)

        assert self.TOKEN not in repr(client)
        assert self.TOKEN not in str(client)

    def test_no_new_method_references_is_active(self):
        src_path = Path(__file__).resolve().parents[1] / "src" / "clients" / "hubspot.py"
        content = src_path.read_text()
        assert "is_active" not in content
