"""
Workflow tasks — auto-assignment of feedback items.
Mirrors the auto-assignment logic from backend-api/src/services/workflow_service.py
but runs as a periodic Celery task to catch items created by integrations and analysis.
"""

import logging
from datetime import datetime
from typing import Optional, List

import redis
from celery import shared_task

from src.database import get_db_session
from src.config import get_redis_url

logger = logging.getLogger(__name__)

_redis_client = None


def _get_redis():
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(get_redis_url(0))
    return _redis_client


def _auto_assign_feedback(db, feedback, org_id: int) -> Optional[int]:
    """
    Auto-assign a single feedback item using category rules first, then round-robin.
    Returns the assigned user ID or None.
    """
    from src.models import AssignmentRule, User, FeedbackItem
    from sqlalchemy import func

    # Try category-based rules (highest priority first)
    rules = db.query(AssignmentRule).filter(
        AssignmentRule.organization_id == org_id,
        AssignmentRule.is_active == True,
    ).order_by(AssignmentRule.priority.desc()).all()

    for rule in rules:
        field_value = getattr(feedback, rule.match_field, None)
        if field_value and field_value == rule.match_value:
            user = db.query(User).filter(
                User.id == rule.assign_to_user_id,
                User.organization_id == org_id,
            ).first()
            if user:
                return user.id

    # Fallback: round-robin (member with fewest open items)
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

    member = (
        db.query(User.id, func.coalesce(open_count.c.open_count, 0).label("cnt"))
        .outerjoin(open_count, User.id == open_count.c.assigned_to)
        .filter(User.organization_id == org_id)
        .order_by(func.coalesce(open_count.c.open_count, 0).asc(), User.id.asc())
        .first()
    )

    return member.id if member else None


def _dispatch_auto_assigned_notification(db, org_id: int, user_id: int, feedback_id: int) -> None:
    """Create in-app notification for auto-assigned feedback."""
    from src.models import Notification, UserAlertPreference, User

    pref = db.query(UserAlertPreference).filter(
        UserAlertPreference.user_id == user_id,
        UserAlertPreference.alert_type == "feedback_assigned",
    ).first()

    is_enabled = pref.is_enabled if pref else True
    channel_inapp = pref.channel_inapp if pref else True

    if not is_enabled or not channel_inapp:
        return

    from datetime import timedelta

    if pref and pref.retention_days:
        retention_days = pref.retention_days
    else:
        user = db.query(User).filter(User.id == user_id).first()
        retention_days = user.notification_retention_days if user else 30

    notification = Notification(
        user_id=user_id,
        organization_id=org_id,
        type="feedback_assigned",
        title="Feedback auto-assigned to you",
        message=f"Feedback #{feedback_id} was automatically assigned to you",
        link=f"/feedbacks/{feedback_id}",
        metadata_={"feedback_id": feedback_id, "auto_assigned": True},
        created_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(days=retention_days),
    )
    db.add(notification)


@shared_task
def auto_assign_unassigned_feedback() -> dict:
    """
    Periodic task: Auto-assign unassigned feedback for orgs with auto_assignment_enabled.
    Runs every 60 seconds via Celery Beat.
    Uses a Redis lock to prevent concurrent execution.
    """
    from src.models import Organization, FeedbackItem, FeedbackWorkflowEvent, User

    r = _get_redis()
    lock = r.lock("lock:auto_assign_unassigned_feedback", timeout=120, blocking=False)

    if not lock.acquire(blocking=False):
        return {"status": "skipped"}

    try:
        with get_db_session() as db:
            # Find orgs with auto-assignment enabled
            orgs = db.query(Organization).filter(
                Organization.auto_assignment_enabled == True,
            ).all()

            if not orgs:
                return {"status": "no_orgs", "assigned": 0}

            total_assigned = 0

            for org in orgs:
                # Find unassigned feedback items for this org
                unassigned = db.query(FeedbackItem).filter(
                    FeedbackItem.organization_id == org.id,
                    FeedbackItem.assigned_to == None,
                    FeedbackItem.workflow_status.in_(["new", "in_review"]),
                ).limit(100).all()

                if not unassigned:
                    continue

                for feedback in unassigned:
                    user_id = _auto_assign_feedback(db, feedback, org.id)
                    if user_id:
                        feedback.assigned_to = user_id

                        # Create workflow event
                        user = db.query(User).filter(User.id == user_id).first()
                        event = FeedbackWorkflowEvent(
                            feedback_id=feedback.id,
                            organization_id=org.id,
                            actor_id=user_id,
                            event_type="assigned",
                            old_value=None,
                            new_value=user.email if user else str(user_id),
                            metadata_={"auto_assigned": True},
                            created_at=datetime.utcnow(),
                        )
                        db.add(event)

                        # Dispatch notification
                        _dispatch_auto_assigned_notification(db, org.id, user_id, feedback.id)

                        total_assigned += 1

                db.commit()

            logger.info(f"Auto-assigned {total_assigned} feedback items across {len(orgs)} orgs")
            return {"status": "complete", "assigned": total_assigned, "orgs": len(orgs)}

    except Exception as e:
        logger.error(f"Auto-assignment task failed: {e}")
        return {"status": "error", "error": str(e)}
    finally:
        try:
            lock.release()
        except redis.exceptions.LockNotOwnedError:
            pass


@shared_task
def auto_assign_feedback_batch(org_id: int, feedback_ids: List[int]) -> dict:
    """
    Auto-assign a specific batch of feedback items.
    Called after analysis completes so category-based rules can match.
    """
    from src.models import Organization, FeedbackItem, FeedbackWorkflowEvent, User

    with get_db_session() as db:
        org = db.query(Organization).filter(Organization.id == org_id).first()
        if not org or not org.auto_assignment_enabled:
            return {"status": "disabled", "assigned": 0}

        items = db.query(FeedbackItem).filter(
            FeedbackItem.id.in_(feedback_ids),
            FeedbackItem.organization_id == org_id,
            FeedbackItem.assigned_to == None,
        ).all()

        assigned = 0
        for feedback in items:
            user_id = _auto_assign_feedback(db, feedback, org_id)
            if user_id:
                feedback.assigned_to = user_id

                user = db.query(User).filter(User.id == user_id).first()
                event = FeedbackWorkflowEvent(
                    feedback_id=feedback.id,
                    organization_id=org_id,
                    actor_id=user_id,
                    event_type="assigned",
                    old_value=None,
                    new_value=user.email if user else str(user_id),
                    metadata_={"auto_assigned": True},
                    created_at=datetime.utcnow(),
                )
                db.add(event)

                _dispatch_auto_assigned_notification(db, org_id, user_id, feedback.id)
                assigned += 1

        db.commit()
        return {"status": "complete", "assigned": assigned, "total": len(feedback_ids)}
