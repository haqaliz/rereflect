"""
Tests for src.services.automation_usage_trend_trigger — worker-trend-evaluator
aspect (M1/M5 of usage-trend-automation-trigger PRD).

Strict TDD: written FIRST (RED) before the evaluator implementation. Modeled
directly on test_automation_churn_trigger.py (same in-memory SQLite +
StaticPool pattern, same `run_playbook.delay` / `_get_redis` patching so no
broker or live Redis is needed).

AC references are to
docs/planning/usage-trend-automation-trigger/worker-trend-evaluator/spec.md.
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
# In-memory DB wiring (isolated engine, same pattern as
# test_automation_churn_trigger.py)
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

from src.services import automation_usage_trend_trigger  # noqa: E402
from src.services.automation_usage_trend_trigger import (  # noqa: E402
    evaluate_usage_trend_triggers,
)


# ---------------------------------------------------------------------------
# Helper builders
# ---------------------------------------------------------------------------

def _make_playbook(db, org_id=1, is_active=True) -> ChurnPlaybook:
    pb = ChurnPlaybook(
        organization_id=org_id,
        name="At-Risk Outreach",
        description="Auto-fired usage-decline outreach playbook",
        probability_min=0.0,
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
    states=None,
    playbook_id=None,
    cooldown_hours=24,
    actions=None,
) -> AutomationRule:
    if states is None:
        states = ["declining", "sharp_decline"]
    if actions is None:
        actions = [{"type": "run_playbook", "config": {"playbook_id": playbook_id}}]
    rule = AutomationRule(
        organization_id=org_id,
        name="Usage decline -> playbook",
        trigger_type="usage_trend",
        trigger_config={"states": states},
        actions=actions,
        cooldown_hours=cooldown_hours,
        mode=mode,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


# ---------------------------------------------------------------------------
# AC1 — stable -> declining fires: ChurnPlaybookExecution created + dispatched
# ---------------------------------------------------------------------------


@patch("src.services.automation_usage_trend_trigger.run_playbook")
@patch("src.services.automation_usage_trend_trigger._get_redis", return_value=None)
def test_stable_to_declining_fires_playbook_and_logs_success(mock_redis, mock_task, db):
    playbook = _make_playbook(db)
    rule = _make_rule(db, mode="active", playbook_id=playbook.id)

    evaluate_usage_trend_triggers(1, "cust@example.com", "stable", "declining", db)

    executions = db.query(ChurnPlaybookExecution).all()
    assert len(executions) == 1
    execution = executions[0]
    assert execution.playbook_id == playbook.id
    assert execution.organization_id == 1
    assert execution.customer_email == "cust@example.com"
    assert execution.triggered_by == "auto_usage_trend"
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
    assert log.trigger_snapshot == {
        "old_trend_state": "stable",
        "new_trend_state": "declining",
    }
    assert log.actions_executed[0]["error"] is None
    assert log.actions_executed[0]["result"]["execution_id"] == execution.id

    db.refresh(rule)
    assert rule.execution_count == 1
    assert rule.last_executed_at is not None


# ---------------------------------------------------------------------------
# AC2 — insufficient_history -> anything creates zero executions (warm-up
# guard), explicitly named per the task instructions.
# ---------------------------------------------------------------------------


@patch("src.services.automation_usage_trend_trigger.run_playbook")
@patch("src.services.automation_usage_trend_trigger._get_redis", return_value=None)
def test_insufficient_history_to_sharp_decline_fires_nothing(mock_redis, mock_task, db):
    """AC2 — the warm-up guard: insufficient_history -> sharp_decline must
    create zero executions of any kind, and must not enqueue the task."""
    playbook = _make_playbook(db)
    _make_rule(db, mode="active", playbook_id=playbook.id)

    evaluate_usage_trend_triggers(
        1, "cust@example.com", "insufficient_history", "sharp_decline", db
    )

    assert db.query(ChurnPlaybookExecution).count() == 0
    assert db.query(AutomationExecution).count() == 0
    mock_task.delay.assert_not_called()


@patch("src.services.automation_usage_trend_trigger.run_playbook")
@patch("src.services.automation_usage_trend_trigger._get_redis", return_value=None)
def test_stable_to_insufficient_history_fires_nothing(mock_redis, mock_task, db):
    """The reverse direction of AC2's warm-up guard also never fires."""
    playbook = _make_playbook(db)
    _make_rule(db, mode="active", playbook_id=playbook.id)

    evaluate_usage_trend_triggers(
        1, "cust@example.com", "stable", "insufficient_history", db
    )

    assert db.query(ChurnPlaybookExecution).count() == 0
    assert db.query(AutomationExecution).count() == 0
    mock_task.delay.assert_not_called()


# ---------------------------------------------------------------------------
# AC3 — edge semantics: a customer staying `declining` across two runs
# fires ONCE, on the first — WITHOUT relying on cooldown (Redis unavailable
# in this test, so cooldown is disabled throughout; the guard must be the
# is_worsening_transition check itself, not the cooldown).
# ---------------------------------------------------------------------------


@patch("src.services.automation_usage_trend_trigger.run_playbook")
@patch("src.services.automation_usage_trend_trigger._get_redis", return_value=None)
def test_declining_to_declining_across_two_runs_fires_once_not_via_cooldown(
    mock_redis, mock_task, db
):
    """AC3 — edge semantics proven WITHOUT the cooldown: Redis is
    unavailable (`_get_redis` -> None) for both calls, so if a second fire
    were suppressed it could only be because no transition occurred, not
    because a cooldown key blocked it."""
    playbook = _make_playbook(db)
    _make_rule(db, mode="active", playbook_id=playbook.id)

    # Run 1: stable -> declining (a real transition) -> fires.
    evaluate_usage_trend_triggers(1, "cust@example.com", "stable", "declining", db)
    assert db.query(ChurnPlaybookExecution).count() == 1
    assert mock_task.delay.call_count == 1

    # Run 2: declining -> declining (no transition, same run-to-run state)
    # -> must NOT fire again, even with cooldown disabled.
    evaluate_usage_trend_triggers(1, "cust@example.com", "declining", "declining", db)
    assert db.query(ChurnPlaybookExecution).count() == 1  # unchanged
    assert mock_task.delay.call_count == 1  # unchanged


# ---------------------------------------------------------------------------
# AC5 — mode="shadow" logs AutomationExecution(status="shadow"), no
# ChurnPlaybookExecution, no task dispatch, but still consumes cooldown.
# ---------------------------------------------------------------------------


@patch("src.services.automation_usage_trend_trigger.run_playbook")
@patch("src.services.automation_usage_trend_trigger._get_redis", return_value=None)
def test_shadow_rule_logs_without_firing(mock_redis, mock_task, db):
    playbook = _make_playbook(db)
    rule = _make_rule(db, mode="shadow", playbook_id=playbook.id)

    evaluate_usage_trend_triggers(1, "cust@example.com", "stable", "sharp_decline", db)

    assert db.query(ChurnPlaybookExecution).count() == 0
    mock_task.delay.assert_not_called()

    logs = db.query(AutomationExecution).all()
    assert len(logs) == 1
    assert logs[0].status == "shadow"
    assert logs[0].actions_executed == []
    assert logs[0].rule_id == rule.id

    db.refresh(rule)
    assert rule.execution_count == 1


@patch("src.services.automation_usage_trend_trigger.run_playbook")
@patch("src.services.automation_usage_trend_trigger._get_redis")
def test_shadow_rule_still_consumes_cooldown(mock_get_redis, mock_task, db):
    """Shadow mode must still SET the cooldown key even though it executes
    nothing — otherwise a shadow rule would log a would-have-run entry on
    every single run for an already-declining customer."""
    playbook = _make_playbook(db)
    _make_rule(db, mode="shadow", playbook_id=playbook.id, cooldown_hours=24)

    fake_redis = MagicMock()
    fake_redis.exists.return_value = False
    mock_get_redis.return_value = fake_redis

    evaluate_usage_trend_triggers(1, "cust@example.com", "stable", "declining", db)

    fake_redis.setex.assert_called_once()
    key_arg = fake_redis.setex.call_args[0][0]
    assert key_arg == "automation_cooldown:1:cust@example.com"


# ---------------------------------------------------------------------------
# AC6 — mode="off" rules are never selected.
# ---------------------------------------------------------------------------


@patch("src.services.automation_usage_trend_trigger.run_playbook")
@patch("src.services.automation_usage_trend_trigger._get_redis", return_value=None)
def test_off_rule_never_selected(mock_redis, mock_task, db):
    playbook = _make_playbook(db)
    _make_rule(db, mode="off", playbook_id=playbook.id)

    evaluate_usage_trend_triggers(1, "cust@example.com", "stable", "sharp_decline", db)

    assert db.query(ChurnPlaybookExecution).count() == 0
    assert db.query(AutomationExecution).count() == 0
    mock_task.delay.assert_not_called()


# ---------------------------------------------------------------------------
# AC7 — shared cooldown key scheme: a cooldown set by the (simulated) backend
# engine suppresses this evaluator, and vice versa.
# ---------------------------------------------------------------------------


@patch("src.services.automation_usage_trend_trigger.run_playbook")
@patch("src.services.automation_usage_trend_trigger._get_redis")
def test_cooldown_prevents_second_fire_identical_key_scheme(mock_get_redis, mock_task, db):
    playbook = _make_playbook(db)
    rule = _make_rule(db, mode="active", playbook_id=playbook.id, cooldown_hours=24)

    fake_redis = MagicMock()
    fake_redis.exists.return_value = False
    mock_get_redis.return_value = fake_redis

    evaluate_usage_trend_triggers(1, "cust@example.com", "stable", "declining", db)
    assert db.query(ChurnPlaybookExecution).count() == 1
    assert mock_task.delay.call_count == 1

    # Assert the exact key scheme is shared with automation_churn_trigger.
    set_key = fake_redis.setex.call_args[0][0]
    assert set_key == f"automation_cooldown:{rule.id}:cust@example.com"

    # Simulate cooldown now active (e.g. set by the backend churn engine
    # using the identical key scheme) for a SECOND real transition.
    fake_redis.exists.return_value = True

    evaluate_usage_trend_triggers(1, "cust@example.com", "declining", "sharp_decline", db)
    assert db.query(ChurnPlaybookExecution).count() == 1  # unchanged
    assert mock_task.delay.call_count == 1  # unchanged


# ---------------------------------------------------------------------------
# AC8 — a raising rule is isolated: other rules still evaluate.
# ---------------------------------------------------------------------------


@patch("src.services.automation_usage_trend_trigger.run_playbook")
@patch("src.services.automation_usage_trend_trigger._get_redis", return_value=None)
def test_one_bad_rule_does_not_block_others(mock_redis, mock_task, db):
    playbook = _make_playbook(db)
    good_rule = _make_rule(db, mode="active", playbook_id=playbook.id)
    # A second rule with a malformed trigger_config (states is not a list)
    # should be caught internally without aborting evaluation of good_rule.
    bad_rule = AutomationRule(
        organization_id=1,
        name="Bad rule",
        trigger_type="usage_trend",
        trigger_config={"states": None},
        actions=[{"type": "run_playbook", "config": {"playbook_id": playbook.id}}],
        cooldown_hours=24,
        mode="active",
    )
    db.add(bad_rule)
    db.commit()

    # Force the bad rule to raise during evaluation regardless of config
    # shape, proving isolation even for unanticipated failure modes.
    original_evaluate = automation_usage_trend_trigger._evaluate_rule

    def _flaky_evaluate(rule, *args, **kwargs):
        if rule.id == bad_rule.id:
            raise RuntimeError("boom")
        return original_evaluate(rule, *args, **kwargs)

    with patch.object(
        automation_usage_trend_trigger, "_evaluate_rule", side_effect=_flaky_evaluate
    ):
        evaluate_usage_trend_triggers(1, "cust@example.com", "stable", "declining", db)

    logs = db.query(AutomationExecution).filter_by(rule_id=good_rule.id).all()
    assert len(logs) == 1
    assert logs[0].status == "success"


# ---------------------------------------------------------------------------
# AC9 — cross-org isolation: a rule only ever fires for customers in its own
# organization.
# ---------------------------------------------------------------------------


@patch("src.services.automation_usage_trend_trigger.run_playbook")
@patch("src.services.automation_usage_trend_trigger._get_redis", return_value=None)
def test_rule_only_fires_for_its_own_org(mock_redis, mock_task, db):
    org1_playbook = _make_playbook(db, org_id=1)
    _make_rule(db, org_id=1, mode="active", playbook_id=org1_playbook.id)

    # Evaluate a transition for org 2 — org 1's rule must not be selected.
    evaluate_usage_trend_triggers(2, "other-org-cust@example.com", "stable", "declining", db)

    assert db.query(ChurnPlaybookExecution).count() == 0
    assert db.query(AutomationExecution).count() == 0
    mock_task.delay.assert_not_called()


# ---------------------------------------------------------------------------
# Additional coverage mirroring test_automation_churn_trigger.py precedent
# ---------------------------------------------------------------------------


@patch("src.services.automation_usage_trend_trigger.run_playbook")
@patch("src.services.automation_usage_trend_trigger._get_redis", return_value=None)
def test_new_state_not_in_configured_states_does_not_fire(mock_redis, mock_task, db):
    """A worsening transition into a state NOT listed in the rule's config
    must not fire (e.g. rule only targets sharp_decline, transition lands
    on declining)."""
    playbook = _make_playbook(db)
    _make_rule(db, mode="active", states=["sharp_decline"], playbook_id=playbook.id)

    evaluate_usage_trend_triggers(1, "cust@example.com", "stable", "declining", db)

    assert db.query(ChurnPlaybookExecution).count() == 0
    assert db.query(AutomationExecution).count() == 0
    mock_task.delay.assert_not_called()


@patch("src.services.automation_usage_trend_trigger.run_playbook")
@patch("src.services.automation_usage_trend_trigger._get_redis", return_value=None)
def test_recovery_transition_never_fires(mock_redis, mock_task, db):
    """declining -> stable (recovery) never fires in v1 (PRD M2)."""
    playbook = _make_playbook(db)
    _make_rule(db, mode="active", playbook_id=playbook.id)

    evaluate_usage_trend_triggers(1, "cust@example.com", "declining", "stable", db)

    assert db.query(ChurnPlaybookExecution).count() == 0
    assert db.query(AutomationExecution).count() == 0
    mock_task.delay.assert_not_called()


@patch("src.services.automation_usage_trend_trigger.run_playbook")
@patch("src.services.automation_usage_trend_trigger._get_redis", return_value=None)
def test_partial_recovery_sharp_decline_to_declining_never_fires(mock_redis, mock_task, db):
    """sharp_decline -> declining (partial recovery) never fires in v1."""
    playbook = _make_playbook(db)
    _make_rule(db, mode="active", playbook_id=playbook.id)

    evaluate_usage_trend_triggers(1, "cust@example.com", "sharp_decline", "declining", db)

    assert db.query(ChurnPlaybookExecution).count() == 0
    assert db.query(AutomationExecution).count() == 0
    mock_task.delay.assert_not_called()


@patch("src.services.automation_usage_trend_trigger.run_playbook")
@patch("src.services.automation_usage_trend_trigger._get_redis", return_value=None)
def test_nonexistent_playbook_records_error_no_execution(mock_redis, mock_task, db):
    _make_rule(db, mode="active", playbook_id=999999)

    evaluate_usage_trend_triggers(1, "cust@example.com", "stable", "declining", db)

    assert db.query(ChurnPlaybookExecution).count() == 0
    mock_task.delay.assert_not_called()

    logs = db.query(AutomationExecution).all()
    assert len(logs) == 1
    assert logs[0].status == "failed"
    assert logs[0].actions_executed[0]["error"] is not None


@patch("src.services.automation_usage_trend_trigger.run_playbook")
@patch("src.services.automation_usage_trend_trigger._get_redis", return_value=None)
def test_non_run_playbook_actions_are_ignored(mock_redis, mock_task, db):
    """Non-run_playbook action types are ignored — matching M4.1.5's
    deliberately narrow mirror (spec 'Out of scope')."""
    _make_rule(
        db,
        mode="active",
        actions=[{"type": "send_notification", "config": {"recipients": "admins"}}],
    )

    evaluate_usage_trend_triggers(1, "cust@example.com", "stable", "declining", db)

    assert db.query(ChurnPlaybookExecution).count() == 0
    mock_task.delay.assert_not_called()

    logs = db.query(AutomationExecution).all()
    assert len(logs) == 1
    assert logs[0].status == "success"
    assert logs[0].actions_executed == []
