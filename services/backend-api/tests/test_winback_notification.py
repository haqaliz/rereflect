"""
Tests for winback_suggested notification type — Phase 3.2 (M4.1).

Verifies:
15. winback_suggested is a valid notification type (can be stored and queried)
16. POST /recover clears has_potential_winback flag
17. POST /recover does not dismiss/delete existing winback notifications (audit trail preserved)
"""

from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.api.auth import create_access_token, hash_password
from src.models.churn_event import CustomerChurnEvent
from src.models.customer_health import CustomerHealth
from src.models.notification import Notification
from src.models.organization import Organization
from src.models.user import User


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_org(db: Session, plan: str = "business") -> Organization:
    org = Organization(name="WinbackOrg", plan=plan)
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def _make_user(db: Session, org: Organization, role: str = "admin") -> User:
    user = User(
        email=f"user-{role}@winback.com",
        password_hash=hash_password("password123"),
        organization_id=org.id,
        role=role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _headers(user: User) -> dict:
    token = create_access_token({
        "user_id": user.id,
        "organization_id": user.organization_id,
        "role": user.role,
    })
    return {"Authorization": f"Bearer {token}"}


def _make_health(
    db: Session,
    org: Organization,
    email: str,
    has_potential_winback: bool = True,
) -> CustomerHealth:
    health = CustomerHealth(
        organization_id=org.id,
        customer_email=email,
        health_score=45,
        risk_level="at_risk",
        has_potential_winback=has_potential_winback,
    )
    db.add(health)
    db.commit()
    db.refresh(health)
    return health


def _make_churn_event(
    db: Session,
    org: Organization,
    email: str,
    recovered_at=None,
    marked_by_user_id=None,
) -> CustomerChurnEvent:
    event = CustomerChurnEvent(
        organization_id=org.id,
        customer_email=email,
        churned_at=datetime(2026, 3, 1),
        reason_code="price",
        recovered_at=recovered_at,
        marked_by_user_id=marked_by_user_id,
        source="manual",
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def _make_winback_notification(db: Session, org: Organization, user: User, email: str) -> Notification:
    notif = Notification(
        user_id=user.id,
        organization_id=org.id,
        type="winback_suggested",
        title=f"Potential winback: {email}",
        message=f"{email} sent new feedback after being marked as churned (price, 10 days ago).",
        metadata_={"customer_email": email, "churn_event_id": 1, "days_since_churn": 10},
    )
    db.add(notif)
    db.commit()
    db.refresh(notif)
    return notif


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_winback_suggested_is_valid_notification_type(db: Session, client: TestClient):
    """'winback_suggested' can be stored as a Notification.type and queried back."""
    org = _make_org(db)
    user = _make_user(db, org)

    notif = _make_winback_notification(db, org, user, "alice@example.com")

    result = (
        db.query(Notification)
        .filter(
            Notification.type == "winback_suggested",
            Notification.organization_id == org.id,
        )
        .first()
    )
    assert result is not None
    assert result.id == notif.id
    assert result.type == "winback_suggested"
    assert result.metadata_["customer_email"] == "alice@example.com"


def test_recover_endpoint_clears_has_potential_winback_flag(db: Session, client: TestClient):
    """POST /recover sets has_potential_winback=False on the CustomerHealth row."""
    org = _make_org(db)
    user = _make_user(db, org)
    health = _make_health(db, org, "alice@example.com", has_potential_winback=True)
    _make_churn_event(db, org, "alice@example.com", marked_by_user_id=user.id)

    resp = client.post(
        "/api/v1/customers/alice%40example.com/recover",
        json={},
        headers=_headers(user),
    )
    assert resp.status_code == 200

    db.refresh(health)
    assert health.has_potential_winback is False


def test_recover_endpoint_does_not_dismiss_existing_winback_notification(
    db: Session, client: TestClient
):
    """POST /recover clears the winback flag but does NOT delete or dismiss past notifications."""
    org = _make_org(db)
    user = _make_user(db, org)
    _make_health(db, org, "alice@example.com", has_potential_winback=True)
    _make_churn_event(db, org, "alice@example.com", marked_by_user_id=user.id)
    notif = _make_winback_notification(db, org, user, "alice@example.com")

    resp = client.post(
        "/api/v1/customers/alice%40example.com/recover",
        json={},
        headers=_headers(user),
    )
    assert resp.status_code == 200

    # Notification must still exist — it's an audit trail
    persisted = db.query(Notification).filter_by(id=notif.id).first()
    assert persisted is not None
    assert persisted.is_dismissed is False
    assert persisted.type == "winback_suggested"
