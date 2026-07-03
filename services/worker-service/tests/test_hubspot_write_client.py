"""
TDD tests for the HubSpotClient write surface (src/clients/hubspot.py):

- update_contact_property(contact_id, property_name, value) -> PATCH
- get_contact_property_def(name) -> GET property definition
- HubSpotScopeError (403), HubSpotNotFoundError (404)
- _format_number helper

No real HTTP. Uses unittest.mock.patch on httpx.Client, matching the mocking
style used in tests/test_hubspot_client.py.
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


# ---------------------------------------------------------------------------
# TestUpdateContactProperty
# ---------------------------------------------------------------------------


class TestUpdateContactProperty:
    def test_issues_correct_patch_url_body_and_auth_header(self):
        from src.clients.hubspot import HubSpotClient

        resp = _make_resp(200, {"id": "123"})

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.patch.return_value = resp

            with HubSpotClient("test-token") as client:
                client.update_contact_property("123", "rereflect_health_score", 47)

        # Bearer auth header set on the underlying httpx.Client construction.
        init_kwargs = MockHTTP.call_args.kwargs
        assert init_kwargs["headers"]["Authorization"] == "Bearer test-token"

        patch_call = instance.patch.call_args
        assert patch_call is not None
        url = patch_call[0][0] if patch_call[0] else patch_call.kwargs.get("url")
        assert url == "/crm/v3/objects/contacts/123"

        body = patch_call.kwargs.get("json")
        assert body == {"properties": {"rereflect_health_score": "47"}}

    def test_429_raises_transient_error(self):
        from src.clients.hubspot import HubSpotClient, HubSpotTransientError

        resp = _make_resp(429, headers={"Retry-After": "1"})

        with patch("httpx.Client") as MockHTTP, patch("time.sleep"):
            instance = MockHTTP.return_value
            instance.patch.return_value = resp

            with HubSpotClient("test-token") as client:
                with pytest.raises(HubSpotTransientError):
                    client.update_contact_property("123", "rereflect_health_score", 47)

    def test_500_raises_transient_error(self):
        from src.clients.hubspot import HubSpotClient, HubSpotTransientError

        resp = _make_resp(500)

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.patch.return_value = resp

            with HubSpotClient("test-token") as client:
                with pytest.raises(HubSpotTransientError):
                    client.update_contact_property("123", "rereflect_health_score", 47)

    def test_403_raises_scope_error(self):
        from src.clients.hubspot import HubSpotClient, HubSpotScopeError

        resp = _make_resp(403, {"message": "missing scope"})

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.patch.return_value = resp

            with HubSpotClient("test-token") as client:
                with pytest.raises(HubSpotScopeError):
                    client.update_contact_property("123", "rereflect_health_score", 47)

    def test_404_raises_not_found_error(self):
        from src.clients.hubspot import HubSpotClient, HubSpotNotFoundError

        resp = _make_resp(404, {"message": "contact not found"})

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.patch.return_value = resp

            with HubSpotClient("test-token") as client:
                with pytest.raises(HubSpotNotFoundError):
                    client.update_contact_property("123", "rereflect_health_score", 47)


# ---------------------------------------------------------------------------
# TestGetContactPropertyDef
# ---------------------------------------------------------------------------


class TestGetContactPropertyDef:
    def test_returns_parsed_def_on_200(self):
        from src.clients.hubspot import HubSpotClient

        prop_def = {
            "name": "rereflect_health_score",
            "type": "number",
            "fieldType": "number",
            "calculated": False,
            "readOnlyValue": False,
        }
        resp = _make_resp(200, prop_def)

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.get.return_value = resp

            with HubSpotClient("test-token") as client:
                result = client.get_contact_property_def("rereflect_health_score")

        get_call = instance.get.call_args
        url = get_call[0][0] if get_call[0] else get_call.kwargs.get("url")
        assert url == "/crm/v3/properties/contacts/rereflect_health_score"

        assert result is not None
        assert result["type"] == "number"
        assert result["fieldType"] == "number"
        assert result["calculated"] is False
        assert result["readOnlyValue"] is False

    def test_returns_none_on_404(self):
        from src.clients.hubspot import HubSpotClient

        resp = _make_resp(404)

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.get.return_value = resp

            with HubSpotClient("test-token") as client:
                result = client.get_contact_property_def("does_not_exist")

        assert result is None

    def test_429_raises_transient_error(self):
        from src.clients.hubspot import HubSpotClient, HubSpotTransientError

        resp = _make_resp(429, headers={"Retry-After": "1"})

        with patch("httpx.Client") as MockHTTP, patch("time.sleep"):
            instance = MockHTTP.return_value
            instance.get.return_value = resp

            with HubSpotClient("test-token") as client:
                with pytest.raises(HubSpotTransientError):
                    client.get_contact_property_def("rereflect_health_score")

    def test_500_raises_transient_error(self):
        from src.clients.hubspot import HubSpotClient, HubSpotTransientError

        resp = _make_resp(500)

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.get.return_value = resp

            with HubSpotClient("test-token") as client:
                with pytest.raises(HubSpotTransientError):
                    client.get_contact_property_def("rereflect_health_score")

    def test_403_raises_scope_error(self):
        from src.clients.hubspot import HubSpotClient, HubSpotScopeError

        resp = _make_resp(403)

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.get.return_value = resp

            with HubSpotClient("test-token") as client:
                with pytest.raises(HubSpotScopeError):
                    client.get_contact_property_def("rereflect_health_score")

    def test_result_flags_non_number_or_calculated_or_readonly_as_rejectable(self):
        """
        The def dict must expose enough for a caller to reject fields that are
        not a writable `number` property (e.g. a `calculation` fieldType, or a
        readOnlyValue prop).
        """
        from src.clients.hubspot import HubSpotClient

        calculated_prop = {
            "name": "days_since_contact",
            "type": "number",
            "fieldType": "calculation",
            "calculated": True,
            "readOnlyValue": True,
        }
        resp = _make_resp(200, calculated_prop)

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.get.return_value = resp

            with HubSpotClient("test-token") as client:
                result = client.get_contact_property_def("days_since_contact")

        assert result["fieldType"] == "calculation"
        assert result["calculated"] is True
        assert result["readOnlyValue"] is True


# ---------------------------------------------------------------------------
# TestFormatNumber
# ---------------------------------------------------------------------------


class TestFormatNumber:
    def test_none_raises(self):
        from src.clients.hubspot import _format_number

        with pytest.raises(Exception):
            _format_number(None)

    def test_int_stringifies(self):
        from src.clients.hubspot import _format_number

        assert _format_number(47) == "47"

    def test_float_stringifies(self):
        from src.clients.hubspot import _format_number

        assert _format_number(47.5) == "47.5"
