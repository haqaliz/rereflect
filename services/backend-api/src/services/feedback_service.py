"""
Shared feedback-mutation helpers used by both the internal dashboard API
(``src/api/routes/feedback.py``) and the public write API
(``src/api/routes/public_api.py``).

Keeping this logic in one place guarantees the two surfaces stay
behaviorally identical for shared operations (e.g. delete).
"""

from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from src.models.feedback import FeedbackItem


async def delete_feedback_item(db: Session, feedback: FeedbackItem, *, org_id: int) -> None:
    """Delete a single feedback item and run its side effects.

    Mirrors the internal single-item delete exactly:
      - delete + commit
      - if this was the customer's last feedback item, archive their
        ``CustomerHealth`` row
      - invalidate dashboard/analytics caches
      - emit a ``feedback:deleted`` event

    NB: does NOT null ``SlackAlertLog.feedback_id`` references — that
    behavior is bulk-delete-only (see ``bulk_delete_feedback``).
    """
    customer_email = feedback.customer_email
    feedback_id = feedback.id  # read before delete — attribute may expire after commit

    db.delete(feedback)
    db.commit()

    # Archive trigger: if this was the last feedback for the customer, archive their health record
    if customer_email:
        remaining = db.query(func.count(FeedbackItem.id)).filter(
            FeedbackItem.organization_id == org_id,
            FeedbackItem.customer_email == customer_email,
        ).scalar() or 0

        if remaining == 0:
            from src.models.customer_health import CustomerHealth
            health = db.query(CustomerHealth).filter(
                CustomerHealth.organization_id == org_id,
                CustomerHealth.customer_email == customer_email,
            ).first()
            if health:
                health.is_archived = True
                db.commit()

    from src.services.cache_service import cache_invalidate
    cache_invalidate(f"dashboard:{org_id}:*")
    cache_invalidate(f"analytics:{org_id}:*")

    from src.services.event_emitter import emit_event
    await emit_event(
        org_id=org_id,
        event_type="feedback:deleted",
        data={"id": feedback_id},
    )
