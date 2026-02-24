"""
Real-time events WebSocket endpoint.

Protocol: wss://{host}/ws/events?token={jwt}

This is a passive endpoint — clients connect to receive push events.
The server sends heartbeat pings every 30 seconds and forwards events
broadcasted by EventConnectionManager.

Client → Server:
  { "type": "ping" }   # Optional client heartbeat

Server → Client:
  { "type": "ping" }   # Server heartbeat every 30s
  {
    "type": "event",
    "event_type": "notification:new",
    "data": { ... },
    "timestamp": "2026-02-24T...",
  }

Internal HTTP endpoint for Celery workers:
  POST /api/internal/events/emit
  Header: X-Internal-Secret: <INTERNAL_EVENTS_SECRET>
  Body: { "org_id": int, "event_type": str, "data": dict }
"""

import asyncio
import json
import logging
import os
import time
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.api.auth import decode_access_token
from src.database.session import get_db
from src.models.user import User
from src.services.event_connection_manager import event_manager
from src.services.event_emitter import emit_event

logger = logging.getLogger(__name__)

router = APIRouter(tags=["events-ws"])

HEARTBEAT_INTERVAL = 30   # seconds
IDLE_TIMEOUT = 600         # 10 minutes (passive endpoint, longer than copilot)

INTERNAL_SECRET = os.getenv("INTERNAL_EVENTS_SECRET", "dev-secret")


# -- Authentication ------------------------------------------------------------


def _authenticate_ws(token: Optional[str], db: Session):
    """Decode JWT and return (user, org) or (None, None) if invalid."""
    if not token:
        return None, None

    payload = decode_access_token(token)
    if not payload:
        return None, None

    user_id = payload.get("user_id")
    if not user_id:
        return None, None

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return None, None

    return user, user.organization


# -- WebSocket endpoint --------------------------------------------------------


@router.websocket("/ws/events")
async def events_ws(
    websocket: WebSocket,
    token: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    Real-time events WebSocket endpoint.
    Authenticate via ?token={jwt} query parameter.
    """
    user, org = _authenticate_ws(token, db)
    if user is None or org is None:
        await websocket.close(code=4001, reason="Invalid or expired token")
        return

    await event_manager.connect(websocket, user.id, org.id)
    logger.info(f"Events WS connected: user_id={user.id} org_id={org.id}")

    last_activity = time.time()

    try:
        while True:
            if time.time() - last_activity > IDLE_TIMEOUT:
                await websocket.close(code=1000, reason="Idle timeout")
                break

            try:
                raw = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=HEARTBEAT_INTERVAL,
                )
                last_activity = time.time()
            except asyncio.TimeoutError:
                # Send heartbeat ping
                try:
                    await websocket.send_json({"type": "ping"})
                except Exception:
                    break
                continue

            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                continue  # Ignore malformed messages on this passive endpoint

            msg_type = message.get("type")
            if msg_type == "ping":
                # Client heartbeat resets idle timer (already done above)
                pass
            # All other message types are silently ignored on this passive endpoint

    except WebSocketDisconnect:
        logger.info(f"Events WS disconnected: user_id={user.id}")
    finally:
        await event_manager.disconnect(websocket, user.id, org.id)


# -- Internal HTTP endpoint for Celery workers ---------------------------------


class InternalEventRequest(BaseModel):
    org_id: int
    event_type: str
    data: dict = {}
    exclude_user_id: Optional[int] = None


@router.post("/api/internal/events/emit", status_code=200)
async def internal_emit(
    request: InternalEventRequest,
    x_internal_secret: Optional[str] = Header(None),
):
    """
    Internal endpoint for Celery workers to push events.
    Protected by INTERNAL_EVENTS_SECRET shared secret.
    """
    if x_internal_secret != INTERNAL_SECRET:
        raise HTTPException(status_code=403, detail="Invalid internal secret")

    await emit_event(
        org_id=request.org_id,
        event_type=request.event_type,
        data=request.data,
        exclude_user_id=request.exclude_user_id,
    )

    return {"ok": True}
