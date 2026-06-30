"""
TDD tests — public-api-customer360 aspect.

Coverage:
  Phase 1: Shared Customer 360 profile serializer
  Phase 2: GET /api/public/v1/customers/{email}       — full profile
  Phase 3: GET /api/public/v1/customers/{email}/timeline — cursor paginated
  Phase 4: GET /api/public/v1/customers/{email}/health   — extended with usage_component

All tests use an in-memory SQLite database (SQLAlchemy ORM-portable queries).
API-key fixture pattern mirrors tests/test_public_api.py.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Generator, Optional

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.api.main import app
from src.database.session import get_db
from src.models.api_key import ApiKey
from src.models.base import Base
from src.models.customer_health import CustomerHealth
from src.models.crm_enrichment import CrmEnrichment
from src.models.feedback import FeedbackItem
from src.models.feedback_workflow_event import FeedbackWorkflowEvent
from src.models.customer_health_history import CustomerHealthHistory
from src.models.organization import Organization
from src.models.user import User
from src.api.auth import create_access_token, hash_password


# ---------------------------------------------------------------------------
# In-process SQLite engine (isolated from conftest)
# ---------------------------------------------------------------------------

_SQLITE_URL = "sqlite:///:memory:"
_engine = create_engine(
    _SQLITE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)


@pytest.fixture(scope="function")
def db() -> Generator[Session, None, None]:
    Base.metadata.create_all(bind=_engine)
    session = _SessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=_engine)


@pytest.fixture(scope="function")
def client(db: Session) -> Generator[TestClient, None, None]:
    def _override():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = _override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_api_key(
    db: Session,
    org_id: int,
    scopes: str = "read",
    revoked: bool = False,
) -> tuple[str, ApiKey]:
    """Create a stored ApiKey row and return (raw_key, orm_row)."""
    raw = f"rrf_{secrets.token_urlsafe(24)}"
    prefix = raw[:10]
    key_hash = hashlib.sha256(raw.encode()).hexdigest()
    row = ApiKey(
        organization_id=org_id,
        name="test key",
        key_prefix=prefix,
        key_hash=key_hash,
        scopes=scopes,
        revoked_at=datetime.utcnow() if revoked else None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return raw, row


def _make_org(db: Session, name: str = "Acme Corp", plan: str = "pro") -> Organization:
    org = Organization(name=name, plan=plan)
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def _make_health(
    db: Session,
    org_id: int,
    email: str,
    *,
    health_score: int = 60,
    risk_level: str = "moderate",
    feedback_count: int = 5,
    confidence_level: str = "medium",
    churn_risk_component: int = 50,
    sentiment_component: int = 60,
    resolution_component: int = 70,
    frequency_component: int = 55,
    usage_component: Optional[int] = None,
    churn_probability: Optional[float] = None,
    churn_probability_low: Optional[float] = None,
    churn_probability_high: Optional[float] = None,
    time_to_churn_bucket: Optional[str] = None,
    customer_name: Optional[str] = None,
    llm_analysis_data: Optional[dict] = None,
    llm_analysis: Optional[str] = None,
    is_archived: bool = False,
) -> CustomerHealth:
    h = CustomerHealth(
        organization_id=org_id,
        customer_email=email,
        customer_name=customer_name,
        health_score=health_score,
        risk_level=risk_level,
        feedback_count=feedback_count,
        confidence_level=confidence_level,
        churn_risk_component=churn_risk_component,
        sentiment_component=sentiment_component,
        resolution_component=resolution_component,
        frequency_component=frequency_component,
        usage_component=usage_component,
        churn_probability=churn_probability,
        churn_probability_low=churn_probability_low,
        churn_probability_high=churn_probability_high,
        time_to_churn_bucket=time_to_churn_bucket,
        llm_analysis_data=llm_analysis_data,
        llm_analysis=llm_analysis,
        is_archived=is_archived,
        last_feedback_at=datetime.utcnow() - timedelta(days=2),
    )
    db.add(h)
    db.commit()
    db.refresh(h)
    return h


def _make_feedback(
    db: Session,
    org_id: int,
    email: str,
    text: str = "some feedback",
    created_at: Optional[datetime] = None,
) -> FeedbackItem:
    fb = FeedbackItem(
        organization_id=org_id,
        customer_email=email,
        text=text,
        source="test",
        workflow_status="new",
        sentiment_label="neutral",
        sentiment_score=0.0,
        churn_risk_score=30,
        is_urgent=False,
        created_at=created_at or datetime.utcnow(),
    )
    db.add(fb)
    db.commit()
    db.refresh(fb)
    return fb


def _make_user(db: Session, org: Organization) -> tuple[User, str]:
    """Create a pro-plan user and return (user, bearer_token)."""
    user = User(
        email=f"user_{secrets.token_hex(4)}@example.com",
        password_hash=hash_password("password123"),
        organization_id=org.id,
        role="admin",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_access_token({
        "user_id": user.id,
        "organization_id": user.organization_id,
        "role": user.role,
    })
    return user, token


# ---------------------------------------------------------------------------
# Phase 1 — Shared Customer 360 profile serializer
# ---------------------------------------------------------------------------

class TestCustomerProfileSerializer:
    """Unit-level tests for src.services.customer_profile_serializer."""

    def test_serializer_module_importable(self):
        """RED: import must succeed once the file is created."""
        from src.services.customer_profile_serializer import serialize_customer_profile  # noqa: F401

    def test_serializer_returns_all_required_fields(self, db: Session):
        """Serializer must return all fields: health_score, risk_level,
        confidence_level, 5 components (incl. usage), churn_probability/bucket,
        LLM summary fields, feedback_count, last_feedback_at."""
        from src.services.customer_profile_serializer import serialize_customer_profile

        org = _make_org(db)
        record = _make_health(
            db,
            org.id,
            "test@acme.com",
            health_score=75,
            risk_level="moderate",
            confidence_level="high",
            usage_component=72,
            churn_probability=0.35,
            churn_probability_low=0.20,
            churn_probability_high=0.50,
            time_to_churn_bucket="2-4w",
            llm_analysis_data={
                "analysis": "Customer is at mild risk",
                "recommended_actions": ["Send check-in email"],
                "risk_drivers": ["low usage"],
                "estimated_urgency": "medium",
                "analysis_type": "full",
            },
        )

        result = serialize_customer_profile(record)

        # Core fields
        assert result["customer_email"] == "test@acme.com"
        assert result["health_score"] == 75
        assert result["risk_level"] == "moderate"
        assert result["confidence_level"] == "high"
        assert result["feedback_count"] == 5
        assert result["last_feedback_at"] is not None
        assert result["is_archived"] is False

        # Components (5 including usage)
        assert result["churn_risk_component"] == 50
        assert result["sentiment_component"] == 60
        assert result["resolution_component"] == 70
        assert result["frequency_component"] == 55
        assert result["usage_component"] == 72

        # Churn prediction
        assert abs(result["churn_probability"] - 0.35) < 0.001
        assert abs(result["churn_probability_low"] - 0.20) < 0.001
        assert abs(result["churn_probability_high"] - 0.50) < 0.001
        assert result["time_to_churn_bucket"] == "2-4w"

        # LLM summary fields
        assert result["llm_analysis_summary"] == "Customer is at mild risk"
        assert result["llm_recommended_actions"] == ["Send check-in email"]
        assert result["llm_risk_drivers"] == ["low usage"]
        assert result["llm_urgency"] == "medium"
        assert result["llm_analysis_type"] == "full"
        assert result["llm_analyzed_at"] is None  # not set in this fixture
        assert "llm_analysis" in result  # legacy field must be present (may be None)

    def test_serializer_handles_null_llm_data(self, db: Session):
        """When llm_analysis_data is None, LLM fields must be None (not raise)."""
        from src.services.customer_profile_serializer import serialize_customer_profile

        org = _make_org(db)
        record = _make_health(db, org.id, "plain@acme.com")
        result = serialize_customer_profile(record)
        assert result["llm_analysis_summary"] is None
        assert result["llm_recommended_actions"] is None
        assert result["llm_risk_drivers"] is None
        assert result["llm_urgency"] is None
        assert result["llm_analysis_type"] is None

    def test_serializer_defaults_components_to_50(self, db: Session):
        """Components that are None/0 in the DB should default to 50."""
        from src.services.customer_profile_serializer import serialize_customer_profile

        org = _make_org(db)
        h = CustomerHealth(
            organization_id=org.id,
            customer_email="defaults@acme.com",
            health_score=50,
            risk_level="moderate",
            feedback_count=0,
            # leave component columns NULL / unset
        )
        db.add(h)
        db.commit()
        db.refresh(h)

        result = serialize_customer_profile(h)
        assert result["churn_risk_component"] == 50
        assert result["sentiment_component"] == 50
        assert result["resolution_component"] == 50
        assert result["frequency_component"] == 50

    def test_serializer_usage_component_none_when_not_set(self, db: Session):
        """usage_component must be None when the DB column is NULL."""
        from src.services.customer_profile_serializer import serialize_customer_profile

        org = _make_org(db)
        record = _make_health(db, org.id, "nousage@acme.com")  # usage_component not set
        result = serialize_customer_profile(record)
        assert result["usage_component"] is None

    def test_serializer_crm_fields_when_row_exists(self, db: Session):
        """B1-RED: serializer returns all 7 crm_* fields from a CrmEnrichment row."""
        from src.services.customer_profile_serializer import serialize_customer_profile
        import datetime as dt

        org = _make_org(db)
        record = _make_health(db, org.id, "crm@acme.com")
        sync_at = dt.datetime(2026, 6, 1, 12, 0, 0)
        renewal = dt.datetime(2026, 9, 1, 0, 0, 0)
        crm_row = CrmEnrichment(
            organization_id=org.id,
            customer_email="crm@acme.com",
            company_name="Acme Corp",
            lifecycle_stage="customer",
            arr=24000.0,
            renewal_date=renewal,
            deal_name="Enterprise Renewal",
            deal_stage="Closed Won",
            deal_amount=12000.0,
            last_synced_at=sync_at,
        )
        db.add(crm_row)
        db.commit()

        result = serialize_customer_profile(record, db)

        assert result["crm_company_name"] == "Acme Corp"
        assert result["crm_lifecycle_stage"] == "customer"
        assert abs(result["crm_arr"] - 24000.0) < 0.01
        assert result["crm_renewal_date"] == renewal
        assert result["crm_deal_name"] == "Enterprise Renewal"
        assert result["crm_deal_stage"] == "Closed Won"
        assert abs(result["crm_deal_amount"] - 12000.0) < 0.01

    def test_serializer_crm_fields_none_when_no_row(self, db: Session):
        """B1-RED: when no CrmEnrichment row exists, all 7 crm_* fields are None."""
        from src.services.customer_profile_serializer import serialize_customer_profile

        org = _make_org(db)
        record = _make_health(db, org.id, "nocrm@acme.com")

        result = serialize_customer_profile(record, db)

        assert result["crm_company_name"] is None
        assert result["crm_lifecycle_stage"] is None
        assert result["crm_arr"] is None
        assert result["crm_renewal_date"] is None
        assert result["crm_deal_name"] is None
        assert result["crm_deal_stage"] is None
        assert result["crm_deal_amount"] is None

    def test_serializer_crm_fields_none_when_db_not_passed(self, db: Session):
        """B1-RED: backward-compatible — db=None gives all 7 crm_* fields as None."""
        from src.services.customer_profile_serializer import serialize_customer_profile

        org = _make_org(db)
        record = _make_health(db, org.id, "nodbarg@acme.com")

        result = serialize_customer_profile(record)  # no db argument

        assert result["crm_company_name"] is None
        assert result["crm_arr"] is None

    def test_v1_profile_endpoint_uses_serializer_shape(self, client: TestClient, db: Session):
        """Characterization: v1 GET /api/v1/customers/{email} still returns the
        same shape after the serializer extraction (regression guard)."""
        org = _make_org(db)
        _, token = _make_user(db, org)
        _make_health(
            db,
            org.id,
            "v1check@acme.com",
            health_score=80,
            risk_level="healthy",
            confidence_level="high",
            usage_component=65,
        )

        resp = client.get(
            "/api/v1/customers/v1check@acme.com",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()

        # All characterization fields must be present and correct
        assert data["customer_email"] == "v1check@acme.com"
        assert data["health_score"] == 80
        assert data["risk_level"] == "healthy"
        assert data["confidence_level"] == "high"
        assert data["churn_risk_component"] == 50
        assert data["sentiment_component"] == 60
        assert data["resolution_component"] == 70
        assert data["frequency_component"] == 55
        assert data["usage_component"] == 65
        assert "is_archived" in data
        assert "created_at" in data


# ---------------------------------------------------------------------------
# Phase 2 — GET /api/public/v1/customers/{email}
# ---------------------------------------------------------------------------

class TestPublicCustomerProfile:
    """Full Customer 360 profile via the public API."""

    def test_valid_read_key_returns_200(self, client: TestClient, db: Session):
        org = _make_org(db)
        _make_health(db, org.id, "alice@acme.com", health_score=75)
        raw, _ = _make_api_key(db, org.id, scopes="read")

        resp = client.get(
            "/api/public/v1/customers/alice@acme.com",
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 200, resp.text

    def test_valid_key_returns_full_profile_shape(self, client: TestClient, db: Session):
        org = _make_org(db)
        _make_health(
            db,
            org.id,
            "shape@acme.com",
            health_score=70,
            risk_level="healthy",
            confidence_level="high",
            feedback_count=12,
            usage_component=80,
            churn_probability=0.1,
            time_to_churn_bucket="low",
            customer_name="Shape Test",
        )
        raw, _ = _make_api_key(db, org.id, scopes="read")

        resp = client.get(
            "/api/public/v1/customers/shape@acme.com",
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()

        # Core
        assert data["customer_email"] == "shape@acme.com"
        assert data["customer_name"] == "Shape Test"
        assert data["health_score"] == 70
        assert data["risk_level"] == "healthy"
        assert data["confidence_level"] == "high"
        assert data["feedback_count"] == 12
        assert "last_feedback_at" in data

        # Components
        assert data["churn_risk_component"] == 50
        assert data["sentiment_component"] == 60
        assert data["resolution_component"] == 70
        assert data["frequency_component"] == 55
        assert data["usage_component"] == 80

        # Churn prediction
        assert abs(data["churn_probability"] - 0.1) < 0.001
        assert data["time_to_churn_bucket"] == "low"

    def test_missing_read_scope_returns_403(self, client: TestClient, db: Session):
        org = _make_org(db)
        _make_health(db, org.id, "scope@acme.com")
        raw, _ = _make_api_key(db, org.id, scopes="ingest")  # no "read" scope

        resp = client.get(
            "/api/public/v1/customers/scope@acme.com",
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 403, resp.text

    def test_bad_key_returns_401(self, client: TestClient, db: Session):
        org = _make_org(db)
        _make_health(db, org.id, "auth@acme.com")
        fake = f"rrf_{secrets.token_urlsafe(24)}"

        resp = client.get(
            "/api/public/v1/customers/auth@acme.com",
            headers={"Authorization": f"Bearer {fake}"},
        )
        assert resp.status_code == 401, resp.text

    def test_no_key_returns_401(self, client: TestClient, db: Session):
        org = _make_org(db)
        _make_health(db, org.id, "noauth@acme.com")

        resp = client.get("/api/public/v1/customers/noauth@acme.com")
        assert resp.status_code == 401, resp.text

    def test_cross_org_returns_404(self, client: TestClient, db: Session):
        """A key for org A cannot read org B's customer."""
        org_a = _make_org(db, "Org A")
        org_b = _make_org(db, "Org B")
        _make_health(db, org_b.id, "secret@orgb.com")
        raw_a, _ = _make_api_key(db, org_a.id, scopes="read")

        resp = client.get(
            "/api/public/v1/customers/secret@orgb.com",
            headers={"Authorization": f"Bearer {raw_a}"},
        )
        assert resp.status_code == 404, resp.text

    def test_unknown_email_returns_404(self, client: TestClient, db: Session):
        org = _make_org(db)
        raw, _ = _make_api_key(db, org.id, scopes="read")

        resp = client.get(
            "/api/public/v1/customers/nobody@missing.com",
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 404, resp.text

    def test_public_profile_parity_with_v1(self, client: TestClient, db: Session):
        """Public profile fields must match v1 profile for the same customer.

        This is the shared-serializer parity guarantee: no drift between
        the two surfaces.
        """
        org = _make_org(db)
        _, token = _make_user(db, org)
        raw_pub, _ = _make_api_key(db, org.id, scopes="read")

        _make_health(
            db,
            org.id,
            "parity@acme.com",
            health_score=65,
            risk_level="at_risk",
            confidence_level="medium",
            usage_component=55,
            llm_analysis_data={
                "analysis": "At risk due to low engagement",
                "recommended_actions": ["Schedule call"],
                "risk_drivers": ["low logins"],
                "estimated_urgency": "high",
                "analysis_type": "full",
            },
        )

        v1_resp = client.get(
            "/api/v1/customers/parity@acme.com",
            headers={"Authorization": f"Bearer {token}"},
        )
        pub_resp = client.get(
            "/api/public/v1/customers/parity@acme.com",
            headers={"Authorization": f"Bearer {raw_pub}"},
        )
        assert v1_resp.status_code == 200, v1_resp.text
        assert pub_resp.status_code == 200, pub_resp.text

        v1 = v1_resp.json()
        pub = pub_resp.json()

        # All v1 fields must appear in public with same values
        parity_fields = [
            "customer_email", "health_score", "risk_level", "confidence_level",
            "feedback_count", "churn_risk_component", "sentiment_component",
            "resolution_component", "frequency_component", "usage_component",
            "llm_analysis_summary", "llm_recommended_actions", "llm_risk_drivers",
            "llm_urgency", "llm_analysis_type", "is_archived",
        ]
        for field in parity_fields:
            assert field in pub, f"Field '{field}' missing from public profile"
            assert v1.get(field) == pub.get(field), (
                f"Parity mismatch for '{field}': v1={v1.get(field)!r} pub={pub.get(field)!r}"
            )

    def test_revoked_key_returns_401(self, client: TestClient, db: Session):
        org = _make_org(db)
        _make_health(db, org.id, "revoked@acme.com")
        raw, _ = _make_api_key(db, org.id, scopes="read", revoked=True)

        resp = client.get(
            "/api/public/v1/customers/revoked@acme.com",
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 401, resp.text


# ---------------------------------------------------------------------------
# Phase 3 — GET /api/public/v1/customers/{email}/timeline
# ---------------------------------------------------------------------------

class TestPublicCustomerTimeline:
    """Cursor-paginated timeline via the public API."""

    def test_valid_key_returns_200_with_shape(self, client: TestClient, db: Session):
        org = _make_org(db)
        _make_health(db, org.id, "tl@acme.com")
        _make_feedback(db, org.id, "tl@acme.com")
        raw, _ = _make_api_key(db, org.id, scopes="read")

        resp = client.get(
            "/api/public/v1/customers/tl@acme.com/timeline",
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "events" in data
        assert "next_cursor" in data

    def test_events_have_required_fields(self, client: TestClient, db: Session):
        org = _make_org(db)
        _make_health(db, org.id, "evfields@acme.com")
        _make_feedback(db, org.id, "evfields@acme.com")
        raw, _ = _make_api_key(db, org.id, scopes="read")

        resp = client.get(
            "/api/public/v1/customers/evfields@acme.com/timeline",
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 200, resp.text
        events = resp.json()["events"]
        assert len(events) > 0
        event = events[0]
        assert "type" in event
        assert "description" in event
        assert "timestamp" in event

    def test_cursor_pagination_next_page(self, client: TestClient, db: Session):
        """With limit=1, first page should have next_cursor; second page uses it."""
        org = _make_org(db)
        _make_health(db, org.id, "paged@acme.com")
        now = datetime.utcnow()
        _make_feedback(db, org.id, "paged@acme.com", "First feedback",
                       created_at=now - timedelta(hours=2))
        _make_feedback(db, org.id, "paged@acme.com", "Second feedback",
                       created_at=now - timedelta(hours=1))
        raw, _ = _make_api_key(db, org.id, scopes="read")

        page1 = client.get(
            "/api/public/v1/customers/paged@acme.com/timeline?limit=1",
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert page1.status_code == 200, page1.text
        data1 = page1.json()
        assert len(data1["events"]) == 1
        cursor = data1["next_cursor"]
        assert cursor is not None, "Expected next_cursor on page 1"

        page2 = client.get(
            f"/api/public/v1/customers/paged@acme.com/timeline?limit=1&before={cursor}",
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert page2.status_code == 200, page2.text
        data2 = page2.json()
        assert len(data2["events"]) >= 1

        # No event duplicated across pages
        ids1 = {(e["type"], e["timestamp"]) for e in data1["events"]}
        ids2 = {(e["type"], e["timestamp"]) for e in data2["events"]}
        assert ids1.isdisjoint(ids2), "Events on page 2 must not duplicate page 1"

    def test_public_timeline_matches_v1_timeline_shape(self, client: TestClient, db: Session):
        """Public timeline uses the same ActivityEvent shape as v1 timeline."""
        org = _make_org(db)
        _, token = _make_user(db, org)
        raw_pub, _ = _make_api_key(db, org.id, scopes="read")

        _make_health(db, org.id, "match@acme.com")
        _make_feedback(db, org.id, "match@acme.com")

        v1_resp = client.get(
            "/api/v1/customers/match@acme.com/timeline",
            headers={"Authorization": f"Bearer {token}"},
        )
        pub_resp = client.get(
            "/api/public/v1/customers/match@acme.com/timeline",
            headers={"Authorization": f"Bearer {raw_pub}"},
        )
        assert v1_resp.status_code == 200, v1_resp.text
        assert pub_resp.status_code == 200, pub_resp.text

        v1_events = v1_resp.json()["events"]
        pub_events = pub_resp.json()["events"]

        # Same number of events, same fields
        assert len(v1_events) == len(pub_events)
        for v1e, pube in zip(v1_events, pub_events):
            assert v1e["type"] == pube["type"]
            assert v1e["timestamp"] == pube["timestamp"]
            assert v1e["description"] == pube["description"]

    def test_no_read_scope_returns_403(self, client: TestClient, db: Session):
        org = _make_org(db)
        _make_health(db, org.id, "noscope@acme.com")
        raw, _ = _make_api_key(db, org.id, scopes="ingest")

        resp = client.get(
            "/api/public/v1/customers/noscope@acme.com/timeline",
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 403, resp.text

    def test_bad_key_returns_401(self, client: TestClient, db: Session):
        org = _make_org(db)
        _make_health(db, org.id, "badkey@acme.com")
        fake = f"rrf_{secrets.token_urlsafe(24)}"

        resp = client.get(
            "/api/public/v1/customers/badkey@acme.com/timeline",
            headers={"Authorization": f"Bearer {fake}"},
        )
        assert resp.status_code == 401, resp.text

    def test_cross_org_returns_empty_events(self, client: TestClient, db: Session):
        """Cross-org customer → 404 (timeline for unknown customer → 404)."""
        org_a = _make_org(db, "A Corp")
        org_b = _make_org(db, "B Corp")
        _make_health(db, org_b.id, "bsecret@orgb.com")
        _make_feedback(db, org_b.id, "bsecret@orgb.com")
        raw_a, _ = _make_api_key(db, org_a.id, scopes="read")

        resp = client.get(
            "/api/public/v1/customers/bsecret@orgb.com/timeline",
            headers={"Authorization": f"Bearer {raw_a}"},
        )
        # build_timeline returns empty list for unknown customer (cross-org → 404 or empty)
        # Our implementation returns 404 for clarity.
        assert resp.status_code == 404, resp.text

    def test_unknown_email_returns_404(self, client: TestClient, db: Session):
        org = _make_org(db)
        raw, _ = _make_api_key(db, org.id, scopes="read")

        resp = client.get(
            "/api/public/v1/customers/nobody@missing.com/timeline",
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 404, resp.text

    def test_invalid_cursor_returns_422(self, client: TestClient, db: Session):
        org = _make_org(db)
        _make_health(db, org.id, "cursor@acme.com")
        raw, _ = _make_api_key(db, org.id, scopes="read")

        resp = client.get(
            "/api/public/v1/customers/cursor@acme.com/timeline?before=not_valid_base64!!",
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 422, resp.text

    def test_limit_param_respected(self, client: TestClient, db: Session):
        org = _make_org(db)
        _make_health(db, org.id, "limited@acme.com")
        now = datetime.utcnow()
        for i in range(5):
            _make_feedback(
                db, org.id, "limited@acme.com",
                f"FB {i}", created_at=now - timedelta(hours=i),
            )
        raw, _ = _make_api_key(db, org.id, scopes="read")

        resp = client.get(
            "/api/public/v1/customers/limited@acme.com/timeline?limit=2",
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 200, resp.text
        assert len(resp.json()["events"]) <= 2


# ---------------------------------------------------------------------------
# Phase 4 — Extended GET /api/public/v1/customers/{email}/health
# ---------------------------------------------------------------------------

class TestPublicCustomerHealthExtended:
    """Verify the health endpoint includes component breakdown + confidence_level + usage_component."""

    def test_health_includes_usage_component(self, client: TestClient, db: Session):
        """usage_component must be present in the health response (additive field)."""
        org = _make_org(db)
        _make_health(db, org.id, "huse@acme.com", usage_component=88)
        raw, _ = _make_api_key(db, org.id, scopes="read")

        resp = client.get(
            "/api/public/v1/customers/huse@acme.com/health",
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "usage_component" in data, "usage_component must be present in health response"
        assert data["usage_component"] == 88

    def test_health_usage_component_none_when_null(self, client: TestClient, db: Session):
        org = _make_org(db)
        _make_health(db, org.id, "hnull@acme.com")  # no usage_component
        raw, _ = _make_api_key(db, org.id, scopes="read")

        resp = client.get(
            "/api/public/v1/customers/hnull@acme.com/health",
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "usage_component" in data
        assert data["usage_component"] is None

    def test_health_still_returns_existing_fields(self, client: TestClient, db: Session):
        """Existing consumers: existing fields must not regress."""
        org = _make_org(db)
        _make_health(
            db, org.id, "hfields@acme.com",
            health_score=55,
            risk_level="at_risk",
            churn_probability=0.7,
            churn_probability_low=0.55,
            churn_probability_high=0.85,
            time_to_churn_bucket="2w",
            confidence_level="high",
        )
        raw, _ = _make_api_key(db, org.id, scopes="read")

        resp = client.get(
            "/api/public/v1/customers/hfields@acme.com/health",
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()

        # Pre-existing fields must still be there
        assert data["health_score"] == 55
        assert data["risk_level"] == "at_risk"
        assert abs(data["churn_probability"] - 0.7) < 0.01
        assert data["time_to_churn_bucket"] == "2w"
        assert data["confidence_level"] == "high"
        assert data["churn_risk_component"] == 50
        assert data["sentiment_component"] == 60

    def test_health_unknown_email_returns_404(self, client: TestClient, db: Session):
        org = _make_org(db)
        raw, _ = _make_api_key(db, org.id, scopes="read")

        resp = client.get(
            "/api/public/v1/customers/ghost@missing.com/health",
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert resp.status_code == 404, resp.text

    def test_health_cross_org_returns_404(self, client: TestClient, db: Session):
        org_a = _make_org(db, "HA")
        org_b = _make_org(db, "HB")
        _make_health(db, org_b.id, "hb@orgb.com")
        raw_a, _ = _make_api_key(db, org_a.id, scopes="read")

        resp = client.get(
            "/api/public/v1/customers/hb@orgb.com/health",
            headers={"Authorization": f"Bearer {raw_a}"},
        )
        assert resp.status_code == 404, resp.text
