"""Tests for Email adapter."""

import sys
from unittest.mock import patch, MagicMock

import pytest

# Pre-mock the email_parser module that email adapter imports from backend-api.
# The actual module doesn't exist in the worker-service's path during testing.
_mock_email_parser = MagicMock()
sys.modules.setdefault("services", MagicMock())
sys.modules.setdefault("services.email_parser", _mock_email_parser)

from src.adapters.email import EmailAdapter


@pytest.fixture
def adapter():
    return EmailAdapter()


class TestCheckTriggers:
    """Email adapter should accept all emails (no trigger filtering for v1)."""

    def test_returns_all_emails_for_any_event(self, adapter):
        result = adapter.check_triggers(
            "email.inbound",
            {"to": "feedback-abc@rereflect.ca", "subject": "Help me"},
            {},
        )
        assert result == "all_emails"

    def test_returns_all_emails_with_empty_triggers(self, adapter):
        result = adapter.check_triggers(
            "email.inbound",
            {"to": "feedback-abc@rereflect.ca"},
            {"all_emails": True},
        )
        assert result == "all_emails"

    def test_returns_all_emails_regardless_of_event_type(self, adapter):
        result = adapter.check_triggers(
            "some.other.type",
            {"to": "feedback-abc@rereflect.ca"},
            {},
        )
        assert result == "all_emails"

    def test_returns_all_emails_with_minimal_event_data(self, adapter):
        result = adapter.check_triggers("email.inbound", {}, {})
        assert result == "all_emails"


class TestExtractContent:
    """Email adapter delegates body parsing to email_parser.parse_email_body."""

    @patch("src.adapters.email.parse_email_body")
    def test_extracts_html_body_via_parser(self, mock_parse, adapter):
        mock_parse.return_value = "Parsed plain text from HTML"
        event_data = {
            "html": "<p>Hello <b>world</b></p>",
            "text": "Hello world",
            "subject": "Feedback",
            "from": "customer@example.com",
            "to": "feedback-abc@rereflect.ca",
        }
        result = adapter.extract_content(event_data, {})
        mock_parse.assert_called_once_with(
            html="<p>Hello <b>world</b></p>",
            text="Hello world",
        )
        assert result["text"] == "Parsed plain text from HTML"

    @patch("src.adapters.email.parse_email_body")
    def test_extracts_plain_text_only(self, mock_parse, adapter):
        mock_parse.return_value = "Plain text feedback"
        event_data = {
            "html": None,
            "text": "Plain text feedback",
            "subject": "Issue report",
            "from": "user@example.com",
            "to": "feedback-xyz@rereflect.ca",
        }
        result = adapter.extract_content(event_data, {})
        mock_parse.assert_called_once_with(html=None, text="Plain text feedback")
        assert result["text"] == "Plain text feedback"

    @patch("src.adapters.email.parse_email_body")
    def test_handles_empty_body(self, mock_parse, adapter):
        mock_parse.return_value = ""
        event_data = {
            "html": None,
            "text": None,
            "subject": "Empty email",
            "from": "sender@example.com",
            "to": "feedback-abc@rereflect.ca",
        }
        result = adapter.extract_content(event_data, {})
        mock_parse.assert_called_once_with(html=None, text=None)
        assert result["text"] == ""

    @patch("src.adapters.email.parse_email_body")
    def test_metadata_includes_subject(self, mock_parse, adapter):
        mock_parse.return_value = "Some text"
        event_data = {
            "html": None,
            "text": "Some text",
            "subject": "Bug report: login fails",
            "from": "customer@example.com",
            "to": "feedback-abc@rereflect.ca",
            "headers": {"message-id": "<msg123@mail.example.com>"},
        }
        result = adapter.extract_content(event_data, {})
        assert result["metadata"]["subject"] == "Bug report: login fails"

    @patch("src.adapters.email.parse_email_body")
    def test_metadata_includes_from_address(self, mock_parse, adapter):
        mock_parse.return_value = "Some text"
        event_data = {
            "html": None,
            "text": "Some text",
            "subject": "Issue",
            "from": "customer@example.com",
            "to": "feedback-abc@rereflect.ca",
        }
        result = adapter.extract_content(event_data, {})
        assert result["metadata"]["from"] == "customer@example.com"

    @patch("src.adapters.email.parse_email_body")
    def test_metadata_handles_missing_fields(self, mock_parse, adapter):
        mock_parse.return_value = ""
        event_data = {}
        result = adapter.extract_content(event_data, {})
        assert result["metadata"]["subject"] is None
        assert result["metadata"]["from"] is None


class TestGetExternalIds:
    """Email adapter returns message_id from headers for deduplication."""

    def test_returns_message_id_from_headers(self, adapter):
        event_data = {
            "headers": {"message-id": "<abc123@mail.example.com>"},
            "from": "customer@example.com",
            "to": "feedback-abc@rereflect.ca",
        }
        event_id, message_id = adapter.get_external_ids(event_data)
        assert event_id == "<abc123@mail.example.com>"
        assert message_id == "<abc123@mail.example.com>"

    def test_returns_unknown_when_no_message_id(self, adapter):
        event_data = {
            "headers": {},
            "from": "customer@example.com",
            "to": "feedback-abc@rereflect.ca",
        }
        event_id, message_id = adapter.get_external_ids(event_data)
        assert event_id == "unknown"
        assert message_id is None

    def test_returns_unknown_when_no_headers(self, adapter):
        event_data = {
            "from": "customer@example.com",
            "to": "feedback-abc@rereflect.ca",
        }
        event_id, message_id = adapter.get_external_ids(event_data)
        assert event_id == "unknown"
        assert message_id is None


class TestFetchContext:
    """Email adapter returns empty context (no additional API calls for v1)."""

    def test_returns_empty_dict(self, adapter):
        event_data = {
            "from": "customer@example.com",
            "to": "feedback-abc@rereflect.ca",
            "subject": "Help",
            "text": "I need help",
        }
        result = adapter.fetch_context(event_data, None, {})
        assert result == {}

    def test_returns_empty_dict_even_with_access_token(self, adapter):
        event_data = {
            "from": "customer@example.com",
            "to": "feedback-abc@rereflect.ca",
        }
        result = adapter.fetch_context(event_data, "some-token", {})
        assert result == {}


class TestAdapterRegistry:
    def test_get_adapter_returns_email_adapter(self):
        from src.adapters import get_adapter
        adapter = get_adapter("email")
        assert isinstance(adapter, EmailAdapter)
