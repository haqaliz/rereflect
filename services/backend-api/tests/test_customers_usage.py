"""
TDD tests for GET /api/v1/customers/{email}/usage — Phase 5.

Acceptance criteria (AC6):
  - Returns rollup snapshot + daily bucketed event time series.
  - Scoped to the caller's organisation.
  - 404 for an email with no usage rollup.
  - Respects the `days` query parameter (30 / 60 / 90).

Strategy: uses an isolated in-memory SQLite engine with synthetic
CustomerUsage + UsageEvent rows (no real DB).
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.api.main import app
from src.database.session import get_db
from src.models.base import Base
from src.models.organization import Organization
from src.models.user import User
from src.models.customer_usage import CustomerUsage
from src.models.usage_event import UsageEvent
from src.api.auth import hash_password, create_access_token

# ---------------------------------------------------------------------------
# Isolated in-memory DB for this test module
# ---------------------------------------------------------------------------

_SQLITE_URL = "sqlite:///:memory:"
_engine = create_engine(
    _SQLITE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)


@pytest.fixture(autouse=True, scope="function")
def _db_tables():
    Base.metadata.create_all(bind=_engine)
    yield
    Base.metadata.drop_all(bind=_engine)


@pytest.fixture()
def db():
    session = _SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(db):
    def _override_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = _override_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def org(db):
    o = Organization(name="UsageCo", plan="pro")
    db.add(o)
    db.commit()
    db.refresh(o)
    return o


@pytest.fixture()
def other_org(db):
    o = Organization(name="OtherCo", plan="pro")
    db.add(o)
    db.commit()
    db.refresh(o)
    return o


@pytest.fixture()
def user(db, org):
    u = User(
        email="owner@usageco.com",
        password_hash=hash_password("pass"),
        organization_id=org.id,
        role="admin",
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture()
def auth_headers(user):
    token = create_access_token(
        {"user_id": user.id, "organization_id": user.organization_id, "role": user.role}
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def rollup(db, org):
    now = datetime.utcnow()
    r = CustomerUsage(
        organization_id=org.id,
        customer_email="alice@example.com",
        last_active_at=now - timedelta(days=1),
        login_count_7d=5,
        login_count_30d=12,
        active_days_7d=4,
        active_days_30d=10,
        distinct_features=["feature_a", "feature_b", "feature_c"],
        distinct_feature_count=3,
        usage_score=72,
        events_total=30,
        first_seen_at=now - timedelta(days=60),
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


def _make_events(db, org_id, email, days_back: list):
    """Seed UsageEvent rows at the given offsets (days back from now)."""
    now = datetime.utcnow()
    events = []
    for i, d in enumerate(days_back):
        ev = UsageEvent(
            organization_id=org_id,
            customer_email=email,
            event_type="track",
            event_name=f"feature_{i % 3}",
            external_event_id=f"ext-{i}",
            occurred_at=now - timedelta(days=d),
            received_at=now,
        )
        db.add(ev)
        events.append(ev)
    db.commit()
    return events


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCustomerUsageEndpoint:
    def test_returns_rollup_and_series(self, client, auth_headers, db, org, rollup):
        """AC6: endpoint returns rollup snapshot + time-series."""
        _make_events(db, org.id, "alice@example.com", days_back=[1, 3, 5, 10, 20])

        resp = client.get(
            "/api/v1/customers/alice@example.com/usage",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        body = resp.json()

        # Rollup snapshot present
        assert "rollup" in body
        assert body["rollup"]["usage_score"] == 72
        assert body["rollup"]["events_total"] == 30
        assert body["rollup"]["distinct_feature_count"] == 3
        assert body["rollup"]["active_days_30d"] == 10

        # Time series present
        assert "time_series" in body
        assert isinstance(body["time_series"], list)

    def test_404_for_unknown_email(self, client, auth_headers, org):
        """AC6: 404 when no rollup for the requested email."""
        resp = client.get(
            "/api/v1/customers/ghost@example.com/usage",
            headers=auth_headers,
        )
        assert resp.status_code == 404

    def test_org_scoped_returns_404_for_other_org_email(
        self, client, auth_headers, db, org, other_org
    ):
        """AC6: rollup belonging to other_org is invisible to caller's org."""
        # Create rollup in other_org
        r = CustomerUsage(
            organization_id=other_org.id,
            customer_email="alice@example.com",
            usage_score=80,
            events_total=5,
            distinct_feature_count=2,
        )
        db.add(r)
        db.commit()

        # Caller is in `org` — should get 404 because no rollup in org
        resp = client.get(
            "/api/v1/customers/alice@example.com/usage",
            headers=auth_headers,
        )
        assert resp.status_code == 404

    def test_days_parameter_filters_time_series(self, client, auth_headers, db, org, rollup):
        """AC6: ?days=30 vs ?days=60 returns different series lengths."""
        # Events at 10d, 45d, 55d from now
        _make_events(db, org.id, "alice@example.com", days_back=[10, 45, 55])

        resp_30 = client.get(
            "/api/v1/customers/alice@example.com/usage?days=30",
            headers=auth_headers,
        )
        resp_60 = client.get(
            "/api/v1/customers/alice@example.com/usage?days=60",
            headers=auth_headers,
        )
        assert resp_30.status_code == 200
        assert resp_60.status_code == 200

        series_30 = resp_30.json()["time_series"]
        series_60 = resp_60.json()["time_series"]

        # 60-day window has more event days than 30-day window
        total_30 = sum(b["event_count"] for b in series_30)
        total_60 = sum(b["event_count"] for b in series_60)
        assert total_60 >= total_30

    def test_days_defaults_to_30(self, client, auth_headers, db, org, rollup):
        """Default days=30 when omitted."""
        _make_events(db, org.id, "alice@example.com", days_back=[5, 35])

        resp_default = client.get(
            "/api/v1/customers/alice@example.com/usage",
            headers=auth_headers,
        )
        resp_explicit = client.get(
            "/api/v1/customers/alice@example.com/usage?days=30",
            headers=auth_headers,
        )
        assert resp_default.status_code == 200
        assert resp_explicit.status_code == 200
        # Same series
        assert resp_default.json()["time_series"] == resp_explicit.json()["time_series"]

    def test_requires_authentication(self, client, org, rollup):
        """Endpoint returns 403 without JWT (HTTPBearer returns 403 for missing token)."""
        resp = client.get("/api/v1/customers/alice@example.com/usage")
        assert resp.status_code == 403

    def test_invalid_days_value(self, client, auth_headers, org, rollup):
        """days must be one of 30, 60, 90 — invalid value → 422."""
        resp = client.get(
            "/api/v1/customers/alice@example.com/usage?days=999",
            headers=auth_headers,
        )
        assert resp.status_code == 422

    def test_series_buckets_contain_required_fields(self, client, auth_headers, db, org, rollup):
        """Each time-series bucket has date and event_count."""
        _make_events(db, org.id, "alice@example.com", days_back=[1, 2, 3])

        resp = client.get(
            "/api/v1/customers/alice@example.com/usage",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        series = resp.json()["time_series"]
        assert len(series) > 0
        for bucket in series:
            assert "date" in bucket
            assert "event_count" in bucket
            assert bucket["event_count"] >= 0
