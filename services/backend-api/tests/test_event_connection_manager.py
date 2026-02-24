"""
TDD tests for EventConnectionManager (realtime events infrastructure).

Tests cover:
- Per-org connection registration/deregistration
- Broadcast to org (with and without actor exclusion)
- send_to_user across all org connections
- Dead connection cleanup on send failure
- Org isolation
- Active org ID tracking
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.services.event_connection_manager import EventConnectionManager


def make_ws() -> AsyncMock:
    """Create a mock WebSocket with accept and send_json as AsyncMocks."""
    ws = AsyncMock()
    ws.accept = AsyncMock()
    ws.send_json = AsyncMock()
    return ws


# =============================================================================
# CONNECT / DISCONNECT
# =============================================================================


class TestConnect:
    @pytest.mark.asyncio
    async def test_connect_registers_connection_under_org(self):
        """connect(ws, user_id=1, org_id=10) → org_connections[10] contains the ws."""
        manager = EventConnectionManager()
        ws = make_ws()

        await manager.connect(ws, user_id=1, org_id=10)

        assert 10 in manager.org_connections
        connections = manager.org_connections[10]
        assert any(w is ws for w, uid in connections)

    @pytest.mark.asyncio
    async def test_connect_calls_ws_accept(self):
        """connect() calls websocket.accept()."""
        manager = EventConnectionManager()
        ws = make_ws()

        await manager.connect(ws, user_id=1, org_id=10)

        ws.accept.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_disconnect_removes_connection(self):
        """connect then disconnect → org_connections[10] is empty (but key may remain)."""
        manager = EventConnectionManager()
        ws = make_ws()

        await manager.connect(ws, user_id=1, org_id=10)
        await manager.disconnect(ws, user_id=1, org_id=10)

        # Either key is removed or list is empty
        conns = manager.org_connections.get(10, [])
        assert not any(w is ws for w, uid in conns)

    @pytest.mark.asyncio
    async def test_disconnect_cleans_empty_org(self):
        """After the last connection disconnects, the org_id key is removed."""
        manager = EventConnectionManager()
        ws = make_ws()

        await manager.connect(ws, user_id=1, org_id=10)
        await manager.disconnect(ws, user_id=1, org_id=10)

        assert 10 not in manager.org_connections


# =============================================================================
# BROADCAST TO ORG
# =============================================================================


class TestBroadcastToOrg:
    @pytest.mark.asyncio
    async def test_broadcast_to_org_sends_to_all_members(self):
        """3 users in org 10, broadcast → all 3 receive the event."""
        manager = EventConnectionManager()
        ws1, ws2, ws3 = make_ws(), make_ws(), make_ws()

        await manager.connect(ws1, user_id=1, org_id=10)
        await manager.connect(ws2, user_id=2, org_id=10)
        await manager.connect(ws3, user_id=3, org_id=10)

        event = {"type": "event", "event_type": "feedback:created", "data": {}}
        await manager.broadcast_to_org(org_id=10, event=event)

        ws1.send_json.assert_awaited_once_with(event)
        ws2.send_json.assert_awaited_once_with(event)
        ws3.send_json.assert_awaited_once_with(event)

    @pytest.mark.asyncio
    async def test_broadcast_excludes_actor(self):
        """broadcast with exclude_user_id=1 → user 1 does NOT receive, users 2 and 3 do."""
        manager = EventConnectionManager()
        ws1, ws2, ws3 = make_ws(), make_ws(), make_ws()

        await manager.connect(ws1, user_id=1, org_id=10)
        await manager.connect(ws2, user_id=2, org_id=10)
        await manager.connect(ws3, user_id=3, org_id=10)

        event = {"type": "event", "event_type": "feedback:created", "data": {}}
        await manager.broadcast_to_org(org_id=10, event=event, exclude_user_id=1)

        ws1.send_json.assert_not_awaited()
        ws2.send_json.assert_awaited_once_with(event)
        ws3.send_json.assert_awaited_once_with(event)

    @pytest.mark.asyncio
    async def test_broadcast_to_empty_org_is_noop(self):
        """broadcast to org with no connections → no errors raised."""
        manager = EventConnectionManager()
        event = {"type": "event", "event_type": "feedback:created", "data": {}}
        # Should not raise
        await manager.broadcast_to_org(org_id=999, event=event)

    @pytest.mark.asyncio
    async def test_dead_connection_cleaned_on_send_failure(self):
        """If ws.send_json raises, that connection is silently removed."""
        manager = EventConnectionManager()
        ws_dead = make_ws()
        ws_alive = make_ws()

        ws_dead.send_json.side_effect = Exception("Connection reset")

        await manager.connect(ws_dead, user_id=1, org_id=10)
        await manager.connect(ws_alive, user_id=2, org_id=10)

        event = {"type": "event", "event_type": "test", "data": {}}
        # Should not raise even though one connection is dead
        await manager.broadcast_to_org(org_id=10, event=event)

        # Dead connection should be removed
        conns = manager.org_connections.get(10, [])
        assert not any(w is ws_dead for w, uid in conns)
        # Alive connection should still be there
        assert any(w is ws_alive for w, uid in conns)


# =============================================================================
# SEND TO USER
# =============================================================================


class TestSendToUser:
    @pytest.mark.asyncio
    async def test_send_to_user_sends_to_all_user_connections(self):
        """User has 2 tabs (2 WS connections), send_to_user → both receive."""
        manager = EventConnectionManager()
        ws_tab1, ws_tab2 = make_ws(), make_ws()

        await manager.connect(ws_tab1, user_id=1, org_id=10)
        await manager.connect(ws_tab2, user_id=1, org_id=10)

        event = {"type": "event", "event_type": "notification:new", "data": {}}
        await manager.send_to_user(user_id=1, event=event)

        ws_tab1.send_json.assert_awaited_once_with(event)
        ws_tab2.send_json.assert_awaited_once_with(event)

    @pytest.mark.asyncio
    async def test_send_to_user_unknown_user_is_noop(self):
        """send to non-connected user → no errors raised."""
        manager = EventConnectionManager()
        event = {"type": "event", "event_type": "notification:new", "data": {}}
        # Should not raise
        await manager.send_to_user(user_id=9999, event=event)


# =============================================================================
# ACTIVE ORG IDS
# =============================================================================


class TestGetActiveOrgIds:
    @pytest.mark.asyncio
    async def test_get_active_org_ids(self):
        """Connect users in orgs 10, 20 → get_active_org_ids returns {10, 20}."""
        manager = EventConnectionManager()
        ws1, ws2 = make_ws(), make_ws()

        await manager.connect(ws1, user_id=1, org_id=10)
        await manager.connect(ws2, user_id=2, org_id=20)

        org_ids = manager.get_active_org_ids()
        assert org_ids == {10, 20}


# =============================================================================
# ORG ISOLATION
# =============================================================================


class TestOrgIsolation:
    @pytest.mark.asyncio
    async def test_multiple_orgs_isolated(self):
        """broadcast to org 10 → org 20 users do NOT receive."""
        manager = EventConnectionManager()
        ws_org10 = make_ws()
        ws_org20 = make_ws()

        await manager.connect(ws_org10, user_id=1, org_id=10)
        await manager.connect(ws_org20, user_id=2, org_id=20)

        event = {"type": "event", "event_type": "feedback:created", "data": {}}
        await manager.broadcast_to_org(org_id=10, event=event)

        ws_org10.send_json.assert_awaited_once_with(event)
        ws_org20.send_json.assert_not_awaited()
