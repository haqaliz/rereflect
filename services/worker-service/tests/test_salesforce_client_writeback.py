"""
TDD tests for SalesforceClient writeback methods (update_contact_field,
describe_object) — salesforce-write-client aspect.

No real HTTP. Uses unittest.mock.patch on httpx.Client methods.
Mirrors test_salesforce_client.py structure.
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
# TestUpdateContactField
# ---------------------------------------------------------------------------


class TestUpdateContactField:
    def test_patches_correct_url_with_raw_number_body(self):
        from src.clients.salesforce import SalesforceClient

        token_resp = _make_token_resp()
        patch_resp = _make_resp(204)

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.post.return_value = token_resp
            instance.patch.return_value = patch_resp

            with SalesforceClient(**_client_kwargs()) as client:
                result = client.update_contact_field(
                    "003XX000004TmiQQAS", "Rereflect_Health_Score__c", 72
                )

        assert result is None
        call = instance.patch.call_args
        url = call[0][0]
        assert url == (
            "https://acme.my.salesforce.com/services/data/v60.0/"
            "sobjects/Contact/003XX000004TmiQQAS"
        )
        body = call[1]["json"]
        assert body == {"Rereflect_Health_Score__c": 72}
        # Regression guard: value must be a raw number, NOT stringified
        # (unlike HubSpot's _format_number).
        assert isinstance(body["Rereflect_Health_Score__c"], int)

    def test_204_returns_none(self):
        from src.clients.salesforce import SalesforceClient

        token_resp = _make_token_resp()
        patch_resp = _make_resp(204)

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.post.return_value = token_resp
            instance.patch.return_value = patch_resp

            with SalesforceClient(**_client_kwargs()) as client:
                result = client.update_contact_field(
                    "003XX000004TmiQQAS", "Rereflect_Health_Score__c", 72
                )

        assert result is None

    def test_429_raises_transient_error(self):
        from src.clients.salesforce import SalesforceClient, SalesforceTransientError

        token_resp = _make_token_resp()
        patch_resp = _make_resp(429, headers={"Retry-After": "1"})

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.post.return_value = token_resp
            instance.patch.return_value = patch_resp

            with SalesforceClient(**_client_kwargs()) as client:
                with pytest.raises(SalesforceTransientError):
                    client.update_contact_field(
                        "003XX000004TmiQQAS", "Rereflect_Health_Score__c", 72
                    )

    def test_5xx_raises_transient_error(self):
        from src.clients.salesforce import SalesforceClient, SalesforceTransientError

        token_resp = _make_token_resp()
        patch_resp = _make_resp(500)

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.post.return_value = token_resp
            instance.patch.return_value = patch_resp

            with SalesforceClient(**_client_kwargs()) as client:
                with pytest.raises(SalesforceTransientError):
                    client.update_contact_field(
                        "003XX000004TmiQQAS", "Rereflect_Health_Score__c", 72
                    )

    def test_403_raises_scope_error(self):
        from src.clients.salesforce import SalesforceClient, SalesforceScopeError

        token_resp = _make_token_resp()
        patch_resp = _make_resp(403)

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.post.return_value = token_resp
            instance.patch.return_value = patch_resp

            with SalesforceClient(**_client_kwargs()) as client:
                with pytest.raises(SalesforceScopeError):
                    client.update_contact_field(
                        "003XX000004TmiQQAS", "Rereflect_Health_Score__c", 72
                    )

    def test_404_raises_not_found_error(self):
        from src.clients.salesforce import SalesforceClient, SalesforceNotFoundError

        token_resp = _make_token_resp()
        patch_resp = _make_resp(404)

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.post.return_value = token_resp
            instance.patch.return_value = patch_resp

            with SalesforceClient(**_client_kwargs()) as client:
                with pytest.raises(SalesforceNotFoundError):
                    client.update_contact_field(
                        "003XX000004TmiQQAS", "Rereflect_Health_Score__c", 72
                    )

    def test_401_refreshes_once_then_retries(self):
        from src.clients.salesforce import SalesforceClient

        token_resp = _make_token_resp()
        unauthorized_resp = _make_resp(401)
        success_resp = _make_resp(204)

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.post.return_value = token_resp
            instance.patch.side_effect = [unauthorized_resp, success_resp]

            with SalesforceClient(**_client_kwargs()) as client:
                result = client.update_contact_field(
                    "003XX000004TmiQQAS", "Rereflect_Health_Score__c", 72
                )

        assert result is None
        assert instance.patch.call_count == 2
        # Refresh (POST) called once at __enter__ + once more on 401 retry.
        assert instance.post.call_count == 2

    def test_401_still_unauthorized_after_retry_raises_auth_error(self):
        from src.clients.salesforce import SalesforceClient, SalesforceAuthError

        token_resp = _make_token_resp()
        unauthorized_resp = _make_resp(401)

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.post.return_value = token_resp
            instance.patch.return_value = unauthorized_resp

            with SalesforceClient(**_client_kwargs()) as client:
                with pytest.raises(SalesforceAuthError):
                    client.update_contact_field(
                        "003XX000004TmiQQAS", "Rereflect_Health_Score__c", 72
                    )

    def test_invalid_contact_id_rejected_before_any_http_call(self):
        from src.clients.salesforce import SalesforceClient, SalesforceQueryError

        token_resp = _make_token_resp()

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.post.return_value = token_resp

            with SalesforceClient(**_client_kwargs()) as client:
                with pytest.raises(SalesforceQueryError):
                    client.update_contact_field(
                        "x' OR Id!='", "Rereflect_Health_Score__c", 72
                    )

        instance.patch.assert_not_called()


# ---------------------------------------------------------------------------
# TestDescribeObject
# ---------------------------------------------------------------------------


class TestDescribeObject:
    def test_gets_describe_endpoint_and_returns_fields(self):
        from src.clients.salesforce import SalesforceClient

        token_resp = _make_token_resp()
        describe_resp = _make_resp(
            200,
            {
                "fields": [
                    {"name": "Rereflect_Health_Score__c", "type": "double", "updateable": True},
                    {"name": "Name", "type": "string", "updateable": False},
                ]
            },
        )

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.post.return_value = token_resp
            instance.get.return_value = describe_resp

            with SalesforceClient(**_client_kwargs()) as client:
                result = client.describe_object("Contact")

        call = instance.get.call_args
        url = call[0][0]
        assert url == (
            "https://acme.my.salesforce.com/services/data/v60.0/"
            "sobjects/Contact/describe"
        )
        assert len(result["fields"]) == 2
        assert result["fields"][0]["name"] == "Rereflect_Health_Score__c"

    def test_defaults_to_contact_object(self):
        from src.clients.salesforce import SalesforceClient

        token_resp = _make_token_resp()
        describe_resp = _make_resp(200, {"fields": []})

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.post.return_value = token_resp
            instance.get.return_value = describe_resp

            with SalesforceClient(**_client_kwargs()) as client:
                client.describe_object()

        url = instance.get.call_args[0][0]
        assert url.endswith("/sobjects/Contact/describe")

    def test_429_raises_transient_error(self):
        from src.clients.salesforce import SalesforceClient, SalesforceTransientError

        token_resp = _make_token_resp()
        describe_resp = _make_resp(429)

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.post.return_value = token_resp
            instance.get.return_value = describe_resp

            with SalesforceClient(**_client_kwargs()) as client:
                with pytest.raises(SalesforceTransientError):
                    client.describe_object("Contact")

    def test_403_raises_scope_error(self):
        from src.clients.salesforce import SalesforceClient, SalesforceScopeError

        token_resp = _make_token_resp()
        describe_resp = _make_resp(403)

        with patch("httpx.Client") as MockHTTP:
            instance = MockHTTP.return_value
            instance.post.return_value = token_resp
            instance.get.return_value = describe_resp

            with SalesforceClient(**_client_kwargs()) as client:
                with pytest.raises(SalesforceScopeError):
                    client.describe_object("Contact")
