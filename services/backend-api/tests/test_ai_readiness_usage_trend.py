"""
SM1 surface — usage-trend addressable-population count on the M5.0
AI-readiness report (usage-trend-automation-trigger, template-and-docs
aspect, S0) — strict TDD.

SM1 (PRD): "The addressable population is non-zero and measurable." An
operator can see how many of their customers currently hold a real
(non-`insufficient_history`) trend state, i.e. whether the `usage_trend`
automation trigger *can* fire for them at all. Follows the M5.0
ready/not-ready honest-count pattern (see test_ai_readiness.py) rather than
inventing a new page/endpoint.

Endpoint under test: GET /api/v1/analytics/ai-readiness
"""

from __future__ import annotations

from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.models.customer_usage import CustomerUsage

from tests.test_ai_readiness import URL, _headers, _make_org, _make_user


def _make_usage_row(
    db: Session, org, email: str, trend_state: str = "insufficient_history"
) -> CustomerUsage:
    row = CustomerUsage(
        organization_id=org.id,
        customer_email=email,
        usage_trend_state=trend_state,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


# ---------------------------------------------------------------------------
# AC5 — zero for an org with no usage data at all (not an error)
# ---------------------------------------------------------------------------


def test_no_usage_data_reports_zero_not_error(client: TestClient, db: Session):
    org = _make_org(db)
    user = _make_user(db, org)

    resp = client.get(URL, headers=_headers(user))
    assert resp.status_code == 200
    body = resp.json()

    assert body["usage_trend_customers_total"] == 0
    assert body["usage_trend_addressable"] == 0
    assert body["usage_trend_addressable_ready"] is False
    assert body["usage_trend_by_state"] == {}


# ---------------------------------------------------------------------------
# AC5 — correct for a fixture org with a known mix of trend states
# ---------------------------------------------------------------------------


def test_mixed_trend_states_counted_correctly(client: TestClient, db: Session):
    org = _make_org(db)
    user = _make_user(db, org)

    _make_usage_row(db, org, "a@example.com", "insufficient_history")
    _make_usage_row(db, org, "b@example.com", "insufficient_history")
    _make_usage_row(db, org, "c@example.com", "stable")
    _make_usage_row(db, org, "d@example.com", "declining")
    _make_usage_row(db, org, "e@example.com", "declining")
    _make_usage_row(db, org, "f@example.com", "sharp_decline")

    resp = client.get(URL, headers=_headers(user))
    assert resp.status_code == 200
    body = resp.json()

    assert body["usage_trend_customers_total"] == 6
    # addressable = declining + sharp_decline (non-insufficient_history AND
    # non-stable would over-restrict; the SM1 definition is specifically
    # "non-insufficient_history", so `stable` counts toward addressable too).
    assert body["usage_trend_addressable"] == 4  # stable(1) + declining(2) + sharp_decline(1)
    assert body["usage_trend_addressable_ready"] is True
    assert body["usage_trend_by_state"] == {
        "insufficient_history": 2,
        "stable": 1,
        "declining": 2,
        "sharp_decline": 1,
    }


# ---------------------------------------------------------------------------
# Only insufficient_history rows -> addressable is zero, not an error
# ---------------------------------------------------------------------------


def test_only_insufficient_history_addressable_zero(client: TestClient, db: Session):
    org = _make_org(db)
    user = _make_user(db, org)

    _make_usage_row(db, org, "a@example.com", "insufficient_history")
    _make_usage_row(db, org, "b@example.com", "insufficient_history")
    _make_usage_row(db, org, "c@example.com", "insufficient_history")

    resp = client.get(URL, headers=_headers(user))
    assert resp.status_code == 200
    body = resp.json()

    assert body["usage_trend_customers_total"] == 3
    assert body["usage_trend_addressable"] == 0
    assert body["usage_trend_addressable_ready"] is False
    assert body["usage_trend_by_state"] == {"insufficient_history": 3}


# ---------------------------------------------------------------------------
# Cross-org isolation
# ---------------------------------------------------------------------------


def test_usage_trend_cross_org_isolation(client: TestClient, db: Session):
    org_a = _make_org(db, name="UsageTrendOrgA")
    org_b = _make_org(db, name="UsageTrendOrgB")
    user_a = _make_user(db, org_a)
    user_b = _make_user(db, org_b)

    _make_usage_row(db, org_a, "a1@example.com", "declining")
    _make_usage_row(db, org_a, "a2@example.com", "insufficient_history")

    _make_usage_row(db, org_b, "b1@example.com", "sharp_decline")
    _make_usage_row(db, org_b, "b2@example.com", "sharp_decline")
    _make_usage_row(db, org_b, "b3@example.com", "insufficient_history")

    resp_a = client.get(URL, headers=_headers(user_a))
    body_a = resp_a.json()
    assert body_a["usage_trend_customers_total"] == 2
    assert body_a["usage_trend_addressable"] == 1
    assert body_a["usage_trend_by_state"] == {"declining": 1, "insufficient_history": 1}

    resp_b = client.get(URL, headers=_headers(user_b))
    body_b = resp_b.json()
    assert body_b["usage_trend_customers_total"] == 3
    assert body_b["usage_trend_addressable"] == 2
    assert body_b["usage_trend_by_state"] == {"sharp_decline": 2, "insufficient_history": 1}
