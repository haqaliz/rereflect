"""
TDD tests for AutomationEngine (M4.4 Phase 2).

All 16 required tests — written RED first, then driven to GREEN by the
implementation in src/services/automation_engine.py.

Run:
    cd services/backend-api && source venv/bin/activate
    pytest tests/test_automation_engine.py -v
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch, call
import pytest

from sqlalchemy.orm import Session

from src.models.automation_rule import AutomationRule
from src.models.automation_execution import AutomationExecution
from src.models.feedback import FeedbackItem
from src.models.organization import Organization
from src.models.user import User


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_rule(
    db: Session,
    org_id: int,
    trigger_type: str,
    trigger_config: dict,
    actions: list,
    is_active: bool = True,
    cooldown_hours: int = 24,
    name: str = "Test Rule",
) -> AutomationRule:
    rule = AutomationRule(
        organization_id=org_id,
        name=name,
        trigger_type=trigger_type,
        trigger_config=trigger_config,
        actions=actions,
        is_active=is_active,
        cooldown_hours=cooldown_hours,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


def _make_feedback(
    db: Session,
    org_id: int,
    *,
    customer_email: str = "customer@test.com",
    sentiment_label: str = "negative",
    sentiment_score: float = -0.8,
    is_urgent: bool = False,
    pain_point_category: str = None,
    workflow_status: str = "new",
    created_at: datetime = None,
) -> FeedbackItem:
    fb = FeedbackItem(
        organization_id=org_id,
        text="Some feedback text",
        source="email",
        customer_email=customer_email,
        sentiment_label=sentiment_label,
        sentiment_score=sentiment_score,
        is_urgent=is_urgent,
        pain_point_category=pain_point_category,
        workflow_status=workflow_status,
        created_at=created_at or datetime.utcnow(),
    )
    db.add(fb)
    db.commit()
    db.refresh(fb)
    return fb


# ---------------------------------------------------------------------------
# 1. test_evaluate_matches_active_rules_only
# ---------------------------------------------------------------------------

def test_evaluate_matches_active_rules_only(db: Session, test_organization: Organization):
    """evaluate() must skip inactive rules and only process active ones."""
    from src.services.automation_engine import AutomationEngine

    active_rule = _make_rule(
        db, test_organization.id,
        trigger_type="health_score_threshold",
        trigger_config={"threshold": 50, "direction": "below"},
        actions=[{"type": "change_status", "config": {"status": "in_review"}}],
        is_active=True,
    )
    _make_rule(
        db, test_organization.id,
        trigger_type="health_score_threshold",
        trigger_config={"threshold": 50, "direction": "below"},
        actions=[{"type": "change_status", "config": {"status": "in_review"}}],
        is_active=False,
        name="Inactive Rule",
    )

    fb = _make_feedback(db, test_organization.id)
    context = {
        "health_score": 20,
        "customer_email": fb.customer_email,
        "feedback_id": fb.id,
    }

    engine = AutomationEngine(db)
    with patch.object(engine, "_check_cooldown", return_value=False):
        results = engine.evaluate(test_organization.id, "health_score_threshold", context)

    # Only the active rule should have been evaluated and produced a result
    assert len(results) == 1
    assert results[0]["rule_id"] == active_rule.id


# ---------------------------------------------------------------------------
# 2. test_health_score_trigger_fires_below_threshold
# ---------------------------------------------------------------------------

def test_health_score_trigger_fires_below_threshold(db: Session, test_organization: Organization):
    """_check_trigger should return True when health_score < threshold."""
    from src.services.automation_engine import AutomationEngine

    rule = _make_rule(
        db, test_organization.id,
        trigger_type="health_score_threshold",
        trigger_config={"threshold": 30, "direction": "below"},
        actions=[],
    )
    engine = AutomationEngine(db)
    context = {"health_score": 25, "customer_email": "c@test.com", "feedback_id": 1}
    assert engine._check_trigger(rule, context) is True


# ---------------------------------------------------------------------------
# 3. test_health_score_trigger_skips_above_threshold
# ---------------------------------------------------------------------------

def test_health_score_trigger_skips_above_threshold(db: Session, test_organization: Organization):
    """_check_trigger should return False when health_score >= threshold."""
    from src.services.automation_engine import AutomationEngine

    rule = _make_rule(
        db, test_organization.id,
        trigger_type="health_score_threshold",
        trigger_config={"threshold": 30, "direction": "below"},
        actions=[],
    )
    engine = AutomationEngine(db)
    context = {"health_score": 35, "customer_email": "c@test.com", "feedback_id": 1}
    assert engine._check_trigger(rule, context) is False


# ---------------------------------------------------------------------------
# 4. test_sentiment_pattern_trigger_fires
# ---------------------------------------------------------------------------

def test_sentiment_pattern_trigger_fires(db: Session, test_organization: Organization):
    """_check_trigger fires when customer has >= count negative feedbacks in window."""
    from src.services.automation_engine import AutomationEngine

    rule = _make_rule(
        db, test_organization.id,
        trigger_type="sentiment_pattern",
        trigger_config={"count": 3, "days": 7, "sentiment": "negative"},
        actions=[],
    )

    email = "repeat@test.com"
    for _ in range(3):
        _make_feedback(db, test_organization.id, customer_email=email, sentiment_label="negative")

    fb = _make_feedback(db, test_organization.id, customer_email=email, sentiment_label="negative")
    context = {"customer_email": email, "feedback_id": fb.id}

    engine = AutomationEngine(db)
    assert engine._check_trigger(rule, context) is True


# ---------------------------------------------------------------------------
# 5. test_sentiment_pattern_trigger_skips_insufficient_count
# ---------------------------------------------------------------------------

def test_sentiment_pattern_trigger_skips_insufficient_count(db: Session, test_organization: Organization):
    """_check_trigger returns False when negative feedback count is below threshold."""
    from src.services.automation_engine import AutomationEngine

    rule = _make_rule(
        db, test_organization.id,
        trigger_type="sentiment_pattern",
        trigger_config={"count": 5, "days": 7, "sentiment": "negative"},
        actions=[],
    )

    email = "rare@test.com"
    _make_feedback(db, test_organization.id, customer_email=email, sentiment_label="negative")

    fb = _make_feedback(db, test_organization.id, customer_email=email, sentiment_label="negative")
    context = {"customer_email": email, "feedback_id": fb.id}

    engine = AutomationEngine(db)
    assert engine._check_trigger(rule, context) is False


# ---------------------------------------------------------------------------
# 6. test_churn_risk_level_trigger_fires
# ---------------------------------------------------------------------------

def test_churn_risk_level_trigger_fires(db: Session, test_organization: Organization):
    """_check_trigger fires when new_risk_level matches target_level."""
    from src.services.automation_engine import AutomationEngine

    rule = _make_rule(
        db, test_organization.id,
        trigger_type="churn_risk_level_change",
        trigger_config={"target_level": "critical"},
        actions=[],
    )
    engine = AutomationEngine(db)
    context = {
        "new_risk_level": "critical",
        "old_risk_level": "at_risk",
        "customer_email": "c@test.com",
        "feedback_id": 1,
    }
    assert engine._check_trigger(rule, context) is True


# ---------------------------------------------------------------------------
# 7. test_category_match_trigger_fires
# ---------------------------------------------------------------------------

def test_category_match_trigger_fires(db: Session, test_organization: Organization):
    """_check_trigger fires when feedback categories intersect with configured categories."""
    from src.services.automation_engine import AutomationEngine

    rule = _make_rule(
        db, test_organization.id,
        trigger_type="feedback_category_match",
        trigger_config={"categories": ["critical_bug", "security_breach"]},
        actions=[],
    )

    fb = _make_feedback(
        db, test_organization.id,
        pain_point_category="critical_bug",
        is_urgent=True,
    )
    context = {
        "customer_email": fb.customer_email,
        "feedback_id": fb.id,
    }

    engine = AutomationEngine(db)
    assert engine._check_trigger(rule, context) is True


# ---------------------------------------------------------------------------
# 8. test_category_match_trigger_skips_no_match
# ---------------------------------------------------------------------------

def test_category_match_trigger_skips_no_match(db: Session, test_organization: Organization):
    """_check_trigger returns False when feedback categories don't match configured ones."""
    from src.services.automation_engine import AutomationEngine

    rule = _make_rule(
        db, test_organization.id,
        trigger_type="feedback_category_match",
        trigger_config={"categories": ["critical_bug", "security_breach"]},
        actions=[],
    )

    fb = _make_feedback(
        db, test_organization.id,
        pain_point_category="performance",
    )
    context = {"customer_email": fb.customer_email, "feedback_id": fb.id}

    engine = AutomationEngine(db)
    assert engine._check_trigger(rule, context) is False


# ---------------------------------------------------------------------------
# 9. test_cooldown_prevents_refire
# ---------------------------------------------------------------------------

def test_cooldown_prevents_refire(db: Session, test_organization: Organization):
    """evaluate() skips execution if the rule is in cooldown for this customer."""
    from src.services.automation_engine import AutomationEngine

    rule = _make_rule(
        db, test_organization.id,
        trigger_type="health_score_threshold",
        trigger_config={"threshold": 50, "direction": "below"},
        actions=[{"type": "change_status", "config": {"status": "in_review"}}],
    )

    fb = _make_feedback(db, test_organization.id)
    context = {
        "health_score": 10,
        "customer_email": fb.customer_email,
        "feedback_id": fb.id,
    }

    engine = AutomationEngine(db)
    # Simulate Redis returning True (key exists = in cooldown)
    with patch.object(engine, "_check_cooldown", return_value=True) as mock_cd:
        results = engine.evaluate(test_organization.id, "health_score_threshold", context)

    # Nothing should have executed
    assert results == []
    mock_cd.assert_called_once_with(rule.id, fb.customer_email)


# ---------------------------------------------------------------------------
# 10. test_cooldown_expires_allows_refire
# ---------------------------------------------------------------------------

def test_cooldown_expires_allows_refire(db: Session, test_organization: Organization):
    """evaluate() executes the rule when cooldown has expired (Redis key absent)."""
    from src.services.automation_engine import AutomationEngine

    rule = _make_rule(
        db, test_organization.id,
        trigger_type="health_score_threshold",
        trigger_config={"threshold": 50, "direction": "below"},
        actions=[{"type": "change_status", "config": {"status": "in_review"}}],
    )

    fb = _make_feedback(db, test_organization.id)
    context = {
        "health_score": 10,
        "customer_email": fb.customer_email,
        "feedback_id": fb.id,
    }

    engine = AutomationEngine(db)
    # Cooldown not active (key absent)
    with patch.object(engine, "_check_cooldown", return_value=False):
        with patch.object(engine, "_set_cooldown"):
            results = engine.evaluate(test_organization.id, "health_score_threshold", context)

    assert len(results) == 1
    assert results[0]["rule_id"] == rule.id


# ---------------------------------------------------------------------------
# 11. test_assign_action_executes
# ---------------------------------------------------------------------------

def test_assign_action_executes(db: Session, test_organization: Organization):
    """_execute_assign should assign the feedback to the target user."""
    from src.services.automation_engine import AutomationEngine

    user = User(
        email="assignee@test.com",
        password_hash="hashed",
        organization_id=test_organization.id,
        role="admin",
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    fb = _make_feedback(db, test_organization.id)
    engine = AutomationEngine(db)

    config = {"assign_to": f"user:{user.id}"}
    result = engine._execute_assign(config, fb)

    db.refresh(fb)
    assert fb.assigned_to == user.id
    assert result["type"] == "auto_assign"
    assert result["error"] is None


# ---------------------------------------------------------------------------
# 12. test_change_status_action_executes
# ---------------------------------------------------------------------------

def test_change_status_action_executes(db: Session, test_organization: Organization):
    """_execute_change_status should update feedback.workflow_status."""
    from src.services.automation_engine import AutomationEngine

    fb = _make_feedback(db, test_organization.id, workflow_status="new")
    engine = AutomationEngine(db)

    config = {"status": "in_review"}
    result = engine._execute_change_status(config, fb)

    db.refresh(fb)
    assert fb.workflow_status == "in_review"
    assert result["type"] == "change_status"
    assert result["error"] is None


# ---------------------------------------------------------------------------
# 13. test_notify_action_executes
# ---------------------------------------------------------------------------

def test_notify_action_executes(db: Session, test_organization: Organization):
    """_execute_notify should create Notification records for target recipients."""
    from src.services.automation_engine import AutomationEngine
    from src.models.notification import Notification

    # Create an admin user to receive the notification
    admin = User(
        email="admin@test.com",
        password_hash="hashed",
        organization_id=test_organization.id,
        role="admin",
    )
    db.add(admin)
    db.commit()

    fb = _make_feedback(db, test_organization.id)

    rule = _make_rule(
        db, test_organization.id,
        trigger_type="health_score_threshold",
        trigger_config={"threshold": 30},
        actions=[],
        name="Notify Rule",
    )

    engine = AutomationEngine(db)
    config = {"recipients": "admins", "channels": ["dashboard"]}
    result = engine._execute_notify(config, fb, rule)

    assert result["type"] == "send_notification"
    assert result["error"] is None

    notifications = db.query(Notification).filter(
        Notification.user_id == admin.id,
    ).all()
    assert len(notifications) >= 1


# ---------------------------------------------------------------------------
# 14. test_multiple_actions_execute_sequentially
# ---------------------------------------------------------------------------

def test_multiple_actions_execute_sequentially(db: Session, test_organization: Organization):
    """_execute_actions should run all actions and return one result per action."""
    from src.services.automation_engine import AutomationEngine

    rule = _make_rule(
        db, test_organization.id,
        trigger_type="health_score_threshold",
        trigger_config={"threshold": 50},
        actions=[
            {"type": "change_status", "config": {"status": "in_review"}},
            {"type": "change_status", "config": {"status": "resolved"}},
        ],
    )
    fb = _make_feedback(db, test_organization.id)
    context = {"customer_email": fb.customer_email, "feedback_id": fb.id}

    engine = AutomationEngine(db)
    action_results = engine._execute_actions(rule, fb, context)

    assert len(action_results) == 2
    assert all(r["error"] is None for r in action_results)
    db.refresh(fb)
    assert fb.workflow_status == "resolved"


# ---------------------------------------------------------------------------
# 15. test_execution_logged_to_db
# ---------------------------------------------------------------------------

def test_execution_logged_to_db(db: Session, test_organization: Organization):
    """After a successful evaluate, an AutomationExecution record must be persisted."""
    from src.services.automation_engine import AutomationEngine

    rule = _make_rule(
        db, test_organization.id,
        trigger_type="health_score_threshold",
        trigger_config={"threshold": 50, "direction": "below"},
        actions=[{"type": "change_status", "config": {"status": "in_review"}}],
    )

    fb = _make_feedback(db, test_organization.id)
    context = {
        "health_score": 10,
        "customer_email": fb.customer_email,
        "feedback_id": fb.id,
    }

    engine = AutomationEngine(db)
    with patch.object(engine, "_check_cooldown", return_value=False):
        with patch.object(engine, "_set_cooldown"):
            engine.evaluate(test_organization.id, "health_score_threshold", context)

    executions = db.query(AutomationExecution).filter(
        AutomationExecution.rule_id == rule.id
    ).all()

    assert len(executions) == 1
    exec_record = executions[0]
    assert exec_record.organization_id == test_organization.id
    assert exec_record.feedback_id == fb.id
    assert exec_record.customer_email == fb.customer_email
    assert exec_record.status in ("success", "partial_failure", "failed")
    assert exec_record.trigger_snapshot is not None
    assert exec_record.actions_executed is not None


# ---------------------------------------------------------------------------
# 16. test_failed_action_logs_error
# ---------------------------------------------------------------------------

def test_failed_action_logs_error(db: Session, test_organization: Organization):
    """If an action raises an exception, the execution record captures the error."""
    from src.services.automation_engine import AutomationEngine

    rule = _make_rule(
        db, test_organization.id,
        trigger_type="health_score_threshold",
        trigger_config={"threshold": 50, "direction": "below"},
        actions=[{"type": "auto_assign", "config": {"assign_to": "round_robin"}}],
    )

    fb = _make_feedback(db, test_organization.id)
    context = {
        "health_score": 10,
        "customer_email": fb.customer_email,
        "feedback_id": fb.id,
    }

    engine = AutomationEngine(db)

    # Force the assign action to raise so we can verify error logging
    with patch.object(engine, "_check_cooldown", return_value=False):
        with patch.object(engine, "_set_cooldown"):
            with patch.object(
                engine,
                "_execute_assign",
                side_effect=RuntimeError("assign boom"),
            ):
                results = engine.evaluate(
                    test_organization.id, "health_score_threshold", context
                )

    assert len(results) == 1
    execution = db.query(AutomationExecution).filter(
        AutomationExecution.rule_id == rule.id
    ).first()
    assert execution is not None
    assert execution.status in ("partial_failure", "failed")
    # At least one action result should contain the error message
    actions_executed = execution.actions_executed or []
    errors = [a.get("error") for a in actions_executed if a.get("error")]
    assert len(errors) >= 1
    assert "assign boom" in errors[0]
