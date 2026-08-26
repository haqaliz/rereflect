"""
Tests for the `create_task` / `schedule_task` playbook actions —
playbook_engine._handle_create_task / _handle_schedule_task
(playbook-tasks aspect, M3).

TDD: written RED-first — every test fails with
`unsupported action type: 'create_task'` until the handlers land.

Tasks persist to the worker `PlaybookTask` mirror; `due_at` precedence is
explicit `due_at` > `due_in_days` > NULL (AC3).
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
    PlaybookTask,
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
            {"type": "create_task", "config": {"description": "Follow-up"}},
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


def _build_run(db, org_id: int, config: dict, action_type: str = "create_task", email: str = "customer@example.com"):
    pb = _make_playbook(db, org_id, action_sequence=[
        {"type": action_type, "config": config},
    ])
    _make_health(db, org_id, email=email)
    return _make_execution(db, pb.id, org_id, customer_email=email, status="queued")


def _execute(db, exe):
    from src.services import playbook_engine
    playbook_engine.execute(exe.id, db)
    db.expire_all()
    updated = db.query(ChurnPlaybookExecution).filter_by(id=exe.id).first()
    tasks = db.query(PlaybookTask).all()
    return updated, tasks


# ---------------------------------------------------------------------------
# AC1 — persisted row + result shape
# ---------------------------------------------------------------------------

def test_create_task_persists_row_linked_to_execution(db):
    """AC1: a PlaybookTask row is persisted with org/customer/description/due/
    priority/status 'open' and the run's execution id; the result carries
    task_id + due_at."""
    org = _make_org(db)
    before = datetime.utcnow()

    exe = _build_run(db, org.id, {
        "description": "Follow-up check-in", "due_in_days": 3, "priority": "high",
    })
    updated, tasks = _execute(db, exe)
    after = datetime.utcnow()

    assert updated.status == "done"
    entry = updated.action_log[0]
    assert entry["ok"] is True

    assert len(tasks) == 1
    task = tasks[0]
    assert task.organization_id == org.id
    assert task.customer_email == "customer@example.com"
    assert task.description == "Follow-up check-in"
    assert task.priority == "high"
    assert task.status == "open"
    assert task.playbook_execution_id == exe.id
    assert task.due_at is not None
    assert before + timedelta(days=3) <= task.due_at <= after + timedelta(days=3)

    assert entry["result"]["task_id"] == task.id
    assert entry["result"]["description"] == "Follow-up check-in"
    assert entry["result"]["due_at"] == task.due_at.isoformat()


# ---------------------------------------------------------------------------
# AC2 — due_in_days vs no-due → NULL
# ---------------------------------------------------------------------------

def test_create_task_due_in_days_sets_due_at(db):
    """AC2: due_in_days: 3 → due_at ≈ utcnow + 3 calendar days."""
    org = _make_org(db)
    before = datetime.utcnow()

    exe = _build_run(db, org.id, {"description": "Follow-up", "due_in_days": 3})
    _, tasks = _execute(db, exe)
    after = datetime.utcnow()

    assert len(tasks) == 1
    due = tasks[0].due_at
    assert before + timedelta(days=3) <= due <= after + timedelta(days=3)


def test_create_task_due_in_days_zero_is_accepted(db):
    """AC2 edge: due_in_days: 0 → due_at ≈ now (accepted, not refused)."""
    org = _make_org(db)

    exe = _build_run(db, org.id, {"description": "Follow-up", "due_in_days": 0})
    _, tasks = _execute(db, exe)

    assert len(tasks) == 1
    assert tasks[0].due_at is not None


def test_create_task_without_due_config_leaves_due_at_null(db):
    """AC2: no due_in_days and no due_at → due_at = NULL."""
    org = _make_org(db)

    exe = _build_run(db, org.id, {"description": "Follow-up"})
    updated, tasks = _execute(db, exe)

    assert updated.action_log[0]["ok"] is True
    assert len(tasks) == 1
    assert tasks[0].due_at is None
    assert updated.action_log[0]["result"]["due_at"] is None


# ---------------------------------------------------------------------------
# AC3 — explicit due_at wins over due_in_days
# ---------------------------------------------------------------------------

def test_create_task_explicit_due_at_beats_due_in_days(db):
    """AC3: when both are given, due_at is used verbatim."""
    org = _make_org(db)

    exe = _build_run(db, org.id, {
        "description": "Follow-up",
        "due_at": "2026-09-01T10:00:00",
        "due_in_days": 3,
    })
    _, tasks = _execute(db, exe)

    assert len(tasks) == 1
    assert tasks[0].due_at == datetime(2026, 9, 1, 10, 0, 0)


# ---------------------------------------------------------------------------
# AC4 — schedule_task: priority default / refusal / validation
# ---------------------------------------------------------------------------

def test_schedule_task_defaults_priority_medium(db):
    """AC4: schedule_task without priority persists with priority 'medium'."""
    org = _make_org(db)

    exe = _build_run(db, org.id, {"description": "Scheduled follow-up"}, action_type="schedule_task")
    updated, tasks = _execute(db, exe)

    assert updated.action_log[0]["ok"] is True
    assert len(tasks) == 1
    assert tasks[0].priority == "medium"
    assert tasks[0].playbook_execution_id == exe.id


def test_schedule_task_refuses_explicit_priority(db):
    """AC4: an explicit priority in schedule_task config is refused loudly
    (honest config — no silent ignore)."""
    org = _make_org(db)

    exe = _build_run(db, org.id, {
        "description": "Scheduled follow-up", "priority": "high",
    }, action_type="schedule_task")
    updated, tasks = _execute(db, exe)

    entry = updated.action_log[0]
    assert entry["ok"] is False
    assert "priority" in entry["error"].lower()
    assert tasks == []


def test_create_task_invalid_priority_is_refused(db):
    """AC4: priority outside low|medium|high → ok=False, no row."""
    org = _make_org(db)

    exe = _build_run(db, org.id, {
        "description": "Follow-up", "priority": "urgent",
    })
    updated, tasks = _execute(db, exe)

    entry = updated.action_log[0]
    assert entry["ok"] is False
    assert "priority" in entry["error"].lower()
    assert tasks == []


# ---------------------------------------------------------------------------
# AC5 — missing / empty description
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("config", [
    {},
    {"description": ""},
    {"description": "   "},
])
def test_create_task_missing_or_empty_description_is_refused(db, config):
    """AC5: missing/empty description → ok=False, no row persisted."""
    org = _make_org(db)

    exe = _build_run(db, org.id, config)
    updated, tasks = _execute(db, exe)

    entry = updated.action_log[0]
    assert entry["ok"] is False
    assert "description" in entry["error"].lower()
    assert tasks == []


def test_create_task_invalid_due_config_is_refused(db):
    """Negative / non-int due_in_days and invalid ISO due_at → ok=False."""
    org = _make_org(db)

    for i, config in enumerate((
        {"description": "Follow-up", "due_in_days": -1},
        {"description": "Follow-up", "due_in_days": "three"},
        {"description": "Follow-up", "due_at": "not-a-date"},
    )):
        exe = _build_run(db, org.id, config, email=f"customer{i}@example.com")
        updated, tasks = _execute(db, exe)
        entry = updated.action_log[0]
        assert entry["ok"] is False
        assert tasks == []


# ---------------------------------------------------------------------------
# AC6 — a failing task action never blocks siblings
# ---------------------------------------------------------------------------

def test_failing_create_task_does_not_stop_sibling_actions(db):
    """AC6: a create_task with a missing description (ok=False) is logged
    loudly; the next action still runs and succeeds."""
    org = _make_org(db)
    pb = _make_playbook(db, org.id, action_sequence=[
        {"type": "create_task", "config": {}},
        {"type": "tag", "config": {"tag": "at-risk"}},
    ])
    _make_health(db, org.id)
    exe = _make_execution(db, pb.id, org.id, status="queued")
    updated, tasks = _execute(db, exe)

    assert len(updated.action_log) == 2
    assert updated.action_log[0]["ok"] is False
    assert "description" in updated.action_log[0]["error"].lower()
    assert updated.action_log[1]["type"] == "tag"
    assert updated.action_log[1]["ok"] is True
    assert tasks == []
    assert updated.status == "done"