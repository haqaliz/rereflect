"""
TDD tests for GET /api/v1/customers/ list endpoint.
"""
import pytest
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

from src.models.customer_health import CustomerHealth
from src.models.feedback import FeedbackItem
from src.models.organization import Organization
from src.models.user import User
from src.api.auth import hash_password, create_access_token


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def pro_org(db: Session) -> Organization:
    org = Organization(name="Pro Company", plan="pro")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


@pytest.fixture
def pro_user(db: Session, pro_org: Organization) -> User:
    user = User(
        email="pro@example.com",
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


@pytest.fixture
def free_org(db: Session) -> Organization:
    org = Organization(name="Free Company", plan="free")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


@pytest.fixture
def free_user(db: Session, free_org: Organization) -> User:
    user = User(
        email="free@example.com",
        password_hash=hash_password("password123"),
        organization_id=free_org.id,
        role="admin",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def free_headers(free_user: User) -> dict:
    token = create_access_token({
        "user_id": free_user.id,
        "organization_id": free_user.organization_id,
        "role": free_user.role,
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
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


# ---------------------------------------------------------------------------
# Plan Gating
# ---------------------------------------------------------------------------

class TestCustomerListPlanGating:
    """Free plan users should get 403 on the customers list endpoint."""

    def test_free_plan_returns_403(self, client: TestClient, free_headers: dict):
        response = client.get("/api/v1/customers/", headers=free_headers)
        assert response.status_code == 403

    def test_pro_plan_allowed(self, client: TestClient, pro_headers: dict):
        response = client.get("/api/v1/customers/", headers=pro_headers)
        assert response.status_code == 200

    def test_unauthenticated_returns_401(self, client: TestClient):
        response = client.get("/api/v1/customers/")
        assert response.status_code == 403  # HTTPBearer returns 403 when no token


# ---------------------------------------------------------------------------
# Basic Response Structure
# ---------------------------------------------------------------------------

class TestCustomerListResponse:
    """Test response structure and basic data retrieval."""

    def test_empty_org_returns_empty_list(self, client: TestClient, pro_headers: dict):
        response = client.get("/api/v1/customers/", headers=pro_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0
        assert data["page"] == 1
        assert "summary" in data

    def test_response_has_required_fields(self, client: TestClient, pro_org: Organization, pro_headers: dict, db: Session):
        make_customer_health(db, pro_org, "user@example.com", health_score=75, risk_level="healthy")
        response = client.get("/api/v1/customers/", headers=pro_headers)
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "page_size" in data
        assert "summary" in data

    def test_item_has_required_fields(self, client: TestClient, pro_org: Organization, pro_headers: dict, db: Session):
        make_customer_health(db, pro_org, "user@example.com", health_score=75, risk_level="healthy",
                            customer_name="John Doe")
        response = client.get("/api/v1/customers/", headers=pro_headers)
        item = response.json()["items"][0]
        assert "customer_email" in item
        assert "customer_name" in item
        assert "health_score" in item
        assert "risk_level" in item
        assert "confidence_level" in item
        assert "feedback_count" in item
        assert "last_feedback_at" in item
        assert "sentiment_trend" in item
        assert "is_archived" in item

    def test_summary_has_required_fields(self, client: TestClient, pro_org: Organization, pro_headers: dict, db: Session):
        make_customer_health(db, pro_org, "a@example.com", health_score=80, risk_level="healthy")
        make_customer_health(db, pro_org, "b@example.com", health_score=20, risk_level="critical")
        response = client.get("/api/v1/customers/", headers=pro_headers)
        summary = response.json()["summary"]
        assert "total_customers" in summary
        assert "avg_health_score" in summary
        assert "risk_distribution" in summary
        dist = summary["risk_distribution"]
        assert "healthy" in dist
        assert "moderate" in dist
        assert "at_risk" in dist
        assert "critical" in dist


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------

class TestCustomerListPagination:
    """Test pagination behavior."""

    def test_default_pagination(self, client: TestClient, pro_org: Organization, pro_headers: dict, db: Session):
        for i in range(5):
            make_customer_health(db, pro_org, f"user{i}@example.com")
        response = client.get("/api/v1/customers/", headers=pro_headers)
        data = response.json()
        assert data["page"] == 1
        assert data["page_size"] == 20
        assert len(data["items"]) == 5

    def test_custom_page_size(self, client: TestClient, pro_org: Organization, pro_headers: dict, db: Session):
        for i in range(10):
            make_customer_health(db, pro_org, f"page{i}@example.com")
        response = client.get("/api/v1/customers/?page_size=3", headers=pro_headers)
        data = response.json()
        assert data["page_size"] == 3
        assert len(data["items"]) == 3

    def test_page_2(self, client: TestClient, pro_org: Organization, pro_headers: dict, db: Session):
        for i in range(5):
            make_customer_health(db, pro_org, f"p2user{i}@example.com")
        response = client.get("/api/v1/customers/?page=2&page_size=3", headers=pro_headers)
        data = response.json()
        assert data["page"] == 2
        assert len(data["items"]) == 2  # 5 total, page 2 with size 3 = 2

    def test_total_reflects_all_records(self, client: TestClient, pro_org: Organization, pro_headers: dict, db: Session):
        for i in range(7):
            make_customer_health(db, pro_org, f"tot{i}@example.com")
        response = client.get("/api/v1/customers/?page_size=3", headers=pro_headers)
        data = response.json()
        assert data["total"] == 7

    def test_page_size_max_100(self, client: TestClient, pro_headers: dict):
        response = client.get("/api/v1/customers/?page_size=200", headers=pro_headers)
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# Sorting
# ---------------------------------------------------------------------------

class TestCustomerListSorting:
    """Test sorting by all 4 supported fields."""

    def test_sort_by_health_score_asc(self, client: TestClient, pro_org: Organization, pro_headers: dict, db: Session):
        make_customer_health(db, pro_org, "low@example.com", health_score=20)
        make_customer_health(db, pro_org, "high@example.com", health_score=80)
        response = client.get("/api/v1/customers/?sort_by=health_score&sort_order=asc", headers=pro_headers)
        items = response.json()["items"]
        assert items[0]["health_score"] <= items[1]["health_score"]

    def test_sort_by_health_score_desc(self, client: TestClient, pro_org: Organization, pro_headers: dict, db: Session):
        make_customer_health(db, pro_org, "low@example.com", health_score=20)
        make_customer_health(db, pro_org, "high@example.com", health_score=80)
        response = client.get("/api/v1/customers/?sort_by=health_score&sort_order=desc", headers=pro_headers)
        items = response.json()["items"]
        assert items[0]["health_score"] >= items[1]["health_score"]

    def test_sort_by_feedback_count(self, client: TestClient, pro_org: Organization, pro_headers: dict, db: Session):
        make_customer_health(db, pro_org, "few@example.com", feedback_count=2)
        make_customer_health(db, pro_org, "many@example.com", feedback_count=20)
        response = client.get("/api/v1/customers/?sort_by=feedback_count&sort_order=asc", headers=pro_headers)
        items = response.json()["items"]
        assert items[0]["feedback_count"] <= items[1]["feedback_count"]

    def test_sort_by_customer_email(self, client: TestClient, pro_org: Organization, pro_headers: dict, db: Session):
        make_customer_health(db, pro_org, "z@example.com")
        make_customer_health(db, pro_org, "a@example.com")
        response = client.get("/api/v1/customers/?sort_by=customer_email&sort_order=asc", headers=pro_headers)
        items = response.json()["items"]
        assert items[0]["customer_email"] <= items[1]["customer_email"]

    def test_sort_by_last_feedback_at(self, client: TestClient, pro_org: Organization, pro_headers: dict, db: Session):
        old_date = datetime.utcnow() - timedelta(days=10)
        new_date = datetime.utcnow() - timedelta(days=1)
        make_customer_health(db, pro_org, "old@example.com", last_feedback_at=old_date)
        make_customer_health(db, pro_org, "new@example.com", last_feedback_at=new_date)
        response = client.get("/api/v1/customers/?sort_by=last_feedback_at&sort_order=desc", headers=pro_headers)
        items = response.json()["items"]
        assert items[0]["customer_email"] == "new@example.com"

    def test_invalid_sort_field_rejected(self, client: TestClient, pro_headers: dict):
        response = client.get("/api/v1/customers/?sort_by=invalid_field", headers=pro_headers)
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# Risk Level Filtering
# ---------------------------------------------------------------------------

class TestCustomerListRiskFilter:
    """Test filtering by risk level."""

    def test_filter_by_healthy(self, client: TestClient, pro_org: Organization, pro_headers: dict, db: Session):
        make_customer_health(db, pro_org, "healthy@example.com", health_score=80, risk_level="healthy")
        make_customer_health(db, pro_org, "critical@example.com", health_score=10, risk_level="critical")
        response = client.get("/api/v1/customers/?risk_level=healthy", headers=pro_headers)
        items = response.json()["items"]
        assert len(items) == 1
        assert items[0]["customer_email"] == "healthy@example.com"

    def test_filter_by_critical(self, client: TestClient, pro_org: Organization, pro_headers: dict, db: Session):
        make_customer_health(db, pro_org, "healthy@example.com", health_score=80, risk_level="healthy")
        make_customer_health(db, pro_org, "critical@example.com", health_score=10, risk_level="critical")
        response = client.get("/api/v1/customers/?risk_level=critical", headers=pro_headers)
        items = response.json()["items"]
        assert len(items) == 1
        assert items[0]["customer_email"] == "critical@example.com"

    def test_invalid_risk_level_rejected(self, client: TestClient, pro_headers: dict):
        response = client.get("/api/v1/customers/?risk_level=unknown_level", headers=pro_headers)
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

class TestCustomerListSearch:
    """Test search by email and name (ILIKE)."""

    def test_search_by_email(self, client: TestClient, pro_org: Organization, pro_headers: dict, db: Session):
        make_customer_health(db, pro_org, "john@acme.com", customer_name="John Doe")
        make_customer_health(db, pro_org, "jane@corp.io", customer_name="Jane Smith")
        response = client.get("/api/v1/customers/?search=acme", headers=pro_headers)
        items = response.json()["items"]
        assert len(items) == 1
        assert items[0]["customer_email"] == "john@acme.com"

    def test_search_by_name(self, client: TestClient, pro_org: Organization, pro_headers: dict, db: Session):
        make_customer_health(db, pro_org, "john@acme.com", customer_name="John Doe")
        make_customer_health(db, pro_org, "jane@corp.io", customer_name="Jane Smith")
        response = client.get("/api/v1/customers/?search=Jane", headers=pro_headers)
        items = response.json()["items"]
        assert len(items) == 1
        assert items[0]["customer_email"] == "jane@corp.io"

    def test_search_case_insensitive(self, client: TestClient, pro_org: Organization, pro_headers: dict, db: Session):
        make_customer_health(db, pro_org, "upper@EXAMPLE.com", customer_name="UPPER Case")
        response = client.get("/api/v1/customers/?search=upper", headers=pro_headers)
        items = response.json()["items"]
        assert len(items) == 1

    def test_search_no_results(self, client: TestClient, pro_org: Organization, pro_headers: dict, db: Session):
        make_customer_health(db, pro_org, "john@acme.com")
        response = client.get("/api/v1/customers/?search=nomatch", headers=pro_headers)
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0


# ---------------------------------------------------------------------------
# Archived Customers
# ---------------------------------------------------------------------------

class TestCustomerListArchived:
    """Test that archived customers are excluded by default."""

    def test_archived_excluded_by_default(self, client: TestClient, pro_org: Organization, pro_headers: dict, db: Session):
        make_customer_health(db, pro_org, "active@example.com", is_archived=False)
        make_customer_health(db, pro_org, "archived@example.com", is_archived=True)
        response = client.get("/api/v1/customers/", headers=pro_headers)
        items = response.json()["items"]
        assert len(items) == 1
        assert items[0]["customer_email"] == "active@example.com"

    def test_include_archived_shows_all(self, client: TestClient, pro_org: Organization, pro_headers: dict, db: Session):
        make_customer_health(db, pro_org, "active@example.com", is_archived=False)
        make_customer_health(db, pro_org, "archived@example.com", is_archived=True)
        response = client.get("/api/v1/customers/?include_archived=true", headers=pro_headers)
        items = response.json()["items"]
        assert len(items) == 2


# ---------------------------------------------------------------------------
# Org Isolation
# ---------------------------------------------------------------------------

class TestCustomerListOrgIsolation:
    """Test multi-tenant data isolation."""

    def test_org_a_cannot_see_org_b_customers(self, client: TestClient, pro_org: Organization, pro_headers: dict, db: Session):
        other_org = Organization(name="Other Company", plan="pro")
        db.add(other_org)
        db.commit()
        db.refresh(other_org)

        # Customer in pro_org (user's org)
        make_customer_health(db, pro_org, "mine@example.com")
        # Customer in other_org
        make_customer_health(db, other_org, "theirs@example.com")

        response = client.get("/api/v1/customers/", headers=pro_headers)
        items = response.json()["items"]
        assert len(items) == 1
        assert items[0]["customer_email"] == "mine@example.com"


# ---------------------------------------------------------------------------
# Summary Stats
# ---------------------------------------------------------------------------

class TestCustomerListSummary:
    """Test summary statistics in the response."""

    def test_summary_total_customers(self, client: TestClient, pro_org: Organization, pro_headers: dict, db: Session):
        make_customer_health(db, pro_org, "a@example.com", health_score=80, risk_level="healthy")
        make_customer_health(db, pro_org, "b@example.com", health_score=30, risk_level="at_risk")
        response = client.get("/api/v1/customers/", headers=pro_headers)
        summary = response.json()["summary"]
        assert summary["total_customers"] == 2

    def test_summary_avg_health_score(self, client: TestClient, pro_org: Organization, pro_headers: dict, db: Session):
        make_customer_health(db, pro_org, "a@example.com", health_score=60)
        make_customer_health(db, pro_org, "b@example.com", health_score=80)
        response = client.get("/api/v1/customers/", headers=pro_headers)
        summary = response.json()["summary"]
        assert summary["avg_health_score"] == 70

    def test_summary_risk_distribution(self, client: TestClient, pro_org: Organization, pro_headers: dict, db: Session):
        make_customer_health(db, pro_org, "h@example.com", risk_level="healthy")
        make_customer_health(db, pro_org, "m@example.com", risk_level="moderate")
        make_customer_health(db, pro_org, "a@example.com", risk_level="at_risk")
        make_customer_health(db, pro_org, "c@example.com", risk_level="critical")
        response = client.get("/api/v1/customers/", headers=pro_headers)
        dist = response.json()["summary"]["risk_distribution"]
        assert dist["healthy"] == 1
        assert dist["moderate"] == 1
        assert dist["at_risk"] == 1
        assert dist["critical"] == 1

    def test_summary_excludes_archived(self, client: TestClient, pro_org: Organization, pro_headers: dict, db: Session):
        """Summary should count non-archived customers by default."""
        make_customer_health(db, pro_org, "a@example.com", is_archived=False)
        make_customer_health(db, pro_org, "b@example.com", is_archived=True)
        response = client.get("/api/v1/customers/", headers=pro_headers)
        summary = response.json()["summary"]
        assert summary["total_customers"] == 1

    def test_sentiment_trend_in_items(self, client: TestClient, pro_org: Organization, pro_headers: dict, db: Session):
        """Each item should include a sentiment_trend object."""
        make_customer_health(db, pro_org, "trend@example.com")
        response = client.get("/api/v1/customers/", headers=pro_headers)
        item = response.json()["items"][0]
        assert "direction" in item["sentiment_trend"]
        assert "change_percent" in item["sentiment_trend"]
