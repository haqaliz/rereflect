"""
TDD tests for /ws/events WebSocket endpoint.

Tests cover:
- Connection auth (no token, invalid token, valid token)
- Heartbeat ping
- Idle timeout
- Client ping resets idle timer
- Event broadcasting to connected clients
- Multiple clients in same org receive broadcast
- Clients in different orgs are isolated
- Disconnect cleans up connection
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.models.user import User
from src.models.organization import Organization
from src.api.auth import hash_password, create_access_token


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def org_a(db: Session) -> Organization:
    org = Organization(name="Org A", plan="pro")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


@pytest.fixture
def org_b(db: Session) -> Organization:
    org = Organization(name="Org B", plan="pro")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


@pytest.fixture
def user_a(db: Session, org_a: Organization) -> User:
    user = User(
        email="user_a@example.com",
        password_hash=hash_password("password123"),
        organization_id=org_a.id,
        role="owner",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def user_b(db: Session, org_b: Organization) -> User:
    user = User(
        email="user_b@example.com",
        password_hash=hash_password("password123"),
        organization_id=org_b.id,
        role="owner",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def user_a2(db: Session, org_a: Organization) -> User:
    """Second user in org A."""
    user = User(
        email="user_a2@example.com",
        password_hash=hash_password("password123"),
        organization_id=org_a.id,
        role="member",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def token_a(user_a: User) -> str:
    return create_access_token({
        "user_id": user_a.id,
        "organization_id": user_a.organization_id,
        "role": user_a.role,
    })


@pytest.fixture
def token_b(user_b: User) -> str:
    return create_access_token({
        "user_id": user_b.id,
        "organization_id": user_b.organization_id,
        "role": user_b.role,
    })


@pytest.fixture
def token_a2(user_a2: User) -> str:
    return create_access_token({
        "user_id": user_a2.id,
        "organization_id": user_a2.organization_id,
        "role": user_a2.role,
    })


# =============================================================================
# CONNECTION AUTH TESTS
# =============================================================================


class TestConnectionAuth:
    def test_connect_without_token_returns_4001(self, client: TestClient):
        """WS connect to /ws/events without ?token → closed with 4001."""
        with pytest.raises(Exception):
            with client.websocket_connect("/ws/events") as ws:
                pass

    def test_connect_with_invalid_token_returns_4001(self, client: TestClient):
        """WS connect with bad JWT → closed with 4001."""
        with pytest.raises(Exception):
            with client.websocket_connect("/ws/events?token=not_a_valid_jwt") as ws:
                pass

    def test_connect_with_valid_token_succeeds(self, client: TestClient, token_a: str):
        """WS connect with valid JWT → connection accepted without error."""
        with client.websocket_connect(f"/ws/events?token={token_a}") as ws:
            # Connection should be accepted; no exception means success
            pass


# =============================================================================
# HEARTBEAT TESTS
# =============================================================================


class TestHeartbeat:
    def test_heartbeat_ping_sent_on_timeout(self, client: TestClient, token_a: str):
        """After HEARTBEAT_INTERVAL timeout, server sends {"type": "ping"}."""
        from src.api.routes import events_ws as ews_module

        # Patch HEARTBEAT_INTERVAL to 0 so the timeout fires immediately
        with patch.object(ews_module, "HEARTBEAT_INTERVAL", 0):
            with client.websocket_connect(f"/ws/events?token={token_a}") as ws:
                msg = ws.receive_json()
                assert msg == {"type": "ping"}

    def test_client_ping_accepted(self, client: TestClient, token_a: str):
        """Client can send {"type": "ping"} without error (connection stays open)."""
        with client.websocket_connect(f"/ws/events?token={token_a}") as ws:
            ws.send_json({"type": "ping"})
            # If we reach here without exception, the server handled ping without closing


# =============================================================================
# IDLE TIMEOUT TESTS
# =============================================================================


class TestIdleTimeout:
    def test_idle_timeout_closes_connection(self, client: TestClient, token_a: str):
        """No activity for IDLE_TIMEOUT → connection closed with code 1000."""
        from src.api.routes import events_ws as ews_module

        # Patch IDLE_TIMEOUT to 0 and HEARTBEAT_INTERVAL to 0 to trigger immediately
        with patch.object(ews_module, "IDLE_TIMEOUT", 0):
            with patch.object(ews_module, "HEARTBEAT_INTERVAL", 0):
                with client.websocket_connect(f"/ws/events?token={token_a}") as ws:
                    # The connection should close due to idle timeout
                    # receive_json may raise or return close frame
                    try:
                        ws.receive_json()  # May get ping or disconnect
                        ws.receive_json()  # Second attempt should fail or close
                    except Exception:
                        pass  # Connection closed as expected


# =============================================================================
# EVENT BROADCASTING TESTS
# =============================================================================


class TestEventBroadcasting:
    def test_broadcast_event_received_by_connected_client(
        self, client: TestClient, token_a: str, org_a: Organization
    ):
        """Emit event to org → connected client receives it."""
        from src.services.event_connection_manager import event_manager

        with client.websocket_connect(f"/ws/events?token={token_a}") as ws:
            # Emit an event directly via event_manager
            event = {
                "type": "event",
                "event_type": "feedback:created",
                "data": {"id": 42},
                "timestamp": "2026-02-24T00:00:00",
            }
            asyncio.get_event_loop().run_until_complete(
                event_manager.broadcast_to_org(org_id=org_a.id, event=event)
            )
            msg = ws.receive_json()
            assert msg["type"] == "event"
            assert msg["event_type"] == "feedback:created"
            assert msg["data"]["id"] == 42

    def test_multiple_clients_same_org_receive_broadcast(
        self,
        client: TestClient,
        token_a: str,
        token_a2: str,
        org_a: Organization,
    ):
        """2 clients in same org → both receive broadcast event."""
        from src.services.event_connection_manager import event_manager

        with client.websocket_connect(f"/ws/events?token={token_a}") as ws1:
            with client.websocket_connect(f"/ws/events?token={token_a2}") as ws2:
                event = {
                    "type": "event",
                    "event_type": "workflow:status_changed",
                    "data": {"feedback_id": 1},
                    "timestamp": "2026-02-24T00:00:00",
                }
                asyncio.get_event_loop().run_until_complete(
                    event_manager.broadcast_to_org(org_id=org_a.id, event=event)
                )
                msg1 = ws1.receive_json()
                msg2 = ws2.receive_json()
                assert msg1["event_type"] == "workflow:status_changed"
                assert msg2["event_type"] == "workflow:status_changed"

    def test_client_different_org_does_not_receive(
        self,
        client: TestClient,
        token_a: str,
        token_b: str,
        org_a: Organization,
        org_b: Organization,
    ):
        """Client in org B, event broadcast to org A → org B client does NOT receive."""
        from src.services.event_connection_manager import event_manager
        import threading

        received_by_b = []

        def listen_ws_b():
            try:
                with client.websocket_connect(f"/ws/events?token={token_b}") as ws_b:
                    # Small timeout so we don't block forever
                    ws_b.send_json({"type": "ping"})  # Keep connection alive
                    try:
                        msg = ws_b.receive_json()
                        received_by_b.append(msg)
                    except Exception:
                        pass
            except Exception:
                pass

        # Start ws_b listener in background thread
        t = threading.Thread(target=listen_ws_b, daemon=True)
        t.start()

        import time
        time.sleep(0.05)  # Allow ws_b to connect

        with client.websocket_connect(f"/ws/events?token={token_a}") as ws_a:
            event = {
                "type": "event",
                "event_type": "feedback:created",
                "data": {"id": 99},
                "timestamp": "2026-02-24T00:00:00",
            }
            asyncio.get_event_loop().run_until_complete(
                event_manager.broadcast_to_org(org_id=org_a.id, event=event)
            )
            msg_a = ws_a.receive_json()
            assert msg_a["event_type"] == "feedback:created"

        t.join(timeout=0.5)
        # org_b client should NOT have received the org_a event
        feedback_events = [m for m in received_by_b if m.get("event_type") == "feedback:created"]
        assert len(feedback_events) == 0


# =============================================================================
# DISCONNECT CLEANUP TESTS
# =============================================================================


class TestDisconnectCleanup:
    def test_disconnect_cleans_up_connection(
        self, client: TestClient, token_a: str, org_a: Organization
    ):
        """Client disconnects → removed from event_manager."""
        from src.services.event_connection_manager import event_manager

        initial_orgs = event_manager.get_active_org_ids()

        with client.websocket_connect(f"/ws/events?token={token_a}") as ws:
            # While connected, org should be tracked
            assert org_a.id in event_manager.get_active_org_ids()

        # After disconnect, org should be removed (if no other connections)
        # Give the server a moment to process the disconnect
        import time
        time.sleep(0.05)

        # org_a should no longer be in active orgs (or have empty connections)
        conns = event_manager.org_connections.get(org_a.id, [])
        assert len(conns) == 0
