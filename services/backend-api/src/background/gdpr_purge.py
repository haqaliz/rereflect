"""GDPR Purge Task — deletes user data after the 30-day grace period.

This module exposes `check_deletion_requests(db)` which is called:
- By the Celery Beat scheduler (daily)
- Directly in tests
"""

import logging
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from src.models.user import User

logger = logging.getLogger(__name__)

GRACE_PERIOD_DAYS = 30


def _purge_user(db: Session, user: User) -> None:
    """Delete all data associated with *user* and then the user record itself."""
    from src.models.feedback_note import FeedbackNote
    from src.models.user_alert_preference import UserAlertPreference
    from src.models.conversation import Conversation
    from src.models.notification import Notification

    user_id = user.id
    org_id = user.organization_id

    logger.info(f"[gdpr_purge] Purging user id={user_id} email={user.email}")

    # Feedback notes authored by this user
    db.query(FeedbackNote).filter(FeedbackNote.author_id == user_id).delete(
        synchronize_session=False
    )

    # Alert preferences
    db.query(UserAlertPreference).filter(
        UserAlertPreference.user_id == user_id
    ).delete(synchronize_session=False)

    # Copilot conversations created by this user
    # Messages are cascade-deleted by FK
    db.query(Conversation).filter(
        Conversation.created_by_user_id == user_id
    ).delete(synchronize_session=False)

    # Notifications for this user
    try:
        db.query(Notification).filter(Notification.user_id == user_id).delete(
            synchronize_session=False
        )
    except Exception:
        pass  # Notification model may not exist in all test environments

    # Finally delete the user record
    db.delete(user)
    db.commit()

    logger.info(f"[gdpr_purge] User id={user_id} purged successfully")


def check_deletion_requests(db: Session) -> int:
    """Find and purge users whose 30-day grace period has expired.

    Returns the number of users purged.
    """
    cutoff = datetime.utcnow() - timedelta(days=GRACE_PERIOD_DAYS)

    users_to_purge = (
        db.query(User)
        .filter(
            User.is_deactivated.is_(True),
            User.deletion_requested_at.isnot(None),
            User.deletion_requested_at <= cutoff,
        )
        .all()
    )

    count = 0
    for user in users_to_purge:
        try:
            _purge_user(db, user)
            count += 1
        except Exception as exc:
            logger.error(f"[gdpr_purge] Failed to purge user id={user.id}: {exc}")
            db.rollback()

    logger.info(f"[gdpr_purge] Purge run complete. {count} user(s) deleted.")
    return count
