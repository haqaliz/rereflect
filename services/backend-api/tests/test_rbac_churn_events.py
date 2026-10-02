"""RBAC for churn-event mutations (mutation-route-rbac, backend-gating)."""

from datetime import datetime, timedelta

import pytest

from src.models.churn_event import CustomerChurnEvent

ROLE_DETAIL = "This action requires admin or owner privileges"
CSV = b"email,churned_at,reason_code\nalpha@example.com,2026-01-10,price\n"


@pytest.fixture(autouse=True)
def business_org(db, test_organization):
    test_organization.plan = "business"
    db.commit()


def _routes():
    body = {"churned_at": "2026-03-01T00:00:00", "reason_code": "price"}
    return [
        ("POST", "/api/v1/customers/churn-events/bulk",
         {"json": {**body, "emails": ["a@example.com", "b@example.com"]}}),
        ("POST", "/api/v1/customers/zed%40example.com/churn-event",
         {"json": {**body, "customer_email": "zed@example.com"}}),
        ("POST", "/api/v1/customers/churn-events/import",
         {"files": {"file": ("churn.csv", CSV, "text/csv")}}),
    ]


def _event(db, org, author_id, email="vic@example.com", age_hours=0):
    ev = CustomerChurnEvent(
        organization_id=org.id, customer_email=email, churned_at=datetime.utcnow(),
        reason_code="price", marked_by_user_id=author_id, source="manual",
    )
    db.add(ev)
    db.commit()
    ev.created_at = datetime.utcnow() - timedelta(hours=age_hours)
    db.commit()
    db.refresh(ev)
    return ev


@pytest.mark.parametrize("idx", range(3))
def test_member_gets_403_on_create_routes(client, member_headers, db, idx):
    method, path, kw = _routes()[idx]
    resp = client.request(method, path, headers=member_headers, **kw)
    assert resp.status_code == 403
    assert resp.json()["detail"] == ROLE_DETAIL
    assert db.query(CustomerChurnEvent).count() == 0


@pytest.mark.parametrize("headers_fixture", ["auth_headers", "owner_headers"])
@pytest.mark.parametrize("idx", range(3))
def test_admin_and_owner_can_create(client, request, db, headers_fixture, idx):
    headers = request.getfixturevalue(headers_fixture)
    method, path, kw = _routes()[idx]
    resp = client.request(method, path, headers=headers, **kw)
    assert resp.status_code in (200, 201), resp.text
    assert db.query(CustomerChurnEvent).count() >= 1


def test_member_gets_403_on_recover(client, member_headers, db, test_organization, test_user):
    ev = _event(db, test_organization, test_user.id, "rec@example.com")
    resp = client.post("/api/v1/customers/rec%40example.com/recover", json={}, headers=member_headers)
    assert resp.status_code == 403
    assert resp.json()["detail"] == ROLE_DETAIL
    db.refresh(ev)
    assert ev.recovered_at is None


@pytest.mark.parametrize("headers_fixture", ["auth_headers", "owner_headers"])
def test_admin_and_owner_can_recover(client, request, db, test_organization, test_user, headers_fixture):
    ev = _event(db, test_organization, test_user.id, "rec@example.com")
    resp = client.post(
        "/api/v1/customers/rec%40example.com/recover", json={},
        headers=request.getfixturevalue(headers_fixture),
    )
    assert resp.status_code == 200
    db.refresh(ev)
    assert ev.recovered_at is not None


# --- delete: third allowed path (org admin/owner) ---------------------------


def _delete(client, ev, headers):
    return client.delete(
        f"/api/v1/customers/{ev.customer_email.replace('@', '%40')}/churn-event/{ev.id}",
        headers=headers,
    )


@pytest.mark.parametrize("headers_fixture", ["auth_headers", "owner_headers"])
def test_admin_or_owner_non_author_can_delete_old_event(
    client, request, db, test_organization, member_user, headers_fixture
):
    ev = _event(db, test_organization, member_user.id, age_hours=72)
    resp = _delete(client, ev, request.getfixturevalue(headers_fixture))
    assert resp.status_code == 204
    assert db.query(CustomerChurnEvent).filter_by(id=ev.id).first() is None


def test_member_non_author_still_403_with_updated_message(
    client, member_headers, db, test_organization, test_user
):
    ev = _event(db, test_organization, test_user.id)
    resp = _delete(client, ev, member_headers)
    assert resp.status_code == 403
    assert "admin or owner" in resp.json()["detail"]
    assert db.query(CustomerChurnEvent).filter_by(id=ev.id).first() is not None


def test_member_author_within_24h_can_delete(client, member_headers, db, test_organization, member_user):
    ev = _event(db, test_organization, member_user.id)
    assert _delete(client, ev, member_headers).status_code == 204


def test_member_author_after_24h_gets_403(client, member_headers, db, test_organization, member_user):
    ev = _event(db, test_organization, member_user.id, age_hours=30)
    assert _delete(client, ev, member_headers).status_code == 403


def test_member_can_still_list_churn_events(client, member_headers):
    assert client.get("/api/v1/customers/churn-events", headers=member_headers).status_code == 200
