"""
Tests for src.services.automation_feedback_trigger (worker-trigger-mirror, aspect 2).

Strict TDD: written FIRST (RED) before the evaluator implementation.

`src.tasks.analysis` imports `AutomationEngine` from a module that does not
exist in worker-service, wrapped in a bare `except Exception` that swallows
the `ImportError` and just logs a warning. As a result `feedback_category_match`
and `sentiment_pattern` have NEVER fired from the worker. This file proves
that (test_analysis_does_not_swallow_import_error) and drives the mirror
module that fixes it (everything else).

No autouse email/slack stub exists in this suite — email and Slack sends are
mocked explicitly at their source modules (`src.email._send_with_template`,
`src.tasks.alerts.send_slack_message_webhook`), per the plan's testing notes.
"""

import ast
import inspect
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.models import Base, FeedbackItem, Integration, Notification, User
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
# Import the module under test — this import itself is the RED signal for
# test_feedback_category_match_writes_execution before Phase 2 exists.
# ---------------------------------------------------------------------------

from src.services import automation_feedback_trigger  # noqa: E402
from src.services.automation_feedback_trigger import evaluate_feedback_triggers  # noqa: E402


# ---------------------------------------------------------------------------
# Helper builders
# ---------------------------------------------------------------------------


def _make_feedback(
    db,
    org_id=1,
    customer_email="cust@example.com",
    pain_point_category=None,
    feature_request_category=None,
    urgent_category=None,
    tags=None,
    is_urgent=False,
    sentiment_label=None,
    created_at=None,
) -> FeedbackItem:
    fb = FeedbackItem(
        organization_id=org_id,
        text="feedback text",
        customer_email=customer_email,
        pain_point_category=pain_point_category,
        feature_request_category=feature_request_category,
        urgent_category=urgent_category,
        tags=tags,
        is_urgent=is_urgent,
        sentiment_label=sentiment_label,
        created_at=created_at or datetime.utcnow(),
    )
    db.add(fb)
    db.commit()
    db.refresh(fb)
    return fb


def _make_rule(
    db,
    org_id=1,
    mode="active",
    trigger_type="feedback_category_match",
    trigger_config=None,
    actions=None,
    cooldown_hours=24,
) -> AutomationRule:
    rule = AutomationRule(
        organization_id=org_id,
        name="Test rule",
        trigger_type=trigger_type,
        trigger_config=trigger_config or {"categories": ["billing"]},
        actions=actions if actions is not None else [],
        cooldown_hours=cooldown_hours,
        mode=mode,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


def _make_user(db, org_id=1, role="member", email="user@example.com") -> User:
    user = User(email=email, organization_id=org_id, role=role)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _no_cooldown_redis():
    m = MagicMock()
    m.exists.return_value = False
    return m


# ---------------------------------------------------------------------------
# Phase 1 — RED, acceptance criterion 1: feedback_category_match fires
# ---------------------------------------------------------------------------


@patch("src.services.automation_feedback_trigger._get_redis", return_value=None)
def test_feedback_category_match_writes_execution(mock_redis, db):
    """Active rule + matching analysed feedback -> one AutomationExecution row."""
    fb = _make_feedback(db, pain_point_category="billing")
    rule = _make_rule(
        db,
        mode="active",
        trigger_type="feedback_category_match",
        trigger_config={"categories": ["billing"]},
        actions=[],
    )

    context = {"customer_email": fb.customer_email, "feedback_id": fb.id}
    results = evaluate_feedback_triggers(db, 1, context)

    assert len(results) == 1
    logs = db.query(AutomationExecution).all()
    assert len(logs) == 1
    log = logs[0]
    assert log.rule_id == rule.id
    assert log.organization_id == 1
    assert log.feedback_id == fb.id
    assert log.customer_email == fb.customer_email
    assert log.status == "success"

    db.refresh(rule)
    assert rule.execution_count == 1
    assert rule.last_executed_at is not None


@patch("src.services.automation_feedback_trigger._get_redis", return_value=None)
def test_no_matching_category_no_execution(mock_redis, db):
    fb = _make_feedback(db, pain_point_category="bugs")
    _make_rule(
        db,
        trigger_type="feedback_category_match",
        trigger_config={"categories": ["billing"]},
    )

    context = {"customer_email": fb.customer_email, "feedback_id": fb.id}
    results = evaluate_feedback_triggers(db, 1, context)

    assert results == []
    assert db.query(AutomationExecution).count() == 0


@patch("src.services.automation_feedback_trigger._get_redis", return_value=None)
def test_feedback_category_match_respects_is_urgent_filter(mock_redis, db):
    fb = _make_feedback(db, pain_point_category="billing", is_urgent=False)
    _make_rule(
        db,
        trigger_type="feedback_category_match",
        trigger_config={"categories": ["billing"], "is_urgent": True},
    )

    context = {"customer_email": fb.customer_email, "feedback_id": fb.id}
    results = evaluate_feedback_triggers(db, 1, context)

    assert results == []
    assert db.query(AutomationExecution).count() == 0


@patch("src.services.automation_feedback_trigger._get_redis", return_value=None)
def test_off_rule_never_selected(mock_redis, db):
    fb = _make_feedback(db, pain_point_category="billing")
    _make_rule(db, mode="off", trigger_config={"categories": ["billing"]})

    context = {"customer_email": fb.customer_email, "feedback_id": fb.id}
    results = evaluate_feedback_triggers(db, 1, context)

    assert results == []
    assert db.query(AutomationExecution).count() == 0


# ---------------------------------------------------------------------------
# Acceptance criterion 2 — shadow mode logs but executes nothing
# ---------------------------------------------------------------------------


@patch("src.services.automation_feedback_trigger._get_redis", return_value=None)
def test_shadow_mode_logs_no_actions(mock_redis, db):
    fb = _make_feedback(db, pain_point_category="billing")
    rule = _make_rule(
        db,
        mode="shadow",
        trigger_config={"categories": ["billing"]},
        actions=[{"type": "change_status", "config": {"status": "in_review"}}],
    )

    context = {"customer_email": fb.customer_email, "feedback_id": fb.id}
    evaluate_feedback_triggers(db, 1, context)

    logs = db.query(AutomationExecution).all()
    assert len(logs) == 1
    assert logs[0].status == "shadow"
    assert logs[0].actions_executed == []
    assert logs[0].rule_id == rule.id

    # Shadow must not have executed the change_status action.
    db.refresh(fb)
    assert fb.workflow_status == "new"


# ---------------------------------------------------------------------------
# Acceptance criterion 3 — sentiment_pattern count threshold
# ---------------------------------------------------------------------------


@patch("src.services.automation_feedback_trigger._get_redis", return_value=None)
def test_sentiment_pattern_fires_at_count_threshold(mock_redis, db):
    email = "cust@example.com"
    for _ in range(3):
        _make_feedback(db, customer_email=email, sentiment_label="negative")
    trigger_fb = _make_feedback(db, customer_email=email, sentiment_label="negative")

    _make_rule(
        db,
        trigger_type="sentiment_pattern",
        trigger_config={"count": 3, "days": 7, "sentiment": "negative"},
    )

    context = {"customer_email": email, "feedback_id": trigger_fb.id}
    results = evaluate_feedback_triggers(db, 1, context)

    assert len(results) == 1
    assert db.query(AutomationExecution).count() == 1


@patch("src.services.automation_feedback_trigger._get_redis", return_value=None)
def test_sentiment_pattern_does_not_fire_below_count(mock_redis, db):
    email = "cust@example.com"
    for _ in range(2):
        _make_feedback(db, customer_email=email, sentiment_label="negative")

    _make_rule(
        db,
        trigger_type="sentiment_pattern",
        trigger_config={"count": 3, "days": 7, "sentiment": "negative"},
    )

    context = {"customer_email": email, "feedback_id": None}
    results = evaluate_feedback_triggers(db, 1, context)

    assert results == []
    assert db.query(AutomationExecution).count() == 0


@patch("src.services.automation_feedback_trigger._get_redis", return_value=None)
def test_sentiment_pattern_ignores_other_customers(mock_redis, db):
    for _ in range(3):
        _make_feedback(db, customer_email="other@example.com", sentiment_label="negative")

    _make_rule(
        db,
        trigger_type="sentiment_pattern",
        trigger_config={"count": 3, "days": 7, "sentiment": "negative"},
    )

    context = {"customer_email": "cust@example.com", "feedback_id": None}
    results = evaluate_feedback_triggers(db, 1, context)

    assert results == []


# ---------------------------------------------------------------------------
# Acceptance criterion 4 — cooldown key/TTL parity with the backend engine
# ---------------------------------------------------------------------------


def test_cooldown_key_and_ttl_are_literal_and_shared_with_backend(db):
    """A typo here silently decouples the worker mirror from the backend engine."""
    fake_redis = MagicMock()
    fake_redis.exists.return_value = False

    with patch(
        "src.services.automation_feedback_trigger._get_redis", return_value=fake_redis
    ):
        fb = _make_feedback(db, pain_point_category="billing")
        rule = _make_rule(
            db,
            trigger_config={"categories": ["billing"]},
            cooldown_hours=6,
        )
        context = {"customer_email": fb.customer_email, "feedback_id": fb.id}
        evaluate_feedback_triggers(db, 1, context)

    expected_key = f"automation_cooldown:{rule.id}:{fb.customer_email}"
    fake_redis.setex.assert_called_once_with(expected_key, 6 * 3600, "1")
    fake_redis.exists.assert_called_once_with(expected_key)


def test_cooldown_prevents_second_fire(db):
    fake_redis = MagicMock()
    fake_redis.exists.return_value = False

    with patch(
        "src.services.automation_feedback_trigger._get_redis", return_value=fake_redis
    ):
        fb = _make_feedback(db, pain_point_category="billing")
        _make_rule(db, trigger_config={"categories": ["billing"]})
        context = {"customer_email": fb.customer_email, "feedback_id": fb.id}

        evaluate_feedback_triggers(db, 1, context)
        assert db.query(AutomationExecution).count() == 1

        fake_redis.exists.return_value = True
        evaluate_feedback_triggers(db, 1, context)
        assert db.query(AutomationExecution).count() == 1  # unchanged


def test_redis_unavailable_never_raises_and_always_fires(db):
    """_get_redis() returning None degrades cooldowns to 'always fire', never raises."""
    with patch(
        "src.services.automation_feedback_trigger._get_redis", return_value=None
    ):
        fb = _make_feedback(db, pain_point_category="billing")
        _make_rule(db, trigger_config={"categories": ["billing"]})
        context = {"customer_email": fb.customer_email, "feedback_id": fb.id}

        evaluate_feedback_triggers(db, 1, context)
        evaluate_feedback_triggers(db, 1, context)

    # No cooldown available -> fires every time.
    assert db.query(AutomationExecution).count() == 2


# ---------------------------------------------------------------------------
# Acceptance criterion 5 — all four actions execute and are recorded
# ---------------------------------------------------------------------------


@patch("src.services.automation_feedback_trigger._get_redis", return_value=None)
def test_all_four_actions_execute_and_recorded(mock_redis, db):
    fb = _make_feedback(db, pain_point_category="billing")
    assignee = _make_user(db, role="admin", email="assignee@example.com")

    rule = _make_rule(
        db,
        trigger_config={"categories": ["billing"]},
        actions=[
            {"type": "auto_assign", "config": {"assign_to": f"user:{assignee.id}"}},
            {"type": "change_status", "config": {"status": "in_review"}},
            {"type": "send_notification", "config": {"recipients": "admins", "channels": ["dashboard"]}},
            {"type": "draft_response", "config": {"tone": "friendly"}},
        ],
    )

    context = {"customer_email": fb.customer_email, "feedback_id": fb.id}
    evaluate_feedback_triggers(db, 1, context)

    log = db.query(AutomationExecution).filter_by(rule_id=rule.id).first()
    assert log.status == "success"
    types = [a["type"] for a in log.actions_executed]
    assert types == ["auto_assign", "change_status", "send_notification", "draft_response"]
    for a in log.actions_executed:
        assert a["error"] is None

    db.refresh(fb)
    assert fb.assigned_to == assignee.id
    assert fb.workflow_status == "in_review"

    notif = db.query(Notification).filter_by(user_id=assignee.id).first()
    assert notif is not None
    assert notif.type == "automation_trigger"


# ---------------------------------------------------------------------------
# Acceptance criterion 6 — unimplemented action type errors loudly
# ---------------------------------------------------------------------------


@patch("src.services.automation_feedback_trigger._get_redis", return_value=None)
def test_run_playbook_action_errors_loudly_not_silently_skipped(mock_redis, db):
    """run_playbook is out of scope for this mirror; it must record an explicit error."""
    fb = _make_feedback(db, pain_point_category="billing")
    rule = _make_rule(
        db,
        trigger_config={"categories": ["billing"]},
        actions=[
            {"type": "change_status", "config": {"status": "in_review"}},
            {"type": "run_playbook", "config": {"playbook_id": 1}},
        ],
    )

    context = {"customer_email": fb.customer_email, "feedback_id": fb.id}
    evaluate_feedback_triggers(db, 1, context)

    log = db.query(AutomationExecution).filter_by(rule_id=rule.id).first()
    assert log.status == "partial_failure"

    run_playbook_result = next(a for a in log.actions_executed if a["type"] == "run_playbook")
    assert run_playbook_result["result"] is None
    assert run_playbook_result["error"] == "Unsupported action type in worker mirror: run_playbook"


@patch("src.services.automation_feedback_trigger._get_redis", return_value=None)
def test_unknown_action_type_errors_loudly(mock_redis, db):
    fb = _make_feedback(db, pain_point_category="billing")
    rule = _make_rule(
        db,
        trigger_config={"categories": ["billing"]},
        actions=[{"type": "totally_made_up", "config": {}}],
    )

    context = {"customer_email": fb.customer_email, "feedback_id": fb.id}
    evaluate_feedback_triggers(db, 1, context)

    log = db.query(AutomationExecution).filter_by(rule_id=rule.id).first()
    assert log.status == "failed"
    assert log.actions_executed[0]["error"] == (
        "Unsupported action type in worker mirror: totally_made_up"
    )


# ---------------------------------------------------------------------------
# send_notification — email + slack channels (mocked at source per testing notes)
# ---------------------------------------------------------------------------


@patch("src.services.automation_feedback_trigger._send_with_template")
@patch("src.services.automation_feedback_trigger._get_redis", return_value=None)
def test_send_notification_email_channel_uses_send_with_template(
    mock_redis, mock_send_with_template, db
):
    mock_send_with_template.return_value = True
    fb = _make_feedback(db, pain_point_category="billing")
    _make_user(db, role="owner", email="owner@example.com")

    rule = _make_rule(
        db,
        trigger_config={"categories": ["billing"]},
        actions=[{"type": "send_notification", "config": {"recipients": "owner", "channels": ["email"]}}],
    )

    context = {"customer_email": fb.customer_email, "feedback_id": fb.id}
    evaluate_feedback_triggers(db, 1, context)

    mock_send_with_template.assert_called_once()
    call_kwargs = mock_send_with_template.call_args.kwargs
    assert call_kwargs["to"] == "owner@example.com"

    log = db.query(AutomationExecution).filter_by(rule_id=rule.id).first()
    assert log.status == "success"


@patch("src.services.automation_feedback_trigger.send_slack_message_webhook")
@patch("src.services.automation_feedback_trigger._get_redis", return_value=None)
def test_send_notification_slack_is_org_wide_once_per_integration(
    mock_redis, mock_slack, db
):
    mock_slack.return_value = {"success": True}
    fb = _make_feedback(db, pain_point_category="billing")
    _make_user(db, role="admin", email="admin1@example.com")
    _make_user(db, role="admin", email="admin2@example.com")

    integration = Integration(
        organization_id=1,
        type="slack",
        name="#alerts",
        config={"webhook_url": "https://hooks.slack.example/abc"},
        is_active=True,
    )
    db.add(integration)
    db.commit()

    rule = _make_rule(
        db,
        trigger_config={"categories": ["billing"]},
        actions=[{"type": "send_notification", "config": {"recipients": "admins", "channels": ["slack"]}}],
    )

    context = {"customer_email": fb.customer_email, "feedback_id": fb.id}
    evaluate_feedback_triggers(db, 1, context)

    # One Slack post per active integration, NOT one per resolved recipient.
    mock_slack.assert_called_once()

    log = db.query(AutomationExecution).filter_by(rule_id=rule.id).first()
    assert log.status == "success"
    send_notification_result = next(
        a for a in log.actions_executed if a["type"] == "send_notification"
    )
    assert send_notification_result["result"]["slack_sent"] == 1


@patch("src.services.automation_feedback_trigger.send_slack_message_webhook")
@patch("src.services.automation_feedback_trigger._get_redis", return_value=None)
def test_send_notification_slack_send_failure_raises_are_caught(
    mock_redis, mock_slack, db
):
    """Worker's Slack sender RAISES on failure (opposite contract to backend's) — must be caught."""
    mock_slack.side_effect = Exception("slack webhook 500")
    fb = _make_feedback(db, pain_point_category="billing")

    integration = Integration(
        organization_id=1,
        type="slack",
        config={"webhook_url": "https://hooks.slack.example/abc"},
        is_active=True,
    )
    db.add(integration)
    db.commit()

    rule = _make_rule(
        db,
        trigger_config={"categories": ["billing"]},
        actions=[{"type": "send_notification", "config": {"recipients": "admins", "channels": ["slack"]}}],
    )

    context = {"customer_email": fb.customer_email, "feedback_id": fb.id}
    # Must not raise.
    evaluate_feedback_triggers(db, 1, context)

    log = db.query(AutomationExecution).filter_by(rule_id=rule.id).first()
    assert log.status == "partial_failure"
    send_notification_result = next(
        a for a in log.actions_executed if a["type"] == "send_notification"
    )
    assert "slack webhook 500" in send_notification_result["error"]


@patch("src.services.automation_feedback_trigger._get_redis", return_value=None)
def test_send_notification_unknown_channel_records_error(mock_redis, db):
    fb = _make_feedback(db, pain_point_category="billing")
    rule = _make_rule(
        db,
        trigger_config={"categories": ["billing"]},
        actions=[{"type": "send_notification", "config": {"recipients": "admins", "channels": ["carrier_pigeon"]}}],
    )

    context = {"customer_email": fb.customer_email, "feedback_id": fb.id}
    evaluate_feedback_triggers(db, 1, context)

    log = db.query(AutomationExecution).filter_by(rule_id=rule.id).first()
    assert log.status == "partial_failure"
    send_notification_result = next(
        a for a in log.actions_executed if a["type"] == "send_notification"
    )
    assert "unknown channel: carrier_pigeon" in send_notification_result["error"]


@patch("src.services.automation_feedback_trigger._get_redis", return_value=None)
def test_send_notification_slack_no_active_integration_records_error(mock_redis, db):
    fb = _make_feedback(db, pain_point_category="billing")
    rule = _make_rule(
        db,
        trigger_config={"categories": ["billing"]},
        actions=[{"type": "send_notification", "config": {"recipients": "admins", "channels": ["slack"]}}],
    )

    context = {"customer_email": fb.customer_email, "feedback_id": fb.id}
    evaluate_feedback_triggers(db, 1, context)

    log = db.query(AutomationExecution).filter_by(rule_id=rule.id).first()
    assert log.status == "partial_failure"
    send_notification_result = next(
        a for a in log.actions_executed if a["type"] == "send_notification"
    )
    assert "no active Slack integration configured" in send_notification_result["error"]


# ---------------------------------------------------------------------------
# One bad rule must not block others
# ---------------------------------------------------------------------------


@patch("src.services.automation_feedback_trigger._get_redis", return_value=None)
def test_one_bad_rule_does_not_block_others(mock_redis, db):
    fb = _make_feedback(db, pain_point_category="billing")
    good_rule = _make_rule(
        db,
        name="good",
        trigger_config={"categories": ["billing"]},
        actions=[],
    )
    bad_rule = AutomationRule(
        organization_id=1,
        name="bad",
        trigger_type="feedback_category_match",
        trigger_config={"categories": "not-a-list-thats-not-iterable-of-strings-safely"},
        actions=[],
        cooldown_hours=24,
        mode="active",
    )
    db.add(bad_rule)
    db.commit()

    context = {"customer_email": fb.customer_email, "feedback_id": fb.id}
    # Should not raise despite whatever bad_rule does internally.
    evaluate_feedback_triggers(db, 1, context)

    logs = db.query(AutomationExecution).filter_by(rule_id=good_rule.id).all()
    assert len(logs) == 1
    assert logs[0].status == "success"


# ---------------------------------------------------------------------------
# Phase 3 guard — src.tasks.analysis must not swallow the trigger ImportError
# ---------------------------------------------------------------------------


def test_analysis_does_not_swallow_import_error():
    """
    `evaluate_feedback_triggers` must be imported at MODULE level in
    `src.tasks.analysis` (so an import failure surfaces at worker startup),
    not inside a per-item `try/except Exception` that hides an ImportError
    the way the old `AutomationEngine` import did.
    """
    from src.tasks import analysis as analysis_module

    # If the import were still broken/missing, this attribute simply
    # wouldn't exist on the module.
    assert hasattr(analysis_module, "evaluate_feedback_triggers")

    source = inspect.getsource(analysis_module)

    # The exact dead import this bug is about must be gone.
    assert "from src.services.automation_engine import AutomationEngine" not in source
    assert "automation_engine" not in source

    # The replacement import must live at module level (tree.body), not
    # nested inside a function/try block.
    tree = ast.parse(source)
    module_level_names = set()
    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                module_level_names.add(alias.asname or alias.name)

    assert "evaluate_feedback_triggers" in module_level_names, (
        "evaluate_feedback_triggers must be imported at module level, not "
        "inside a try/except, so an ImportError surfaces at startup"
    )
