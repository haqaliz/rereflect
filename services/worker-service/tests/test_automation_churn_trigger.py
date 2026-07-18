"""
Tests for src.services.automation_churn_trigger — Task 4 (churn-triggered-playbooks).

Strict TDD: written FIRST (RED) before the evaluator implementation.

`run_playbook.delay` is patched throughout so no Celery broker is needed.
Redis cooldown is exercised via `_get_redis` patching (no live Redis needed).
"""

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.models import Base, ChurnPlaybook, ChurnPlaybookExecution
from src.models.automation_execution import AutomationExecution
from src.models.automation_rule import AutomationRule


# ---------------------------------------------------------------------------
# In-memory DB wiring (isolated engine, same pattern as test_probability_updater.py)
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
# Import the module under test
# ---------------------------------------------------------------------------

from src.services import automation_churn_trigger  # noqa: E402
from src.services.automation_churn_trigger import evaluate_churn_probability_triggers  # noqa: E402


# ---------------------------------------------------------------------------
# Helper builders
# ---------------------------------------------------------------------------

def _make_playbook(db, org_id=1, is_active=True) -> ChurnPlaybook:
    pb = ChurnPlaybook(
        organization_id=org_id,
        name="Win-back sequence",
        description="Auto-fired win-back playbook",
        probability_min=0.50,
        probability_max=1.00,
        action_sequence=[{"type": "send_email", "config": {}}],
        is_template=False,
        is_active=is_active,
    )
    db.add(pb)
    db.commit()
    db.refresh(pb)
    return pb


def _make_rule(
    db,
    org_id=1,
    mode="active",
    threshold=0.7,
    playbook_id=None,
    cooldown_hours=24,
    actions=None,
) -> AutomationRule:
    if actions is None:
        actions = [{"type": "run_playbook", "config": {"playbook_id": playbook_id}}]
    rule = AutomationRule(
        organization_id=org_id,
        name="High churn risk -> playbook",
        trigger_type="churn_probability_threshold",
        trigger_config={"threshold": threshold},
        actions=actions,
        cooldown_hours=cooldown_hours,
        mode=mode,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


def _no_cooldown_redis():
    """A fake Redis client that always reports 'not in cooldown'."""
    m = MagicMock()
    m.exists.return_value = False
    return m


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@patch("src.services.automation_churn_trigger.run_playbook")
@patch("src.services.automation_churn_trigger._get_redis", return_value=None)
def test_active_rule_breach_fires_playbook_and_logs_success(mock_redis, mock_task, db):
    """Active rule breached -> ChurnPlaybookExecution(queued) + delay + AutomationExecution(success)."""
    playbook = _make_playbook(db)
    rule = _make_rule(db, mode="active", threshold=0.7, playbook_id=playbook.id)

    evaluate_churn_probability_triggers(1, "cust@example.com", 0.85, db)

    executions = db.query(ChurnPlaybookExecution).all()
    assert len(executions) == 1
    execution = executions[0]
    assert execution.playbook_id == playbook.id
    assert execution.organization_id == 1
    assert execution.customer_email == "cust@example.com"
    assert execution.triggered_by == "auto_probability"
    assert execution.triggered_by_user_id is None
    assert execution.status == "queued"

    mock_task.delay.assert_called_once_with(execution.id)

    logs = db.query(AutomationExecution).all()
    assert len(logs) == 1
    log = logs[0]
    assert log.rule_id == rule.id
    assert log.organization_id == 1
    assert log.customer_email == "cust@example.com"
    assert log.status == "success"
    assert log.trigger_snapshot == {"churn_probability": 0.85}
    assert log.actions_executed[0]["error"] is None
    assert log.actions_executed[0]["result"]["execution_id"] == execution.id

    db.refresh(rule)
    assert rule.execution_count == 1
    assert rule.last_executed_at is not None


@patch("src.services.automation_churn_trigger.run_playbook")
@patch("src.services.automation_churn_trigger._get_redis", return_value=None)
def test_below_threshold_does_nothing(mock_redis, mock_task, db):
    """Probability below rule threshold -> no execution rows, no enqueue."""
    playbook = _make_playbook(db)
    _make_rule(db, mode="active", threshold=0.7, playbook_id=playbook.id)

    evaluate_churn_probability_triggers(1, "cust@example.com", 0.5, db)

    assert db.query(ChurnPlaybookExecution).count() == 0
    assert db.query(AutomationExecution).count() == 0
    mock_task.delay.assert_not_called()


@patch("src.services.automation_churn_trigger.run_playbook")
@patch("src.services.automation_churn_trigger._get_redis", return_value=None)
def test_shadow_rule_logs_without_firing(mock_redis, mock_task, db):
    """Shadow rule breached -> AutomationExecution(shadow), NO ChurnPlaybookExecution, NO delay."""
    playbook = _make_playbook(db)
    rule = _make_rule(db, mode="shadow", threshold=0.7, playbook_id=playbook.id)

    evaluate_churn_probability_triggers(1, "cust@example.com", 0.9, db)

    assert db.query(ChurnPlaybookExecution).count() == 0
    mock_task.delay.assert_not_called()

    logs = db.query(AutomationExecution).all()
    assert len(logs) == 1
    assert logs[0].status == "shadow"
    assert logs[0].actions_executed == []
    assert logs[0].rule_id == rule.id

    db.refresh(rule)
    assert rule.execution_count == 1


@patch("src.services.automation_churn_trigger.run_playbook")
@patch("src.services.automation_churn_trigger._get_redis", return_value=None)
def test_off_rule_never_selected(mock_redis, mock_task, db):
    """mode='off' rule is never evaluated, even when probability breaches threshold."""
    playbook = _make_playbook(db)
    _make_rule(db, mode="off", threshold=0.7, playbook_id=playbook.id)

    evaluate_churn_probability_triggers(1, "cust@example.com", 0.99, db)

    assert db.query(ChurnPlaybookExecution).count() == 0
    assert db.query(AutomationExecution).count() == 0
    mock_task.delay.assert_not_called()


@patch("src.services.automation_churn_trigger.run_playbook")
@patch("src.services.automation_churn_trigger._get_redis", return_value=None)
def test_nonexistent_playbook_records_error_no_execution(mock_redis, mock_task, db):
    """Nonexistent playbook_id -> no ChurnPlaybookExecution, error recorded, no delay."""
    _make_rule(db, mode="active", threshold=0.7, playbook_id=999999)

    evaluate_churn_probability_triggers(1, "cust@example.com", 0.9, db)

    assert db.query(ChurnPlaybookExecution).count() == 0
    mock_task.delay.assert_not_called()

    logs = db.query(AutomationExecution).all()
    assert len(logs) == 1
    assert logs[0].status == "failed"
    assert logs[0].actions_executed[0]["error"] is not None


@patch("src.services.automation_churn_trigger.run_playbook")
@patch("src.services.automation_churn_trigger._get_redis", return_value=None)
def test_foreign_org_playbook_ignored(mock_redis, mock_task, db):
    """Playbook belonging to a different org (not NULL/global) -> not resolved, error recorded."""
    other_org_playbook = _make_playbook(db, org_id=2)
    _make_rule(db, org_id=1, mode="active", threshold=0.7, playbook_id=other_org_playbook.id)

    evaluate_churn_probability_triggers(1, "cust@example.com", 0.9, db)

    assert db.query(ChurnPlaybookExecution).count() == 0
    mock_task.delay.assert_not_called()
    logs = db.query(AutomationExecution).all()
    assert len(logs) == 1
    assert logs[0].status == "failed"


@patch("src.services.automation_churn_trigger.run_playbook")
@patch("src.services.automation_churn_trigger._get_redis", return_value=None)
def test_inactive_playbook_ignored(mock_redis, mock_task, db):
    """is_active=False playbook -> not resolved, error recorded, no delay."""
    inactive_playbook = _make_playbook(db, org_id=1, is_active=False)
    _make_rule(db, org_id=1, mode="active", threshold=0.7, playbook_id=inactive_playbook.id)

    evaluate_churn_probability_triggers(1, "cust@example.com", 0.9, db)

    assert db.query(ChurnPlaybookExecution).count() == 0
    mock_task.delay.assert_not_called()
    logs = db.query(AutomationExecution).all()
    assert len(logs) == 1
    assert logs[0].status == "failed"


@patch("src.services.automation_churn_trigger.run_playbook")
@patch("src.services.automation_churn_trigger._get_redis")
def test_cooldown_prevents_second_fire(mock_get_redis, mock_task, db):
    """Second breach within cooldown window (Redis reports key present) -> no second fire."""
    playbook = _make_playbook(db)
    _make_rule(db, mode="active", threshold=0.7, playbook_id=playbook.id, cooldown_hours=24)

    fake_redis = MagicMock()
    fake_redis.exists.return_value = False
    mock_get_redis.return_value = fake_redis

    evaluate_churn_probability_triggers(1, "cust@example.com", 0.9, db)
    assert db.query(ChurnPlaybookExecution).count() == 1
    assert mock_task.delay.call_count == 1

    # Simulate cooldown now active for the second call.
    fake_redis.exists.return_value = True

    evaluate_churn_probability_triggers(1, "cust@example.com", 0.9, db)
    assert db.query(ChurnPlaybookExecution).count() == 1  # unchanged
    assert mock_task.delay.call_count == 1  # unchanged


@patch("src.services.automation_churn_trigger.run_playbook")
@patch("src.services.automation_churn_trigger._get_redis", return_value=None)
def test_non_run_playbook_actions_are_ignored(mock_redis, mock_task, db):
    """Non-run_playbook action types are ignored (worker seam only auto-runs playbooks)."""
    _make_rule(
        db,
        mode="active",
        threshold=0.7,
        actions=[{"type": "send_notification", "config": {"recipients": "admins"}}],
    )

    evaluate_churn_probability_triggers(1, "cust@example.com", 0.9, db)

    assert db.query(ChurnPlaybookExecution).count() == 0
    mock_task.delay.assert_not_called()

    logs = db.query(AutomationExecution).all()
    assert len(logs) == 1
    # No run_playbook actions matched -> empty results -> trivially "success"
    assert logs[0].status == "success"
    assert logs[0].actions_executed == []


@patch("src.services.automation_churn_trigger.run_playbook")
@patch("src.services.automation_churn_trigger._get_redis", return_value=None)
def test_one_bad_rule_does_not_block_others(mock_redis, mock_task, db):
    """A rule that raises during evaluation must not prevent other rules from firing."""
    playbook = _make_playbook(db)
    good_rule = _make_rule(db, mode="active", threshold=0.7, playbook_id=playbook.id)
    # A second rule with a broken trigger_config (non-numeric threshold) should
    # be caught internally without aborting evaluation of good_rule.
    bad_rule = AutomationRule(
        organization_id=1,
        name="Bad rule",
        trigger_type="churn_probability_threshold",
        trigger_config={"threshold": "not-a-number"},
        actions=[{"type": "run_playbook", "config": {"playbook_id": playbook.id}}],
        cooldown_hours=24,
        mode="active",
    )
    db.add(bad_rule)
    db.commit()

    # Should not raise despite bad_rule's malformed threshold.
    evaluate_churn_probability_triggers(1, "cust@example.com", 0.9, db)

    logs = db.query(AutomationExecution).filter_by(rule_id=good_rule.id).all()
    assert len(logs) == 1
    assert logs[0].status == "success"
