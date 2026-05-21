"""
Tests for Celery tasks: run_playbook and purge_old_executions — Phase 5.2 (M4.1).

Written RED-first (TDD). Uses in-memory SQLite and monkeypatching of
playbook_engine.execute to isolate Celery task wiring.
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.models import (
    Base,
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
# Helpers
# ---------------------------------------------------------------------------

def _make_org(db) -> Organization:
    org = Organization(name="Task Org", plan="business")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def _make_playbook(db, org_id: int) -> ChurnPlaybook:
    pb = ChurnPlaybook(
        organization_id=org_id,
        name="Task PB",
        description=None,
        probability_min="0.50",
        probability_max="0.80",
        action_sequence=[{"type": "assign", "config": {}}],
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
    status: str = "queued",
    created_at: datetime = None,
) -> ChurnPlaybookExecution:
    exe = ChurnPlaybookExecution(
        playbook_id=playbook_id,
        organization_id=org_id,
        customer_email="task-test@example.com",
        triggered_by="manual",
        status=status,
        action_log=[],
        created_at=created_at or datetime.utcnow(),
    )
    db.add(exe)
    db.commit()
    db.refresh(exe)
    return exe


# ---------------------------------------------------------------------------
# Import tasks under test
# ---------------------------------------------------------------------------

from src.tasks.churn_playbooks import run_playbook, purge_old_executions  # noqa: E402


# ---------------------------------------------------------------------------
# Tests — run_playbook
# ---------------------------------------------------------------------------


def _patch_db_session(monkeypatch, db):
    """Patch get_db_session in the churn_playbooks task module to yield the test db."""
    from contextlib import contextmanager
    import src.tasks.churn_playbooks as task_mod

    @contextmanager
    def fake_get_db():
        yield db

    monkeypatch.setattr(task_mod, "get_db_session", fake_get_db)


def test_task_calls_engine_with_execution_id(db, monkeypatch):
    """run_playbook task calls playbook_engine.execute with the execution_id."""
    org = _make_org(db)
    pb = _make_playbook(db, org.id)
    exe = _make_execution(db, pb.id, org.id, status="queued")

    called_with = []

    def fake_execute(execution_id, session):
        called_with.append(execution_id)
        return {"status": "done"}

    import src.services.playbook_engine as engine_mod
    monkeypatch.setattr(engine_mod, "execute", fake_execute)
    _patch_db_session(monkeypatch, db)

    run_playbook(exe.id)

    assert called_with == [exe.id]


def test_task_swallows_exceptions_and_marks_execution_failed(db, monkeypatch):
    """If engine.execute raises, task catches it and sets execution status='failed'."""
    org = _make_org(db)
    pb = _make_playbook(db, org.id)
    exe = _make_execution(db, pb.id, org.id, status="queued")

    def exploding_execute(execution_id, session):
        raise RuntimeError("catastrophic failure")

    import src.services.playbook_engine as engine_mod
    monkeypatch.setattr(engine_mod, "execute", exploding_execute)
    _patch_db_session(monkeypatch, db)

    # Must not raise
    result = run_playbook(exe.id)

    assert result is not None
    assert result.get("status") == "error"

    db.expire_all()
    updated = db.query(ChurnPlaybookExecution).filter_by(id=exe.id).first()
    assert updated.status == "failed"


def test_task_is_idempotent_on_celery_retry(db, monkeypatch):
    """
    If execution is already 'done' (e.g. a retry after broker flap),
    engine returns skipped=True and task returns without error.
    """
    org = _make_org(db)
    pb = _make_playbook(db, org.id)
    exe = _make_execution(db, pb.id, org.id, status="done")

    import src.services.playbook_engine as engine_mod
    monkeypatch.setattr(engine_mod, "execute", lambda eid, sess: {"skipped": True})
    _patch_db_session(monkeypatch, db)

    result = run_playbook(exe.id)

    assert result is not None
    # Should not mark as failed or raise
    db.expire_all()
    unchanged = db.query(ChurnPlaybookExecution).filter_by(id=exe.id).first()
    assert unchanged.status == "done"


# ---------------------------------------------------------------------------
# Tests — purge_old_executions
# ---------------------------------------------------------------------------


def test_purge_task_deletes_executions_older_than_90_days(db, monkeypatch):
    """purge_old_executions deletes rows with created_at older than 90 days."""
    org = _make_org(db)
    pb = _make_playbook(db, org.id)

    # Old execution (91 days ago)
    old_exe = _make_execution(
        db, pb.id, org.id, status="done",
        created_at=datetime.utcnow() - timedelta(days=91),
    )

    _patch_db_session(monkeypatch, db)
    old_exe_id = old_exe.id

    result = purge_old_executions()

    assert result["deleted"] >= 1
    db.expunge_all()
    gone = db.query(ChurnPlaybookExecution).filter(ChurnPlaybookExecution.id == old_exe_id).first()
    assert gone is None


def test_purge_task_does_not_delete_recent_executions(db, monkeypatch):
    """purge_old_executions keeps rows newer than 90 days."""
    org = _make_org(db)
    pb = _make_playbook(db, org.id)

    # Recent execution (1 day ago)
    recent_exe = _make_execution(
        db, pb.id, org.id, status="done",
        created_at=datetime.utcnow() - timedelta(days=1),
    )

    _patch_db_session(monkeypatch, db)

    result = purge_old_executions()

    db.expire_all()
    still_there = db.query(ChurnPlaybookExecution).filter_by(id=recent_exe.id).first()
    assert still_there is not None
