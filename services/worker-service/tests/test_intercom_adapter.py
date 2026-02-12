"""Tests for Intercom adapter."""

import pytest
from unittest.mock import patch, MagicMock

from src.adapters.intercom import IntercomAdapter


@pytest.fixture
def adapter():
    return IntercomAdapter()


class TestCheckTriggers:
    def test_all_conversations_matches_new_conversation(self, adapter):
        result = adapter.check_triggers(
            "conversation.user.created",
            {"topic": "conversation.user.created", "data": {"item": {"type": "conversation"}}},
            {"all_conversations": True},
        )
        assert result == "all_conversations"

    def test_all_conversations_matches_reply(self, adapter):
        result = adapter.check_triggers(
            "conversation.user.replied",
            {"topic": "conversation.user.replied", "data": {"item": {"type": "conversation_part"}}},
            {"all_conversations": True},
        )
        assert result == "all_conversations"

    def test_all_conversations_matches_rating(self, adapter):
        result = adapter.check_triggers(
            "conversation.rating.added",
            {"topic": "conversation.rating.added", "data": {"item": {"type": "conversation_rating"}}},
            {"all_conversations": True},
        )
        assert result == "all_conversations"

    def test_new_conversations_only_matches_created(self, adapter):
        result = adapter.check_triggers(
            "conversation.user.created",
            {"topic": "conversation.user.created", "data": {"item": {"type": "conversation"}}},
            {"new_conversations": True},
        )
        assert result == "new_conversations"

    def test_new_conversations_does_not_match_reply(self, adapter):
        result = adapter.check_triggers(
            "conversation.user.replied",
            {"topic": "conversation.user.replied", "data": {"item": {"type": "conversation_part"}}},
            {"new_conversations": True},
        )
        assert result is None

    def test_replies_trigger_matches_reply(self, adapter):
        result = adapter.check_triggers(
            "conversation.user.replied",
            {"topic": "conversation.user.replied", "data": {"item": {"type": "conversation_part"}}},
            {"replies": True},
        )
        assert result == "replies"

    def test_replies_trigger_does_not_match_created(self, adapter):
        result = adapter.check_triggers(
            "conversation.user.created",
            {"topic": "conversation.user.created", "data": {"item": {"type": "conversation"}}},
            {"replies": True},
        )
        assert result is None

    def test_ratings_trigger_matches_rating(self, adapter):
        result = adapter.check_triggers(
            "conversation.rating.added",
            {"topic": "conversation.rating.added", "data": {"item": {"type": "conversation_rating"}}},
            {"ratings": True},
        )
        assert result == "ratings"

    def test_ratings_trigger_does_not_match_reply(self, adapter):
        result = adapter.check_triggers(
            "conversation.user.replied",
            {"topic": "conversation.user.replied", "data": {"item": {"type": "conversation_part"}}},
            {"ratings": True},
        )
        assert result is None

    def test_keywords_trigger_matches_text(self, adapter):
        result = adapter.check_triggers(
            "conversation.user.created",
            {
                "topic": "conversation.user.created",
                "data": {
                    "item": {
                        "type": "conversation",
                        "conversation_message": {
                            "body": "<p>I need help with billing</p>",
                        },
                    }
                },
            },
            {"keywords": ["billing", "payment"]},
        )
        assert result == "keyword:billing"

    def test_keywords_trigger_case_insensitive(self, adapter):
        result = adapter.check_triggers(
            "conversation.user.created",
            {
                "topic": "conversation.user.created",
                "data": {
                    "item": {
                        "type": "conversation",
                        "conversation_message": {
                            "body": "<p>BILLING issue</p>",
                        },
                    }
                },
            },
            {"keywords": ["billing"]},
        )
        assert result == "keyword:billing"

    def test_keywords_trigger_in_reply(self, adapter):
        result = adapter.check_triggers(
            "conversation.user.replied",
            {
                "topic": "conversation.user.replied",
                "data": {
                    "item": {
                        "type": "conversation_part",
                        "body": "<p>I have a billing question</p>",
                    }
                },
            },
            {"keywords": ["billing"]},
        )
        assert result == "keyword:billing"

    def test_no_triggers_returns_none(self, adapter):
        result = adapter.check_triggers(
            "conversation.user.created",
            {"topic": "conversation.user.created", "data": {"item": {"type": "conversation"}}},
            {},
        )
        assert result is None

    def test_keywords_no_match_returns_none(self, adapter):
        result = adapter.check_triggers(
            "conversation.user.created",
            {
                "topic": "conversation.user.created",
                "data": {
                    "item": {
                        "type": "conversation",
                        "conversation_message": {
                            "body": "<p>Hello there</p>",
                        },
                    }
                },
            },
            {"keywords": ["billing", "payment"]},
        )
        assert result is None


class TestExtractContent:
    def test_extracts_new_conversation_text(self, adapter):
        event_data = {
            "topic": "conversation.user.created",
            "data": {
                "item": {
                    "type": "conversation",
                    "id": "123",
                    "conversation_message": {
                        "body": "<p>I need help with billing</p>",
                        "author": {
                            "type": "user",
                            "id": "user_1",
                            "name": "John Doe",
                            "email": "john@example.com",
                        },
                    },
                }
            },
        }
        result = adapter.extract_content(event_data, {})
        assert result["text"] == "I need help with billing"
        assert result["metadata"]["author_name"] == "John Doe"
        assert result["metadata"]["author_email"] == "john@example.com"
        assert result["metadata"]["author_id"] == "user_1"
        assert result["metadata"]["conversation_id"] == "123"

    def test_strips_html_tags_from_body(self, adapter):
        event_data = {
            "topic": "conversation.user.created",
            "data": {
                "item": {
                    "type": "conversation",
                    "id": "456",
                    "conversation_message": {
                        "body": "<p>Hello <b>world</b></p><br/><p>Second line</p>",
                        "author": {"type": "user", "id": "u1", "name": "A", "email": "a@b.com"},
                    },
                }
            },
        }
        result = adapter.extract_content(event_data, {})
        assert "<" not in result["text"]
        assert "Hello" in result["text"]
        assert "world" in result["text"]
        assert "Second line" in result["text"]

    def test_extracts_reply_text(self, adapter):
        event_data = {
            "topic": "conversation.user.replied",
            "data": {
                "item": {
                    "type": "conversation_part",
                    "id": "part_456",
                    "conversation_id": "conv_123",
                    "body": "<p>Thanks for the reply</p>",
                    "author": {
                        "type": "user",
                        "id": "user_2",
                        "name": "Jane Smith",
                        "email": "jane@example.com",
                    },
                }
            },
        }
        result = adapter.extract_content(event_data, {})
        assert result["text"] == "Thanks for the reply"
        assert result["metadata"]["author_name"] == "Jane Smith"
        assert result["metadata"]["conversation_id"] == "conv_123"

    def test_extracts_rating_as_text(self, adapter):
        event_data = {
            "topic": "conversation.rating.added",
            "data": {
                "item": {
                    "type": "conversation_rating",
                    "rating": 5,
                    "remark": "Great support!",
                    "conversation_id": "conv_789",
                    "contact": {"id": "user_3", "name": "Bob"},
                }
            },
        }
        result = adapter.extract_content(event_data, {})
        assert "Great support!" in result["text"]
        assert "5" in result["text"]
        assert result["metadata"]["conversation_id"] == "conv_789"
        assert result["metadata"]["rating"] == 5
        assert result["metadata"]["author_name"] == "Bob"

    def test_handles_missing_body_gracefully(self, adapter):
        event_data = {
            "topic": "conversation.user.created",
            "data": {
                "item": {
                    "type": "conversation",
                    "id": "999",
                    "conversation_message": {
                        "author": {"type": "user", "id": "u1", "name": "X"},
                    },
                }
            },
        }
        result = adapter.extract_content(event_data, {})
        assert result["text"] == ""
        assert result["metadata"]["conversation_id"] == "999"

    def test_handles_rating_without_remark(self, adapter):
        event_data = {
            "topic": "conversation.rating.added",
            "data": {
                "item": {
                    "type": "conversation_rating",
                    "rating": 3,
                    "conversation_id": "conv_100",
                    "contact": {"id": "user_4", "name": "Alice"},
                }
            },
        }
        result = adapter.extract_content(event_data, {})
        assert "3" in result["text"]
        assert result["metadata"]["rating"] == 3


class TestGetExternalIds:
    def test_new_conversation_returns_conversation_id(self, adapter):
        event_data = {
            "topic": "conversation.user.created",
            "data": {
                "item": {
                    "type": "conversation",
                    "id": "conv_100",
                    "conversation_message": {"body": "hi"},
                }
            },
        }
        event_id, message_id = adapter.get_external_ids(event_data)
        assert event_id == "conv_100"
        assert message_id == "conv_100"

    def test_reply_returns_conversation_and_part_id(self, adapter):
        event_data = {
            "topic": "conversation.user.replied",
            "data": {
                "item": {
                    "type": "conversation_part",
                    "id": "part_42",
                    "conversation_id": "conv_100",
                    "body": "reply",
                }
            },
        }
        event_id, message_id = adapter.get_external_ids(event_data)
        assert event_id == "conv_100:part_42"
        assert message_id == "conv_100"

    def test_rating_returns_conversation_and_rating(self, adapter):
        event_data = {
            "topic": "conversation.rating.added",
            "data": {
                "item": {
                    "type": "conversation_rating",
                    "rating": 5,
                    "conversation_id": "conv_200",
                    "contact": {"id": "u1"},
                }
            },
        }
        event_id, message_id = adapter.get_external_ids(event_data)
        assert event_id == "conv_200:rating"
        assert message_id == "conv_200"


class TestFetchContext:
    def test_returns_empty_without_access_token(self, adapter):
        event_data = {
            "topic": "conversation.user.created",
            "data": {"item": {"type": "conversation", "id": "123"}},
        }
        result = adapter.fetch_context(event_data, None, {})
        assert result == {}

    @patch("src.adapters.intercom.httpx.Client")
    def test_fetches_conversation_details(self, mock_client_cls, adapter):
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)

        # Mock conversation response
        conv_response = MagicMock()
        conv_response.json.return_value = {
            "type": "conversation",
            "id": "conv_123",
            "conversation_parts": {
                "conversation_parts": [
                    {"body": "<p>First message</p>", "author": {"type": "user", "name": "John"}},
                    {"body": "<p>Second message</p>", "author": {"type": "admin", "name": "Agent"}},
                ]
            },
        }
        conv_response.status_code = 200

        # Mock contact response
        contact_response = MagicMock()
        contact_response.json.return_value = {
            "type": "contact",
            "id": "user_1",
            "name": "John Doe",
            "email": "john@example.com",
        }
        contact_response.status_code = 200

        mock_client.get.side_effect = [conv_response, contact_response]

        event_data = {
            "topic": "conversation.user.created",
            "data": {
                "item": {
                    "type": "conversation",
                    "id": "conv_123",
                    "conversation_message": {
                        "author": {"type": "user", "id": "user_1"},
                    },
                }
            },
        }
        result = adapter.fetch_context(event_data, "test_token", {})
        assert "previous_messages" in result
        assert len(result["previous_messages"]) == 2
        assert result["contact_name"] == "John Doe"
        assert result["contact_email"] == "john@example.com"

    @patch("src.adapters.intercom.httpx.Client")
    def test_handles_api_error_gracefully(self, mock_client_cls, adapter):
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_client.get.side_effect = Exception("API error")

        event_data = {
            "topic": "conversation.user.created",
            "data": {
                "item": {
                    "type": "conversation",
                    "id": "conv_123",
                    "conversation_message": {
                        "author": {"type": "user", "id": "user_1"},
                    },
                }
            },
        }
        result = adapter.fetch_context(event_data, "test_token", {})
        assert isinstance(result, dict)


class TestAdapterRegistry:
    def test_get_adapter_returns_intercom_adapter(self):
        from src.adapters import get_adapter
        adapter = get_adapter("intercom")
        assert isinstance(adapter, IntercomAdapter)
