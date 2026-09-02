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
    name="Test rule",
) -> AutomationRule:
    rule = AutomationRule(
        organization_id=org_id,
        name=name,
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
    assert log.status == "failed"
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
    assert log.status == "failed"
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
    assert log.status == "failed"
    send_notification_result = next(
        a for a in log.actions_executed if a["type"] == "send_notification"
    )
    assert "no active Slack integration configured" in send_notification_result["error"]


# ---------------------------------------------------------------------------
# send_notification — teams channel (mirror parity with the backend engine:
# same result shape, same loud-error wording)
# ---------------------------------------------------------------------------


@patch("src.services.automation_feedback_trigger.send_teams_message_webhook")
@patch("src.services.automation_feedback_trigger._get_redis", return_value=None)
def test_send_notification_teams_is_org_wide_once_per_integration(
    mock_redis, mock_teams, db
):
    mock_teams.return_value = {"success": True}
    fb = _make_feedback(db, pain_point_category="billing")
    _make_user(db, role="admin", email="admin1@example.com")
    _make_user(db, role="admin", email="admin2@example.com")

    integration = Integration(
        organization_id=1,
        type="teams",
        name="General",
        config={"webhook_url": "https://example.webhook.office.com/abc"},
        is_active=True,
    )
    db.add(integration)
    db.commit()

    rule = _make_rule(
        db,
        trigger_config={"categories": ["billing"]},
        actions=[{"type": "send_notification", "config": {"recipients": "admins", "channels": ["teams"]}}],
    )

    context = {"customer_email": fb.customer_email, "feedback_id": fb.id}
    evaluate_feedback_triggers(db, 1, context)

    # One Teams post per active integration, NOT one per resolved recipient.
    mock_teams.assert_called_once()

    log = db.query(AutomationExecution).filter_by(rule_id=rule.id).first()
    assert log.status == "success"
    send_notification_result = next(
        a for a in log.actions_executed if a["type"] == "send_notification"
    )
    # Same result shape as the backend engine — the mirror-parity guard.
    assert send_notification_result["result"] == {
        "notifications_created": 0,
        "slack_sent": 0,
        "teams_sent": 1,
    }


@patch("src.services.automation_feedback_trigger.send_teams_message_webhook")
@patch("src.services.automation_feedback_trigger._get_redis", return_value=None)
def test_send_notification_teams_send_failure_raises_are_caught(
    mock_redis, mock_teams, db
):
    """Worker's Teams sender RAISES on failure (opposite contract to backend's) — must be caught."""
    mock_teams.side_effect = Exception("teams webhook 500")
    fb = _make_feedback(db, pain_point_category="billing")

    integration = Integration(
        organization_id=1,
        type="teams",
        config={"webhook_url": "https://example.webhook.office.com/abc"},
        is_active=True,
    )
    db.add(integration)
    db.commit()

    rule = _make_rule(
        db,
        trigger_config={"categories": ["billing"]},
        actions=[{"type": "send_notification", "config": {"recipients": "admins", "channels": ["teams"]}}],
    )

    context = {"customer_email": fb.customer_email, "feedback_id": fb.id}
    # Must not raise.
    evaluate_feedback_triggers(db, 1, context)

    log = db.query(AutomationExecution).filter_by(rule_id=rule.id).first()
    assert log.status == "failed"
    send_notification_result = next(
        a for a in log.actions_executed if a["type"] == "send_notification"
    )
    assert "teams webhook 500" in send_notification_result["error"]
    assert send_notification_result["result"]["teams_sent"] == 0


@patch("src.services.automation_feedback_trigger._get_redis", return_value=None)
def test_send_notification_teams_no_active_integration_records_error(mock_redis, db):
    fb = _make_feedback(db, pain_point_category="billing")
    rule = _make_rule(
        db,
        trigger_config={"categories": ["billing"]},
        actions=[{"type": "send_notification", "config": {"recipients": "admins", "channels": ["teams"]}}],
    )

    context = {"customer_email": fb.customer_email, "feedback_id": fb.id}
    evaluate_feedback_triggers(db, 1, context)

    log = db.query(AutomationExecution).filter_by(rule_id=rule.id).first()
    assert log.status == "failed"
    send_notification_result = next(
        a for a in log.actions_executed if a["type"] == "send_notification"
    )
    assert "teams: no active Teams integration configured" in send_notification_result["error"]


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

    # The exact dead import this bug is about must be gone (a comment
    # referencing the old module name by way of explanation is fine — only
    # an executable import statement matters here).
    assert "from src.services.automation_engine import AutomationEngine" not in source
    assert not any(
        isinstance(node, ast.ImportFrom) and node.module == "src.services.automation_engine"
        for node in ast.walk(ast.parse(source))
    )

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


# ---------------------------------------------------------------------------
# batch_sentiment_threshold — Track B (spec: docs/planning/batch-sentiment-
# trigger/trigger-core/spec.md, "THE CONTRACT"). This is the first ORG-WIDE
# trigger: it fires on the org's aggregate sentiment mix, not a single
# customer, so the cooldown identity and AutomationExecution.customer_email
# behave differently from every trigger above (see B3 tests below).
# ---------------------------------------------------------------------------


def _seed_feedback(db, org_id, sentiments, created_at=None):
    """Create one FeedbackItem per entry in *sentiments*, all sharing
    *created_at* (defaults to "now")."""
    for s in sentiments:
        _make_feedback(db, org_id=org_id, sentiment_label=s, created_at=created_at)


def _batch_rule(db, org_id=1, rule_mode="active", cooldown_hours=24, **config_overrides) -> AutomationRule:
    """rule_mode is AutomationRule.mode ('off'/'shadow'/'active'); the config's
    own 'mode' key ('percentage'/'count') is a THE-CONTRACT field passed via
    **config_overrides — deliberately named the same as the rule activation
    mode field to match spec vocabulary, hence the disambiguated param name
    here."""
    config = {
        "sentiment": "negative",
        "window_hours": 24,
        "mode": "percentage",
        "threshold": 0.5,
        "min_total": 5,
    }
    config.update(config_overrides)
    return _make_rule(
        db,
        org_id=org_id,
        mode=rule_mode,
        trigger_type="batch_sentiment_threshold",
        trigger_config=config,
        actions=[],
        cooldown_hours=cooldown_hours,
        name="Batch sentiment rule",
    )


@patch("src.services.automation_feedback_trigger._get_redis", return_value=None)
def test_batch_sentiment_fires_at_threshold(mock_redis, db):
    """AC4: window with 6 of 10 negative, threshold 0.5, min_total 5 -> fires."""
    _seed_feedback(db, 1, ["negative"] * 5 + ["positive"] * 4)
    trigger_fb = _make_feedback(db, org_id=1, sentiment_label="negative")

    rule = _batch_rule(db, threshold=0.5, min_total=5)

    context = {"customer_email": "", "feedback_id": trigger_fb.id}
    results = evaluate_feedback_triggers(db, 1, context)

    assert len(results) == 1
    logs = db.query(AutomationExecution).all()
    assert len(logs) == 1
    assert logs[0].rule_id == rule.id
    assert logs[0].status == "success"


@patch("src.services.automation_feedback_trigger._get_redis", return_value=None)
def test_batch_sentiment_does_not_fire_below_threshold(mock_redis, db):
    """2 of 10 negative (20%), threshold 0.5 -> does not fire."""
    _seed_feedback(db, 1, ["negative"] + ["positive"] * 8)
    trigger_fb = _make_feedback(db, org_id=1, sentiment_label="negative")

    _batch_rule(db, threshold=0.5, min_total=5)

    context = {"customer_email": "", "feedback_id": trigger_fb.id}
    results = evaluate_feedback_triggers(db, 1, context)

    assert results == []
    assert db.query(AutomationExecution).count() == 0


@patch("src.services.automation_feedback_trigger._get_redis", return_value=None)
def test_batch_sentiment_does_not_fire_when_total_below_min_total(mock_redis, db):
    """The false-alarm case from THE CONTRACT: 2 negative of 3 total is 67%,
    comfortably above a 0.5 threshold, but under a min_total=5 floor -> must
    NOT fire."""
    _seed_feedback(db, 1, ["negative"])
    trigger_fb = _make_feedback(db, org_id=1, sentiment_label="negative")
    # total so far = 2 (both negative). One more, non-matching, would still
    # keep total at 3 for the count below — but the pivot item itself must
    # match cfg["sentiment"] to reach the aggregate check at all, so seed a
    # third feedback item directly.
    _make_feedback(db, org_id=1, sentiment_label="positive")

    _batch_rule(db, threshold=0.5, min_total=5)

    context = {"customer_email": "", "feedback_id": trigger_fb.id}
    results = evaluate_feedback_triggers(db, 1, context)

    assert results == [], "2 of 3 (67%) must not fire below the min_total=5 sample floor"
    assert db.query(AutomationExecution).count() == 0


@patch("src.services.automation_feedback_trigger._get_redis", return_value=None)
def test_batch_sentiment_count_mode_fires_on_absolute_count(mock_redis, db):
    """count mode: threshold=3, 4 negative -> fires regardless of percentage."""
    _seed_feedback(db, 1, ["negative"] * 3)
    trigger_fb = _make_feedback(db, org_id=1, sentiment_label="negative")

    rule = _batch_rule(db, mode="count", threshold=3, min_total=3)

    context = {"customer_email": "", "feedback_id": trigger_fb.id}
    results = evaluate_feedback_triggers(db, 1, context)

    assert len(results) == 1
    assert db.query(AutomationExecution).filter_by(rule_id=rule.id).count() == 1


@patch("src.services.automation_feedback_trigger._get_redis", return_value=None)
def test_batch_sentiment_window_boundary_excludes_older_items(mock_redis, db):
    """Items outside window_hours must not count toward total/matching. If
    they wrongly did, this would fire; the assertion proves they don't."""
    stale = datetime.utcnow() - timedelta(hours=25)
    _seed_feedback(db, 1, ["negative"] * 5, created_at=stale)  # outside a 24h window
    _seed_feedback(db, 1, ["negative"])  # inside window
    trigger_fb = _make_feedback(db, org_id=1, sentiment_label="negative")

    _batch_rule(db, window_hours=24, threshold=0.5, min_total=5)

    context = {"customer_email": "", "feedback_id": trigger_fb.id}
    results = evaluate_feedback_triggers(db, 1, context)

    # In-window total is only 2 (well below min_total=5) — the stale rows
    # must not be counted, or this would incorrectly fire.
    assert results == []
    assert db.query(AutomationExecution).count() == 0


@patch("src.services.automation_feedback_trigger._get_redis", return_value=None)
def test_batch_sentiment_non_matching_item_never_fires(mock_redis, db):
    """Per-item seam: even with the aggregate already past threshold, a
    pivot item whose own sentiment doesn't match cfg["sentiment"] must skip
    before ever running the aggregate COUNT (THE CONTRACT's short-circuit
    order, step 2)."""
    _seed_feedback(db, 1, ["negative"] * 8)
    trigger_fb = _make_feedback(db, org_id=1, sentiment_label="positive")

    _batch_rule(db, threshold=0.5, min_total=5)

    context = {"customer_email": "", "feedback_id": trigger_fb.id}
    results = evaluate_feedback_triggers(db, 1, context)

    assert results == []
    assert db.query(AutomationExecution).count() == 0


def test_batch_sentiment_cooldown_suppresses_second_fire(db):
    fake_redis = MagicMock()
    fake_redis.exists.return_value = False

    with patch(
        "src.services.automation_feedback_trigger._get_redis", return_value=fake_redis
    ):
        _seed_feedback(db, 1, ["negative"] * 5)
        fb1 = _make_feedback(db, org_id=1, sentiment_label="negative")
        _batch_rule(db, threshold=0.5, min_total=5)

        context1 = {"customer_email": "", "feedback_id": fb1.id}
        evaluate_feedback_triggers(db, 1, context1)
        assert db.query(AutomationExecution).count() == 1

        fake_redis.exists.return_value = True
        fb2 = _make_feedback(db, org_id=1, sentiment_label="negative")
        context2 = {"customer_email": "", "feedback_id": fb2.id}
        evaluate_feedback_triggers(db, 1, context2)
        assert db.query(AutomationExecution).count() == 1  # unchanged


@patch("src.services.automation_feedback_trigger._get_redis", return_value=None)
def test_batch_sentiment_shadow_mode_logs_no_actions(mock_redis, db):
    _seed_feedback(db, 1, ["negative"] * 5)
    trigger_fb = _make_feedback(db, org_id=1, sentiment_label="negative")

    rule = _batch_rule(
        db,
        rule_mode="shadow",
        threshold=0.5,
        min_total=5,
    )
    # Even with actions configured, shadow must run none of them.
    rule.actions = [{"type": "send_notification", "config": {"recipients": "admins"}}]
    db.commit()

    context = {"customer_email": "", "feedback_id": trigger_fb.id}
    evaluate_feedback_triggers(db, 1, context)

    logs = db.query(AutomationExecution).filter_by(rule_id=rule.id).all()
    assert len(logs) == 1
    assert logs[0].status == "shadow"
    assert logs[0].actions_executed == []


# ---------------------------------------------------------------------------
# B3 — org-wide cooldown identity: "__org__" is the Redis key identity, but
# AutomationExecution.customer_email must always be NULL for this trigger,
# even when the triggering context happens to carry a real customer_email.
# ---------------------------------------------------------------------------


@patch("src.services.automation_feedback_trigger._get_redis", return_value=None)
def test_batch_sentiment_execution_customer_email_is_null(mock_redis, db):
    _seed_feedback(db, 1, ["negative"] * 5)
    trigger_fb = _make_feedback(
        db, org_id=1, sentiment_label="negative", customer_email="real-customer@example.com"
    )

    _batch_rule(db, threshold=0.5, min_total=5)

    # A real customer_email in context must NOT leak into the execution row.
    context = {"customer_email": "real-customer@example.com", "feedback_id": trigger_fb.id}
    evaluate_feedback_triggers(db, 1, context)

    log = db.query(AutomationExecution).first()
    assert log is not None
    assert log.customer_email is None


def test_batch_sentiment_cooldown_key_uses_org_sentinel(db):
    """The shared cooldown key must be automation_cooldown:{rule_id}:__org__
    — ONE key per rule, not one per customer_email, even when context
    carries a real customer_email."""
    fake_redis = MagicMock()
    fake_redis.exists.return_value = False

    with patch(
        "src.services.automation_feedback_trigger._get_redis", return_value=fake_redis
    ):
        _seed_feedback(db, 1, ["negative"] * 5)
        trigger_fb = _make_feedback(
            db, org_id=1, sentiment_label="negative", customer_email="someone@example.com"
        )
        rule = _batch_rule(db, threshold=0.5, min_total=5, cooldown_hours=6)

        context = {"customer_email": "someone@example.com", "feedback_id": trigger_fb.id}
        evaluate_feedback_triggers(db, 1, context)

    expected_key = f"automation_cooldown:{rule.id}:__org__"
    fake_redis.setex.assert_called_once_with(expected_key, 6 * 3600, "1")


# ---------------------------------------------------------------------------
# send_customer_email action (automation-send-customer-email, worker-mirrors
# Phase 3) — this mirror now HANDLES it; every skip stays loud.
# ---------------------------------------------------------------------------


def _make_org(db, org_id=1, product_name="Acme"):
    from src.models import Organization

    org = Organization(id=org_id, name="Acme", plan="pro",
                       product_name_display=product_name)
    db.add(org)
    db.commit()
    return org


def _make_health(db, org_id=1, email="cust@example.com", name="Dana",
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


EMAIL_ACTION = {
    "type": "send_customer_email",
    "config": {"template": "re_engagement", "recipient": "customer"},
}


@patch("src.services.automation_email_delivery.send_automation_email")
@patch("src.services.automation_feedback_trigger._get_redis", return_value=None)
def test_send_customer_email_action_queues_delivery(mock_redis, mock_task, db):
    from src.models import AutomationEmailDelivery

    _make_org(db)
    fb = _make_feedback(db, pain_point_category="billing")
    _make_health(db)
    rule = _make_rule(db, trigger_config={"categories": ["billing"]},
                      actions=[EMAIL_ACTION])

    context = {"customer_email": fb.customer_email, "feedback_id": fb.id}
    with patch("src.email.RESEND_API_KEY", "test-key"):
        evaluate_feedback_triggers(db, 1, context)

    row = db.query(AutomationEmailDelivery).one()
    assert row.status == "queued"
    assert row.to_email == "cust@example.com"
    assert "Dana" in row.body
    assert "Acme" in row.body
    mock_task.delay.assert_called_once_with(row.id)

    log = db.query(AutomationExecution).filter_by(rule_id=rule.id).first()
    assert log.status == "success"
    result = next(a for a in log.actions_executed if a["type"] == "send_customer_email")
    assert result["error"] is None
    assert result["result"] == {"status": "queued", "delivery_id": row.id}


@patch("src.services.automation_email_delivery.send_automation_email")
@patch("src.services.automation_feedback_trigger._get_redis", return_value=None)
def test_send_customer_email_no_key_is_loud(mock_redis, mock_task, db):
    from src.models import AutomationEmailDelivery

    _make_org(db)
    fb = _make_feedback(db, pain_point_category="billing")
    _make_health(db)
    rule = _make_rule(db, trigger_config={"categories": ["billing"]},
                      actions=[EMAIL_ACTION])

    context = {"customer_email": fb.customer_email, "feedback_id": fb.id}
    with patch("src.email.RESEND_API_KEY", ""):
        evaluate_feedback_triggers(db, 1, context)

    log = db.query(AutomationExecution).filter_by(rule_id=rule.id).first()
    assert log.status == "failed"
    result = next(a for a in log.actions_executed if a["type"] == "send_customer_email")
    assert result["error"] == "email not configured"

    row = db.query(AutomationEmailDelivery).one()
    assert row.status == "skipped"
    assert row.reason == "email not configured"
    mock_task.delay.assert_not_called()


@patch("src.services.automation_email_delivery.send_automation_email")
@patch("src.services.automation_feedback_trigger._get_redis", return_value=None)
def test_send_customer_email_org_wide_trigger_is_loud(mock_redis, mock_task, db):
    """batch_sentiment_threshold carries a pivot feedback's email — not a
    recipient. The skip is keyed on the TRIGGER TYPE, not the context value."""
    from src.models import AutomationEmailDelivery

    _make_org(db)
    for _ in range(5):
        _make_feedback(db, sentiment_label="negative")
    fb = _make_feedback(db, sentiment_label="negative")
    _make_health(db)
    rule = _make_rule(
        db,
        trigger_type="batch_sentiment_threshold",
        trigger_config={"sentiment": "negative", "threshold": 1, "mode": "count",
                        "window_days": 7},
        actions=[EMAIL_ACTION],
    )

    context = {"customer_email": fb.customer_email, "feedback_id": fb.id}
    with patch("src.email.RESEND_API_KEY", "test-key"):
        evaluate_feedback_triggers(db, 1, context)

    log = db.query(AutomationExecution).filter_by(rule_id=rule.id).first()
    assert log is not None, "the org-wide rule should still have fired"
    result = next(a for a in log.actions_executed if a["type"] == "send_customer_email")
    assert result["error"] == "no customer email (org-wide trigger)"
    assert db.query(AutomationEmailDelivery).count() == 0
    mock_task.delay.assert_not_called()


@patch("src.services.automation_email_delivery.send_automation_email")
@patch("src.services.automation_feedback_trigger._get_redis", return_value=None)
def test_send_customer_email_archived_customer_is_loud(mock_redis, mock_task, db):
    from src.models import AutomationEmailDelivery

    _make_org(db)
    fb = _make_feedback(db, pain_point_category="billing")
    _make_health(db, is_archived=True)
    rule = _make_rule(db, trigger_config={"categories": ["billing"]},
                      actions=[EMAIL_ACTION])

    context = {"customer_email": fb.customer_email, "feedback_id": fb.id}
    with patch("src.email.RESEND_API_KEY", "test-key"):
        evaluate_feedback_triggers(db, 1, context)

    log = db.query(AutomationExecution).filter_by(rule_id=rule.id).first()
    result = next(a for a in log.actions_executed if a["type"] == "send_customer_email")
    assert result["error"] == "customer archived"
    assert db.query(AutomationEmailDelivery).count() == 0
    mock_task.delay.assert_not_called()


@patch("src.services.automation_email_delivery.send_automation_email")
@patch("src.services.automation_feedback_trigger._get_redis", return_value=None)
def test_send_customer_email_cs_assignee_resolves_owner(mock_redis, mock_task, db):
    from src.models import AutomationEmailDelivery

    _make_org(db)
    owner = _make_user(db, role="owner", email="owner@acme.test")
    fb = _make_feedback(db, pain_point_category="billing")
    _make_health(db, cs_owner_user_id=owner.id)
    _make_rule(
        db,
        trigger_config={"categories": ["billing"]},
        actions=[{
            "type": "send_customer_email",
            "config": {"template": "re_engagement", "recipient": "cs_assignee"},
        }],
    )

    context = {"customer_email": fb.customer_email, "feedback_id": fb.id}
    with patch("src.email.RESEND_API_KEY", "test-key"):
        evaluate_feedback_triggers(db, 1, context)

    row = db.query(AutomationEmailDelivery).one()
    assert row.to_email == "owner@acme.test"
    assert row.customer_email == "cust@example.com"


@patch("src.services.automation_email_delivery.send_automation_email")
@patch("src.services.automation_feedback_trigger._get_redis", return_value=None)
def test_send_customer_email_unknown_template_is_loud(mock_redis, mock_task, db):
    from src.models import AutomationEmailDelivery

    _make_org(db)
    fb = _make_feedback(db, pain_point_category="billing")
    _make_health(db)
    rule = _make_rule(
        db,
        trigger_config={"categories": ["billing"]},
        actions=[{"type": "send_customer_email", "config": {"template": "nope"}}],
    )

    context = {"customer_email": fb.customer_email, "feedback_id": fb.id}
    with patch("src.email.RESEND_API_KEY", "test-key"):
        evaluate_feedback_triggers(db, 1, context)

    log = db.query(AutomationExecution).filter_by(rule_id=rule.id).first()
    result = next(a for a in log.actions_executed if a["type"] == "send_customer_email")
    assert result["error"] == "unknown template key: nope"
    assert db.query(AutomationEmailDelivery).count() == 0
    mock_task.delay.assert_not_called()
