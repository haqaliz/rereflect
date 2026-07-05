"""Tests for Zendesk adapter (ingestion-core aspect)."""

import pytest

from src.adapters.zendesk import ZendeskAdapter


@pytest.fixture
def adapter():
    return ZendeskAdapter()


class TestGetExternalIds:
    def test_returns_ticket_id_as_both_ids(self, adapter):
        event_data = {"ticket": {"id": 4521, "subject": "Billing issue"}, "subdomain": "acmeco"}
        event_id, message_id = adapter.get_external_ids(event_data)
        assert event_id == "4521"
        assert message_id == "4521"
        assert isinstance(event_id, str)
        assert isinstance(message_id, str)


class TestExtractContent:
    def test_builds_text_from_subject_and_description(self, adapter):
        event_data = {
            "ticket": {
                "id": 4521,
                "subject": "Billing issue",
                "description": "<p>My invoice is wrong</p>",
                "status": "open",
                "tags": ["billing", "urgent"],
                "requester_email": "jane@example.com",
            },
            "subdomain": "acmeco",
        }
        result = adapter.extract_content(event_data, {})
        assert result["text"] == "Billing issue\n\nMy invoice is wrong"
        assert result["metadata"] == {
            "subdomain": "acmeco",
            "ticket_id": 4521,
            "status": "open",
            "requester_email": "jane@example.com",
            "tags": ["billing", "urgent"],
        }
        assert result["customer_email"] == "jane@example.com"

    def test_strips_html_from_subject_too(self, adapter):
        event_data = {
            "ticket": {
                "id": 1,
                "subject": "<b>Urgent</b>: cannot login",
                "description": "help",
            },
            "subdomain": "acmeco",
        }
        result = adapter.extract_content(event_data, {})
        assert "<" not in result["text"]

    def test_handles_missing_description(self, adapter):
        event_data = {
            "ticket": {"id": 1, "subject": "Billing issue"},
            "subdomain": "acmeco",
        }
        result = adapter.extract_content(event_data, {})
        assert result["text"] == "Billing issue"

    def test_handles_empty_string_description(self, adapter):
        event_data = {
            "ticket": {"id": 1, "subject": "Billing issue", "description": ""},
            "subdomain": "acmeco",
        }
        result = adapter.extract_content(event_data, {})
        assert result["text"] == "Billing issue"

    def test_handles_missing_requester_email(self, adapter):
        event_data = {
            "ticket": {"id": 1, "subject": "Billing issue", "description": "help"},
            "subdomain": "acmeco",
        }
        result = adapter.extract_content(event_data, {})
        assert result["metadata"]["requester_email"] is None
        assert result.get("customer_email") is None

    def test_handles_missing_tags(self, adapter):
        event_data = {
            "ticket": {"id": 1, "subject": "Billing issue", "description": "help"},
            "subdomain": "acmeco",
        }
        result = adapter.extract_content(event_data, {})
        assert result["metadata"]["tags"] == []


class TestAdapterRegistry:
    def test_get_adapter_returns_zendesk_adapter(self):
        from src.adapters import get_adapter

        adapter = get_adapter("zendesk")
        assert isinstance(adapter, ZendeskAdapter)
