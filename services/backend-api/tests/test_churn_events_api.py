"""
Tests for Churn Events API (M4.1 Phase 2.1) — strict TDD.

All tests are written before the implementation (RED phase).
"""

import csv
import io
from datetime import datetime, timedelta
from typing import Optional

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.api.auth import create_access_token, hash_password
from src.models.churn_event import CustomerChurnEvent
from src.models.customer_health import CustomerHealth
from src.models.organization import Organization
from src.models.user import User


# ---------------------------------------------------------------------------
# Helpers / shared fixtures
# ---------------------------------------------------------------------------


def _make_org(db: Session, plan: str = "business") -> Organization:
    org = Organization(name=f"Org-{plan}", plan=plan)
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def _make_user(db: Session, org: Organization, role: str = "admin", is_system_admin: bool = False) -> User:
    user = User(
        email=f"user-{org.id}-{role}@example.com",
        password_hash=hash_password("password123"),
        organization_id=org.id,
        role=role,
        is_system_admin=is_system_admin,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _headers(user: User) -> dict:
    token = create_access_token({"user_id": user.id, "organization_id": user.organization_id, "role": user.role})
    return {"Authorization": f"Bearer {token}"}


def _make_churn_event(
    db: Session,
    org: Organization,
    email: str,
    reason_code: str = "price",
    churned_at: Optional[datetime] = None,
    recovered_at: Optional[datetime] = None,
    marked_by_user_id: Optional[int] = None,
    source: str = "manual",
) -> CustomerChurnEvent:
    event = CustomerChurnEvent(
        organization_id=org.id,
        customer_email=email,
        churned_at=churned_at or datetime.utcnow(),
        reason_code=reason_code,
        recovered_at=recovered_at,
        marked_by_user_id=marked_by_user_id,
        source=source,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def _make_health(db: Session, org: Organization, email: str) -> CustomerHealth:
    health = CustomerHealth(
        organization_id=org.id,
        customer_email=email,
        health_score=50,
        risk_level="moderate",
        probability_computed_at=datetime.utcnow(),
        has_potential_winback=True,
    )
    db.add(health)
    db.commit()
    db.refresh(health)
    return health


def _build_csv(rows: list[dict]) -> bytes:
    """Build CSV bytes from list of row dicts."""
    buf = io.StringIO()
    fieldnames = ["email", "churned_at", "reason_code", "reason_text"]
    writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return buf.getvalue().encode()


# ---------------------------------------------------------------------------
# POST /api/v1/customers/{email}/churn-event
# ---------------------------------------------------------------------------


def test_post_churn_event_creates_record_for_business_plan_org(client: TestClient, db: Session):
    org = _make_org(db, plan="business")
    user = _make_user(db, org)
    resp = client.post(
        "/api/v1/customers/alice%40example.com/churn-event",
        json={"reason_code": "price", "customer_email": "alice@example.com"},
        headers=_headers(user),
    )
    assert resp.status_code == 201
    assert db.query(CustomerChurnEvent).filter_by(organization_id=org.id).count() == 1


def test_post_churn_event_returns_201_with_response_schema(client: TestClient, db: Session):
    org = _make_org(db, plan="business")
    user = _make_user(db, org)
    resp = client.post(
        "/api/v1/customers/bob%40example.com/churn-event",
        json={"reason_code": "competitor", "customer_email": "bob@example.com"},
        headers=_headers(user),
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["reason_code"] == "competitor"
    assert body["customer_email"] == "bob@example.com"
    assert "id" in body
    assert "churned_at" in body
    assert "created_at" in body
    assert body["source"] == "manual"


def test_post_churn_event_blocked_for_free_plan(client: TestClient, db: Session):
    org = _make_org(db, plan="free")
    user = _make_user(db, org)
    resp = client.post(
        "/api/v1/customers/alice%40example.com/churn-event",
        json={"reason_code": "price", "customer_email": "alice@example.com"},
        headers=_headers(user),
    )
    assert resp.status_code == 403


def test_post_churn_event_blocked_for_pro_plan(client: TestClient, db: Session):
    org = _make_org(db, plan="pro")
    user = _make_user(db, org)
    resp = client.post(
        "/api/v1/customers/alice%40example.com/churn-event",
        json={"reason_code": "price", "customer_email": "alice@example.com"},
        headers=_headers(user),
    )
    assert resp.status_code == 403


def test_post_churn_event_rejects_invalid_reason_code(client: TestClient, db: Session):
    org = _make_org(db, plan="business")
    user = _make_user(db, org)
    resp = client.post(
        "/api/v1/customers/alice%40example.com/churn-event",
        json={"reason_code": "INVALID_CODE", "customer_email": "alice@example.com"},
        headers=_headers(user),
    )
    assert resp.status_code == 422


def test_post_churn_event_normalizes_email_lowercase(client: TestClient, db: Session):
    org = _make_org(db, plan="business")
    user = _make_user(db, org)
    resp = client.post(
        "/api/v1/customers/Alice%40Example.COM/churn-event",
        json={"reason_code": "price", "customer_email": "Alice@Example.COM"},
        headers=_headers(user),
    )
    assert resp.status_code == 201
    assert resp.json()["customer_email"] == "alice@example.com"


def test_post_churn_event_defaults_churned_at_to_now_when_omitted(client: TestClient, db: Session):
    org = _make_org(db, plan="business")
    user = _make_user(db, org)
    before = datetime.utcnow()
    resp = client.post(
        "/api/v1/customers/carol%40example.com/churn-event",
        json={"reason_code": "other", "customer_email": "carol@example.com"},
        headers=_headers(user),
    )
    after = datetime.utcnow()
    assert resp.status_code == 201
    churned_at = datetime.fromisoformat(resp.json()["churned_at"].replace("Z", ""))
    assert before <= churned_at <= after


def test_post_churn_event_rejects_duplicate_for_same_org_email_date(client: TestClient, db: Session):
    org = _make_org(db, plan="business")
    user = _make_user(db, org)
    ts = "2026-01-15T10:00:00"
    payload = {"reason_code": "price", "customer_email": "dave@example.com", "churned_at": ts}
    r1 = client.post("/api/v1/customers/dave%40example.com/churn-event", json=payload, headers=_headers(user))
    assert r1.status_code == 201
    r2 = client.post("/api/v1/customers/dave%40example.com/churn-event", json=payload, headers=_headers(user))
    assert r2.status_code == 409


def test_post_churn_event_persists_marked_by_user_id_from_jwt(client: TestClient, db: Session):
    org = _make_org(db, plan="business")
    user = _make_user(db, org)
    resp = client.post(
        "/api/v1/customers/eve%40example.com/churn-event",
        json={"reason_code": "price", "customer_email": "eve@example.com"},
        headers=_headers(user),
    )
    assert resp.status_code == 201
    assert resp.json()["marked_by_user_id"] == user.id


def test_post_churn_event_invalidates_probability_computed_at(client: TestClient, db: Session):
    org = _make_org(db, plan="business")
    user = _make_user(db, org)
    health = _make_health(db, org, "frank@example.com")
    assert health.probability_computed_at is not None
    resp = client.post(
        "/api/v1/customers/frank%40example.com/churn-event",
        json={"reason_code": "competitor", "customer_email": "frank@example.com"},
        headers=_headers(user),
    )
    assert resp.status_code == 201
    db.refresh(health)
    assert health.probability_computed_at is None


# ---------------------------------------------------------------------------
# POST /api/v1/customers/{email}/recover
# ---------------------------------------------------------------------------


def test_post_recover_sets_recovered_at_on_active_event(client: TestClient, db: Session):
    org = _make_org(db, plan="business")
    user = _make_user(db, org)
    event = _make_churn_event(db, org, "grace@example.com")
    resp = client.post(
        "/api/v1/customers/grace%40example.com/recover",
        json={"recovered_at": "2026-02-01T00:00:00", "note": "came back"},
        headers=_headers(user),
    )
    assert resp.status_code == 200
    db.refresh(event)
    assert event.recovered_at is not None


def test_post_recover_clears_has_potential_winback_flag(client: TestClient, db: Session):
    org = _make_org(db, plan="business")
    user = _make_user(db, org)
    _make_churn_event(db, org, "heidi@example.com")
    health = _make_health(db, org, "heidi@example.com")
    assert health.has_potential_winback is True
    client.post(
        "/api/v1/customers/heidi%40example.com/recover",
        json={},
        headers=_headers(user),
    )
    db.refresh(health)
    assert health.has_potential_winback is False


def test_post_recover_returns_404_when_no_active_event(client: TestClient, db: Session):
    org = _make_org(db, plan="business")
    user = _make_user(db, org)
    resp = client.post(
        "/api/v1/customers/nobody%40example.com/recover",
        json={},
        headers=_headers(user),
    )
    assert resp.status_code == 404


def test_post_recover_uses_now_when_recovered_at_omitted(client: TestClient, db: Session):
    org = _make_org(db, plan="business")
    user = _make_user(db, org)
    _make_churn_event(db, org, "ivan@example.com")
    before = datetime.utcnow()
    resp = client.post(
        "/api/v1/customers/ivan%40example.com/recover",
        json={},
        headers=_headers(user),
    )
    after = datetime.utcnow()
    assert resp.status_code == 200
    recovered_at = datetime.fromisoformat(resp.json()["recovered_at"].replace("Z", ""))
    assert before <= recovered_at <= after


def test_post_recover_only_affects_latest_active_event_when_multiple_history(client: TestClient, db: Session):
    org = _make_org(db, plan="business")
    user = _make_user(db, org)
    # Older recovered event
    old_time = datetime.utcnow() - timedelta(days=30)
    old_event = _make_churn_event(
        db, org, "judy@example.com",
        churned_at=old_time,
        recovered_at=datetime.utcnow() - timedelta(days=10),
    )
    # Newer active event
    new_event = _make_churn_event(db, org, "judy@example.com", churned_at=datetime.utcnow() - timedelta(days=5))
    resp = client.post(
        "/api/v1/customers/judy%40example.com/recover",
        json={},
        headers=_headers(user),
    )
    assert resp.status_code == 200
    db.refresh(new_event)
    db.refresh(old_event)
    assert new_event.recovered_at is not None
    # Old event's recovered_at is unchanged (still the old date)
    assert old_event.recovered_at is not None
    assert old_event.recovered_at < new_event.recovered_at


# ---------------------------------------------------------------------------
# DELETE /api/v1/customers/{email}/churn-event/{event_id}
# ---------------------------------------------------------------------------


def test_delete_churn_event_succeeds_for_original_author_within_24h(client: TestClient, db: Session):
    org = _make_org(db, plan="business")
    user = _make_user(db, org)
    event = _make_churn_event(db, org, "karl@example.com", marked_by_user_id=user.id)
    resp = client.delete(
        f"/api/v1/customers/karl%40example.com/churn-event/{event.id}",
        headers=_headers(user),
    )
    assert resp.status_code == 204
    assert db.query(CustomerChurnEvent).filter_by(id=event.id).first() is None


def test_delete_churn_event_succeeds_for_system_admin_anytime(client: TestClient, db: Session):
    org = _make_org(db, plan="business")
    author = _make_user(db, org, role="member")
    admin = _make_user(db, org, role="admin", is_system_admin=True)
    # Event created >24h ago by a different user
    event = _make_churn_event(db, org, "lara@example.com", marked_by_user_id=author.id)
    event.created_at = datetime.utcnow() - timedelta(hours=48)
    db.commit()
    resp = client.delete(
        f"/api/v1/customers/lara%40example.com/churn-event/{event.id}",
        headers=_headers(admin),
    )
    assert resp.status_code == 204


def test_delete_churn_event_returns_403_for_other_member_within_24h(client: TestClient, db: Session):
    org = _make_org(db, plan="business")
    author = _make_user(db, org, role="admin")
    other = _make_user(db, org, role="member")
    # give other a unique email to avoid collision
    other.email = "other-member@example.com"
    db.commit()
    event = _make_churn_event(db, org, "mike@example.com", marked_by_user_id=author.id)
    resp = client.delete(
        f"/api/v1/customers/mike%40example.com/churn-event/{event.id}",
        headers=_headers(other),
    )
    assert resp.status_code == 403


def test_delete_churn_event_returns_403_after_24h_for_non_admin(client: TestClient, db: Session):
    org = _make_org(db, plan="business")
    user = _make_user(db, org)
    event = _make_churn_event(db, org, "nina@example.com", marked_by_user_id=user.id)
    event.created_at = datetime.utcnow() - timedelta(hours=25)
    db.commit()
    resp = client.delete(
        f"/api/v1/customers/nina%40example.com/churn-event/{event.id}",
        headers=_headers(user),
    )
    assert resp.status_code == 403


def test_delete_churn_event_returns_404_for_unknown_id(client: TestClient, db: Session):
    org = _make_org(db, plan="business")
    user = _make_user(db, org)
    resp = client.delete(
        "/api/v1/customers/nobody%40example.com/churn-event/99999",
        headers=_headers(user),
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/v1/customers/churn-events/bulk
# ---------------------------------------------------------------------------


def test_post_bulk_creates_events_for_each_email(client: TestClient, db: Session):
    org = _make_org(db, plan="business")
    user = _make_user(db, org)
    resp = client.post(
        "/api/v1/customers/churn-events/bulk",
        json={
            "emails": ["a@example.com", "b@example.com", "c@example.com"],
            "churned_at": "2026-03-01T00:00:00",
            "reason_code": "price",
        },
        headers=_headers(user),
    )
    assert resp.status_code == 200
    assert resp.json()["created"] == 3
    assert db.query(CustomerChurnEvent).filter_by(organization_id=org.id).count() == 3


def test_post_bulk_skips_emails_with_existing_active_event(client: TestClient, db: Session):
    org = _make_org(db, plan="business")
    user = _make_user(db, org)
    _make_churn_event(db, org, "existing@example.com")
    resp = client.post(
        "/api/v1/customers/churn-events/bulk",
        json={
            "emails": ["existing@example.com", "new@example.com"],
            "churned_at": "2026-03-01T00:00:00",
            "reason_code": "competitor",
        },
        headers=_headers(user),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["created"] == 1
    assert body["skipped"] == 1


def test_post_bulk_returns_summary_counts(client: TestClient, db: Session):
    org = _make_org(db, plan="business")
    user = _make_user(db, org)
    resp = client.post(
        "/api/v1/customers/churn-events/bulk",
        json={
            "emails": ["x@example.com", "y@example.com"],
            "churned_at": "2026-03-01T00:00:00",
            "reason_code": "other",
        },
        headers=_headers(user),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "created" in body
    assert "skipped" in body
    assert "errors" in body


def test_post_bulk_blocked_for_free_plan(client: TestClient, db: Session):
    org = _make_org(db, plan="free")
    user = _make_user(db, org)
    resp = client.post(
        "/api/v1/customers/churn-events/bulk",
        json={"emails": ["z@example.com"], "churned_at": "2026-03-01T00:00:00", "reason_code": "price"},
        headers=_headers(user),
    )
    assert resp.status_code == 403


def test_post_bulk_rejects_empty_email_list(client: TestClient, db: Session):
    org = _make_org(db, plan="business")
    user = _make_user(db, org)
    resp = client.post(
        "/api/v1/customers/churn-events/bulk",
        json={"emails": [], "churned_at": "2026-03-01T00:00:00", "reason_code": "price"},
        headers=_headers(user),
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# POST /api/v1/customers/churn-events/import  (CSV)
# ---------------------------------------------------------------------------


def test_post_import_creates_events_from_valid_csv(client: TestClient, db: Session):
    org = _make_org(db, plan="business")
    user = _make_user(db, org)
    csv_bytes = _build_csv([
        {"email": "alpha@example.com", "churned_at": "2026-01-10", "reason_code": "price"},
        {"email": "beta@example.com", "churned_at": "2026-01-11", "reason_code": "competitor"},
    ])
    resp = client.post(
        "/api/v1/customers/churn-events/import",
        files={"file": ("churn.csv", csv_bytes, "text/csv")},
        headers=_headers(user),
    )
    assert resp.status_code == 200
    assert resp.json()["created"] == 2
    assert db.query(CustomerChurnEvent).filter_by(organization_id=org.id).count() == 2


def test_post_import_returns_error_per_invalid_row_but_imports_valid_ones(client: TestClient, db: Session):
    org = _make_org(db, plan="business")
    user = _make_user(db, org)
    csv_bytes = _build_csv([
        {"email": "good@example.com", "churned_at": "2026-01-10", "reason_code": "price"},
        {"email": "not-an-email", "churned_at": "2026-01-11", "reason_code": "price"},
    ])
    resp = client.post(
        "/api/v1/customers/churn-events/import",
        files={"file": ("churn.csv", csv_bytes, "text/csv")},
        headers=_headers(user),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["created"] == 1
    assert len(body["errors"]) >= 1


def test_post_import_dedupes_against_existing_events(client: TestClient, db: Session):
    org = _make_org(db, plan="business")
    user = _make_user(db, org)
    churned_at = datetime(2026, 1, 10, 0, 0, 0)
    _make_churn_event(db, org, "dupe@example.com", churned_at=churned_at)
    csv_bytes = _build_csv([
        {"email": "dupe@example.com", "churned_at": "2026-01-10", "reason_code": "price"},
        {"email": "new@example.com", "churned_at": "2026-01-10", "reason_code": "price"},
    ])
    resp = client.post(
        "/api/v1/customers/churn-events/import",
        files={"file": ("churn.csv", csv_bytes, "text/csv")},
        headers=_headers(user),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["created"] == 1
    assert body["skipped"] == 1


def test_post_import_rejects_invalid_email_format(client: TestClient, db: Session):
    org = _make_org(db, plan="business")
    user = _make_user(db, org)
    csv_bytes = _build_csv([
        {"email": "not-valid", "churned_at": "2026-01-10", "reason_code": "price"},
    ])
    resp = client.post(
        "/api/v1/customers/churn-events/import",
        files={"file": ("churn.csv", csv_bytes, "text/csv")},
        headers=_headers(user),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["created"] == 0
    assert len(body["errors"]) == 1


def test_post_import_rejects_invalid_iso_date(client: TestClient, db: Session):
    org = _make_org(db, plan="business")
    user = _make_user(db, org)
    csv_bytes = _build_csv([
        {"email": "good@example.com", "churned_at": "not-a-date", "reason_code": "price"},
    ])
    resp = client.post(
        "/api/v1/customers/churn-events/import",
        files={"file": ("churn.csv", csv_bytes, "text/csv")},
        headers=_headers(user),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["created"] == 0
    assert len(body["errors"]) == 1


def test_post_import_rejects_invalid_reason_code(client: TestClient, db: Session):
    org = _make_org(db, plan="business")
    user = _make_user(db, org)
    csv_bytes = _build_csv([
        {"email": "good@example.com", "churned_at": "2026-01-10", "reason_code": "NOT_VALID"},
    ])
    resp = client.post(
        "/api/v1/customers/churn-events/import",
        files={"file": ("churn.csv", csv_bytes, "text/csv")},
        headers=_headers(user),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["created"] == 0
    assert len(body["errors"]) == 1


def test_post_import_blocked_for_pro_plan_without_csv_import_feature(client: TestClient, db: Session):
    org = _make_org(db, plan="pro")
    user = _make_user(db, org)
    csv_bytes = _build_csv([
        {"email": "good@example.com", "churned_at": "2026-01-10", "reason_code": "price"},
    ])
    resp = client.post(
        "/api/v1/customers/churn-events/import",
        files={"file": ("churn.csv", csv_bytes, "text/csv")},
        headers=_headers(user),
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /api/v1/customers/churn-events
# ---------------------------------------------------------------------------


def test_get_churn_events_returns_paginated_list(client: TestClient, db: Session):
    org = _make_org(db, plan="business")
    user = _make_user(db, org)
    for i in range(5):
        _make_churn_event(db, org, f"cust{i}@example.com")
    resp = client.get(
        "/api/v1/customers/churn-events?page=1&page_size=3",
        headers=_headers(user),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 5
    assert len(body["items"]) == 3
    assert body["page"] == 1
    assert body["page_size"] == 3


def test_get_churn_events_filter_active_only(client: TestClient, db: Session):
    org = _make_org(db, plan="business")
    user = _make_user(db, org)
    _make_churn_event(db, org, "active@example.com")
    _make_churn_event(db, org, "recovered@example.com", recovered_at=datetime.utcnow())
    resp = client.get(
        "/api/v1/customers/churn-events?active=true",
        headers=_headers(user),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["customer_email"] == "active@example.com"


def test_get_churn_events_filter_by_reason_code(client: TestClient, db: Session):
    org = _make_org(db, plan="business")
    user = _make_user(db, org)
    _make_churn_event(db, org, "p@example.com", reason_code="price")
    _make_churn_event(db, org, "c@example.com", reason_code="competitor")
    resp = client.get(
        "/api/v1/customers/churn-events?reason_code=price",
        headers=_headers(user),
    )
    assert resp.status_code == 200
    assert resp.json()["total"] == 1
    assert resp.json()["items"][0]["reason_code"] == "price"


def test_get_churn_events_filter_by_date_range(client: TestClient, db: Session):
    org = _make_org(db, plan="business")
    user = _make_user(db, org)
    _make_churn_event(db, org, "jan@example.com", churned_at=datetime(2026, 1, 15))
    _make_churn_event(db, org, "mar@example.com", churned_at=datetime(2026, 3, 15))
    resp = client.get(
        "/api/v1/customers/churn-events?from_date=2026-01-01&to_date=2026-02-01",
        headers=_headers(user),
    )
    assert resp.status_code == 200
    assert resp.json()["total"] == 1
    assert resp.json()["items"][0]["customer_email"] == "jan@example.com"


def test_get_churn_events_scoped_to_caller_org(client: TestClient, db: Session):
    org_a = _make_org(db, plan="business")
    org_b = _make_org(db, plan="business")
    user_a = _make_user(db, org_a)
    _make_churn_event(db, org_a, "a@example.com")
    _make_churn_event(db, org_b, "b@example.com")
    resp = client.get("/api/v1/customers/churn-events", headers=_headers(user_a))
    assert resp.status_code == 200
    assert resp.json()["total"] == 1
    assert resp.json()["items"][0]["customer_email"] == "a@example.com"


# ---------------------------------------------------------------------------
# Tenancy isolation
# ---------------------------------------------------------------------------


def test_post_churn_event_for_org_a_invisible_to_org_b(client: TestClient, db: Session):
    org_a = _make_org(db, plan="business")
    org_b = _make_org(db, plan="business")
    user_a = _make_user(db, org_a)
    user_b = _make_user(db, org_b)
    # Org A marks a customer as churned
    r = client.post(
        "/api/v1/customers/shared%40example.com/churn-event",
        json={"reason_code": "price", "customer_email": "shared@example.com"},
        headers=_headers(user_a),
    )
    assert r.status_code == 201
    # Org B lists events — should see zero
    resp = client.get("/api/v1/customers/churn-events", headers=_headers(user_b))
    assert resp.status_code == 200
    assert resp.json()["total"] == 0
