"""
WebSocket connection manager for the AI Copilot (M2.2).

Tracks active connections per user, supports sending targeted messages.
"""

import asyncio
from typing import Dict, List, Optional
from fastapi import WebSocket


class ConnectionManager:
    """Manages active WebSocket connections for the AI Copilot."""

    def __init__(self):
        # user_id → list of WebSocket connections (multiple tabs/devices)
        self._connections: Dict[int, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, user_id: int) -> None:
        """Register a new WebSocket connection for a user."""
        await websocket.accept()
        if user_id not in self._connections:
            self._connections[user_id] = []
        self._connections[user_id].append(websocket)

    def disconnect(self, websocket: WebSocket, user_id: int) -> None:
        """Remove a WebSocket connection when it closes."""
        if user_id in self._connections:
            self._connections[user_id] = [
                ws for ws in self._connections[user_id] if ws is not websocket
            ]
            if not self._connections[user_id]:
                del self._connections[user_id]

    async def send_to_user(self, user_id: int, message: dict) -> None:
        """Send a JSON message to all connections for a given user."""
        if user_id not in self._connections:
            return
        dead = []
        for ws in self._connections[user_id]:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws, user_id)

    async def send(self, websocket: WebSocket, message: dict) -> None:
        """Send a JSON message to a specific WebSocket connection."""
        await websocket.send_json(message)

    def get_active_user_ids(self) -> List[int]:
        """Return list of user IDs with active connections."""
        return list(self._connections.keys())

    def get_active_connections(self) -> int:
        """Return total number of active connections."""
        return sum(len(conns) for conns in self._connections.values())


# Singleton instance used by the WebSocket route
manager = ConnectionManager()
