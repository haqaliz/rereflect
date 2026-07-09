"""
TDD tests — bulk-actions-api aspect (segment-actions feature), Phase 4.

Coverage:
  - POST /api/v1/customers/bulk/tags: add/remove (union/difference), trim/
    dedupe/drop-empty/50-char validation, 20-tag cap (over-cap -> errors, not
    silently dropped), org scope, cross-org/unknown emails skipped, summary.
  - POST /api/v1/customers/bulk/assign-owner: set/clear, non-member user_id
    -> 422, org scope, summary.
  - Both require admin/owner (member -> 403).
  - Both registered before /{email} (not swallowed as an email).

See docs/planning/segment-actions/bulk-actions-api/{plan_20260709.md,spec.md}.
"""
import pytest
from datetime import datetime
from sqlalchemy.orm import Session

from src.models.customer_health import CustomerHealth
from src.models.organization import Organization
from src.models.user import User
from src.api.auth import hash_password, create_access_token


@pytest.fixture
def org(db: Session) -> Organization:
    o = Organization(name="Bulk Co", plan="business")
    db.add(o)
    db.commit()
    db.refresh(o)
    return o


@pytest.fixture
def other_org(db: Session) -> Organization:
    o = Organization(name="Other Bulk Co", plan="business")
    db.add(o)
    db.commit()
    db.refresh(o)
    return o


def _make_user(db, org, email, role="owner", is_deactivated=False):
    u = User(
        email=email,
        password_hash=hash_password("password123"),
        organization_id=org.id,
        role=role,
        is_deactivated=is_deactivated,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _headers_for(u: User) -> dict:
    token = create_access_token({"user_id": u.id, "organization_id": u.organization_id, "role": u.role})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def owner_user(db, org):
    return _make_user(db, org, "owner@bulk.com", role="owner")


@pytest.fixture
def admin_user(db, org):
    return _make_user(db, org, "admin@bulk.com", role="admin")


@pytest.fixture
def member_user(db, org):
    return _make_user(db, org, "member@bulk.com", role="member")


@pytest.fixture
def owner_headers(owner_user):
    return _headers_for(owner_user)


@pytest.fixture
def member_headers(member_user):
    return _headers_for(member_user)


def make_ch(db, org, email, **kwargs) -> CustomerHealth:
    defaults = dict(
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
    )
    defaults.update(kwargs)
    record = CustomerHealth(organization_id=org.id, customer_email=email, **defaults)
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


# ---------------------------------------------------------------------------
# POST /customers/bulk/tags
# ---------------------------------------------------------------------------

class TestBulkTagsRBAC:
    def test_member_forbidden(self, client, org, member_headers, db):
        make_ch(db, org, "a@example.com")
        body = {"cohort": {"emails": ["a@example.com"]}, "tags": ["vip"], "mode": "add"}
        r = client.post("/api/v1/customers/bulk/tags", json=body, headers=member_headers)
        assert r.status_code == 403

    def test_admin_allowed(self, client, org, db):
        admin = _make_user(db, org, "admin2@bulk.com", role="admin")
        headers = _headers_for(admin)
        make_ch(db, org, "a@example.com")
        body = {"cohort": {"emails": ["a@example.com"]}, "tags": ["vip"], "mode": "add"}
        r = client.post("/api/v1/customers/bulk/tags", json=body, headers=headers)
        assert r.status_code == 200


class TestBulkTagsAdd:
    def test_add_union(self, client, org, owner_headers, db):
        make_ch(db, org, "a@example.com", tags=["existing"])
        body = {"cohort": {"emails": ["a@example.com"]}, "tags": ["vip", "existing"], "mode": "add"}
        r = client.post("/api/v1/customers/bulk/tags", json=body, headers=owner_headers)
        assert r.status_code == 200
        summary = r.json()
        assert summary == {"matched": 1, "updated": 1, "skipped": 0, "errors": []}

        row = db.query(CustomerHealth).filter_by(customer_email="a@example.com").first()
        assert set(row.tags) == {"existing", "vip"}

    def test_add_trims_dedupes_drops_empty(self, client, org, owner_headers, db):
        make_ch(db, org, "a@example.com", tags=[])
        body = {
            "cohort": {"emails": ["a@example.com"]},
            "tags": ["  vip  ", "vip", "", "   ", "expansion"],
            "mode": "add",
        }
        r = client.post("/api/v1/customers/bulk/tags", json=body, headers=owner_headers)
        assert r.status_code == 200
        row = db.query(CustomerHealth).filter_by(customer_email="a@example.com").first()
        assert set(row.tags) == {"vip", "expansion"}

    def test_tag_over_50_chars_rejected(self, client, org, owner_headers, db):
        make_ch(db, org, "a@example.com")
        body = {"cohort": {"emails": ["a@example.com"]}, "tags": ["x" * 51], "mode": "add"}
        r = client.post("/api/v1/customers/bulk/tags", json=body, headers=owner_headers)
        assert r.status_code == 422

    def test_over_cap_customer_goes_to_errors_not_silently_dropped(self, client, org, owner_headers, db):
        existing = [f"tag{i}" for i in range(19)]
        make_ch(db, org, "full@example.com", tags=existing)
        make_ch(db, org, "room@example.com", tags=["tag0"])

        body = {
            "cohort": {"emails": ["full@example.com", "room@example.com"]},
            "tags": ["new1", "new2"],
            "mode": "add",
        }
        r = client.post("/api/v1/customers/bulk/tags", json=body, headers=owner_headers)
        assert r.status_code == 200
        summary = r.json()
        assert summary["matched"] == 2
        assert summary["updated"] == 1  # only room@example.com applied
        assert len(summary["errors"]) == 1
        assert "full@example.com" in summary["errors"][0]

        full_row = db.query(CustomerHealth).filter_by(customer_email="full@example.com").first()
        assert set(full_row.tags) == set(existing)  # unchanged

        room_row = db.query(CustomerHealth).filter_by(customer_email="room@example.com").first()
        assert set(room_row.tags) == {"tag0", "new1", "new2"}

    def test_exactly_20_tags_after_add_is_allowed(self, client, org, owner_headers, db):
        existing = [f"tag{i}" for i in range(18)]
        make_ch(db, org, "exact@example.com", tags=existing)
        body = {
            "cohort": {"emails": ["exact@example.com"]},
            "tags": ["new1", "new2"],
            "mode": "add",
        }
        r = client.post("/api/v1/customers/bulk/tags", json=body, headers=owner_headers)
        assert r.status_code == 200
        summary = r.json()
        assert summary["updated"] == 1
        assert summary["errors"] == []
        row = db.query(CustomerHealth).filter_by(customer_email="exact@example.com").first()
        assert len(row.tags) == 20


class TestBulkTagsRemove:
    def test_remove_difference(self, client, org, owner_headers, db):
        make_ch(db, org, "a@example.com", tags=["vip", "expansion", "keep"])
        body = {"cohort": {"emails": ["a@example.com"]}, "tags": ["vip", "expansion"], "mode": "remove"}
        r = client.post("/api/v1/customers/bulk/tags", json=body, headers=owner_headers)
        assert r.status_code == 200
        row = db.query(CustomerHealth).filter_by(customer_email="a@example.com").first()
        assert row.tags == ["keep"]

    def test_remove_nonexistent_tag_is_noop_not_error(self, client, org, owner_headers, db):
        make_ch(db, org, "a@example.com", tags=["keep"])
        body = {"cohort": {"emails": ["a@example.com"]}, "tags": ["not-there"], "mode": "remove"}
        r = client.post("/api/v1/customers/bulk/tags", json=body, headers=owner_headers)
        assert r.status_code == 200
        summary = r.json()
        assert summary == {"matched": 1, "updated": 1, "skipped": 0, "errors": []}


class TestBulkTagsScopeAndCohort:
    def test_invalid_mode_rejected(self, client, org, owner_headers, db):
        make_ch(db, org, "a@example.com")
        body = {"cohort": {"emails": ["a@example.com"]}, "tags": ["vip"], "mode": "bogus"}
        r = client.post("/api/v1/customers/bulk/tags", json=body, headers=owner_headers)
        assert r.status_code == 422

    def test_both_emails_and_filter_rejected(self, client, org, owner_headers, db):
        make_ch(db, org, "a@example.com")
        body = {
            "cohort": {"emails": ["a@example.com"], "filter": {"segment": "dormant"}},
            "tags": ["vip"],
            "mode": "add",
        }
        r = client.post("/api/v1/customers/bulk/tags", json=body, headers=owner_headers)
        assert r.status_code == 422

    def test_cross_org_email_skipped(self, client, org, other_org, owner_headers, db):
        make_ch(db, other_org, "theirs@example.com")
        body = {"cohort": {"emails": ["theirs@example.com"]}, "tags": ["vip"], "mode": "add"}
        r = client.post("/api/v1/customers/bulk/tags", json=body, headers=owner_headers)
        assert r.status_code == 200
        summary = r.json()
        assert summary == {"matched": 0, "updated": 0, "skipped": 1, "errors": []}

        other_row = db.query(CustomerHealth).filter_by(customer_email="theirs@example.com").first()
        assert other_row.tags in (None, [])

    def test_filter_cohort_applies_to_matching_customers(self, client, org, owner_headers, db):
        make_ch(db, org, "risky@example.com", segment="at_risk")
        make_ch(db, org, "healthy@example.com", segment="happy_advocate")
        body = {
            "cohort": {"filter": {"segment": "at_risk"}},
            "tags": ["watch"],
            "mode": "add",
        }
        r = client.post("/api/v1/customers/bulk/tags", json=body, headers=owner_headers)
        assert r.status_code == 200
        summary = r.json()
        assert summary["matched"] == 1
        assert summary["updated"] == 1

        risky = db.query(CustomerHealth).filter_by(customer_email="risky@example.com").first()
        assert "watch" in risky.tags
        healthy = db.query(CustomerHealth).filter_by(customer_email="healthy@example.com").first()
        assert healthy.tags in (None, [])

    def test_route_not_swallowed_by_email_route(self, client, org, owner_headers):
        body = {"cohort": {"emails": []}, "tags": ["vip"], "mode": "add"}
        r = client.post("/api/v1/customers/bulk/tags", json=body, headers=owner_headers)
        assert r.status_code != 404


# ---------------------------------------------------------------------------
# POST /customers/bulk/assign-owner
# ---------------------------------------------------------------------------

class TestBulkAssignOwnerRBAC:
    def test_member_forbidden(self, client, org, member_headers, owner_user, db):
        make_ch(db, org, "a@example.com")
        body = {"cohort": {"emails": ["a@example.com"]}, "user_id": owner_user.id}
        r = client.post("/api/v1/customers/bulk/assign-owner", json=body, headers=member_headers)
        assert r.status_code == 403


class TestBulkAssignOwnerSetClear:
    def test_set_owner(self, client, org, owner_headers, owner_user, db):
        make_ch(db, org, "a@example.com")
        body = {"cohort": {"emails": ["a@example.com"]}, "user_id": owner_user.id}
        r = client.post("/api/v1/customers/bulk/assign-owner", json=body, headers=owner_headers)
        assert r.status_code == 200
        summary = r.json()
        assert summary == {"matched": 1, "updated": 1, "skipped": 0, "errors": []}
        row = db.query(CustomerHealth).filter_by(customer_email="a@example.com").first()
        assert row.cs_owner_user_id == owner_user.id

    def test_clear_owner_with_null(self, client, org, owner_headers, owner_user, db):
        make_ch(db, org, "a@example.com", cs_owner_user_id=owner_user.id)
        body = {"cohort": {"emails": ["a@example.com"]}, "user_id": None}
        r = client.post("/api/v1/customers/bulk/assign-owner", json=body, headers=owner_headers)
        assert r.status_code == 200
        row = db.query(CustomerHealth).filter_by(customer_email="a@example.com").first()
        assert row.cs_owner_user_id is None

    def test_non_member_user_id_rejected(self, client, org, other_org, owner_headers, db):
        outsider = _make_user(db, other_org, "outsider@other.com", role="admin")
        make_ch(db, org, "a@example.com")
        body = {"cohort": {"emails": ["a@example.com"]}, "user_id": outsider.id}
        r = client.post("/api/v1/customers/bulk/assign-owner", json=body, headers=owner_headers)
        assert r.status_code == 422
        row = db.query(CustomerHealth).filter_by(customer_email="a@example.com").first()
        assert row.cs_owner_user_id is None

    def test_deactivated_member_user_id_rejected(self, client, org, owner_headers, db):
        deactivated = _make_user(db, org, "gone@bulk.com", role="member", is_deactivated=True)
        make_ch(db, org, "a@example.com")
        body = {"cohort": {"emails": ["a@example.com"]}, "user_id": deactivated.id}
        r = client.post("/api/v1/customers/bulk/assign-owner", json=body, headers=owner_headers)
        assert r.status_code == 422

    def test_nonexistent_user_id_rejected(self, client, org, owner_headers, db):
        make_ch(db, org, "a@example.com")
        body = {"cohort": {"emails": ["a@example.com"]}, "user_id": 999999}
        r = client.post("/api/v1/customers/bulk/assign-owner", json=body, headers=owner_headers)
        assert r.status_code == 422

    def test_org_scoped_cohort(self, client, org, other_org, owner_headers, owner_user, db):
        make_ch(db, other_org, "theirs@example.com")
        body = {"cohort": {"emails": ["theirs@example.com"]}, "user_id": owner_user.id}
        r = client.post("/api/v1/customers/bulk/assign-owner", json=body, headers=owner_headers)
        assert r.status_code == 200
        summary = r.json()
        assert summary == {"matched": 0, "updated": 0, "skipped": 1, "errors": []}

    def test_filter_cohort(self, client, org, owner_headers, owner_user, db):
        make_ch(db, org, "risky@example.com", segment="at_risk")
        make_ch(db, org, "other@example.com", segment="dormant")
        body = {"cohort": {"filter": {"segment": "at_risk"}}, "user_id": owner_user.id}
        r = client.post("/api/v1/customers/bulk/assign-owner", json=body, headers=owner_headers)
        assert r.status_code == 200
        summary = r.json()
        assert summary["matched"] == 1
        assert summary["updated"] == 1
        risky = db.query(CustomerHealth).filter_by(customer_email="risky@example.com").first()
        assert risky.cs_owner_user_id == owner_user.id
        other = db.query(CustomerHealth).filter_by(customer_email="other@example.com").first()
        assert other.cs_owner_user_id is None

    def test_route_not_swallowed_by_email_route(self, client, org, owner_headers):
        body = {"cohort": {"emails": []}, "user_id": None}
        r = client.post("/api/v1/customers/bulk/assign-owner", json=body, headers=owner_headers)
        assert r.status_code != 404
