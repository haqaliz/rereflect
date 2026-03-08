"""
Linear webhook receiver.
Handles inbound events from Linear (issue status changes) and syncs them to Rereflect.
"""

import hashlib
import hmac
import json
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy.orm import Session

from src.database.session import get_db
from src.models.feedback import FeedbackItem
from src.models.feedback_workflow_event import FeedbackWorkflowEvent
from src.models.linear_integration import (
    FeedbackLinearIssue,
    LinearIntegration,
    LinearStatusMapping,
)

# FastAPI dependency injection — imported with Depends at call site
from fastapi import Depends

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/webhooks/linear", tags=["linear-webhooks"])


def _verify_linear_signature(body: bytes, signature: str, secret: str) -> bool:
    """Verify Linear webhook HMAC-SHA256 signature."""
    if not secret:
        logger.warning("No webhook secret configured — skipping verification")
        return True
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def _find_integration_by_secret(signature: str, body: bytes, db: Session) -> Optional[LinearIntegration]:
    """
    Find the LinearIntegration whose webhook_secret matches the given signature.
    Linear sends a single global webhook, so we check all active integrations.
    """
    active_integrations = (
        db.query(LinearIntegration)
        .filter(LinearIntegration.is_active.is_(True))
        .all()
    )
    for integration in active_integrations:
        if integration.webhook_secret and _verify_linear_signature(
            body, signature, integration.webhook_secret
        ):
            return integration
    return None


def emit_event(org_id: int, event_type: str, payload: dict) -> None:
    """Emit a real-time event via EventConnectionManager (best effort)."""
    try:
        from src.api.routes.events_ws import manager
        import asyncio
        loop = asyncio.get_event_loop()
        loop.run_until_complete(
            manager.broadcast_to_org(org_id, {"type": event_type, **payload})
        )
    except Exception as exc:
        logger.debug(f"Real-time event emission failed (non-critical): {exc}")


@router.post("/inbound")
async def linear_webhook_inbound(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Receive Linear webhook events and sync issue status changes to Rereflect.

    Flow:
    1. Verify HMAC-SHA256 signature against stored webhook_secret(s)
    2. Parse event — only handle Issue updates for v1
    3. Look up linked FeedbackLinearIssue by linear_issue_id
    4. Update linear_status, linear_assignee, linear_priority
    5. Map Linear status → Rereflect workflow_status via LinearStatusMapping
    6. Add timeline FeedbackWorkflowEvent
    7. Emit real-time event
    """
    body = await request.body()
    signature = request.headers.get("Linear-Signature", "")

    if not signature:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Linear-Signature header.",
        )

    # Find matching integration by verifying signature against each org's secret
    integration = _find_integration_by_secret(signature, body, db)
    if not integration:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook signature.",
        )

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload.",
        )

    event_type = payload.get("type", "")
    action = payload.get("action", "")
    data = payload.get("data", {})

    # Only handle Issue events for v1
    if event_type != "Issue":
        logger.debug(f"Ignoring Linear webhook event type: {event_type}")
        return {"status": "ignored", "reason": f"event type '{event_type}' not handled"}

    linear_issue_id = data.get("id")
    if not linear_issue_id:
        return {"status": "ignored", "reason": "no issue id in payload"}

    # Look up linked feedback issue
    link = (
        db.query(FeedbackLinearIssue)
        .filter(FeedbackLinearIssue.linear_issue_id == linear_issue_id)
        .first()
    )
    if not link:
        logger.debug(f"No linked feedback found for Linear issue {linear_issue_id}")
        return {"status": "ignored", "reason": "issue not linked to any feedback"}

    org_id = link.organization_id

    # Extract updated fields from payload
    state_data = data.get("state", {})
    new_status_name = state_data.get("name") if state_data else None
    new_status_type = state_data.get("type") if state_data else None
    assignee_data = data.get("assignee")
    new_assignee = assignee_data.get("name") if assignee_data else None
    new_priority = data.get("priority")

    old_status = link.linear_status
    status_changed = new_status_name and new_status_name != old_status

    # Update linked issue record
    if new_status_name is not None:
        link.linear_status = new_status_name
    if new_assignee is not None:
        link.linear_assignee = new_assignee
    if new_priority is not None:
        link.linear_priority = new_priority
    link.updated_at = datetime.utcnow()
    db.flush()

    # If status changed: look up Rereflect status mapping and update feedback
    if status_changed and new_status_type:
        status_mapping = (
            db.query(LinearStatusMapping)
            .filter(
                LinearStatusMapping.organization_id == org_id,
                LinearStatusMapping.linear_status_type == new_status_type,
            )
            .first()
        )
        if status_mapping:
            feedback = db.query(FeedbackItem).filter(
                FeedbackItem.id == link.feedback_id
            ).first()
            if feedback:
                feedback.workflow_status = status_mapping.rereflect_status
                db.flush()

        # Add timeline entry
        event = FeedbackWorkflowEvent(
            feedback_id=link.feedback_id,
            organization_id=org_id,
            actor_id=None,  # System action
            event_type="linear_status_changed",
            old_value=old_status,
            new_value=new_status_name,
            metadata_={
                "linear_issue_identifier": link.linear_issue_identifier,
                "linear_issue_url": link.linear_issue_url,
                "linear_status": new_status_name,
                "rereflect_status": status_mapping.rereflect_status if status_mapping else None,
            },
        )
        db.add(event)

    db.commit()

    # Emit real-time event
    emit_event(
        org_id=org_id,
        event_type="linear_issue_updated",
        payload={
            "feedback_id": link.feedback_id,
            "linear_issue_id": linear_issue_id,
            "linear_issue_identifier": link.linear_issue_identifier,
            "linear_status": link.linear_status,
        },
    )

    logger.info(f"Processed Linear webhook for issue {link.linear_issue_identifier}")
    return {"status": "ok", "processed": True}
