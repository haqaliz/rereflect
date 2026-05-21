"""
Tests for GET /api/v1/analytics/churn-cohorts (M4.1 Phase 4) — strict TDD.

All tests are written before the implementation (RED phase).
Tests run on SQLite in-memory; production uses PostgreSQL.
"""

from datetime import datetime, timedelta
from typing import Optional

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.api.auth import create_access_token, hash_password
from src.models.churn_event import CustomerChurnEvent
from src.models.customer_health import CustomerHealth
from src.models.feedback import FeedbackItem
from src.models.organization import Organization
from src.models.user import User


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_org(db: Session, plan: str = "business") -> Organization:
    org = Organization(name=f"Org-{plan}-{id(db)}", plan=plan)
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def _make_user(db: Session, org: Organization, role: str = "admin") -> User:
    user = User(
        email=f"u{org.id}@example.com",
        password_hash=hash_password("pw"),
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


def _make_health(
    db: Session,
    org: Organization,
    email: str,
    source: str = "email",
    feedback_count: int = 5,
    last_feedback_at: Optional[datetime] = None,
    churn_probability: Optional[float] = None,
    first_feedback_at: Optional[datetime] = None,
) -> CustomerHealth:
    """Create a CustomerHealth row and a matching FeedbackItem for source lookup."""
    now = datetime.utcnow()
    ch = CustomerHealth(
        organization_id=org.id,
        customer_email=email,
        health_score=50,
        feedback_count=feedback_count,
        last_feedback_at=last_feedback_at or now,
        churn_probability=churn_probability,
    )
    db.add(ch)
    db.commit()
    db.refresh(ch)

    # Create FeedbackItem so source dimension has data to group on
    fi = FeedbackItem(
        organization_id=org.id,
        text="test feedback",
        source=source,
        sentiment_label="neutral",
        sentiment_score=0.0,
        created_at=first_feedback_at or now,
    )
    db.add(fi)
    # Also associate the feedback with the customer email via a second field we can query
    fi.customer_email = email  # type: ignore[attr-defined]
    db.commit()
    db.refresh(fi)
    return ch


def _make_churn(
    db: Session,
    org: Organization,
    email: str,
    reason_code: str = "price",
    churned_at: Optional[datetime] = None,
    recovered_at: Optional[datetime] = None,
) -> CustomerChurnEvent:
    ev = CustomerChurnEvent(
        organization_id=org.id,
        customer_email=email,
        churned_at=churned_at or datetime.utcnow(),
        reason_code=reason_code,
        recovered_at=recovered_at,
        source="manual",
    )
    db.add(ev)
    db.commit()
    db.refresh(ev)
    return ev


BASE_URL = "/api/v1/analytics/churn-cohorts"


# ===========================================================================
# 1. Auth + plan gating
# ===========================================================================


def test_returns_403_for_pro_plan_org(client: TestClient, db: Session):
    """Pro plan does not include churn_cohorts — expect 403."""
    org = _make_org(db, plan="pro")
    user = _make_user(db, org)
    resp = client.get(BASE_URL, params={"dimension": "source", "range": "all"}, headers=_headers(user))
    assert resp.status_code == 403
    body = resp.json()
    assert body["detail"]["feature"] == "churn_cohorts"


def test_returns_200_for_business_plan_org(client: TestClient, db: Session):
    """Business plan has churn_cohorts — expect 200."""
    org = _make_org(db, plan="business")
    user = _make_user(db, org)
    resp = client.get(BASE_URL, params={"dimension": "source", "range": "all"}, headers=_headers(user))
    assert resp.status_code == 200


def test_returns_200_for_enterprise_plan_org(client: TestClient, db: Session):
    """Enterprise plan has churn_cohorts — expect 200."""
    org = _make_org(db, plan="enterprise")
    user = _make_user(db, org)
    resp = client.get(BASE_URL, params={"dimension": "source", "range": "all"}, headers=_headers(user))
    assert resp.status_code == 200


# ===========================================================================
# 2. Dimension switching
# ===========================================================================


def test_dimension_source_groups_by_feedback_source(client: TestClient, db: Session):
    """dimension=source produces cohort labels matching the feedback sources."""
    org = _make_org(db)
    user = _make_user(db, org)

    _make_health(db, org, "a@x.com", source="slack")
    _make_health(db, org, "b@x.com", source="intercom")

    resp = client.get(BASE_URL, params={"dimension": "source", "range": "all"}, headers=_headers(user))
    assert resp.status_code == 200
    labels = {c["label"] for c in resp.json()["cohorts"]}
    assert "slack" in labels
    assert "intercom" in labels


def test_dimension_month_groups_by_first_feedback_at_year_month(client: TestClient, db: Session):
    """dimension=month produces YYYY-MM labels derived from first_feedback_at."""
    org = _make_org(db)
    user = _make_user(db, org)

    jan = datetime(2026, 1, 15)
    mar = datetime(2026, 3, 10)
    _make_health(db, org, "jan@x.com", first_feedback_at=jan)
    _make_health(db, org, "mar@x.com", first_feedback_at=mar)

    resp = client.get(BASE_URL, params={"dimension": "month", "range": "all"}, headers=_headers(user))
    assert resp.status_code == 200
    labels = {c["label"] for c in resp.json()["cohorts"]}
    assert "2026-01" in labels
    assert "2026-03" in labels


def test_dimension_volume_buckets_correctly_at_boundaries(client: TestClient, db: Session):
    """
    volume dimension:
      feedback_count=3  → "Light (1-3)"
      feedback_count=4  → "Regular (4-10)"
      feedback_count=11 → "Power (11+)"
    """
    org = _make_org(db)
    user = _make_user(db, org)

    _make_health(db, org, "light@x.com", feedback_count=3)
    _make_health(db, org, "regular@x.com", feedback_count=4)
    _make_health(db, org, "power@x.com", feedback_count=11)

    resp = client.get(BASE_URL, params={"dimension": "volume", "range": "all"}, headers=_headers(user))
    assert resp.status_code == 200
    labels = {c["label"] for c in resp.json()["cohorts"]}
    assert "Light (1-3)" in labels
    assert "Regular (4-10)" in labels
    assert "Power (11+)" in labels


def test_invalid_dimension_returns_422(client: TestClient, db: Session):
    """Unsupported dimension value triggers a 422 validation error."""
    org = _make_org(db)
    user = _make_user(db, org)
    resp = client.get(BASE_URL, params={"dimension": "banana", "range": "all"}, headers=_headers(user))
    assert resp.status_code == 422


# ===========================================================================
# 3. Range filter
# ===========================================================================


def test_range_30d_excludes_customers_inactive_beyond_30_days(client: TestClient, db: Session):
    """range=30d: only customers with last_feedback_at within last 30 days appear."""
    org = _make_org(db)
    user = _make_user(db, org)

    recent = datetime.utcnow() - timedelta(days=10)
    old = datetime.utcnow() - timedelta(days=60)

    _make_health(db, org, "recent@x.com", last_feedback_at=recent)
    _make_health(db, org, "old@x.com", last_feedback_at=old)

    resp = client.get(BASE_URL, params={"dimension": "source", "range": "30d"}, headers=_headers(user))
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_customers"] == 1


def test_range_all_includes_every_customer(client: TestClient, db: Session):
    """range=all: no time filter — all customers returned."""
    org = _make_org(db)
    user = _make_user(db, org)

    old = datetime.utcnow() - timedelta(days=400)
    _make_health(db, org, "ancient@x.com", last_feedback_at=old)
    _make_health(db, org, "recent@x.com", last_feedback_at=datetime.utcnow())

    resp = client.get(BASE_URL, params={"dimension": "source", "range": "all"}, headers=_headers(user))
    assert resp.status_code == 200
    assert resp.json()["total_customers"] == 2


def test_invalid_range_returns_422(client: TestClient, db: Session):
    """Unsupported range value triggers a 422 validation error."""
    org = _make_org(db)
    user = _make_user(db, org)
    resp = client.get(BASE_URL, params={"dimension": "source", "range": "7d"}, headers=_headers(user))
    assert resp.status_code == 422


# ===========================================================================
# 4. Metric correctness
# ===========================================================================


def test_churn_rate_equals_churned_over_total_per_cohort(client: TestClient, db: Session):
    """churn_rate in each cohort = churned_customers / total_customers."""
    org = _make_org(db)
    user = _make_user(db, org)

    _make_health(db, org, "a@x.com", source="slack", feedback_count=5)
    _make_health(db, org, "b@x.com", source="slack", feedback_count=5)
    _make_health(db, org, "c@x.com", source="slack", feedback_count=5)
    _make_churn(db, org, "a@x.com")  # 1 of 3 slack churned

    resp = client.get(BASE_URL, params={"dimension": "source", "range": "all"}, headers=_headers(user))
    assert resp.status_code == 200
    slack = next(c for c in resp.json()["cohorts"] if c["label"] == "slack")
    assert slack["total_customers"] == 3
    assert slack["churned_customers"] == 1
    assert abs(slack["churn_rate"] - 1 / 3) < 0.001


def test_overall_churn_rate_is_aggregate_across_all_cohorts(client: TestClient, db: Session):
    """overall_churn_rate = total_churned / total_customers across all cohorts."""
    org = _make_org(db)
    user = _make_user(db, org)

    _make_health(db, org, "x@x.com", source="slack")
    _make_health(db, org, "y@x.com", source="email")
    _make_churn(db, org, "x@x.com")

    resp = client.get(BASE_URL, params={"dimension": "source", "range": "all"}, headers=_headers(user))
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_customers"] == 2
    assert data["total_churned"] == 1
    assert abs(data["overall_churn_rate"] - 0.5) < 0.001


def test_avg_probability_is_null_when_no_customers_have_probability(client: TestClient, db: Session):
    """avg_probability is None when all customers have NULL churn_probability."""
    org = _make_org(db)
    user = _make_user(db, org)

    _make_health(db, org, "np@x.com", source="slack", churn_probability=None)

    resp = client.get(BASE_URL, params={"dimension": "source", "range": "all"}, headers=_headers(user))
    assert resp.status_code == 200
    cohorts = resp.json()["cohorts"]
    assert len(cohorts) >= 1
    slack = next(c for c in cohorts if c["label"] == "slack")
    assert slack["avg_probability"] is None


def test_top_reason_codes_returns_at_most_three_sorted_by_count(client: TestClient, db: Session):
    """top_reason_codes has at most 3 items, sorted descending by count."""
    org = _make_org(db)
    user = _make_user(db, org)

    emails = [f"e{i}@x.com" for i in range(7)]
    for e in emails:
        _make_health(db, org, e, source="slack")

    # price x3, competitor x2, other x1, product_quality x1
    for i, rc in enumerate(["price", "price", "price", "competitor", "competitor", "other", "product_quality"]):
        _make_churn(db, org, emails[i], reason_code=rc)

    resp = client.get(BASE_URL, params={"dimension": "source", "range": "all"}, headers=_headers(user))
    assert resp.status_code == 200
    slack = next(c for c in resp.json()["cohorts"] if c["label"] == "slack")
    codes = slack["top_reason_codes"]
    assert len(codes) <= 3
    # first item must be 'price' (count=3)
    assert codes[0]["code"] == "price"
    assert codes[0]["count"] == 3
    # counts are descending
    counts = [c["count"] for c in codes]
    assert counts == sorted(counts, reverse=True)


def test_recovered_customers_count_as_churned_for_rate(client: TestClient, db: Session):
    """
    A churn event with recovered_at set is historical — still counts toward
    churned_customers and churn_rate (recovery doesn't erase history).
    """
    org = _make_org(db)
    user = _make_user(db, org)

    _make_health(db, org, "recovered@x.com", source="email")
    _make_churn(
        db, org, "recovered@x.com",
        recovered_at=datetime.utcnow() - timedelta(days=5),
    )

    resp = client.get(BASE_URL, params={"dimension": "source", "range": "all"}, headers=_headers(user))
    assert resp.status_code == 200
    email_cohort = next(c for c in resp.json()["cohorts"] if c["label"] == "email")
    assert email_cohort["churned_customers"] == 1
    assert email_cohort["churn_rate"] == 1.0


# ===========================================================================
# 5. Grid + tenancy
# ===========================================================================


def test_grid_cells_match_dimension_x_time_bucket(client: TestClient, db: Session):
    """Grid contains cells with both cohort_label and time_bucket fields."""
    org = _make_org(db)
    user = _make_user(db, org)

    _make_health(db, org, "g@x.com", source="slack")
    _make_churn(db, org, "g@x.com")

    resp = client.get(BASE_URL, params={"dimension": "source", "range": "all"}, headers=_headers(user))
    assert resp.status_code == 200
    grid = resp.json()["grid"]
    assert isinstance(grid, list)
    if grid:
        cell = grid[0]
        assert "cohort_label" in cell
        assert "time_bucket" in cell
        assert "churn_rate" in cell
        assert "churned_count" in cell


def test_grid_data_scoped_to_caller_org_only(client: TestClient, db: Session):
    """Grid and cohorts must not leak data from another organization."""
    org_a = _make_org(db, plan="business")
    org_b = _make_org(db, plan="business")

    user_a = _make_user(db, org_a)
    user_b = _make_user(db, org_b)

    # Each org has one customer
    _make_health(db, org_a, "oa@x.com", source="slack")
    _make_health(db, org_b, "ob@x.com", source="slack")

    # Only org_b has a churned customer
    _make_churn(db, org_b, "ob@x.com")

    # Org A should see 0 churned
    resp_a = client.get(BASE_URL, params={"dimension": "source", "range": "all"}, headers=_headers(user_a))
    assert resp_a.status_code == 200
    data_a = resp_a.json()
    assert data_a["total_churned"] == 0
    assert data_a["total_customers"] == 1

    # Org B should see 1 churned
    resp_b = client.get(BASE_URL, params={"dimension": "source", "range": "all"}, headers=_headers(user_b))
    assert resp_b.status_code == 200
    data_b = resp_b.json()
    assert data_b["total_churned"] == 1
    assert data_b["total_customers"] == 1
