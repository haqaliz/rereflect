"""
Event emitter helper for broadcasting real-time events to org members.

Usage from route handlers:
    from src.services.event_emitter import emit_event

    await emit_event(
        org_id=current_org.id,
        event_type="feedback:created",
        data={"id": feedback.id, "title": feedback.title},
        exclude_user_id=current_user.id,  # skip the actor
    )
"""

from datetime import datetime
from typing import Optional

from src.services.event_connection_manager import event_manager


async def emit_event(
    org_id: int,
    event_type: str,
    data: dict,
    exclude_user_id: Optional[int] = None,
) -> None:
    """Broadcast a typed event to all connected org members."""
    await event_manager.broadcast_to_org(
        org_id=org_id,
        event={
            "type": "event",
            "event_type": event_type,
            "data": data,
            "timestamp": datetime.utcnow().isoformat(),
        },
        exclude_user_id=exclude_user_id,
    )
