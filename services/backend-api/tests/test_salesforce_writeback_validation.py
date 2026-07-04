"""
Tests for the backend Salesforce writeback-field validation helper
(salesforce-write-client aspect, Phase 2). Mirrors
test_hubspot_writeback_validation.py's structure and (bool, reason) contract.
"""
from unittest.mock import MagicMock, patch

import httpx
import pytest

from src.services.salesforce_writeback_validation import validate_writeback_field

REFRESH_TOKEN = "5Aep861..."  # noqa: S105 - test fixture value, not a real token
INSTANCE_URL = "https://acme.my.salesforce.com"
FIELD_NAME = "Rereflect_Health_Score__c"

REFRESH_TARGET = "src.api.routes.salesforce_integration._refresh_access_token"
HTTP_CLIENT_TARGET = "src.services.salesforce_writeback_validation.httpx.Client"


def _token_data(access_token="access-token-123", instance_url=INSTANCE_URL):
    return {"access_token": access_token, "instance_url": instance_url}


def _mock_describe_client(resp=None, side_effect=None):
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


def _describe_resp(fields):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"fields": fields}
    resp.raise_for_status = MagicMock()
    return resp


class TestValidateWritebackFieldOk:
    def test_numeric_updateable_field_returns_ok(self):
        fields = [
            {"name": FIELD_NAME, "type": "double", "updateable": True},
            {"name": "Name", "type": "string", "updateable": False},
        ]
        with patch(REFRESH_TARGET, return_value=_token_data()), patch(
            HTTP_CLIENT_TARGET, return_value=_mock_describe_client(resp=_describe_resp(fields))
        ):
            ok, reason = validate_writeback_field(REFRESH_TOKEN, INSTANCE_URL, FIELD_NAME)
        assert ok is True
        assert reason is None

    @pytest.mark.parametrize("field_type", ["double", "int", "currency", "percent"])
    def test_each_numeric_type_returns_ok(self, field_type):
        fields = [{"name": FIELD_NAME, "type": field_type, "updateable": True}]
        with patch(REFRESH_TARGET, return_value=_token_data()), patch(
            HTTP_CLIENT_TARGET, return_value=_mock_describe_client(resp=_describe_resp(fields))
        ):
            ok, reason = validate_writeback_field(REFRESH_TOKEN, INSTANCE_URL, FIELD_NAME)
        assert ok is True
        assert reason is None


class TestValidateWritebackFieldNotFound:
    def test_field_absent_from_describe_returns_field_not_found(self):
        fields = [{"name": "Some_Other_Field__c", "type": "double", "updateable": True}]
        with patch(REFRESH_TARGET, return_value=_token_data()), patch(
            HTTP_CLIENT_TARGET, return_value=_mock_describe_client(resp=_describe_resp(fields))
        ):
            ok, reason = validate_writeback_field(REFRESH_TOKEN, INSTANCE_URL, FIELD_NAME)
        assert ok is False
        assert reason == "field_not_found"


class TestValidateWritebackFieldWrongType:
    def test_not_updateable_returns_wrong_type(self):
        fields = [{"name": FIELD_NAME, "type": "double", "updateable": False}]
        with patch(REFRESH_TARGET, return_value=_token_data()), patch(
            HTTP_CLIENT_TARGET, return_value=_mock_describe_client(resp=_describe_resp(fields))
        ):
            ok, reason = validate_writeback_field(REFRESH_TOKEN, INSTANCE_URL, FIELD_NAME)
        assert ok is False
        assert reason == "wrong_type"

    def test_non_numeric_type_returns_wrong_type(self):
        fields = [{"name": FIELD_NAME, "type": "string", "updateable": True}]
        with patch(REFRESH_TARGET, return_value=_token_data()), patch(
            HTTP_CLIENT_TARGET, return_value=_mock_describe_client(resp=_describe_resp(fields))
        ):
            ok, reason = validate_writeback_field(REFRESH_TOKEN, INSTANCE_URL, FIELD_NAME)
        assert ok is False
        assert reason == "wrong_type"


class TestValidateWritebackFieldMissingScope:
    def test_403_on_describe_returns_missing_write_scope(self):
        with patch(REFRESH_TARGET, return_value=_token_data()), patch(
            HTTP_CLIENT_TARGET,
            return_value=_mock_describe_client(side_effect=_http_status_error(403)),
        ):
            ok, reason = validate_writeback_field(REFRESH_TOKEN, INSTANCE_URL, FIELD_NAME)
        assert ok is False
        assert reason == "missing_write_scope"

    def test_403_on_token_refresh_returns_missing_write_scope(self):
        with patch(REFRESH_TARGET, side_effect=_http_status_error(403)):
            ok, reason = validate_writeback_field(REFRESH_TOKEN, INSTANCE_URL, FIELD_NAME)
        assert ok is False
        assert reason == "missing_write_scope"


class TestValidateWritebackFieldOtherErrors:
    def test_other_http_error_on_describe_returns_validation_error(self):
        with patch(REFRESH_TARGET, return_value=_token_data()), patch(
            HTTP_CLIENT_TARGET,
            return_value=_mock_describe_client(side_effect=_http_status_error(500)),
        ):
            ok, reason = validate_writeback_field(REFRESH_TOKEN, INSTANCE_URL, FIELD_NAME)
        assert ok is False
        assert reason == "validation_error"

    def test_network_error_on_describe_returns_validation_error(self):
        with patch(REFRESH_TARGET, return_value=_token_data()), patch(
            HTTP_CLIENT_TARGET,
            return_value=_mock_describe_client(
                side_effect=httpx.RequestError("boom", request=MagicMock())
            ),
        ):
            ok, reason = validate_writeback_field(REFRESH_TOKEN, INSTANCE_URL, FIELD_NAME)
        assert ok is False
        assert reason == "validation_error"

    def test_other_http_error_on_token_refresh_returns_validation_error(self):
        with patch(REFRESH_TARGET, side_effect=_http_status_error(400)):
            ok, reason = validate_writeback_field(REFRESH_TOKEN, INSTANCE_URL, FIELD_NAME)
        assert ok is False
        assert reason == "validation_error"

    def test_network_error_on_token_refresh_returns_validation_error(self):
        with patch(REFRESH_TARGET, side_effect=httpx.RequestError("boom", request=MagicMock())):
            ok, reason = validate_writeback_field(REFRESH_TOKEN, INSTANCE_URL, FIELD_NAME)
        assert ok is False
        assert reason == "validation_error"

    def test_incomplete_token_response_returns_validation_error(self):
        with patch(REFRESH_TARGET, return_value={"instance_url": INSTANCE_URL}):
            ok, reason = validate_writeback_field(REFRESH_TOKEN, INSTANCE_URL, FIELD_NAME)
        assert ok is False
        assert reason == "validation_error"

    def test_unexpected_exception_never_raises(self):
        with patch(REFRESH_TARGET, side_effect=RuntimeError("boom")):
            ok, reason = validate_writeback_field(REFRESH_TOKEN, INSTANCE_URL, FIELD_NAME)
        assert ok is False
        assert reason == "validation_error"
