"""
WebSocket connection manager for real-time event broadcasting.

Tracks active connections grouped per organization. Supports broadcast
to an entire org (with optional actor exclusion) and targeted send to
a specific user across all their connections (multiple tabs/devices).
"""

from typing import Dict, List, Set, Tuple, Optional
from fastapi import WebSocket


class EventConnectionManager:
    """Manages WS connections for real-time event broadcasting, grouped by org."""

    def __init__(self):
        # org_id → list of (websocket, user_id) tuples
        self.org_connections: Dict[int, List[Tuple[WebSocket, int]]] = {}

    async def connect(self, ws: WebSocket, user_id: int, org_id: int) -> None:
        """Accept and register connection under the org."""
        await ws.accept()
        if org_id not in self.org_connections:
            self.org_connections[org_id] = []
        self.org_connections[org_id].append((ws, user_id))

    async def disconnect(self, ws: WebSocket, user_id: int, org_id: int) -> None:
        """Remove connection from org group, clean up empty orgs."""
        if org_id not in self.org_connections:
            return
        self.org_connections[org_id] = [
            (w, uid)
            for w, uid in self.org_connections[org_id]
            if w is not ws
        ]
        if not self.org_connections[org_id]:
            del self.org_connections[org_id]

    async def broadcast_to_org(
        self,
        org_id: int,
        event: dict,
        exclude_user_id: Optional[int] = None,
    ) -> None:
        """Send event to all org members, optionally excluding the actor."""
        if org_id not in self.org_connections:
            return

        dead: List[Tuple[WebSocket, int]] = []
        for ws, uid in list(self.org_connections[org_id]):
            if exclude_user_id is not None and uid == exclude_user_id:
                continue
            try:
                await ws.send_json(event)
            except Exception:
                dead.append((ws, uid))

        for ws, uid in dead:
            await self.disconnect(ws, uid, org_id)

    async def send_to_user(self, user_id: int, event: dict) -> None:
        """Send event to a specific user (all their connections across all orgs)."""
        dead: List[Tuple[WebSocket, int, int]] = []  # (ws, uid, org_id)
        for org_id, conns in list(self.org_connections.items()):
            for ws, uid in list(conns):
                if uid != user_id:
                    continue
                try:
                    await ws.send_json(event)
                except Exception:
                    dead.append((ws, uid, org_id))

        for ws, uid, org_id in dead:
            await self.disconnect(ws, uid, org_id)

    def get_active_org_ids(self) -> Set[int]:
        """Return the set of org IDs with at least one active connection."""
        return set(self.org_connections.keys())


# Singleton instance importable by route handlers and workers
event_manager = EventConnectionManager()
