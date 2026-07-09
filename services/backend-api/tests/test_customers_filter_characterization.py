"""
Characterization test — segment-actions / bulk-actions-api, Phase 1.

Locks the exact output of GET /api/v1/customers/ across a grid of filter
param combinations (segment, risk_level, search, include_archived) BEFORE
extracting `_apply_customer_filters(...)` out of `list_customers`. Must stay
green, byte-for-byte (same matched customer_emails, same order, same count),
after the extraction.

See docs/planning/segment-actions/bulk-actions-api/{plan_20260709.md,spec.md}.
"""
import pytest
from datetime import datetime
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

from src.models.customer_health import CustomerHealth
from src.models.organization import Organization
from src.models.user import User
from src.api.auth import hash_password, create_access_token


@pytest.fixture
def org(db: Session) -> Organization:
    o = Organization(name="Characterization Co", plan="business")
    db.add(o)
    db.commit()
    db.refresh(o)
    return o


@pytest.fixture
def other_org(db: Session) -> Organization:
    o = Organization(name="Other Co", plan="business")
    db.add(o)
    db.commit()
    db.refresh(o)
    return o


@pytest.fixture
def user(db: Session, org: Organization) -> User:
    u = User(
        email="owner@characterization.com",
        password_hash=hash_password("password123"),
        organization_id=org.id,
        role="owner",
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture
def headers(user: User) -> dict:
    token = create_access_token({
        "user_id": user.id,
        "organization_id": user.organization_id,
        "role": user.role,
    })
    return {"Authorization": f"Bearer {token}"}


def make_ch(
    db: Session,
    org: Organization,
    email: str,
    *,
    name: str = None,
    health_score: int = 60,
    risk_level: str = "moderate",
    segment: str = None,
    is_archived: bool = False,
) -> CustomerHealth:
    record = CustomerHealth(
        organization_id=org.id,
        customer_email=email,
        customer_name=name,
        health_score=health_score,
        risk_level=risk_level,
        feedback_count=5,
        confidence_level="medium",
        last_feedback_at=datetime(2026, 1, 1),
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


@pytest.fixture
def seeded(db: Session, org: Organization, other_org: Organization):
    """A fixed grid of customers covering segment / risk_level / archived / search."""
    make_ch(db, org, "alice@acme.com", name="Alice", health_score=85,
            risk_level="healthy", segment="happy_advocate", is_archived=False)
    make_ch(db, org, "bob@acme.com", name="Bob", health_score=40,
            risk_level="at_risk", segment="silent_churner", is_archived=False)
    make_ch(db, org, "carol@beta.com", name="Carol", health_score=20,
            risk_level="critical", segment="silent_churner", is_archived=False)
    make_ch(db, org, "dave@beta.com", name="Dave", health_score=55,
            risk_level="moderate", segment=None, is_archived=False)
    make_ch(db, org, "erin@acme.com", name="Erin", health_score=10,
            risk_level="critical", segment="dormant", is_archived=True)
    # Cross-org row — must never leak into any combo below.
    make_ch(db, other_org, "intruder@other.com", risk_level="critical", segment="dormant")
    return None


# Grid of (query_params, expected_emails_in_order) using sort_by=customer_email&sort_order=asc
# for a deterministic order regardless of default health_score sort.
COMBOS = [
    ({}, ["alice@acme.com", "bob@acme.com", "carol@beta.com", "dave@beta.com"]),
    ({"risk_level": "critical"}, ["carol@beta.com"]),
    ({"segment": "silent_churner"}, ["bob@acme.com", "carol@beta.com"]),
    ({"search": "acme"}, ["alice@acme.com", "bob@acme.com"]),
    ({"search": "Carol"}, ["carol@beta.com"]),
    ({"include_archived": "true"}, ["alice@acme.com", "bob@acme.com", "carol@beta.com",
                                     "dave@beta.com", "erin@acme.com"]),
    ({"segment": "silent_churner", "risk_level": "critical"}, ["carol@beta.com"]),
    ({"segment": "silent_churner", "search": "bob"}, ["bob@acme.com"]),
    ({"risk_level": "critical", "include_archived": "true"}, ["carol@beta.com", "erin@acme.com"]),
    ({"segment": "dormant", "include_archived": "true"}, ["erin@acme.com"]),
    ({"search": "nomatch"}, []),
]


@pytest.mark.parametrize("params,expected_emails", COMBOS)
def test_filter_combo_characterization(
    client: TestClient, headers: dict, seeded, params: dict, expected_emails: list
):
    query = dict(params)
    query["sort_by"] = "customer_email"
    query["sort_order"] = "asc"
    query["page_size"] = 100

    response = client.get("/api/v1/customers/", params=query, headers=headers)
    assert response.status_code == 200
    body = response.json()
    emails = [item["customer_email"] for item in body["items"]]
    assert emails == expected_emails
    assert body["total"] == len(expected_emails)


def test_full_item_shape_snapshot(client: TestClient, headers: dict, seeded):
    """Pin the full item shape (all fields) for one deterministic row."""
    response = client.get(
        "/api/v1/customers/",
        params={"search": "carol", "sort_by": "customer_email", "sort_order": "asc"},
        headers=headers,
    )
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    item = items[0]
    assert item["customer_email"] == "carol@beta.com"
    assert item["customer_name"] == "Carol"
    assert item["health_score"] == 20
    assert item["risk_level"] == "critical"
    assert item["confidence_level"] == "medium"
    assert item["feedback_count"] == 5
    assert item["is_archived"] is False
    assert item["segment"] == "silent_churner"
    assert item["tags"] == []
    assert item["cs_owner"] is None


def test_summary_unchanged_by_extraction(client: TestClient, headers: dict, seeded):
    """Summary counts (independent of the filter helper) stay correct alongside it."""
    response = client.get("/api/v1/customers/", headers=headers)
    assert response.status_code == 200
    summary = response.json()["summary"]
    assert summary["total_customers"] == 4  # non-archived, org-scoped
