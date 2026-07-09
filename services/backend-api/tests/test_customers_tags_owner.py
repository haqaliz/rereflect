"""
TDD tests — customer-fields-model aspect (segment-actions feature), Phase 3.

Coverage:
  - `tags` + `cs_owner` on CustomerListItem (GET /api/v1/customers/)
  - `tags` + `cs_owner` on the internal profile (GET /api/v1/customers/{email})
  - cs_owner ref shape is {id, email} only (User has no name field)
  - batched owner resolution — no per-row N+1 on the list

See docs/planning/segment-actions/customer-fields-model/{plan_20260709.md,spec.md}.
"""
import pytest
from datetime import datetime
from sqlalchemy import event
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

from src.models.customer_health import CustomerHealth
from src.models.organization import Organization
from src.models.user import User
from src.api.auth import hash_password, create_access_token
from tests.conftest import engine


@pytest.fixture
def org(db: Session) -> Organization:
    o = Organization(name="Tags Owner Co", plan="pro")
    db.add(o)
    db.commit()
    db.refresh(o)
    return o


@pytest.fixture
def admin_user(db: Session, org: Organization) -> User:
    u = User(
        email="admin@tagsowner.com",
        password_hash=hash_password("password123"),
        organization_id=org.id,
        role="admin",
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture
def headers(admin_user: User) -> dict:
    token = create_access_token({
        "user_id": admin_user.id,
        "organization_id": admin_user.organization_id,
        "role": admin_user.role,
    })
    return {"Authorization": f"Bearer {token}"}


def make_ch(db, org, email, *, tags=None, cs_owner_user_id=None) -> CustomerHealth:
    record = CustomerHealth(
        organization_id=org.id,
        customer_email=email,
        health_score=60,
        risk_level="moderate",
        feedback_count=5,
        confidence_level="medium",
        last_feedback_at=datetime.utcnow(),
        is_archived=False,
        churn_risk_component=50,
        sentiment_component=60,
        resolution_component=70,
        frequency_component=55,
        tags=tags,
        cs_owner_user_id=cs_owner_user_id,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


class TestTagsField:
    def test_list_item_tags_default_empty(self, client, org, headers, db):
        make_ch(db, org, "notags@example.com", tags=None)
        r = client.get("/api/v1/customers/", headers=headers)
        assert r.status_code == 200
        item = r.json()["items"][0]
        assert item["tags"] == []

    def test_list_item_tags_populated(self, client, org, headers, db):
        make_ch(db, org, "tagged@example.com", tags=["expansion", "vip"])
        r = client.get("/api/v1/customers/", headers=headers)
        item = r.json()["items"][0]
        assert item["tags"] == ["expansion", "vip"]

    def test_profile_includes_tags(self, client, org, headers, db):
        make_ch(db, org, "prof@example.com", tags=["churn-watch"])
        r = client.get("/api/v1/customers/prof@example.com", headers=headers)
        assert r.status_code == 200
        assert r.json()["tags"] == ["churn-watch"]


class TestCsOwnerField:
    def test_owner_null_when_unassigned(self, client, org, headers, db):
        make_ch(db, org, "noowner@example.com", cs_owner_user_id=None)
        r = client.get("/api/v1/customers/", headers=headers)
        assert r.json()["items"][0]["cs_owner"] is None

    def test_owner_ref_shape_id_email_only(self, client, org, headers, db, admin_user):
        make_ch(db, org, "owned@example.com", cs_owner_user_id=admin_user.id)
        r = client.get("/api/v1/customers/", headers=headers)
        owner = r.json()["items"][0]["cs_owner"]
        assert owner == {"id": admin_user.id, "email": admin_user.email}

    def test_profile_includes_owner(self, client, org, headers, db, admin_user):
        make_ch(db, org, "ownedprof@example.com", cs_owner_user_id=admin_user.id)
        r = client.get("/api/v1/customers/ownedprof@example.com", headers=headers)
        assert r.status_code == 200
        assert r.json()["cs_owner"] == {"id": admin_user.id, "email": admin_user.email}


class TestNoOwnerNPlusOne:
    def _count_user_selects(self, client, headers):
        user_selects = []

        def _before(conn, cursor, statement, params, context, executemany):
            if "from users" in statement.lower():
                user_selects.append(statement)

        event.listen(engine, "before_cursor_execute", _before)
        try:
            r = client.get("/api/v1/customers/?page_size=100", headers=headers)
        finally:
            event.remove(engine, "before_cursor_execute", _before)
        assert r.status_code == 200
        return r.json()["items"], len(user_selects)

    def test_owner_resolution_is_batched(self, client, org, headers, db):
        # Distinct org members, each owning customers.
        owners = []
        for i in range(3):
            u = User(
                email=f"csm{i}@tagsowner.com",
                password_hash=hash_password("x"),
                organization_id=org.id,
                role="member",
            )
            db.add(u)
            owners.append(u)
        db.commit()
        for u in owners:
            db.refresh(u)

        # Baseline: 3 owned customers.
        for i in range(3):
            make_ch(db, org, f"c{i}@example.com", cs_owner_user_id=owners[i % 3].id)
        _, base_count = self._count_user_selects(client, headers)

        # Grow to 9 owned customers.
        for i in range(3, 9):
            make_ch(db, org, f"c{i}@example.com", cs_owner_user_id=owners[i % 3].id)
        items, grown_count = self._count_user_selects(client, headers)

        # Correctness: every owner resolves.
        by_email = {it["customer_email"]: it for it in items}
        for i in range(9):
            assert by_email[f"c{i}@example.com"]["cs_owner"]["email"] == f"csm{i % 3}@tagsowner.com"

        # No N+1: tripling the owned rows must NOT increase the number of users
        # SELECTs (batched → constant). An N+1 would grow with row count.
        assert grown_count == base_count, (
            f"users SELECTs grew with rows ({base_count} -> {grown_count}); owner load is not batched"
        )
