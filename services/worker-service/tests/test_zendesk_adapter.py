"""Tests for Zendesk adapter (ingestion-core aspect)."""

import sys

import pytest
from unittest.mock import patch, MagicMock

from src.adapters.zendesk import ZendeskAdapter


@pytest.fixture
def adapter():
    return ZendeskAdapter()


class TestCheckTriggers:
    def test_new_ticket_trigger_matches_created_event(self, adapter):
        result = adapter.check_triggers(
            "ticket.created",
            {"ticket": {"id": 1, "subject": "Hi"}, "subdomain": "acmeco"},
            {"new_ticket": True},
        )
        assert result == "new_ticket"

    def test_new_ticket_trigger_does_not_match_other_event(self, adapter):
        result = adapter.check_triggers(
            "ticket.updated",
            {"ticket": {"id": 1, "subject": "Hi"}, "subdomain": "acmeco"},
            {"new_ticket": True},
        )
        assert result is None

    def test_no_triggers_returns_none(self, adapter):
        result = adapter.check_triggers(
            "ticket.created",
            {"ticket": {"id": 1, "subject": "Hi"}, "subdomain": "acmeco"},
            {},
        )
        assert result is None

    def test_keyword_trigger_matches_subject(self, adapter):
        result = adapter.check_triggers(
            "ticket.updated",
            {"ticket": {"id": 1, "subject": "Billing question"}, "subdomain": "acmeco"},
            {"keywords": ["billing"]},
        )
        assert result == "keyword:billing"

    def test_keyword_trigger_matches_description(self, adapter):
        result = adapter.check_triggers(
            "ticket.updated",
            {
                "ticket": {
                    "id": 1,
                    "subject": "Hi",
                    "description": "<p>I have a billing question</p>",
                },
                "subdomain": "acmeco",
            },
            {"keywords": ["billing"]},
        )
        assert result == "keyword:billing"

    def test_keyword_trigger_case_insensitive(self, adapter):
        result = adapter.check_triggers(
            "ticket.updated",
            {"ticket": {"id": 1, "subject": "BILLING issue"}, "subdomain": "acmeco"},
            {"keywords": ["billing"]},
        )
        assert result == "keyword:billing"

    def test_keyword_trigger_no_match_returns_none(self, adapter):
        result = adapter.check_triggers(
            "ticket.updated",
            {"ticket": {"id": 1, "subject": "Hello there"}, "subdomain": "acmeco"},
            {"keywords": ["billing"]},
        )
        assert result is None

    def test_new_ticket_and_keyword_both_configured_new_ticket_wins(self, adapter):
        result = adapter.check_triggers(
            "ticket.created",
            {"ticket": {"id": 1, "subject": "Billing issue"}, "subdomain": "acmeco"},
            {"new_ticket": True, "keywords": ["billing"]},
        )
        assert result == "new_ticket"


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


class TestFetchContext:
    def test_returns_empty_without_access_token(self, adapter):
        event_data = {"ticket": {"id": 4521}, "subdomain": "acmeco"}
        result = adapter.fetch_context(event_data, None, {})
        assert result == {}

    def test_returns_empty_on_malformed_access_token(self, adapter):
        event_data = {"ticket": {"id": 4521}, "subdomain": "acmeco"}
        result = adapter.fetch_context(event_data, "no-colon-here", {})
        assert result == {}

    @patch("src.adapters.zendesk.httpx.Client")
    def test_fetches_ticket_and_requester_details(self, mock_client_cls, adapter):
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)

        ticket_response = MagicMock()
        ticket_response.json.return_value = {"ticket": {"id": 4521, "requester_id": 999}}

        user_response = MagicMock()
        user_response.json.return_value = {
            "user": {"id": 999, "name": "Jane Doe", "email": "jane@example.com"}
        }

        mock_client.get.side_effect = [ticket_response, user_response]

        event_data = {"ticket": {"id": 4521}, "subdomain": "acmeco"}
        result = adapter.fetch_context(event_data, "agent@acmeco.com:apitoken123", {})

        first_call = mock_client.get.call_args_list[0]
        second_call = mock_client.get.call_args_list[1]
        assert first_call.args[0] == "https://acmeco.zendesk.com/api/v2/tickets/4521"
        assert second_call.args[0] == "https://acmeco.zendesk.com/api/v2/users/999"

        mock_client_cls.assert_called_once_with(
            timeout=10, auth=("agent@acmeco.com/token", "apitoken123")
        )

        assert result["requester_name"] == "Jane Doe"
        assert result["requester_email"] == "jane@example.com"
        assert result["ticket_url"] == "https://acmeco.zendesk.com/agent/tickets/4521"

    @patch("src.adapters.zendesk.httpx.Client")
    def test_skips_requester_fetch_when_no_requester_id(self, mock_client_cls, adapter):
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)

        ticket_response = MagicMock()
        ticket_response.json.return_value = {"ticket": {"id": 4521}}
        mock_client.get.side_effect = [ticket_response]

        event_data = {"ticket": {"id": 4521}, "subdomain": "acmeco"}
        result = adapter.fetch_context(event_data, "agent@acmeco.com:apitoken123", {})

        assert mock_client.get.call_count == 1
        assert result["ticket_url"] == "https://acmeco.zendesk.com/agent/tickets/4521"
        assert "requester_name" not in result
        assert "requester_email" not in result

    @patch("src.adapters.zendesk.httpx.Client")
    def test_handles_api_error_gracefully(self, mock_client_cls, adapter):
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_client.get.side_effect = Exception("API error")

        event_data = {"ticket": {"id": 4521}, "subdomain": "acmeco"}
        result = adapter.fetch_context(event_data, "agent@acmeco.com:apitoken123", {})
        assert isinstance(result, dict)


class TestAdapterRegistry:
    def test_get_adapter_returns_zendesk_adapter(self):
        from src.adapters import get_adapter

        adapter = get_adapter("zendesk")
        assert isinstance(adapter, ZendeskAdapter)


class TestModelsAndMigration:
    def test_worker_and_backend_zendesk_integration_columns_match(self):
        """Worker ZendeskIntegration mirror columns must exactly match
        backend-api model columns (ingestion-core aspect).

        Same sys.path/sys.modules swap technique as
        test_salesforce_sync.py::TestModelsAndMigration.
        """
        import os

        from src.models import ZendeskIntegration as WorkerModel
        worker_cols = {c.name for c in WorkerModel.__table__.columns}

        worktree = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        )
        backend_src = os.path.join(worktree, "services", "backend-api")

        saved_mods = {k: v for k, v in sys.modules.items() if k == "src" or k.startswith("src.")}
        for k in saved_mods:
            del sys.modules[k]

        sys.path.insert(0, backend_src)
        try:
            from src.models.zendesk_integration import ZendeskIntegration as BackendModel
            backend_cols = {c.name for c in BackendModel.__table__.columns}
        finally:
            sys.path.remove(backend_src)
            for k in list(sys.modules.keys()):
                if k == "src" or k.startswith("src."):
                    del sys.modules[k]
            sys.modules.update(saved_mods)

        assert worker_cols == backend_cols, (
            f"Column mismatch!\n"
            f"  Worker only:  {worker_cols - backend_cols}\n"
            f"  Backend only: {backend_cols - worker_cols}"
        )
