"""
Tests for the CRM churn-suggestion review queue (review-queue aspect) —
strict TDD, RED first.

This is the feature's trust boundary: nothing a CRM suggests is trainable
until a human confirms it here. See docs/planning/crm-churn-labels/review-queue/.
"""

from datetime import datetime, timedelta
from typing import Optional

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.api.auth import create_access_token, hash_password
from src.models.churn_event import CustomerChurnEvent
from src.models.churn_label_suggestion import (
    CHURN_SUGGESTION_STATUSES,
    ChurnLabelSuggestion,
)
from src.models.customer_health import CustomerHealth
from src.models.organization import Organization
from src.models.user import User


# ---------------------------------------------------------------------------
# Helpers (copied style: tests/test_churn_events_api.py:28-52)
# ---------------------------------------------------------------------------


def _make_org(db: Session, plan: str = "business") -> Organization:
    org = Organization(name=f"Org-{plan}-{datetime.utcnow().timestamp()}", plan=plan)
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def _make_user(db: Session, org: Organization, role: str = "admin") -> User:
    user = User(
        email=f"user-{org.id}-{role}-{datetime.utcnow().timestamp()}@example.com",
        password_hash=hash_password("password123"),
        organization_id=org.id,
        role=role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _headers(user: User) -> dict:
    token = create_access_token(
        {"user_id": user.id, "organization_id": user.organization_id, "role": user.role}
    )
    return {"Authorization": f"Bearer {token}"}


def _make_suggestion(
    db: Session,
    org: Organization,
    email: str,
    provider: str = "hubspot",
    ext_id: str = "deal-1",
    suggested_churned_at: Optional[datetime] = None,
    status: str = "pending",
    evidence: Optional[dict] = None,
) -> ChurnLabelSuggestion:
    row = ChurnLabelSuggestion(
        organization_id=org.id,
        customer_email=email,
        provider=provider,
        external_opportunity_id=ext_id,
        suggested_churned_at=suggested_churned_at or datetime.utcnow(),
        evidence=evidence,
        status=status,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _make_health(db: Session, org: Organization, email: str) -> CustomerHealth:
    health = CustomerHealth(
        organization_id=org.id,
        customer_email=email,
        health_score=50,
        risk_level="moderate",
        probability_computed_at=datetime.utcnow(),
        has_potential_winback=False,
    )
    db.add(health)
    db.commit()
    db.refresh(health)
    return health


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


LIST_URL = "/api/v1/customers/churn-suggestions"


# ---------------------------------------------------------------------------
# GET /api/v1/customers/churn-suggestions — AC1, AC2
# ---------------------------------------------------------------------------


def test_list_returns_only_callers_org_suggestions(client: TestClient, db: Session):
    org_a = _make_org(db)
    org_b = _make_org(db)
    user_a = _make_user(db, org_a, role="admin")
    _make_suggestion(db, org_a, "alice@example.com")
    row_b = _make_suggestion(db, org_b, "bob@example.com")

    resp = client.get(LIST_URL, headers=_headers(user_a))
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert all(item["id"] != row_b.id for item in data["items"])


def test_list_default_status_is_pending(client: TestClient, db: Session):
    org = _make_org(db)
    user = _make_user(db, org)
    _make_suggestion(db, org, "a@example.com", ext_id="d1", status="pending")
    _make_suggestion(db, org, "b@example.com", ext_id="d2", status="confirmed")
    _make_suggestion(db, org, "c@example.com", ext_id="d3", status="rejected")

    resp = client.get(LIST_URL, headers=_headers(user))
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["customer_email"] == "a@example.com"


def test_list_status_query_filters_explicitly(client: TestClient, db: Session):
    org = _make_org(db)
    user = _make_user(db, org)
    _make_suggestion(db, org, "a@example.com", ext_id="d1", status="pending")
    _make_suggestion(db, org, "b@example.com", ext_id="d2", status="confirmed")

    resp = client.get(f"{LIST_URL}?status=confirmed", headers=_headers(user))
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["customer_email"] == "b@example.com"


def test_list_member_forbidden(client: TestClient, db: Session):
    org = _make_org(db)
    user = _make_user(db, org, role="member")
    resp = client.get(LIST_URL, headers=_headers(user))
    assert resp.status_code == 403


@pytest.mark.parametrize("role", ["admin", "owner"])
def test_list_admin_and_owner_allowed(client: TestClient, db: Session, role: str):
    org = _make_org(db)
    user = _make_user(db, org, role=role)
    resp = client.get(LIST_URL, headers=_headers(user))
    assert resp.status_code == 200


@pytest.mark.parametrize("plan", ["free", "pro"])
def test_list_requires_business_plan_or_higher(client: TestClient, db: Session, plan: str):
    org = _make_org(db, plan=plan)
    user = _make_user(db, org, role="owner")
    resp = client.get(LIST_URL, headers=_headers(user))
    assert resp.status_code == 403


def test_list_pagination_bounds(client: TestClient, db: Session):
    org = _make_org(db)
    user = _make_user(db, org)
    for i in range(5):
        _make_suggestion(db, org, f"user{i}@example.com", ext_id=f"d{i}")

    resp = client.get(f"{LIST_URL}?page=1&page_size=2", headers=_headers(user))
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 2
    assert data["total"] == 5
    assert data["page"] == 1
    assert data["page_size"] == 2

    resp_too_big = client.get(f"{LIST_URL}?page_size=101", headers=_headers(user))
    assert resp_too_big.status_code == 422

    resp_zero_page = client.get(f"{LIST_URL}?page=0", headers=_headers(user))
    assert resp_zero_page.status_code == 422


def test_list_provider_filter(client: TestClient, db: Session):
    org = _make_org(db)
    user = _make_user(db, org)
    _make_suggestion(db, org, "a@example.com", provider="hubspot", ext_id="d1")
    _make_suggestion(db, org, "b@example.com", provider="salesforce", ext_id="d2")

    resp = client.get(f"{LIST_URL}?provider=salesforce", headers=_headers(user))
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["customer_email"] == "b@example.com"


def test_list_search_filter(client: TestClient, db: Session):
    org = _make_org(db)
    user = _make_user(db, org)
    _make_suggestion(db, org, "alice@example.com", ext_id="d1")
    _make_suggestion(db, org, "bob@example.com", ext_id="d2")

    resp = client.get(f"{LIST_URL}?search=alice", headers=_headers(user))
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["customer_email"] == "alice@example.com"


def test_list_ordering_suggested_churned_at_desc_then_id_desc(client: TestClient, db: Session):
    org = _make_org(db)
    user = _make_user(db, org)
    now = datetime.utcnow()
    older = _make_suggestion(
        db, org, "a@example.com", ext_id="d1", suggested_churned_at=now - timedelta(days=5)
    )
    newer = _make_suggestion(
        db, org, "b@example.com", ext_id="d2", suggested_churned_at=now
    )
    same_date_1 = _make_suggestion(
        db, org, "c@example.com", ext_id="d3", suggested_churned_at=now
    )

    resp = client.get(LIST_URL, headers=_headers(user))
    assert resp.status_code == 200
    ids = [item["id"] for item in resp.json()["items"]]
    # newer/same_date_1 both at `now` -> id desc tiebreak; older last.
    assert ids == [same_date_1.id, newer.id, older.id]


def test_list_item_includes_evidence_and_churn_event_id(client: TestClient, db: Session):
    org = _make_org(db)
    user = _make_user(db, org)
    _make_suggestion(
        db, org, "a@example.com", evidence={"deal_name": "Acme Renewal", "amount": 5000}
    )

    resp = client.get(LIST_URL, headers=_headers(user))
    assert resp.status_code == 200
    item = resp.json()["items"][0]
    assert item["evidence"] == {"deal_name": "Acme Renewal", "amount": 5000}
    assert item["churn_event_id"] is None
