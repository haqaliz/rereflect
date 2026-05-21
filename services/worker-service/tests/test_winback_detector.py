"""
Tests for winback_detector.check() — Phase 3.2 (M4.1).

Written RED-first before implementation. All 10 tests must fail initially
with ImportError or AttributeError, then pass after winback_detector.py is
implemented.
"""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.models import (
    Base,
    CustomerChurnEvent,
    CustomerHealth,
    Notification,
    User,
    Organization,
)


# ---------------------------------------------------------------------------
# In-memory DB wiring (independent of conftest to avoid fixture collision)
# ---------------------------------------------------------------------------

SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

_engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_Session = sessionmaker(autocommit=False, autoflush=False, bind=_engine)


@pytest.fixture()
def db():
    Base.metadata.create_all(bind=_engine)
    session = _Session()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=_engine)


# ---------------------------------------------------------------------------
# Helper builders
# ---------------------------------------------------------------------------


def _make_org(db, plan: str = "business") -> Organization:
    org = Organization(name="Test Corp", plan=plan)
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def _make_user(db, org: Organization, role: str = "admin") -> User:
    user = User(
        email=f"user-{role}@test.com",
        organization_id=org.id,
        role=role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _make_health(
    db,
    org_id: int,
    email: str = "alice@example.com",
    has_potential_winback: bool = False,
) -> CustomerHealth:
    row = CustomerHealth(
        organization_id=org_id,
        customer_email=email,
        has_potential_winback=has_potential_winback,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _make_churn_event(
    db,
    org_id: int,
    email: str = "alice@example.com",
    reason_code: str = "price",
    recovered_at=None,
    marked_by_user_id=None,
    churned_at=None,
) -> CustomerChurnEvent:
    event = CustomerChurnEvent(
        organization_id=org_id,
        customer_email=email,
        churned_at=churned_at or (datetime.utcnow() - timedelta(days=10)),
        reason_code=reason_code,
        recovered_at=recovered_at,
        marked_by_user_id=marked_by_user_id,
        source="manual",
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def _count_notifications(db, org_id: int, notif_type: str) -> int:
    return (
        db.query(Notification)
        .filter(
            Notification.organization_id == org_id,
            Notification.type == notif_type,
        )
        .count()
    )


# ---------------------------------------------------------------------------
# Import the module under test (will raise ImportError in RED phase)
# ---------------------------------------------------------------------------

from src.services import winback_detector  # noqa: E402


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_check_noops_when_customer_has_no_health_row(db):
    """No CustomerHealth row → check() returns without raising or inserting anything."""
    org = _make_org(db)
    # No health row seeded
    winback_detector.check(org.id, "nobody@example.com", db)
    assert _count_notifications(db, org.id, "winback_suggested") == 0


def test_check_noops_when_no_churn_event_exists(db):
    """CustomerHealth present but no churn event → customer never marked churned; no winback."""
    org = _make_org(db)
    _make_health(db, org.id)
    winback_detector.check(org.id, "alice@example.com", db)
    assert _count_notifications(db, org.id, "winback_suggested") == 0


def test_check_noops_when_active_churn_event_is_already_recovered(db):
    """Most recent churn event has recovered_at set → customer is recovered; no winback."""
    org = _make_org(db)
    _make_health(db, org.id)
    _make_churn_event(db, org.id, recovered_at=datetime.utcnow())
    winback_detector.check(org.id, "alice@example.com", db)
    assert _count_notifications(db, org.id, "winback_suggested") == 0


def test_check_sets_has_potential_winback_when_active_churn_event_present(db):
    """Active churn event (recovered_at IS NULL) → has_potential_winback flipped to True."""
    org = _make_org(db)
    health = _make_health(db, org.id, has_potential_winback=False)
    _make_health_user(db, org)
    _make_churn_event(db, org.id)
    winback_detector.check(org.id, "alice@example.com", db)
    db.refresh(health)
    assert health.has_potential_winback is True


def test_check_creates_notification_of_type_winback_suggested(db):
    """Active churn event → one notification of type 'winback_suggested' is created."""
    org = _make_org(db)
    _make_health(db, org.id)
    _make_health_user(db, org)
    _make_churn_event(db, org.id)
    winback_detector.check(org.id, "alice@example.com", db)
    assert _count_notifications(db, org.id, "winback_suggested") >= 1


def test_check_notification_includes_customer_email_in_metadata(db):
    """Notification metadata JSON contains 'customer_email' key matching the customer."""
    org = _make_org(db)
    _make_health(db, org.id)
    _make_health_user(db, org)
    _make_churn_event(db, org.id)
    winback_detector.check(org.id, "alice@example.com", db)
    notif = (
        db.query(Notification)
        .filter(
            Notification.organization_id == org.id,
            Notification.type == "winback_suggested",
        )
        .first()
    )
    assert notif is not None
    meta = notif.metadata_
    assert meta is not None
    assert meta.get("customer_email") == "alice@example.com"


def test_check_notification_recipient_is_original_marker_when_available(db):
    """When marked_by_user_id is set, the notification is sent only to that user."""
    org = _make_org(db)
    _make_health(db, org.id)
    marker = _make_user(db, org, role="admin")
    other = _make_user_extra(db, org, email="other@test.com", role="member")
    _make_churn_event(db, org.id, marked_by_user_id=marker.id)
    winback_detector.check(org.id, "alice@example.com", db)
    notifications = (
        db.query(Notification)
        .filter(
            Notification.organization_id == org.id,
            Notification.type == "winback_suggested",
        )
        .all()
    )
    recipient_ids = {n.user_id for n in notifications}
    assert marker.id in recipient_ids
    assert other.id not in recipient_ids


def test_check_notification_recipients_fallback_to_org_admins_when_marker_null(db):
    """When marked_by_user_id is NULL, all admin/owner users receive the notification."""
    org = _make_org(db)
    _make_health(db, org.id)
    admin = _make_user(db, org, role="admin")
    owner = _make_user_extra(db, org, email="owner@test.com", role="owner")
    member = _make_user_extra(db, org, email="member@test.com", role="member")
    _make_churn_event(db, org.id, marked_by_user_id=None)
    winback_detector.check(org.id, "alice@example.com", db)
    notifications = (
        db.query(Notification)
        .filter(
            Notification.organization_id == org.id,
            Notification.type == "winback_suggested",
        )
        .all()
    )
    recipient_ids = {n.user_id for n in notifications}
    assert admin.id in recipient_ids
    assert owner.id in recipient_ids
    assert member.id not in recipient_ids


def test_check_is_idempotent_when_has_potential_winback_already_true(db):
    """If has_potential_winback is already True, check() is a no-op (no new notification)."""
    org = _make_org(db)
    _make_health(db, org.id, has_potential_winback=True)
    _make_health_user(db, org)
    _make_churn_event(db, org.id)
    # Call twice
    winback_detector.check(org.id, "alice@example.com", db)
    winback_detector.check(org.id, "alice@example.com", db)
    assert _count_notifications(db, org.id, "winback_suggested") == 0


def test_check_handles_multiple_churn_events_uses_latest_active(db):
    """Multiple churn events → uses the most recent one with recovered_at IS NULL."""
    org = _make_org(db)
    _make_health(db, org.id)
    _make_health_user(db, org)
    # Older event — recovered
    _make_churn_event(
        db, org.id,
        reason_code="price",
        recovered_at=datetime.utcnow() - timedelta(days=5),
        churned_at=datetime.utcnow() - timedelta(days=30),
    )
    # Newer event — active
    _make_churn_event(
        db, org.id,
        reason_code="competitor",
        recovered_at=None,
        churned_at=datetime.utcnow() - timedelta(days=3),
    )
    winback_detector.check(org.id, "alice@example.com", db)
    assert _count_notifications(db, org.id, "winback_suggested") >= 1
    notif = (
        db.query(Notification)
        .filter(
            Notification.organization_id == org.id,
            Notification.type == "winback_suggested",
        )
        .first()
    )
    # Metadata should reference the newest event's reason code
    assert "competitor" in notif.message


# ---------------------------------------------------------------------------
# Private helpers for multi-user test fixtures (avoid name collision)
# ---------------------------------------------------------------------------


def _make_health_user(db, org: Organization) -> User:
    """Create a default admin user so fallback notifications have a recipient."""
    user = User(
        email="admin@test.com",
        organization_id=org.id,
        role="admin",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _make_user_extra(db, org: Organization, email: str, role: str) -> User:
    user = User(
        email=email,
        organization_id=org.id,
        role=role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
