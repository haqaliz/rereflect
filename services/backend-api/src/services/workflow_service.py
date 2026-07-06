"""
Workflow service — auto-assignment engine and timeline event helpers.
"""
from datetime import datetime
from typing import List, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import func

from src.models.feedback import FeedbackItem
from src.models.feedback_workflow_event import FeedbackWorkflowEvent
from src.models.assignment_rule import AssignmentRule
from src.models.user import User


def apply_status_change(
    db: Session,
    feedbacks: List[FeedbackItem],
    new_status: str,
    *,
    organization_id: int,
    actor_id: Optional[int] = None,
    actor_label: str,
    resolution_note: Optional[str] = None,
) -> List[Tuple[FeedbackItem, str]]:
    """Mutate workflow_status and emit a timeline event for each feedback item
    whose status actually changes.

    Returns a list of ``(feedback, old_status)`` tuples for the items that
    changed (used by the caller for webhook/WS dispatch).  The caller is
    responsible for validating ``new_status``, committing, and handling
    cache/webhook/WS side effects.  ``actor_id`` may be ``None`` for API-key
    writes (the FK is nullable).  ``actor_label`` is accepted for parity with
    the webhook dispatch helper / caller ergonomics and is not persisted here.
    """
    changed: List[Tuple[FeedbackItem, str]] = []
    for fb in feedbacks:
        old_status = fb.workflow_status
        if old_status == new_status:
            continue
        fb.workflow_status = new_status
        meta = None
        if resolution_note and new_status == "resolved":
            meta = {"resolution_note": resolution_note}
        create_workflow_event(
            db, fb.id, organization_id, actor_id,
            "status_changed", old_value=old_status, new_value=new_status,
            metadata=meta,
        )
        changed.append((fb, old_status))
    return changed


def dispatch_status_webhooks(
    db: Session,
    org_id: int,
    changed: List[Tuple[FeedbackItem, str]],
    new_status: str,
    changed_by_label: str,
) -> None:
    """Fire ``feedback.status_changed`` webhook events for each changed item.

    Mirrors the loop previously inlined in the internal status-change route so
    that both the internal and public write paths dispatch identical payloads.
    Callers should wrap this in a best-effort try/except (fire-and-forget).
    """
    from src.services.webhook_dispatcher import dispatch_webhook_event
    for fb, old_status in changed:
        dispatch_webhook_event(
            db=db,
            org_id=org_id,
            event_type="feedback.status_changed",
            feedback=fb,
            changes={
                "old_status": old_status,
                "new_status": new_status,
                "changed_by": changed_by_label,
            },
        )


def create_workflow_event(
    db: Session,
    feedback_id: int,
    organization_id: int,
    actor_id: int,
    event_type: str,
    old_value: Optional[str] = None,
    new_value: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> FeedbackWorkflowEvent:
    """Create a timeline event for a feedback item."""
    event = FeedbackWorkflowEvent(
        feedback_id=feedback_id,
        organization_id=organization_id,
        actor_id=actor_id,
        event_type=event_type,
        old_value=old_value,
        new_value=new_value,
        metadata_=metadata,
        created_at=datetime.utcnow(),
    )
    db.add(event)
    return event


def auto_assign_feedback(db: Session, feedback: FeedbackItem, org_id: int) -> Optional[int]:
    """
    Auto-assign a feedback item using category rules first, then round-robin fallback.
    Returns the assigned user ID or None if no assignment was made.
    """
    # Try category-based rules first (highest priority first)
    rules = db.query(AssignmentRule).filter(
        AssignmentRule.organization_id == org_id,
        AssignmentRule.is_active == True,
    ).order_by(AssignmentRule.priority.desc()).all()

    for rule in rules:
        field_value = getattr(feedback, rule.match_field, None)
        if field_value and field_value == rule.match_value:
            # Verify the target user still belongs to the org
            user = db.query(User).filter(
                User.id == rule.assign_to_user_id,
                User.organization_id == org_id,
            ).first()
            if user:
                return user.id

    # Fallback to round-robin (load-balanced: member with fewest open items)
    return round_robin_assign(db, org_id)


def round_robin_assign(db: Session, org_id: int) -> Optional[int]:
    """
    Assign to the org member with the fewest open (new + in_review) feedback items.
    Returns user ID or None if no members exist.
    """
    # Subquery: count of open items per user
    open_count = (
        db.query(
            FeedbackItem.assigned_to,
            func.count(FeedbackItem.id).label("open_count"),
        )
        .filter(
            FeedbackItem.organization_id == org_id,
            FeedbackItem.workflow_status.in_(["new", "in_review"]),
            FeedbackItem.assigned_to.isnot(None),
        )
        .group_by(FeedbackItem.assigned_to)
        .subquery()
    )

    # Get all org members with their open counts (0 if none)
    members = (
        db.query(User.id, func.coalesce(open_count.c.open_count, 0).label("cnt"))
        .outerjoin(open_count, User.id == open_count.c.assigned_to)
        .filter(User.organization_id == org_id)
        .order_by(func.coalesce(open_count.c.open_count, 0).asc(), User.id.asc())
        .first()
    )

    return members.id if members else None
