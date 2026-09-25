"""
Tests for reap_stale_executions (playbook-execution-reaper R2/R3).

Rows can be stranded at `queued` (publish lost after commit) or `running`
(worker died mid-run). The reaper re-publishes young queued rows, fails old
queued rows, and fails stale running rows — never re-running those.
"""

from contextlib import contextmanager
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.models import Base, ChurnPlaybookExecution
import src.tasks.churn_playbooks as task_mod

_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_Session = sessionmaker(autocommit=False, autoflush=False, bind=_engine)


@pytest.fixture()
def db(monkeypatch):
    Base.metadata.create_all(bind=_engine)
    session = _Session()

    @contextmanager
    def fake_get_db():
        yield session

    monkeypatch.setattr(task_mod, "get_db_session", fake_get_db)
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=_engine)


def _exe(db, status="queued", created_ago=None, started_ago=None):
    now = datetime.utcnow()
    row = ChurnPlaybookExecution(
        playbook_id=1,
        organization_id=1,
        customer_email="c@example.com",
        triggered_by="automation",
        status=status,
        action_log=[],
        created_at=now - (created_ago or timedelta(0)),
        started_at=(now - started_ago) if started_ago is not None else None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row.id


def _get(db, exe_id):
    db.expire_all()
    return db.query(ChurnPlaybookExecution).filter_by(id=exe_id).first()


def _reap():
    return task_mod.reap_stale_executions()


@patch.object(task_mod.run_playbook, "delay")
def test_queued_past_15_minutes_is_redispatched_and_left_queued(mock_delay, db):
    exe_id = _exe(db, created_ago=timedelta(minutes=20))

    result = _reap()

    mock_delay.assert_called_once_with(exe_id)
    assert _get(db, exe_id).status == "queued"
    assert result == {"status": "complete", "redispatched": 1,
                      "expired_queued": 0, "failed_running": 0}


@patch.object(task_mod.run_playbook, "delay")
def test_fresh_queued_row_is_untouched(mock_delay, db):
    exe_id = _exe(db, created_ago=timedelta(minutes=5))

    result = _reap()

    mock_delay.assert_not_called()
    assert _get(db, exe_id).status == "queued"
    assert result["redispatched"] == 0


@patch.object(task_mod.run_playbook, "delay")
def test_queued_older_than_24h_is_failed_not_rerun(mock_delay, db):
    exe_id = _exe(db, created_ago=timedelta(hours=25))

    result = _reap()

    mock_delay.assert_not_called()
    row = _get(db, exe_id)
    assert row.status == "failed"
    assert "never picked up" in row.error_message
    assert row.completed_at is not None
    assert result["expired_queued"] == 1
    assert result["redispatched"] == 0


@patch.object(task_mod.run_playbook, "delay")
def test_running_older_than_1h_is_failed_not_rerun(mock_delay, db):
    exe_id = _exe(db, status="running", created_ago=timedelta(hours=2),
                  started_ago=timedelta(hours=2))

    result = _reap()

    mock_delay.assert_not_called()
    row = _get(db, exe_id)
    assert row.status == "failed"
    assert "worker stopped mid-run" in row.error_message
    assert row.completed_at is not None
    assert result["failed_running"] == 1


@patch.object(task_mod.run_playbook, "delay")
def test_recent_running_row_is_untouched(mock_delay, db):
    exe_id = _exe(db, status="running", created_ago=timedelta(minutes=10),
                  started_ago=timedelta(minutes=10))

    result = _reap()

    mock_delay.assert_not_called()
    assert _get(db, exe_id).status == "running"
    assert result["failed_running"] == 0


@pytest.mark.parametrize("status", ["done", "failed", "cancelled"])
@patch.object(task_mod.run_playbook, "delay")
def test_terminal_rows_are_untouched(mock_delay, db, status):
    exe_id = _exe(db, status=status, created_ago=timedelta(days=3),
                  started_ago=timedelta(days=3))

    result = _reap()

    mock_delay.assert_not_called()
    row = _get(db, exe_id)
    assert row.status == status
    assert row.error_message is None
    assert result == {"status": "complete", "redispatched": 0,
                      "expired_queued": 0, "failed_running": 0}


@patch.object(task_mod.run_playbook, "delay")
def test_batch_limit_bounds_each_class_oldest_first(mock_delay, db, monkeypatch):
    monkeypatch.setattr(task_mod, "REAP_BATCH_LIMIT", 2)
    oldest = _exe(db, created_ago=timedelta(minutes=50))
    middle = _exe(db, created_ago=timedelta(minutes=40))
    _exe(db, created_ago=timedelta(minutes=30))

    result = _reap()

    assert result["redispatched"] == 2
    assert [c.args[0] for c in mock_delay.call_args_list] == [oldest, middle]


@patch.object(task_mod.run_playbook, "delay")
def test_publish_failure_for_one_id_does_not_abort_the_run(mock_delay, db):
    bad = _exe(db, created_ago=timedelta(minutes=40))
    good = _exe(db, created_ago=timedelta(minutes=30))

    def flaky(exe_id):
        if exe_id == bad:
            raise ConnectionError("broker down")

    mock_delay.side_effect = flaky

    result = _reap()

    assert [c.args[0] for c in mock_delay.call_args_list] == [bad, good]
    assert result["redispatched"] == 1
    assert _get(db, bad).status == "queued"


@patch.object(task_mod.run_playbook, "delay")
def test_failed_marking_is_committed_before_republishing(mock_delay, db):
    _exe(db, created_ago=timedelta(minutes=20))
    _exe(db, created_ago=timedelta(hours=25))

    calls = []
    mock_delay.side_effect = lambda *a, **k: calls.append("delay")
    real_commit = db.commit

    def spy_commit():
        calls.append("commit")
        real_commit()

    with patch.object(db, "commit", side_effect=spy_commit):
        _reap()

    assert "delay" in calls and "commit" in calls
    assert calls.index("commit") < calls.index("delay"), calls


def test_reaper_is_on_the_beat_schedule():
    from src.celery_app import celery_app

    entry = celery_app.conf.beat_schedule["reap-stale-playbook-executions"]
    assert entry["task"] == "src.tasks.churn_playbooks.reap_stale_executions"
    assert entry["schedule"] == 600.0
