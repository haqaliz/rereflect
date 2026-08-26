"""
Tests for the `tag` playbook action — playbook_engine._handle_tag
(tag-notify-actions aspect, M1).

TDD: written RED-first — every test fails with
`unsupported action type: 'tag'` until the handler lands.

Constraint source mirrored from backend-api customers.py bulk-tag route:
_TAG_MAX_LENGTH = 50, _TAG_CAP_PER_CUSTOMER = 20, trim/dedupe/sort,
over-cap leaves the row unchanged + loud error.
"""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.models import (
    Base,
    CustomerHealth,
    Organization,
    ChurnPlaybook,
    ChurnPlaybookExecution,
)

# ---------------------------------------------------------------------------
# In-memory DB wiring (same pattern as test_playbook_engine.py)
# ---------------------------------------------------------------------------

SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

_engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_Session = sessionmaker(autocommit=False, autoflush=False, bind=_engine)


@pytest.fixture()
def db():
    Base.metadata.create_all(bind=_engine)
    session = _Session()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=_engine)


# ---------------------------------------------------------------------------
# Helper builders (copied from test_playbook_engine.py fixture pattern)
# ---------------------------------------------------------------------------

def _make_org(db) -> Organization:
    org = Organization(name="Test Org", plan="business")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def _make_playbook(db, org_id: int, action_sequence=None) -> ChurnPlaybook:
    pb = ChurnPlaybook(
        organization_id=org_id,
        name="Test Playbook",
        description="A test playbook",
        probability_min="0.50",
        probability_max="0.85",
        action_sequence=action_sequence or [
            {"type": "tag", "config": {"tag": "at-risk"}},
        ],
        is_template=False,
        is_active=True,
    )
    db.add(pb)
    db.commit()
    db.refresh(pb)
    return pb


def _make_execution(
    db,
    playbook_id: int,
    org_id: int,
    customer_email: str = "customer@example.com",
    status: str = "queued",
) -> ChurnPlaybookExecution:
    exe = ChurnPlaybookExecution(
        playbook_id=playbook_id,
        organization_id=org_id,
        customer_email=customer_email,
        triggered_by="manual",
        status=status,
        action_log=[],
        created_at=datetime.utcnow(),
    )
    db.add(exe)
    db.commit()
    db.refresh(exe)
    return exe


def _make_health(db, org_id: int, email: str = "customer@example.com") -> CustomerHealth:
    health = CustomerHealth(
        organization_id=org_id,
        customer_email=email,
        health_score=40,
        churn_risk_component=70,
        sentiment_component=30,
        resolution_component=40,
        frequency_component=50,
    )
    db.add(health)
    db.commit()
    db.refresh(health)
    return health


def _run_tag_playbook(db, org_id, tag, *, health_kwargs=None, email="customer@example.com"):
    pb = _make_playbook(db, org_id, action_sequence=[
        {"type": "tag", "config": {"tag": tag}},
    ])
    health = _make_health(db, org_id, email=email)
    for k, v in (health_kwargs or {}).items():
        setattr(health, k, v)
    db.commit()
    exe = _make_execution(db, pb.id, org_id, customer_email=email, status="queued")
    from src.services import playbook_engine
    playbook_engine.execute(exe.id, db)
    db.expire_all()
    updated = db.query(ChurnPlaybookExecution).filter_by(id=exe.id).first()
    health_row = db.query(CustomerHealth).filter_by(id=health.id).first()
    return updated, health_row


# ---------------------------------------------------------------------------
# AC1 — add / dedupe / sort / persist
# ---------------------------------------------------------------------------

def test_tag_adds_sorts_and_persists(db):
    """AC1: a missing tag is added, the list is sorted, and the change is
    persisted after the run (visible to a fresh query)."""
    org = _make_org(db)
    updated, health_row = _run_tag_playbook(
        db, org.id, "beta", health_kwargs={"tags": ["zeta", "alpha"]},
    )

    assert updated.status == "done"
    entry = updated.action_log[0]
    assert entry["type"] == "tag"
    assert entry["ok"] is True
    assert entry["result"] == {"tag": "beta", "tags": ["alpha", "beta", "zeta"]}
    assert health_row.tags == ["alpha", "beta", "zeta"]


def test_tag_idempotent_retag_is_noop(db):
    """AC1 (idempotency): re-tagging a tag the customer already has is a
    successful no-op — no duplicate entry, honest unchanged result."""
    org = _make_org(db)
    updated, health_row = _run_tag_playbook(
        db, org.id, "alpha", health_kwargs={"tags": ["alpha", "beta"]},
    )

    assert updated.status == "done"
    entry = updated.action_log[0]
    assert entry["ok"] is True
    assert entry["result"] == {"tag": "alpha", "tags": ["alpha", "beta"]}
    assert health_row.tags == ["alpha", "beta"]


# ---------------------------------------------------------------------------
# AC2 — cap / length / empty refusals, row unchanged
# ---------------------------------------------------------------------------

def test_tag_over_cap_is_refused_and_row_unchanged(db):
    """AC2: 20 existing tags + a new one → ok=False mentioning the cap; the
    row keeps exactly its original 20 tags (nothing applied)."""
    org = _make_org(db)
    updated, health_row = _run_tag_playbook(
        db, org.id, "twenty-first",
        health_kwargs={"tags": sorted([f"tag-{i:02d}" for i in range(20)])},
    )

    entry = updated.action_log[0]
    assert entry["ok"] is False
    assert "cap" in entry["error"].lower()
    assert "20" in entry["error"]
    assert health_row.tags == [f"tag-{i:02d}" for i in range(20)]


def test_tag_over_50_chars_is_refused(db):
    """AC2: a >50-char tag → ok=False, loud, row unchanged."""
    org = _make_org(db)
    long_tag = "x" * 51

    updated, health_row = _run_tag_playbook(db, org.id, long_tag)

    entry = updated.action_log[0]
    assert entry["ok"] is False
    assert "50" in entry["error"]
    assert (health_row.tags or []) == []


def test_tag_empty_and_whitespace_are_refused(db):
    """AC2: empty / whitespace-only tags → ok=False with a specific reason."""
    org = _make_org(db)

    for i, bad in enumerate(("", "   ")):
        updated, health_row = _run_tag_playbook(
            db, org.id, bad, email=f"customer{i}@example.com",
        )
        entry = updated.action_log[0]
        assert entry["ok"] is False
        assert "non-empty" in entry["error"]
        assert (health_row.tags or []) == []


# ---------------------------------------------------------------------------
# AC3 — NULL tags initialized
# ---------------------------------------------------------------------------

def test_tag_initializes_null_tags_array(db):
    """AC3: health.tags = None → the array is initialized with the new tag."""
    org = _make_org(db)

    updated, health_row = _run_tag_playbook(db, org.id, "at-risk")

    assert updated.action_log[0]["ok"] is True
    assert health_row.tags == ["at-risk"]


# ---------------------------------------------------------------------------
# AC8 — a failing tag never blocks sibling actions
# ---------------------------------------------------------------------------

def test_failing_tag_does_not_stop_sibling_actions(db):
    """AC8: an over-cap tag (ok=False) is logged loudly; the next action
    still runs and succeeds."""
    org = _make_org(db)
    health = _make_health(db, org.id)
    health.tags = sorted([f"tag-{i:02d}" for i in range(20)])
    db.commit()

    pb = _make_playbook(db, org.id, action_sequence=[
        {"type": "tag", "config": {"tag": "twenty-first"}},
        {"type": "send_notification", "config": {"recipients": "admins"}},
    ])
    exe = _make_execution(db, pb.id, org.id, status="queued")

    from src.services import playbook_engine
    playbook_engine.execute(exe.id, db)
    db.expire_all()
    updated = db.query(ChurnPlaybookExecution).filter_by(id=exe.id).first()

    assert len(updated.action_log) == 2
    assert updated.action_log[0]["ok"] is False
    assert "cap" in updated.action_log[0]["error"].lower()
    assert updated.action_log[1]["type"] == "send_notification"
    assert updated.action_log[1]["ok"] is True
    assert updated.status == "done"