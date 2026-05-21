"""
Winback detector service — Phase 3.2 (M4.1).

Detects when a previously churned customer submits new feedback and flags them
as a potential winback by setting has_potential_winback=True and inserting an
in-app notification of type 'winback_suggested'.

Entry point
-----------
    check(org_id, customer_email, db) -> None

The function is idempotent: if has_potential_winback is already True the call
is a no-op (no duplicate notifications fired).
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from src.models import CustomerChurnEvent, CustomerHealth, Notification, User

logger = logging.getLogger(__name__)

# Notification type constant — single source of truth.
WINBACK_NOTIFICATION_TYPE = "winback_suggested"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def check(org_id: int, customer_email: str, db: Session) -> None:
    """Detect and flag a potential winback for customer_email in org_id.

    Steps:
    1. Load CustomerHealth; return early if absent.
    2. Load most recent active CustomerChurnEvent (recovered_at IS NULL).
       If none, return (customer was never churned or already recovered).
    3. If has_potential_winback is already True, no-op (idempotent guard).
    4. Set has_potential_winback = True.
    5. Insert winback_suggested notification(s) with correct recipient(s).
    6. Commit.
    """
    health = _get_customer_health(org_id, customer_email, db)
    if health is None:
        return

    churn_event = _get_active_churn_event(org_id, customer_email, db)
    if churn_event is None:
        return

    if health.has_potential_winback:
        # Already flagged — idempotent guard, no new notifications.
        return

    health.has_potential_winback = True
    db.add(health)

    recipients = _get_notification_recipients(org_id, churn_event, db)
    days_since_churn = _days_since(churn_event.churned_at)

    title = f"Potential winback: {customer_email}"
    message = (
        f"{customer_email} sent new feedback after being marked as churned "
        f"({churn_event.reason_code}, {days_since_churn} days ago)."
    )
    metadata = {
        "customer_email": customer_email,
        "churn_event_id": churn_event.id,
        "days_since_churn": days_since_churn,
    }

    for user_id in recipients:
        _insert_notification(db, user_id, org_id, title, message, metadata)

    db.commit()


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _get_customer_health(
    org_id: int, customer_email: str, db: Session
) -> Optional[CustomerHealth]:
    """Return the CustomerHealth row or None if not found."""
    return (
        db.query(CustomerHealth)
        .filter(
            CustomerHealth.organization_id == org_id,
            CustomerHealth.customer_email == customer_email,
        )
        .first()
    )


def _get_active_churn_event(
    org_id: int, customer_email: str, db: Session
) -> Optional[CustomerChurnEvent]:
    """Return the most recent CustomerChurnEvent with recovered_at IS NULL, or None."""
    return (
        db.query(CustomerChurnEvent)
        .filter(
            CustomerChurnEvent.organization_id == org_id,
            CustomerChurnEvent.customer_email == customer_email,
            CustomerChurnEvent.recovered_at.is_(None),
        )
        .order_by(CustomerChurnEvent.churned_at.desc())
        .first()
    )


def _get_notification_recipients(
    org_id: int,
    churn_event: CustomerChurnEvent,
    db: Session,
) -> list[int]:
    """Return the list of user IDs that should receive the notification.

    If marked_by_user_id is set, return that single user.
    Otherwise, return all admin/owner users of the org.
    """
    if churn_event.marked_by_user_id is not None:
        return [churn_event.marked_by_user_id]

    # Fallback: all admin and owner users
    users = (
        db.query(User)
        .filter(
            User.organization_id == org_id,
            User.role.in_(["admin", "owner"]),
        )
        .all()
    )
    return [u.id for u in users]


def _insert_notification(
    db: Session,
    user_id: int,
    org_id: int,
    title: str,
    message: str,
    metadata: dict,
) -> None:
    """Insert a single winback_suggested Notification row."""
    notif = Notification(
        user_id=user_id,
        organization_id=org_id,
        type=WINBACK_NOTIFICATION_TYPE,
        title=title,
        message=message,
        metadata_=metadata,
        created_at=datetime.utcnow(),
    )
    db.add(notif)


def _days_since(dt: datetime) -> int:
    """Return the integer number of days between dt and now (UTC)."""
    delta = datetime.utcnow() - dt
    return max(0, delta.days)
