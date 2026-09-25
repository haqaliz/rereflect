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
def test_unsupported_action_types_are_loud_not_silently_skipped(mock_redis, mock_task, db):
    """R2 (automation-action-support): an action type this mirror cannot run
    is recorded as an explicit error entry, so the rule is `failed` — never
    silently dropped with a false `success`. REWRITTEN from the former
    test_non_run_playbook_actions_are_ignored, which pinned the silent skip."""
    _make_rule(
        db,
        mode="active",
        threshold=0.7, actions=[{"type": "auto_assign", "config": {"user_id": 1}}],
    )

    evaluate_churn_probability_triggers(1, "cust@example.com", 0.9, db)

    mock_task.delay.assert_not_called()
    logs = db.query(AutomationExecution).all()
    assert len(logs) == 1
    assert logs[0].status == "failed"
    entries = logs[0].actions_executed
    assert len(entries) == 1
    assert entries[0]["type"] == "auto_assign"
    assert entries[0]["result"] is None
    assert "auto_assign" in entries[0]["error"]
    assert "churn_probability_threshold" in entries[0]["error"]


@pytest.mark.parametrize("bad_type", ["change_status", "draft_response"])
@patch("src.services.automation_churn_trigger.run_playbook")
@patch("src.services.automation_churn_trigger._get_redis", return_value=None)
def test_unsupported_action_mixed_with_working_action_is_partial_failure(
    mock_redis, mock_task, db, bad_type
):
    playbook = _make_playbook(db)
    _make_rule(
        db,
        mode="active",
        threshold=0.7, actions=[
            {"type": "run_playbook", "config": {"playbook_id": playbook.id}},
            {"type": bad_type, "config": {}},
        ],
    )

    evaluate_churn_probability_triggers(1, "cust@example.com", 0.9, db)

    mock_task.delay.assert_called_once()
    log = db.query(AutomationExecution).one()
    assert log.status == "partial_failure"
    bad = [e for e in log.actions_executed if e["type"] == bad_type]
    assert len(bad) == 1 and bad[0]["error"] and bad_type in bad[0]["error"]


def _make_admin(db, org_id=1, email="admin@acme.test"):
    from src.models import User

    user = User(email=email, organization_id=org_id, role="admin")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@patch("src.services.automation_churn_trigger.run_playbook")
@patch("src.services.automation_churn_trigger._get_redis", return_value=None)
def test_send_notification_creates_dashboard_notification(mock_redis, mock_task, db):
    """R1: send_notification now executes (via the feedback mirror's
    _execute_notify, feedback=None) and names the customer."""
    from src.models import Notification

    admin = _make_admin(db)
    _make_rule(
        db,
        mode="active",
        threshold=0.7, actions=[{
            "type": "send_notification",
            "config": {"recipients": "admins", "channels": ["dashboard"]},
        }],
    )

    evaluate_churn_probability_triggers(1, "cust@example.com", 0.9, db)

    notes = db.query(Notification).filter_by(user_id=admin.id).all()
    assert len(notes) == 1
    assert "cust@example.com" in notes[0].message
    assert notes[0].link is None

    log = db.query(AutomationExecution).one()
    assert log.status == "success"
    entries = [e for e in log.actions_executed if e["type"] == "send_notification"]
    assert len(entries) == 1
    assert entries[0]["error"] is None
    assert entries[0]["result"]["notifications_created"] == 1


@patch("src.services.automation_churn_trigger.run_playbook")
@patch("src.services.automation_churn_trigger._get_redis", return_value=None)
def test_send_notification_respects_configured_message_template(mock_redis, mock_task, db):
    from src.models import Notification

    admin = _make_admin(db)
    _make_rule(
        db,
        mode="active",
        threshold=0.7, actions=[{
            "type": "send_notification",
            "config": {"recipients": "admins", "channels": ["dashboard"],
                       "message_template": "Custom text"},
        }],
    )

    evaluate_churn_probability_triggers(1, "cust@example.com", 0.9, db)

    note = db.query(Notification).filter_by(user_id=admin.id).one()
    assert note.message == "Custom text"


@patch("src.services.automation_churn_trigger.run_playbook")
@patch("src.services.automation_churn_trigger._get_redis", return_value=None)
def test_send_notification_assignee_without_feedback_is_loud(mock_redis, mock_task, db):
    """`assignee` needs a feedback item this trigger never has -> explicit
    error entry, not a crash and not a silent zero-recipient success."""
    from src.models import Notification

    _make_admin(db)
    _make_rule(
        db,
        mode="active",
        threshold=0.7, actions=[{
            "type": "send_notification",
            "config": {"recipients": "assignee", "channels": ["dashboard"]},
        }],
    )

    evaluate_churn_probability_triggers(1, "cust@example.com", 0.9, db)

    assert db.query(Notification).count() == 0
    log = db.query(AutomationExecution).one()
    assert log.status == "failed"
    entry = log.actions_executed[0]
    assert entry["type"] == "send_notification"
    assert "assignee" in entry["error"]


def test_handled_action_types_match_golden_support_matrix():
    """Pins this mirror's executed set to the shared golden fixture that the
    backend's SUPPORTED_ACTIONS_BY_TRIGGER is also checked against."""
    import json
    from pathlib import Path

    golden = json.loads(
        (Path(__file__).parent / "fixtures" / "automation_action_support.json").read_text()
    )
    assert set(automation_churn_trigger.HANDLED_ACTION_TYPES) == set(golden["churn_probability_threshold"])


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


# ---------------------------------------------------------------------------
# send_customer_email (automation-send-customer-email, worker-mirrors Phase 4)
# This mirror now executes send_customer_email in addition to run_playbook.
# Every OTHER unsupported action type is recorded as a loud error (above).
# ---------------------------------------------------------------------------


def _make_org_row(db, org_id=1, product_name="Acme"):
    from src.models import Organization

    org = Organization(id=org_id, name="Acme", plan="pro",
                       product_name_display=product_name)
    db.add(org)
    db.commit()
    return org


def _make_health_row(db, org_id=1, email="cust@example.com", name="Dana",
                     is_archived=False, cs_owner_user_id=None):
    from src.models import CustomerHealth

    row = CustomerHealth(
        organization_id=org_id,
        customer_email=email,
        customer_name=name,
        health_score=20,
        is_archived=is_archived,
        cs_owner_user_id=cs_owner_user_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _make_owner(db, org_id=1, email="owner@acme.test"):
    from src.models import User

    user = User(email=email, organization_id=org_id, role="owner")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


EMAIL_ACTION = {
    "type": "send_customer_email",
    "config": {"template": "re_engagement", "recipient": "customer"},
}


@patch("src.services.automation_email_delivery.send_automation_email")
@patch("src.services.automation_churn_trigger._get_redis", return_value=None)
def test_send_customer_email_action_executes(mock_redis, mock_task, db):
    from src.models import AutomationEmailDelivery

    _make_org_row(db)
    _make_health_row(db)
    _make_rule(db, mode="active", threshold=0.7, actions=[EMAIL_ACTION])

    with patch("src.email.RESEND_API_KEY", "test-key"):
        evaluate_churn_probability_triggers(1, "cust@example.com", 0.9, db)

    row = db.query(AutomationEmailDelivery).one()
    assert row.status == "queued"
    assert row.to_email == "cust@example.com"
    assert "Dana" in row.body
    mock_task.delay.assert_called_once_with(row.id)

    log = db.query(AutomationExecution).one()
    assert log.status == "success"
    assert log.actions_executed[0]["result"] == {
        "status": "queued", "delivery_id": row.id
    }


@patch("src.services.automation_email_delivery.send_automation_email")
@patch("src.services.automation_churn_trigger._get_redis", return_value=None)
def test_send_customer_email_cs_assignee_resolves_owner(mock_redis, mock_task, db):
    from src.models import AutomationEmailDelivery

    _make_org_row(db)
    owner = _make_owner(db)
    _make_health_row(db, cs_owner_user_id=owner.id)
    _make_rule(
        db, mode="active", threshold=0.7,
        actions=[{"type": "send_customer_email",
                  "config": {"template": "re_engagement", "recipient": "cs_assignee"}}],
    )

    with patch("src.email.RESEND_API_KEY", "test-key"):
        evaluate_churn_probability_triggers(1, "cust@example.com", 0.9, db)

    assert db.query(AutomationEmailDelivery).one().to_email == "owner@acme.test"


@patch("src.services.automation_email_delivery.send_automation_email")
@patch("src.services.automation_churn_trigger._get_redis", return_value=None)
def test_send_customer_email_skips_are_loud(mock_redis, mock_task, db):
    from src.models import AutomationEmailDelivery

    _make_org_row(db)
    _make_health_row(db, is_archived=True)
    _make_rule(db, mode="active", threshold=0.7, actions=[EMAIL_ACTION])

    with patch("src.email.RESEND_API_KEY", "test-key"):
        evaluate_churn_probability_triggers(1, "cust@example.com", 0.9, db)

    log = db.query(AutomationExecution).one()
    assert log.status == "failed"
    assert log.actions_executed[0]["error"] == "customer archived"
    assert db.query(AutomationEmailDelivery).count() == 0
    mock_task.delay.assert_not_called()


@patch("src.services.automation_email_delivery.send_automation_email")
@patch("src.services.automation_churn_trigger.run_playbook")
@patch("src.services.automation_churn_trigger._get_redis", return_value=None)
def test_send_customer_email_alongside_run_playbook(mock_redis, mock_pb, mock_task, db):
    from src.models import AutomationEmailDelivery

    _make_org_row(db)
    _make_health_row(db)
    playbook = _make_playbook(db)
    _make_rule(
        db, mode="active", threshold=0.7,
        actions=[
            {"type": "run_playbook", "config": {"playbook_id": playbook.id}},
            EMAIL_ACTION,
            {"type": "send_notification", "config": {"recipients": "admins"}},
        ],
    )

    with patch("src.email.RESEND_API_KEY", "test-key"):
        evaluate_churn_probability_triggers(1, "cust@example.com", 0.9, db)

    assert db.query(ChurnPlaybookExecution).count() == 1
    assert db.query(AutomationEmailDelivery).count() == 1

    log = db.query(AutomationExecution).one()
    types = [a["type"] for a in log.actions_executed]
    # send_notification now executes too (automation-action-support R1);
    # it used to be silently skipped here.
    assert types == ["run_playbook", "send_customer_email", "send_notification"]
    assert log.status == "success"


# ---------------------------------------------------------------------------
# Durable-then-publish (automation-playbook-dispatch-commit)
# ---------------------------------------------------------------------------


@patch("src.services.automation_churn_trigger.run_playbook")
@patch("src.services.automation_churn_trigger._get_redis", return_value=None)
def test_run_playbook_commits_before_enqueueing(mock_redis, mock_task, db):
    """The execution row must be committed before its id is published.

    With only a flush, the run_playbook worker (another connection) can
    consume the message before the row is visible, and the row is orphaned
    at `queued`. Mirrors test_automation_email_delivery's ordering test.
    """
    playbook = _make_playbook(db)
    _make_rule(db, mode="active", threshold=0.7, playbook_id=playbook.id)

    calls = []
    delayed_ids = []

    def spy_delay(*a, **k):
        calls.append("delay")
        delayed_ids.append(a[0])

    mock_task.delay.side_effect = spy_delay
    real_commit = db.commit

    def spy_commit():
        calls.append("commit")
        real_commit()

    with patch.object(db, "commit", side_effect=spy_commit):
        evaluate_churn_probability_triggers(1, "cust@example.com", 0.85, db)

    assert "delay" in calls, "run_playbook was never enqueued"
    assert "commit" in calls, "the execution row was never committed"
    assert calls.index("commit") < calls.index("delay"), (
        f"the row must be committed before the message is published; got {calls}"
    )
    execution = db.query(ChurnPlaybookExecution).one()
    assert delayed_ids == [execution.id]
