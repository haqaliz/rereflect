"""
Tests for the backend HubSpot writeback-field validation helper (Phase 2 of
writeback-config-api). Mirrors the httpx-Bearer GET pattern used by
_validate_hubspot_token in src/api/routes/hubspot_integration.py.
"""
from unittest.mock import MagicMock, patch

import httpx
import pytest

from src.services.hubspot_writeback_validation import validate_writeback_field

TOKEN = "pat-na1-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"


def _mock_client(resp=None, side_effect=None):
    mock_resp = resp
    mock = MagicMock()
    mock.__enter__ = MagicMock(return_value=mock)
    mock.__exit__ = MagicMock(return_value=False)
    if side_effect is not None:
        mock.get = MagicMock(side_effect=side_effect)
    else:
        mock.get = MagicMock(return_value=mock_resp)
    return mock


def _http_status_error(status_code):
    return httpx.HTTPStatusError(
        str(status_code), request=MagicMock(), response=MagicMock(status_code=status_code)
    )


class TestValidateWritebackFieldOk:
    def test_number_writable_field_returns_ok(self):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "name": "rereflect_health_score",
            "type": "number",
            "calculated": False,
            "modificationMetadata": {"readOnlyValue": False},
        }
        resp.raise_for_status = MagicMock()
        with patch(
            "src.services.hubspot_writeback_validation.httpx.Client",
            return_value=_mock_client(resp=resp),
        ):
            ok, reason = validate_writeback_field(TOKEN, "rereflect_health_score")
        assert ok is True
        assert reason is None


class TestValidateWritebackFieldNotFound:
    def test_404_returns_field_not_found(self):
        with patch(
            "src.services.hubspot_writeback_validation.httpx.Client",
            return_value=_mock_client(side_effect=_http_status_error(404)),
        ):
            ok, reason = validate_writeback_field(TOKEN, "nonexistent_field")
        assert ok is False
        assert reason == "field_not_found"


class TestValidateWritebackFieldWrongType:
    def test_string_type_returns_wrong_type(self):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "name": "company_name",
            "type": "string",
            "calculated": False,
            "modificationMetadata": {"readOnlyValue": False},
        }
        resp.raise_for_status = MagicMock()
        with patch(
            "src.services.hubspot_writeback_validation.httpx.Client",
            return_value=_mock_client(resp=resp),
        ):
            ok, reason = validate_writeback_field(TOKEN, "company_name")
        assert ok is False
        assert reason == "wrong_type"


class TestValidateWritebackFieldMissingScope:
    def test_403_returns_missing_write_scope(self):
        with patch(
            "src.services.hubspot_writeback_validation.httpx.Client",
            return_value=_mock_client(side_effect=_http_status_error(403)),
        ):
            ok, reason = validate_writeback_field(TOKEN, "rereflect_health_score")
        assert ok is False
        assert reason == "missing_write_scope"


class TestValidateWritebackFieldOtherErrors:
    def test_other_http_error_returns_validation_error(self):
        with patch(
            "src.services.hubspot_writeback_validation.httpx.Client",
            return_value=_mock_client(side_effect=_http_status_error(500)),
        ):
            ok, reason = validate_writeback_field(TOKEN, "rereflect_health_score")
        assert ok is False
        assert reason == "validation_error"

    def test_network_error_returns_validation_error(self):
        with patch(
            "src.services.hubspot_writeback_validation.httpx.Client",
            return_value=_mock_client(
                side_effect=httpx.RequestError("boom", request=MagicMock())
            ),
        ):
            ok, reason = validate_writeback_field(TOKEN, "rereflect_health_score")
        assert ok is False
        assert reason == "validation_error"
