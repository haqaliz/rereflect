"""
Tests for the backend CRM churn-label options seam
(org-config-api-and-ui aspect, Phase 1).

fetch_renewal_options(provider, integration) -> (options, reason) is the
single source of truth shared by the PATCH .../churn-labels validator and
GET .../churn-labels/options. Mirrors the (bool, reason) contract of
services/salesforce_writeback_validation.py / hubspot_writeback_validation.py
— never raises, hand-written fakes injected through one httpx.Client seam
(no real network, no Celery).
"""
import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx
import pytest

from src.services.crm_churn_label_options import fetch_renewal_options

TEST_FERNET_KEY = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="

REFRESH_TARGET = "src.api.routes.salesforce_integration._refresh_access_token"
HUBSPOT_HTTP_CLIENT_TARGET = "src.services.crm_churn_label_options.httpx.Client"
SALESFORCE_HTTP_CLIENT_TARGET = "src.services.crm_churn_label_options.httpx.Client"

INSTANCE_URL = "https://acme.my.salesforce.com"


@pytest.fixture(autouse=True)
def _fernet_key_env():
    with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
        yield


def _hubspot_integration():
    from src.utils.encryption import encrypt_api_key

    return SimpleNamespace(access_token=encrypt_api_key("pat-na1-sentinel"))


def _salesforce_integration():
    from src.utils.encryption import encrypt_api_key

    return SimpleNamespace(
        refresh_token=encrypt_api_key("5Aep861-refresh"),
        instance_url=INSTANCE_URL,
    )


def _mock_http_client(resp=None, side_effect=None):
    mock = MagicMock()
    mock.__enter__ = MagicMock(return_value=mock)
    mock.__exit__ = MagicMock(return_value=False)
    if side_effect is not None:
        mock.get = MagicMock(side_effect=side_effect)
    else:
        mock.get = MagicMock(return_value=resp)
    return mock


def _http_status_error(status_code):
    return httpx.HTTPStatusError(
        str(status_code), request=MagicMock(), response=MagicMock(status_code=status_code)
    )


def _resp(status_code=200, json_data=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.raise_for_status = MagicMock()
    return resp


def _token_data(access_token="access-token-123", instance_url=INSTANCE_URL):
    return {"access_token": access_token, "instance_url": instance_url}


# ──────────────────────────── HubSpot ────────────────────────────────────────


class TestFetchRenewalOptionsHubSpot:
    def test_200_returns_options_from_results(self):
        resp = _resp(
            200,
            {
                "results": [
                    {"id": "default", "label": "Sales Pipeline"},
                    {"id": "12345678", "label": "Renewals"},
                ]
            },
        )
        with patch(HUBSPOT_HTTP_CLIENT_TARGET, return_value=_mock_http_client(resp=resp)):
            options, reason = fetch_renewal_options("hubspot", _hubspot_integration())
        assert reason is None
        assert options == [
            {"id": "default", "label": "Sales Pipeline"},
            {"id": "12345678", "label": "Renewals"},
        ]

    def test_404_returns_empty_list_not_an_error(self):
        with patch(
            HUBSPOT_HTTP_CLIENT_TARGET,
            return_value=_mock_http_client(resp=_resp(404, {})),
        ):
            options, reason = fetch_renewal_options("hubspot", _hubspot_integration())
        assert options == []
        assert reason is None

    def test_403_returns_missing_read_scope(self):
        with patch(
            HUBSPOT_HTTP_CLIENT_TARGET,
            return_value=_mock_http_client(side_effect=_http_status_error(403)),
        ):
            options, reason = fetch_renewal_options("hubspot", _hubspot_integration())
        assert options == []
        assert reason == "missing_read_scope"

    def test_429_returns_options_fetch_failed(self):
        with patch(
            HUBSPOT_HTTP_CLIENT_TARGET,
            return_value=_mock_http_client(side_effect=_http_status_error(429)),
        ):
            options, reason = fetch_renewal_options("hubspot", _hubspot_integration())
        assert options == []
        assert reason == "options_fetch_failed"

    def test_500_returns_options_fetch_failed(self):
        with patch(
            HUBSPOT_HTTP_CLIENT_TARGET,
            return_value=_mock_http_client(side_effect=_http_status_error(500)),
        ):
            options, reason = fetch_renewal_options("hubspot", _hubspot_integration())
        assert options == []
        assert reason == "options_fetch_failed"

    def test_network_error_returns_options_fetch_failed(self):
        with patch(
            HUBSPOT_HTTP_CLIENT_TARGET,
            return_value=_mock_http_client(
                side_effect=httpx.RequestError("boom", request=MagicMock())
            ),
        ):
            options, reason = fetch_renewal_options("hubspot", _hubspot_integration())
        assert options == []
        assert reason == "options_fetch_failed"


# ──────────────────────────── Salesforce ─────────────────────────────────────


class TestFetchRenewalOptionsSalesforce:
    def test_describe_returns_active_picklist_values(self):
        fields = [
            {
                "name": "Type",
                "picklistValues": [
                    {"value": "Renewal", "label": "Renewal", "active": True},
                    {"value": "Existing Business", "label": "Existing Business", "active": True},
                    {"value": "Old Value", "label": "Old Value", "active": False},
                ],
            }
        ]
        with patch(REFRESH_TARGET, return_value=_token_data()), patch(
            SALESFORCE_HTTP_CLIENT_TARGET,
            return_value=_mock_http_client(resp=_resp(200, {"fields": fields})),
        ):
            options, reason = fetch_renewal_options("salesforce", _salesforce_integration())
        assert reason is None
        assert options == [
            {"id": "Renewal", "label": "Renewal"},
            {"id": "Existing Business", "label": "Existing Business"},
        ]

    def test_picklist_value_without_label_falls_back_to_value(self):
        fields = [
            {
                "name": "Type",
                "picklistValues": [{"value": "Renewal", "active": True}],
            }
        ]
        with patch(REFRESH_TARGET, return_value=_token_data()), patch(
            SALESFORCE_HTTP_CLIENT_TARGET,
            return_value=_mock_http_client(resp=_resp(200, {"fields": fields})),
        ):
            options, reason = fetch_renewal_options("salesforce", _salesforce_integration())
        assert reason is None
        assert options == [{"id": "Renewal", "label": "Renewal"}]

    def test_type_field_absent_returns_empty_list_not_an_error(self):
        fields = [{"name": "StageName", "picklistValues": []}]
        with patch(REFRESH_TARGET, return_value=_token_data()), patch(
            SALESFORCE_HTTP_CLIENT_TARGET,
            return_value=_mock_http_client(resp=_resp(200, {"fields": fields})),
        ):
            options, reason = fetch_renewal_options("salesforce", _salesforce_integration())
        assert options == []
        assert reason is None

    def test_403_on_token_refresh_returns_missing_read_scope(self):
        with patch(REFRESH_TARGET, side_effect=_http_status_error(403)):
            options, reason = fetch_renewal_options("salesforce", _salesforce_integration())
        assert options == []
        assert reason == "missing_read_scope"

    def test_403_on_describe_returns_missing_read_scope(self):
        with patch(REFRESH_TARGET, return_value=_token_data()), patch(
            SALESFORCE_HTTP_CLIENT_TARGET,
            return_value=_mock_http_client(side_effect=_http_status_error(403)),
        ):
            options, reason = fetch_renewal_options("salesforce", _salesforce_integration())
        assert options == []
        assert reason == "missing_read_scope"

    def test_network_error_on_token_refresh_returns_options_fetch_failed(self):
        with patch(
            REFRESH_TARGET, side_effect=httpx.RequestError("boom", request=MagicMock())
        ):
            options, reason = fetch_renewal_options("salesforce", _salesforce_integration())
        assert options == []
        assert reason == "options_fetch_failed"

    def test_network_error_on_describe_returns_options_fetch_failed(self):
        with patch(REFRESH_TARGET, return_value=_token_data()), patch(
            SALESFORCE_HTTP_CLIENT_TARGET,
            return_value=_mock_http_client(
                side_effect=httpx.RequestError("boom", request=MagicMock())
            ),
        ):
            options, reason = fetch_renewal_options("salesforce", _salesforce_integration())
        assert options == []
        assert reason == "options_fetch_failed"

    def test_unexpected_exception_never_raises(self):
        with patch(REFRESH_TARGET, side_effect=RuntimeError("boom")):
            options, reason = fetch_renewal_options("salesforce", _salesforce_integration())
        assert options == []
        assert reason == "options_fetch_failed"


class TestFetchRenewalOptionsUnknownProvider:
    def test_unknown_provider_returns_options_fetch_failed(self):
        options, reason = fetch_renewal_options("acme_crm", SimpleNamespace())
        assert options == []
        assert reason == "options_fetch_failed"
