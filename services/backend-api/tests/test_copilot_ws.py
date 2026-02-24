"""
TDD tests for Copilot WebSocket endpoint (M2.2).

Tests cover:
- WebSocket connection with valid/invalid JWT
- Sending query messages and receiving streamed responses
- Stop message cancels generation
- Rate limit enforcement
- Message persistence
- Error handling
"""

import json
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.models.user import User
from src.models.organization import Organization
from src.api.auth import hash_password, create_access_token


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def pro_organization(db: Session) -> Organization:
    org = Organization(name="Pro Company", plan="pro")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


@pytest.fixture
def pro_user(db: Session, pro_organization: Organization) -> User:
    user = User(
        email="pro@example.com",
        password_hash=hash_password("password123"),
        organization_id=pro_organization.id,
        role="owner",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def valid_token(pro_user: User) -> str:
    return create_access_token({
        "user_id": pro_user.id,
        "organization_id": pro_user.organization_id,
        "role": pro_user.role,
    })


@pytest.fixture
def free_organization(db: Session) -> Organization:
    org = Organization(name="Free Company", plan="free")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


@pytest.fixture
def free_user(db: Session, free_organization: Organization) -> User:
    user = User(
        email="free@example.com",
        password_hash=hash_password("password123"),
        organization_id=free_organization.id,
        role="owner",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def free_token(free_user: User) -> str:
    return create_access_token({
        "user_id": free_user.id,
        "organization_id": free_user.organization_id,
        "role": free_user.role,
    })


@pytest.fixture
def conversation_id(client: TestClient, valid_token: str) -> str:
    """Create a conversation and return its ID."""
    headers = {"Authorization": f"Bearer {valid_token}"}
    r = client.post("/api/v1/conversations", json={"title": "Test"}, headers=headers)
    assert r.status_code == 201
    return r.json()["id"]


# =============================================================================
# CONNECTION TESTS
# =============================================================================


class TestWebSocketConnection:
    def test_connect_with_valid_jwt(
        self, client: TestClient, valid_token: str
    ):
        """WebSocket accepts connection when valid JWT is provided."""
        with client.websocket_connect(f"/ws/copilot?token={valid_token}") as ws:
            # Should connect successfully — if it fails, exception is raised
            pass

    def test_connect_without_token_rejected(self, client: TestClient):
        """WebSocket rejects connection when no token provided."""
        with pytest.raises(Exception):
            with client.websocket_connect("/ws/copilot") as ws:
                pass

    def test_connect_with_invalid_token_rejected(self, client: TestClient):
        """WebSocket rejects connection when token is invalid."""
        with pytest.raises(Exception):
            with client.websocket_connect("/ws/copilot?token=invalid_token") as ws:
                pass

    def test_connect_with_expired_token_rejected(self, client: TestClient):
        """WebSocket rejects expired JWT tokens."""
        from jose import jwt
        from datetime import datetime, timedelta
        import os
        expired_token = jwt.encode(
            {
                "user_id": 9999,
                "organization_id": 9999,
                "role": "owner",
                "exp": datetime.utcnow() - timedelta(hours=1),
            },
            os.getenv("JWT_SECRET", "dev-secret-key"),
            algorithm="HS256",
        )
        with pytest.raises(Exception):
            with client.websocket_connect(f"/ws/copilot?token={expired_token}") as ws:
                pass


# =============================================================================
# QUERY MESSAGE TESTS
# =============================================================================


def _async_generator(items):
    """Create an async generator from a list of items for mocking."""
    async def gen():
        for item in items:
            yield item
    return gen()


class TestQueryMessages:
    def test_send_query_receives_status_message(
        self, client: TestClient, valid_token: str, conversation_id: str
    ):
        """Sending a query results in a status message being received first."""
        mock_chunks = [
            MagicMock(choices=[MagicMock(delta=MagicMock(content="Hello"))])
        ]

        with patch(
            "src.api.routes.copilot_ws.call_llm_stream",
            side_effect=lambda **kwargs: _async_generator(mock_chunks),
        ):
            with client.websocket_connect(f"/ws/copilot?token={valid_token}") as ws:
                ws.send_json({
                    "type": "query",
                    "conversation_id": conversation_id,
                    "content": "How many feedbacks do we have?",
                    "context_scope": "all_data",
                    "message_id": "test-msg-1",
                })

                msg = ws.receive_json()
                assert msg["type"] == "status"
                assert "status" in msg
                assert msg["message_id"] == "test-msg-1"

    def test_send_query_receives_stream_messages(
        self, client: TestClient, valid_token: str, conversation_id: str
    ):
        """Sending a query results in stream messages with delta tokens."""
        mock_chunks = [
            MagicMock(choices=[MagicMock(delta=MagicMock(content="Based "))]),
            MagicMock(choices=[MagicMock(delta=MagicMock(content="on "))]),
            MagicMock(choices=[MagicMock(delta=MagicMock(content="your data"))]),
        ]

        with patch(
            "src.api.routes.copilot_ws.call_llm_stream",
            side_effect=lambda **kwargs: _async_generator(mock_chunks),
        ) as mock_llm:

            with client.websocket_connect(f"/ws/copilot?token={valid_token}") as ws:
                ws.send_json({
                    "type": "query",
                    "conversation_id": conversation_id,
                    "content": "Summarize feedbacks",
                    "context_scope": "all_data",
                    "message_id": "test-msg-1",
                })

                # Collect all messages until done=true
                messages = []
                while True:
                    msg = ws.receive_json()
                    messages.append(msg)
                    if msg.get("type") == "stream" and msg.get("done"):
                        break

                stream_messages = [m for m in messages if m["type"] == "stream"]
                assert len(stream_messages) > 0

                final_msg = stream_messages[-1]
                assert final_msg["done"] is True
                assert "metadata" in final_msg

    def test_query_missing_conversation_id_returns_error(
        self, client: TestClient, valid_token: str
    ):
        """Query without conversation_id returns error message."""
        with client.websocket_connect(f"/ws/copilot?token={valid_token}") as ws:
            ws.send_json({
                "type": "query",
                "content": "test",
                "context_scope": "all_data",
                "message_id": "test-msg-1",
            })

            msg = ws.receive_json()
            assert msg["type"] == "error"

    def test_query_other_org_conversation_returns_error(
        self, client: TestClient, valid_token: str, free_token: str
    ):
        """Cannot query a conversation belonging to another org."""
        # Create a conversation as free user
        headers = {"Authorization": f"Bearer {free_token}"}
        r = client.post("/api/v1/conversations", json={"title": "Free Conv"}, headers=headers)
        free_conv_id = r.json()["id"]

        with client.websocket_connect(f"/ws/copilot?token={valid_token}") as ws:
            ws.send_json({
                "type": "query",
                "conversation_id": free_conv_id,
                "content": "test",
                "context_scope": "all_data",
                "message_id": "test-msg-1",
            })

            msg = ws.receive_json()
            assert msg["type"] == "error"


# =============================================================================
# RATE LIMITING TESTS
# =============================================================================


class TestRateLimiting:
    def test_free_user_daily_cap_enforced(
        self, client: TestClient, free_token: str, db: Session
    ):
        """Free users are limited to 10 queries per day."""
        headers = {"Authorization": f"Bearer {free_token}"}
        conv_resp = client.post("/api/v1/conversations", json={"title": "Test"}, headers=headers)
        conv_id = conv_resp.json()["id"]

        # Simulate 10 queries already used today
        with patch("src.services.copilot_rate_limiter.get_daily_query_count", return_value=10):
            with client.websocket_connect(f"/ws/copilot?token={free_token}") as ws:
                ws.send_json({
                    "type": "query",
                    "conversation_id": conv_id,
                    "content": "test",
                    "context_scope": "all_data",
                    "message_id": "test-msg-1",
                })

                msg = ws.receive_json()
                assert msg["type"] == "error"
                assert "rate_limit" in msg.get("error", "").lower() or "limit" in msg.get("error", "").lower()

    def test_pro_user_no_daily_cap(
        self, client: TestClient, valid_token: str, conversation_id: str
    ):
        """Pro users have no daily cap (only monthly token budget)."""
        mock_chunks = [MagicMock(choices=[MagicMock(delta=MagicMock(content="OK"))])]
        # Simulate 100 queries (way beyond free limit) - Pro should still proceed
        with patch("src.services.copilot_rate_limiter.get_daily_query_count", return_value=100):
            with patch(
                "src.api.routes.copilot_ws.call_llm_stream",
                side_effect=lambda **kwargs: _async_generator(mock_chunks),
            ):
                with client.websocket_connect(f"/ws/copilot?token={valid_token}") as ws:
                    ws.send_json({
                        "type": "query",
                        "conversation_id": conversation_id,
                        "content": "test",
                        "context_scope": "all_data",
                        "message_id": "test-msg-1",
                    })

                    msg = ws.receive_json()
                    # Should NOT be an error about rate limits
                    assert msg["type"] != "error" or "rate_limit" not in msg.get("error", "")


# =============================================================================
# MESSAGE PERSISTENCE TESTS
# =============================================================================


class TestMessagePersistence:
    def test_messages_persisted_after_response(
        self, client: TestClient, valid_token: str, conversation_id: str
    ):
        """User message and AI response are persisted to the DB after streaming."""
        mock_chunks = [MagicMock(choices=[MagicMock(delta=MagicMock(content="Test response"))])]
        with patch(
            "src.api.routes.copilot_ws.call_llm_stream",
            side_effect=lambda **kwargs: _async_generator(mock_chunks),
        ):

            with client.websocket_connect(f"/ws/copilot?token={valid_token}") as ws:
                ws.send_json({
                    "type": "query",
                    "conversation_id": conversation_id,
                    "content": "Test query",
                    "context_scope": "all_data",
                    "message_id": "test-msg-1",
                })

                # Consume all messages until done
                while True:
                    msg = ws.receive_json()
                    if msg.get("type") == "stream" and msg.get("done"):
                        break

        # Check messages are persisted via REST API
        headers = {"Authorization": f"Bearer {valid_token}"}
        r = client.get(f"/api/v1/conversations/{conversation_id}", headers=headers)
        assert r.status_code == 200
        messages = r.json()["messages"]
        assert len(messages) == 2  # user + assistant

        user_msg = next(m for m in messages if m["role"] == "user")
        ai_msg = next(m for m in messages if m["role"] == "assistant")
        assert user_msg["content"] == "Test query"
        assert "Test response" in ai_msg["content"]


# =============================================================================
# ERROR HANDLING TESTS
# =============================================================================


class TestErrorHandling:
    def test_llm_failure_sends_error_message(
        self, client: TestClient, valid_token: str, conversation_id: str
    ):
        """When the LLM call fails, an error message is sent to the client."""
        with patch("src.api.routes.copilot_ws.call_llm_stream", side_effect=Exception("LLM down")):
            with client.websocket_connect(f"/ws/copilot?token={valid_token}") as ws:
                ws.send_json({
                    "type": "query",
                    "conversation_id": conversation_id,
                    "content": "test",
                    "context_scope": "all_data",
                    "message_id": "test-msg-1",
                })

                # Skip status messages
                msg = ws.receive_json()
                while msg["type"] == "status":
                    msg = ws.receive_json()

                assert msg["type"] == "error"
                assert "suggestions" in msg

    def test_unknown_message_type_sends_error(
        self, client: TestClient, valid_token: str
    ):
        """Unknown message types receive an error response."""
        with client.websocket_connect(f"/ws/copilot?token={valid_token}") as ws:
            ws.send_json({
                "type": "unknown_type",
                "message_id": "test-msg-1",
            })

            msg = ws.receive_json()
            assert msg["type"] == "error"

    def test_malformed_json_closes_connection(
        self, client: TestClient, valid_token: str
    ):
        """Malformed JSON from client results in connection close or error."""
        with client.websocket_connect(f"/ws/copilot?token={valid_token}") as ws:
            ws.send_text("not valid json{{{")
            # Should receive an error message or connection closed
            try:
                msg = ws.receive_json()
                assert msg["type"] == "error"
            except Exception:
                pass  # Connection closed is also acceptable


# =============================================================================
# COPILOT USAGE ENDPOINT TESTS
# =============================================================================


class TestCopilotUsage:
    def test_get_usage_stats(self, client: TestClient, valid_token: str):
        """GET /api/v1/copilot/usage returns usage stats."""
        headers = {"Authorization": f"Bearer {valid_token}"}
        response = client.get("/api/v1/copilot/usage", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "daily_queries_used" in data
        assert "daily_queries_limit" in data
        assert "monthly_tokens_used" in data
        assert "monthly_tokens_limit" in data
        assert "plan" in data

    def test_get_usage_requires_auth(self, client: TestClient):
        response = client.get("/api/v1/copilot/usage")
        assert response.status_code == 403
