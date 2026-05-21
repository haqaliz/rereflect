"""
Tests for playbook_engine.execute() — Phase 5.2 (M4.1).

Written RED-first (TDD). All ~14 tests must fail before implementation,
then pass after src/services/playbook_engine.py is complete.

Pattern mirrors test_probability_updater.py: in-memory SQLite, no real DB.
Action handlers are monkeypatched to isolate engine logic.
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
# In-memory DB wiring
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
# Helper builders
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
            {"type": "assign", "config": {"assign_to": "round_robin"}},
            {"type": "send_notification", "config": {"recipients": "admins"}},
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
    created_at: datetime = None,
) -> ChurnPlaybookExecution:
    exe = ChurnPlaybookExecution(
        playbook_id=playbook_id,
        organization_id=org_id,
        customer_email=customer_email,
        triggered_by="manual",
        status=status,
        action_log=[],
        created_at=created_at or datetime.utcnow(),
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


# ---------------------------------------------------------------------------
# Import module under test (after models are importable)
# ---------------------------------------------------------------------------

from src.services import playbook_engine  # noqa: E402


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_execute_loads_execution_by_id_and_sets_running(db):
    """Engine loads execution by id and transitions status from queued → running."""
    org = _make_org(db)
    pb = _make_playbook(db, org.id, action_sequence=[{"type": "assign", "config": {}}])
    _make_health(db, org.id)
    exe = _make_execution(db, pb.id, org.id, status="queued")

    playbook_engine.execute(exe.id, db)

    # Re-query to see persisted state
    db.expire_all()
    updated = db.query(ChurnPlaybookExecution).filter_by(id=exe.id).first()
    assert updated.status in ("done", "failed")  # ran to completion
    assert updated.started_at is not None


def test_execute_returns_early_when_execution_already_done(db):
    """If status is already 'done', engine returns immediately (idempotent)."""
    org = _make_org(db)
    pb = _make_playbook(db, org.id)
    exe = _make_execution(db, pb.id, org.id, status="done")
    fixed_completed_at = datetime(2026, 1, 1, 10, 0, 0)
    exe.completed_at = fixed_completed_at
    db.commit()

    result = playbook_engine.execute(exe.id, db)

    assert result is not None
    assert result.get("skipped") is True
    db.expire_all()
    unchanged = db.query(ChurnPlaybookExecution).filter_by(id=exe.id).first()
    assert unchanged.completed_at == fixed_completed_at


def test_execute_returns_early_when_execution_already_running(db):
    """If status is 'running', engine returns immediately (prevents double-execution)."""
    org = _make_org(db)
    pb = _make_playbook(db, org.id)
    exe = _make_execution(db, pb.id, org.id, status="running")

    result = playbook_engine.execute(exe.id, db)

    assert result is not None
    assert result.get("skipped") is True


def test_execute_fails_gracefully_when_playbook_deleted(db):
    """Execution with missing playbook gets status='failed', error_message set."""
    org = _make_org(db)
    pb = _make_playbook(db, org.id)
    exe = _make_execution(db, pb.id, org.id, status="queued")

    # Detach playbook relationship then delete it
    db.delete(pb)
    db.commit()

    playbook_engine.execute(exe.id, db)

    db.expire_all()
    updated = db.query(ChurnPlaybookExecution).filter_by(id=exe.id).first()
    assert updated.status == "failed"
    assert "deleted" in (updated.error_message or "").lower()


def test_execute_fails_gracefully_when_customer_health_missing(db):
    """No CustomerHealth row → status='failed', error_message mentions customer."""
    org = _make_org(db)
    pb = _make_playbook(db, org.id)
    # Intentionally no _make_health call
    exe = _make_execution(db, pb.id, org.id, customer_email="ghost@example.com", status="queued")

    playbook_engine.execute(exe.id, db)

    db.expire_all()
    updated = db.query(ChurnPlaybookExecution).filter_by(id=exe.id).first()
    assert updated.status == "failed"
    assert updated.error_message is not None


def test_execute_runs_all_actions_in_sequence(db, monkeypatch):
    """Each action in action_sequence is dispatched to its handler."""
    org = _make_org(db)
    pb = _make_playbook(db, org.id, action_sequence=[
        {"type": "assign", "config": {}},
        {"type": "send_notification", "config": {}},
    ])
    _make_health(db, org.id)
    exe = _make_execution(db, pb.id, org.id, status="queued")

    dispatched = []

    def fake_handler(action_type, action_config, customer_email, health, db):
        dispatched.append(action_type)
        return {"ok": True, "result": {}}

    monkeypatch.setattr(playbook_engine, "_dispatch_action", fake_handler)

    playbook_engine.execute(exe.id, db)

    assert dispatched == ["assign", "send_notification"]


def test_execute_continues_after_action_failure(db, monkeypatch):
    """If action 1 fails, action 2 still executes (no short-circuit)."""
    org = _make_org(db)
    pb = _make_playbook(db, org.id, action_sequence=[
        {"type": "assign", "config": {}},
        {"type": "send_notification", "config": {}},
    ])
    _make_health(db, org.id)
    exe = _make_execution(db, pb.id, org.id, status="queued")

    dispatched = []

    def fake_handler(action_type, action_config, customer_email, health, db):
        dispatched.append(action_type)
        if action_type == "assign":
            raise RuntimeError("assign exploded")
        return {"ok": True, "result": {}}

    monkeypatch.setattr(playbook_engine, "_dispatch_action", fake_handler)

    playbook_engine.execute(exe.id, db)

    assert "assign" in dispatched
    assert "send_notification" in dispatched


def test_execute_action_log_records_each_outcome(db, monkeypatch):
    """action_log is persisted as a list with one entry per action."""
    org = _make_org(db)
    pb = _make_playbook(db, org.id, action_sequence=[
        {"type": "assign", "config": {}},
        {"type": "send_notification", "config": {}},
    ])
    _make_health(db, org.id)
    exe = _make_execution(db, pb.id, org.id, status="queued")

    def fake_handler(action_type, action_config, customer_email, health, db):
        return {"ok": True, "result": {"done": True}}

    monkeypatch.setattr(playbook_engine, "_dispatch_action", fake_handler)

    playbook_engine.execute(exe.id, db)

    db.expire_all()
    updated = db.query(ChurnPlaybookExecution).filter_by(id=exe.id).first()
    assert isinstance(updated.action_log, list)
    assert len(updated.action_log) == 2
    for entry in updated.action_log:
        assert "type" in entry
        assert "ok" in entry


def test_execute_marks_done_when_any_action_succeeds(db, monkeypatch):
    """status='done' when at least one action returns ok=True."""
    org = _make_org(db)
    pb = _make_playbook(db, org.id, action_sequence=[
        {"type": "assign", "config": {}},
        {"type": "send_notification", "config": {}},
    ])
    _make_health(db, org.id)
    exe = _make_execution(db, pb.id, org.id, status="queued")

    call_count = [0]

    def fake_handler(action_type, action_config, customer_email, health, db):
        call_count[0] += 1
        if call_count[0] == 1:
            raise RuntimeError("first action fails")
        return {"ok": True, "result": {}}

    monkeypatch.setattr(playbook_engine, "_dispatch_action", fake_handler)

    playbook_engine.execute(exe.id, db)

    db.expire_all()
    updated = db.query(ChurnPlaybookExecution).filter_by(id=exe.id).first()
    assert updated.status == "done"


def test_execute_marks_failed_when_all_actions_fail(db, monkeypatch):
    """status='failed' when every action raises or returns ok=False."""
    org = _make_org(db)
    pb = _make_playbook(db, org.id, action_sequence=[
        {"type": "assign", "config": {}},
        {"type": "send_notification", "config": {}},
    ])
    _make_health(db, org.id)
    exe = _make_execution(db, pb.id, org.id, status="queued")

    def fake_handler(action_type, action_config, customer_email, health, db):
        raise RuntimeError("boom")

    monkeypatch.setattr(playbook_engine, "_dispatch_action", fake_handler)

    playbook_engine.execute(exe.id, db)

    db.expire_all()
    updated = db.query(ChurnPlaybookExecution).filter_by(id=exe.id).first()
    assert updated.status == "failed"


def test_execute_unsupported_action_type_logged_not_crashed(db, monkeypatch):
    """Unsupported action type is logged in action_log but does not raise."""
    org = _make_org(db)
    pb = _make_playbook(db, org.id, action_sequence=[
        {"type": "send_spaceship", "config": {}},  # unsupported
    ])
    _make_health(db, org.id)
    exe = _make_execution(db, pb.id, org.id, status="queued")

    # Do NOT monkeypatch _dispatch_action — let real one handle unknown type
    playbook_engine.execute(exe.id, db)

    db.expire_all()
    updated = db.query(ChurnPlaybookExecution).filter_by(id=exe.id).first()
    assert updated.status == "failed"  # only action failed
    assert len(updated.action_log) == 1
    entry = updated.action_log[0]
    assert entry["ok"] is False
    assert "unsupported" in (entry.get("error") or "").lower()


def test_execute_rate_limited_when_same_playbook_recently_ran_for_customer(db):
    """
    If a done execution exists for same (playbook_id, customer_email) within
    last 60 minutes, new execution is cancelled with error_message='rate-limited'.
    """
    org = _make_org(db)
    pb = _make_playbook(db, org.id, action_sequence=[{"type": "assign", "config": {}}])
    _make_health(db, org.id)

    # Seed a done execution 30 minutes ago
    recent_done = _make_execution(
        db, pb.id, org.id,
        customer_email="customer@example.com",
        status="done",
        created_at=datetime.utcnow() - timedelta(minutes=30),
    )

    # New queued execution for the same customer
    new_exe = _make_execution(db, pb.id, org.id, status="queued")

    playbook_engine.execute(new_exe.id, db)

    db.expire_all()
    updated = db.query(ChurnPlaybookExecution).filter_by(id=new_exe.id).first()
    assert updated.status == "cancelled"
    assert "rate" in (updated.error_message or "").lower()


def test_execute_allows_run_after_60_minute_window(db):
    """
    A done execution older than 60 minutes does NOT rate-limit the new one.
    """
    org = _make_org(db)
    pb = _make_playbook(db, org.id, action_sequence=[{"type": "assign", "config": {}}])
    _make_health(db, org.id)

    # Seed a done execution 90 minutes ago (outside window)
    _make_execution(
        db, pb.id, org.id,
        customer_email="customer@example.com",
        status="done",
        created_at=datetime.utcnow() - timedelta(minutes=90),
    )

    new_exe = _make_execution(db, pb.id, org.id, status="queued")

    playbook_engine.execute(new_exe.id, db)

    db.expire_all()
    updated = db.query(ChurnPlaybookExecution).filter_by(id=new_exe.id).first()
    assert updated.status != "cancelled"


def test_execute_persists_started_at_and_completed_at(db, monkeypatch):
    """started_at and completed_at are both set after a successful run."""
    org = _make_org(db)
    pb = _make_playbook(db, org.id, action_sequence=[{"type": "assign", "config": {}}])
    _make_health(db, org.id)
    exe = _make_execution(db, pb.id, org.id, status="queued")

    def fake_handler(action_type, action_config, customer_email, health, db):
        return {"ok": True, "result": {}}

    monkeypatch.setattr(playbook_engine, "_dispatch_action", fake_handler)

    before = datetime.utcnow()
    playbook_engine.execute(exe.id, db)
    after = datetime.utcnow()

    db.expire_all()
    updated = db.query(ChurnPlaybookExecution).filter_by(id=exe.id).first()
    assert updated.started_at is not None
    assert updated.completed_at is not None
    assert before <= updated.started_at <= after
    assert updated.started_at <= updated.completed_at
