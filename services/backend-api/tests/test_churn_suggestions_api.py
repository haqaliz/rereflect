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
from sqlalchemy.exc import IntegrityError
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


# ---------------------------------------------------------------------------
# POST /api/v1/customers/churn-suggestions/{id}/confirm — AC3, AC4, AC5
# ---------------------------------------------------------------------------


def _confirm_url(suggestion_id: int) -> str:
    return f"/api/v1/customers/churn-suggestions/{suggestion_id}/confirm"


def _reject_url(suggestion_id: int) -> str:
    return f"/api/v1/customers/churn-suggestions/{suggestion_id}/reject"


def test_confirm_creates_trainable_churn_event(client: TestClient, db: Session):
    org = _make_org(db)
    user = _make_user(db, org, role="admin")
    churned_at = datetime(2026, 5, 1, 10, 0, 0)
    suggestion = _make_suggestion(
        db, org, "alice@example.com", suggested_churned_at=churned_at
    )

    resp = client.post(
        _confirm_url(suggestion.id),
        json={"reason_code": "price"},
        headers=_headers(user),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "confirmed"
    assert body["churn_event_id"] is not None

    events = db.query(CustomerChurnEvent).filter_by(organization_id=org.id).all()
    assert len(events) == 1
    event = events[0]
    assert event.source == "manual"
    assert event.marked_by_user_id == user.id
    assert event.churned_at == churned_at
    assert event.customer_email == "alice@example.com"

    db.refresh(suggestion)
    assert suggestion.status == "confirmed"
    assert suggestion.churn_event_id == event.id


def test_confirm_leaves_probability_computed_at_null(client: TestClient, db: Session):
    org = _make_org(db)
    user = _make_user(db, org)
    _make_health(db, org, "alice@example.com")
    suggestion = _make_suggestion(db, org, "alice@example.com")

    resp = client.post(_confirm_url(suggestion.id), json={"reason_code": "price"}, headers=_headers(user))
    assert resp.status_code == 200

    health = (
        db.query(CustomerHealth)
        .filter_by(organization_id=org.id, customer_email="alice@example.com")
        .first()
    )
    assert health.probability_computed_at is None


def test_confirm_without_reason_code_is_422_and_writes_nothing(client: TestClient, db: Session):
    org = _make_org(db)
    user = _make_user(db, org)
    suggestion = _make_suggestion(db, org, "alice@example.com")

    resp = client.post(_confirm_url(suggestion.id), json={}, headers=_headers(user))
    assert resp.status_code == 422

    assert db.query(CustomerChurnEvent).count() == 0
    db.refresh(suggestion)
    assert suggestion.status == "pending"


def test_confirm_with_invalid_reason_code_is_422_and_writes_nothing(client: TestClient, db: Session):
    org = _make_org(db)
    user = _make_user(db, org)
    suggestion = _make_suggestion(db, org, "alice@example.com")

    resp = client.post(
        _confirm_url(suggestion.id),
        json={"reason_code": "crm_lost"},
        headers=_headers(user),
    )
    assert resp.status_code == 422

    assert db.query(CustomerChurnEvent).count() == 0
    db.refresh(suggestion)
    assert suggestion.status == "pending"


def test_confirm_precheck_collision_resolves_to_skipped(client: TestClient, db: Session):
    org = _make_org(db)
    user = _make_user(db, org)
    existing_event = _make_churn_event(db, org, "alice@example.com")
    suggestion = _make_suggestion(db, org, "alice@example.com")

    resp = client.post(_confirm_url(suggestion.id), json={"reason_code": "price"}, headers=_headers(user))
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "skipped"
    assert body["churn_event_id"] == existing_event.id

    assert db.query(CustomerChurnEvent).filter_by(organization_id=org.id).count() == 1
    db.refresh(suggestion)
    assert suggestion.status == "confirmed"
    assert suggestion.churn_event_id == existing_event.id


def test_confirm_race_path_never_500_and_session_stays_usable(
    client: TestClient, db: Session, monkeypatch
):
    """AC5 race path: pre-check patched to miss the collision, backstop
    IntegrityError catch must still resolve to skipped — not 500 — and the
    session must remain usable for a subsequent write."""
    import src.api.routes.churn_suggestions as churn_suggestions

    org = _make_org(db)
    user = _make_user(db, org)
    # Same churned_at on both rows so the INSERT actually collides on the
    # (org, email, churned_at) UNIQUE constraint once the pre-check is
    # patched to miss it — otherwise the two `datetime.utcnow()` calls
    # would differ by microseconds and never collide.
    shared_churned_at = datetime(2026, 6, 1, 12, 0, 0)
    existing_event = _make_churn_event(db, org, "alice@example.com", churned_at=shared_churned_at)
    suggestion = _make_suggestion(
        db, org, "alice@example.com", suggested_churned_at=shared_churned_at
    )

    monkeypatch.setattr(churn_suggestions, "_get_active_churn_event", lambda *a, **k: None)

    resp = client.post(_confirm_url(suggestion.id), json={"reason_code": "price"}, headers=_headers(user))
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "skipped"

    assert db.query(CustomerChurnEvent).filter_by(organization_id=org.id).count() == 1

    # Session must still be usable — a later write in the same session succeeds.
    other_suggestion = _make_suggestion(db, org, "bob@example.com", ext_id="d-bob")
    resp2 = client.post(
        _confirm_url(other_suggestion.id), json={"reason_code": "price"}, headers=_headers(user)
    )
    assert resp2.status_code == 200
    assert resp2.json()["status"] == "confirmed"


def test_confirm_on_non_pending_suggestion_is_skipped_idempotent(client: TestClient, db: Session):
    org = _make_org(db)
    user = _make_user(db, org)
    suggestion = _make_suggestion(db, org, "alice@example.com", status="rejected")

    resp = client.post(_confirm_url(suggestion.id), json={"reason_code": "price"}, headers=_headers(user))
    assert resp.status_code == 200
    assert resp.json()["status"] == "skipped"
    assert db.query(CustomerChurnEvent).count() == 0


def test_confirm_cross_org_id_is_404(client: TestClient, db: Session):
    org_a = _make_org(db)
    org_b = _make_org(db)
    user_a = _make_user(db, org_a)
    suggestion_b = _make_suggestion(db, org_b, "bob@example.com")

    resp = client.post(
        _confirm_url(suggestion_b.id), json={"reason_code": "price"}, headers=_headers(user_a)
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/v1/customers/churn-suggestions/{id}/reject — AC5 (reject path), AC6
# ---------------------------------------------------------------------------


def test_reject_writes_no_event_and_clears_from_pending(client: TestClient, db: Session):
    org = _make_org(db)
    user = _make_user(db, org)
    suggestion = _make_suggestion(db, org, "alice@example.com")

    resp = client.post(_reject_url(suggestion.id), json={}, headers=_headers(user))
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "rejected"
    assert body["churn_event_id"] is None

    assert db.query(CustomerChurnEvent).count() == 0

    list_resp = client.get(f"{LIST_URL}?status=pending", headers=_headers(user))
    assert list_resp.json()["total"] == 0


def test_reject_then_reharvest_natural_key_stays_rejected(client: TestClient, db: Session):
    """Asserts wave-1 behaviour rather than building it: the harvester
    (worker-service, a separate service/package — not importable here)
    pre-checks the same (org, provider, external_opportunity_id) natural
    key this test queries directly, and its INSERT is backstopped by the
    model's own UNIQUE constraint (churn_label_suggestion.py:85-90). A
    re-harvest attempt on this key must find the existing (now rejected)
    row rather than resurrecting it to pending."""
    org = _make_org(db)
    user = _make_user(db, org)
    suggestion = _make_suggestion(
        db, org, "alice@example.com", provider="hubspot", ext_id="deal-42"
    )

    resp = client.post(_reject_url(suggestion.id), json={"note": "not a real churn"}, headers=_headers(user))
    assert resp.status_code == 200

    # Same natural-key lookup the harvester's `_existing_suggestion_row`
    # performs before every insert.
    found = (
        db.query(ChurnLabelSuggestion)
        .filter_by(organization_id=org.id, provider="hubspot", external_opportunity_id="deal-42")
        .first()
    )
    assert found is not None
    assert found.status == "rejected"

    # The UNIQUE constraint is the real backstop: attempting to insert a
    # fresh "pending" row for the same natural key must fail, not silently
    # resurrect the rejected suggestion.
    dupe = ChurnLabelSuggestion(
        organization_id=org.id,
        customer_email="alice@example.com",
        provider="hubspot",
        external_opportunity_id="deal-42",
        suggested_churned_at=datetime.utcnow(),
        status="pending",
    )
    db.add(dupe)
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()

    list_resp = client.get(f"{LIST_URL}?status=pending", headers=_headers(user))
    assert list_resp.json()["total"] == 0


def test_reject_on_non_pending_is_skipped_idempotent(client: TestClient, db: Session):
    org = _make_org(db)
    user = _make_user(db, org)
    suggestion = _make_suggestion(db, org, "alice@example.com", status="confirmed")

    resp = client.post(_reject_url(suggestion.id), json={}, headers=_headers(user))
    assert resp.status_code == 200
    # Non-pending target is idempotent: reject on an already-confirmed row
    # must not flip it to rejected.
    db.refresh(suggestion)
    assert suggestion.status == "confirmed"
