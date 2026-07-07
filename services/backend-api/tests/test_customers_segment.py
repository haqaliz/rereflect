"""
TDD tests — segment-api aspect (customer-segments feature).

Coverage:
  Phase 1: `segment` query param + column on GET /api/v1/customers/
  Phase 2: `segment` field on the shared Customer 360 profile serializer,
           exposed via GET /api/v1/customers/{email} (internal route).

See docs/planning/customer-segments/segment-api/{plan_20260708.md,spec.md}.
"""
import pytest
from datetime import datetime
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

from src.models.customer_health import CustomerHealth
from src.models.organization import Organization
from src.models.user import User
from src.api.auth import hash_password, create_access_token
from src.services.segment_service import SEGMENT_SLUGS


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def pro_org(db: Session) -> Organization:
    org = Organization(name="Segment Test Co", plan="pro")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


@pytest.fixture
def pro_user(db: Session, pro_org: Organization) -> User:
    user = User(
        email="segpro@example.com",
        password_hash=hash_password("password123"),
        organization_id=pro_org.id,
        role="admin",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def pro_headers(pro_user: User) -> dict:
    token = create_access_token({
        "user_id": pro_user.id,
        "organization_id": pro_user.organization_id,
        "role": pro_user.role,
    })
    return {"Authorization": f"Bearer {token}"}


def make_customer_health(
    db: Session,
    org: Organization,
    email: str,
    health_score: int = 60,
    risk_level: str = "moderate",
    feedback_count: int = 5,
    confidence_level: str = "medium",
    last_feedback_at: datetime = None,
    is_archived: bool = False,
    customer_name: str = None,
    segment: str = None,
) -> CustomerHealth:
    record = CustomerHealth(
        organization_id=org.id,
        customer_email=email,
        customer_name=customer_name,
        health_score=health_score,
        risk_level=risk_level,
        feedback_count=feedback_count,
        confidence_level=confidence_level,
        last_feedback_at=last_feedback_at or datetime.utcnow(),
        is_archived=is_archived,
        churn_risk_component=50,
        sentiment_component=60,
        resolution_component=70,
        frequency_component=55,
        segment=segment,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


# ---------------------------------------------------------------------------
# Phase 1 — segment filter + column on the list endpoint
# ---------------------------------------------------------------------------

class TestCustomerListSegmentFilter:
    """GET /api/v1/customers/?segment=<slug> filters by the persisted segment."""

    def test_filter_by_segment_returns_only_matching(
        self, client: TestClient, pro_org: Organization, pro_headers: dict, db: Session
    ):
        make_customer_health(db, pro_org, "churner@example.com", segment="silent_churner")
        make_customer_health(db, pro_org, "advocate@example.com", segment="happy_advocate")

        response = client.get("/api/v1/customers/?segment=silent_churner", headers=pro_headers)
        assert response.status_code == 200
        items = response.json()["items"]
        assert len(items) == 1
        assert items[0]["customer_email"] == "churner@example.com"

    def test_filter_by_unsegmented(
        self, client: TestClient, pro_org: Organization, pro_headers: dict, db: Session
    ):
        make_customer_health(db, pro_org, "none@example.com", segment=None)
        make_customer_health(db, pro_org, "advocate@example.com", segment="happy_advocate")

        response = client.get("/api/v1/customers/?segment=unsegmented", headers=pro_headers)
        assert response.status_code == 200
        # "unsegmented" is a valid slug per SEGMENT_SLUGS, but records store
        # NULL rather than the literal string "unsegmented" when unclassified
        # (see segment-engine). The filter must not error, and must not match
        # NULL rows via a literal string comparison.
        items = response.json()["items"]
        assert all(it["customer_email"] != "advocate@example.com" for it in items)

    def test_invalid_segment_slug_returns_422(
        self, client: TestClient, pro_headers: dict
    ):
        response = client.get("/api/v1/customers/?segment=not_a_real_segment", headers=pro_headers)
        assert response.status_code == 422

    def test_segment_composes_with_risk_level(
        self, client: TestClient, pro_org: Organization, pro_headers: dict, db: Session
    ):
        make_customer_health(
            db, pro_org, "match@example.com",
            segment="at_risk", risk_level="at_risk",
        )
        make_customer_health(
            db, pro_org, "wrong_risk@example.com",
            segment="at_risk", risk_level="critical",
        )
        make_customer_health(
            db, pro_org, "wrong_segment@example.com",
            segment="dormant", risk_level="at_risk",
        )

        response = client.get(
            "/api/v1/customers/?segment=at_risk&risk_level=at_risk", headers=pro_headers
        )
        assert response.status_code == 200
        items = response.json()["items"]
        assert len(items) == 1
        assert items[0]["customer_email"] == "match@example.com"

    def test_segment_composes_with_search(
        self, client: TestClient, pro_org: Organization, pro_headers: dict, db: Session
    ):
        make_customer_health(
            db, pro_org, "findme@acme.com", segment="power_user",
        )
        make_customer_health(
            db, pro_org, "other@acme.com", segment="power_user",
        )
        make_customer_health(
            db, pro_org, "findme@other.com", segment="new",
        )

        response = client.get(
            "/api/v1/customers/?segment=power_user&search=findme", headers=pro_headers
        )
        assert response.status_code == 200
        items = response.json()["items"]
        assert len(items) == 1
        assert items[0]["customer_email"] == "findme@acme.com"

    def test_all_segment_slugs_are_valid_query_values(
        self, client: TestClient, pro_org: Organization, pro_headers: dict, db: Session
    ):
        """Every slug in SEGMENT_SLUGS must be accepted (not 422)."""
        for slug in SEGMENT_SLUGS:
            response = client.get(f"/api/v1/customers/?segment={slug}", headers=pro_headers)
            assert response.status_code == 200, f"slug '{slug}' unexpectedly rejected"

    def test_segment_filter_is_org_scoped(
        self, client: TestClient, pro_org: Organization, pro_headers: dict, db: Session
    ):
        other_org = Organization(name="Other Segment Co", plan="pro")
        db.add(other_org)
        db.commit()
        db.refresh(other_org)

        make_customer_health(db, other_org, "theirs@example.com", segment="dormant")

        response = client.get("/api/v1/customers/?segment=dormant", headers=pro_headers)
        assert response.status_code == 200
        assert response.json()["items"] == []


class TestCustomerListItemSegmentField:
    """CustomerListItem must carry the segment field, populated from the row."""

    def test_item_includes_segment_field(
        self, client: TestClient, pro_org: Organization, pro_headers: dict, db: Session
    ):
        make_customer_health(db, pro_org, "tagged@example.com", segment="new")
        response = client.get("/api/v1/customers/", headers=pro_headers)
        items = response.json()["items"]
        assert len(items) == 1
        assert items[0]["segment"] == "new"

    def test_item_segment_null_when_not_yet_computed(
        self, client: TestClient, pro_org: Organization, pro_headers: dict, db: Session
    ):
        make_customer_health(db, pro_org, "untagged@example.com", segment=None)
        response = client.get("/api/v1/customers/", headers=pro_headers)
        items = response.json()["items"]
        assert len(items) == 1
        assert items[0]["segment"] is None


class TestCustomerListSegmentSort:
    """Optional should-have: sort_by=segment is accepted."""

    def test_sort_by_segment_is_accepted(
        self, client: TestClient, pro_org: Organization, pro_headers: dict, db: Session
    ):
        make_customer_health(db, pro_org, "a@example.com", segment="at_risk")
        make_customer_health(db, pro_org, "b@example.com", segment="new")
        response = client.get(
            "/api/v1/customers/?sort_by=segment&sort_order=asc", headers=pro_headers
        )
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# Phase 2 — segment on the shared profile serializer (internal route)
# ---------------------------------------------------------------------------

class TestCustomerProfileSegmentField:
    """GET /api/v1/customers/{email} must include the persisted segment."""

    def test_profile_includes_segment(
        self, client: TestClient, pro_org: Organization, pro_headers: dict, db: Session
    ):
        make_customer_health(db, pro_org, "profile@example.com", segment="happy_advocate")
        response = client.get("/api/v1/customers/profile@example.com", headers=pro_headers)
        assert response.status_code == 200
        assert response.json()["segment"] == "happy_advocate"

    def test_profile_segment_null_when_not_yet_computed(
        self, client: TestClient, pro_org: Organization, pro_headers: dict, db: Session
    ):
        make_customer_health(db, pro_org, "noseg@example.com", segment=None)
        response = client.get("/api/v1/customers/noseg@example.com", headers=pro_headers)
        assert response.status_code == 200
        assert response.json()["segment"] is None


class TestSerializerSegmentField:
    """Unit-level: serialize_customer_profile() output includes 'segment'."""

    def test_serializer_output_contains_segment(
        self, db: Session, pro_org: Organization
    ):
        from src.services.customer_profile_serializer import serialize_customer_profile

        record = make_customer_health(db, pro_org, "unit@example.com", segment="dormant")
        data = serialize_customer_profile(record, db)
        assert "segment" in data
        assert data["segment"] == "dormant"
