"""
Helpers for dispatching targeted workflow notifications directly from the backend-api.
Creates Notification records in the database for specific users, respecting their alert preferences.
"""
import logging
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any

from src.services.email_service import send_alert_email

logger = logging.getLogger(__name__)


def _create_targeted_notifications(
    db,
    org_id: int,
    target_user_ids: List[int],
    alert_type: str,
    title: str,
    message: str,
    link: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> int:
    """Create in-app notifications for specific users, respecting their preferences."""
    from src.models.notification import Notification
    from src.models.user import User
    from src.models.user_alert_preference import UserAlertPreference

    # Fetch preferences for these users + this alert type
    prefs = db.query(UserAlertPreference).filter(
        UserAlertPreference.user_id.in_(target_user_ids),
        UserAlertPreference.alert_type == alert_type,
    ).all()
    pref_map = {p.user_id: p for p in prefs}

    count = 0
    for uid in target_user_ids:
        pref = pref_map.get(uid)

        # Default: enabled, inapp on, email off
        is_enabled = pref.is_enabled if pref else True
        channel_inapp = pref.channel_inapp if pref else True
        channel_email = pref.channel_email if pref else False

        if not is_enabled:
            continue

        # In-app notification
        if channel_inapp:
            # Determine retention
            if pref and pref.retention_days:
                retention_days = pref.retention_days
            else:
                user = db.query(User).filter(User.id == uid).first()
                retention_days = user.notification_retention_days if user else 30

            notification = Notification(
                user_id=uid,
                organization_id=org_id,
                type=alert_type,
                title=title,
                message=message,
                link=link,
                metadata_=metadata,
                created_at=datetime.utcnow(),
                expires_at=datetime.utcnow() + timedelta(days=retention_days),
            )
            db.add(notification)
            count += 1

        # Email notification
        if channel_email:
            user = db.query(User).filter(User.id == uid).first()
            if user:
                send_alert_email(
                    to_email=user.email,
                    alert_type=alert_type,
                    alert_data={
                        "title": title,
                        "description": message,
                    },
                )

    return count


def dispatch_status_changed(org_id: int, actor, feedbacks: list, new_status: str):
    """Dispatch status_changed notifications to assigned users."""
    from src.database.session import SessionLocal

    try:
        db = SessionLocal()
        for fb in feedbacks:
            if fb.assigned_to and fb.assigned_to != actor.id:
                _create_targeted_notifications(
                    db, org_id,
                    target_user_ids=[fb.assigned_to],
                    alert_type="status_changed",
                    title=f"Status changed to {new_status.replace('_', ' ').title()}",
                    message=f"{actor.email} changed the status of feedback #{fb.id}",
                    link=f"/feedbacks/{fb.id}",
                    metadata={"feedback_id": fb.id, "new_status": new_status, "actor_email": actor.email},
                )
        db.commit()
        db.close()
    except Exception as e:
        logger.error(f"Failed to dispatch status_changed notification: {e}")


def dispatch_feedback_assigned(org_id: int, actor, assignee, feedbacks: list):
    """Dispatch feedback_assigned notifications to the assignee."""
    from src.database.session import SessionLocal

    try:
        db = SessionLocal()
        for fb in feedbacks:
            if assignee.id != actor.id:
                _create_targeted_notifications(
                    db, org_id,
                    target_user_ids=[assignee.id],
                    alert_type="feedback_assigned",
                    title="Feedback assigned to you",
                    message=f"{actor.email} assigned feedback #{fb.id} to you",
                    link=f"/feedbacks/{fb.id}",
                    metadata={"feedback_id": fb.id, "actor_email": actor.email},
                )
        db.commit()
        db.close()
    except Exception as e:
        logger.error(f"Failed to dispatch feedback_assigned notification: {e}")


def dispatch_health_drop_alert_impl(
    org_id: int,
    customer_email: str,
    customer_name,
    old_score: int,
    new_score: int,
    old_risk_level: str,
    new_risk_level: str,
    components: dict,
    is_recovery: bool = False,
) -> None:
    """
    Backend-api side implementation of health drop alert dispatch.
    Creates in-app Notification records and flags email/slack channels
    based on user preferences for the 'customer_health_drop' alert type.
    Delegates dedup and Slack to the worker-service notification_dispatch
    when called from the Celery context; when called inline (from health_score_service)
    this creates in-app notifications synchronously.
    """
    from src.database.session import SessionLocal
    from src.models.notification import Notification
    from src.models.user import User
    from src.models.user_alert_preference import UserAlertPreference
    from datetime import timedelta
    from urllib.parse import quote

    RISK_LEVEL_ORDER = {"healthy": 0, "moderate": 1, "at_risk": 2, "critical": 3}

    old_order = RISK_LEVEL_ORDER.get(old_risk_level, 0)
    new_order = RISK_LEVEL_ORDER.get(new_risk_level, 0)

    try:
        db = SessionLocal()
        users = db.query(User).filter(User.organization_id == org_id).all()
        if not users:
            db.close()
            return

        user_ids = [u.id for u in users]
        prefs = db.query(UserAlertPreference).filter(
            UserAlertPreference.user_id.in_(user_ids),
            UserAlertPreference.alert_type == "customer_health_drop",
        ).all()
        pref_by_user = {p.user_id: p for p in prefs}

        customer_link = f"/customers/{quote(customer_email, safe='')}"

        if is_recovery:
            title = f"Customer health improved: {customer_email}"
            message = (
                f"Health score recovered from {old_score} to {new_score} "
                f"({old_risk_level} → {new_risk_level})."
            )
        else:
            sorted_drivers = sorted(components.items(), key=lambda x: x[1])
            top_drivers = [k for k, _ in sorted_drivers[:2]]
            drivers_text = ", ".join(d.replace("_", " ").title() for d in top_drivers)
            title = f"Customer health drop: {customer_email}"
            message = (
                f"Health score dropped from {old_score} to {new_score} "
                f"({old_risk_level} → {new_risk_level}). "
                f"Top risk drivers: {drivers_text}."
            )

        notification_metadata = {
            "customer_email": customer_email,
            "customer_name": customer_name,
            "old_score": old_score,
            "new_score": new_score,
            "old_risk_level": old_risk_level,
            "new_risk_level": new_risk_level,
            "is_recovery": is_recovery,
            "components": components,
        }

        for user in users:
            pref = pref_by_user.get(user.id)
            is_enabled = pref.is_enabled if pref else True
            if not is_enabled:
                continue
            channel_inapp = pref.channel_inapp if pref else True
            if channel_inapp:
                retention_days = pref.retention_days if pref else 30
                notification = Notification(
                    user_id=user.id,
                    organization_id=org_id,
                    type="customer_health_drop",
                    title=title,
                    message=message,
                    link=customer_link,
                    metadata_=notification_metadata,
                    created_at=datetime.utcnow(),
                    expires_at=datetime.utcnow() + timedelta(days=retention_days),
                )
                db.add(notification)

        db.commit()
        db.close()
    except Exception as e:
        logger.error(f"dispatch_health_drop_alert_impl failed for {customer_email}: {e}")


def dispatch_note_added(org_id: int, actor, feedback, note):
    """Dispatch note_added notifications to assigned user + previous note authors."""
    from src.database.session import SessionLocal
    from src.models.feedback_note import FeedbackNote

    try:
        db = SessionLocal()
        target_ids = set()
        if feedback.assigned_to and feedback.assigned_to != actor.id:
            target_ids.add(feedback.assigned_to)

        prev_authors = db.query(FeedbackNote.author_id).filter(
            FeedbackNote.feedback_id == feedback.id,
            FeedbackNote.organization_id == org_id,
            FeedbackNote.author_id != actor.id,
        ).distinct().all()
        for (aid,) in prev_authors:
            target_ids.add(aid)

        if target_ids:
            _create_targeted_notifications(
                db, org_id,
                target_user_ids=list(target_ids),
                alert_type="note_added",
                title="New note on feedback",
                message=f"{actor.email} added a note on feedback #{feedback.id}",
                link=f"/feedbacks/{feedback.id}",
                metadata={"feedback_id": feedback.id, "note_id": note.id, "actor_email": actor.email},
            )
            db.commit()
        db.close()
    except Exception as e:
        logger.error(f"Failed to dispatch note_added notification: {e}")
