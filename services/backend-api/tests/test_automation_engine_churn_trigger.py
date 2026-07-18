"""
TDD tests for AutomationEngine — churn_probability_threshold trigger + mode gating
(churn-triggered-playbooks, task 2).

Run:
    cd services/backend-api && source venv/bin/activate
    pytest tests/test_automation_engine_churn_trigger.py -v
"""

from datetime import datetime
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

from src.models.automation_rule import AutomationRule
from src.models.automation_execution import AutomationExecution
from src.models.feedback import FeedbackItem
from src.models.notification import Notification
from src.models.organization import Organization


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_rule(
    db: Session,
    org_id: int,
    trigger_type: str,
    trigger_config: dict,
    actions: list,
    mode: str = "active",
    cooldown_hours: int = 24,
    name: str = "Test Rule",
) -> AutomationRule:
    rule = AutomationRule(
        organization_id=org_id,
        name=name,
        trigger_type=trigger_type,
        trigger_config=trigger_config,
        actions=actions,
        mode=mode,
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
) -> FeedbackItem:
    fb = FeedbackItem(
        organization_id=org_id,
        text="Some feedback text",
        source="email",
        customer_email=customer_email,
        sentiment_label="negative",
        sentiment_score=-0.8,
        is_urgent=False,
        workflow_status="new",
        created_at=datetime.utcnow(),
    )
    db.add(fb)
    db.commit()
    db.refresh(fb)
    return fb


# ---------------------------------------------------------------------------
# 1. churn_probability_threshold trigger — fires above threshold
# ---------------------------------------------------------------------------

def test_churn_probability_threshold_fires_above_threshold(
    db: Session, test_organization: Organization
):
    """_check_trigger fires when churn_probability >= threshold."""
    from src.services.automation_engine import AutomationEngine

    rule = _make_rule(
        db, test_organization.id,
        trigger_type="churn_probability_threshold",
        trigger_config={"threshold": 0.7},
        actions=[],
    )
    engine = AutomationEngine(db)
    context = {"churn_probability": 0.82, "customer_email": "c@x.com"}
    assert engine._check_trigger(rule, context) is True


# ---------------------------------------------------------------------------
# 2. churn_probability_threshold trigger — does not fire below threshold
# ---------------------------------------------------------------------------

def test_churn_probability_threshold_skips_below_threshold(
    db: Session, test_organization: Organization
):
    """_check_trigger returns False when churn_probability < threshold."""
    from src.services.automation_engine import AutomationEngine

    rule = _make_rule(
        db, test_organization.id,
        trigger_type="churn_probability_threshold",
        trigger_config={"threshold": 0.7},
        actions=[],
    )
    engine = AutomationEngine(db)
    context = {"churn_probability": 0.5, "customer_email": "c@x.com"}
    assert engine._check_trigger(rule, context) is False


# ---------------------------------------------------------------------------
# 3. churn_probability_threshold trigger — p is None never fires
# ---------------------------------------------------------------------------

def test_churn_probability_threshold_none_never_fires(
    db: Session, test_organization: Organization
):
    """_check_trigger returns False when churn_probability is absent from context."""
    from src.services.automation_engine import AutomationEngine

    rule = _make_rule(
        db, test_organization.id,
        trigger_type="churn_probability_threshold",
        trigger_config={"threshold": 0.7},
        actions=[],
    )
    engine = AutomationEngine(db)
    context = {"customer_email": "c@x.com"}
    assert engine._check_trigger(rule, context) is False


# ---------------------------------------------------------------------------
# 4. mode="off" rule is never selected by evaluate()
# ---------------------------------------------------------------------------

def test_mode_off_rule_never_selected(db: Session, test_organization: Organization):
    """A mode='off' rule must not be returned by the rule-selection query, even
    when the signal clearly breaches the threshold."""
    from src.services.automation_engine import AutomationEngine

    rule = _make_rule(
        db, test_organization.id,
        trigger_type="churn_probability_threshold",
        trigger_config={"threshold": 0.7},
        actions=[{"type": "send_notification", "config": {"recipients": "admins"}}],
        mode="off",
        name="Off Rule",
    )
    context = {"churn_probability": 0.95, "customer_email": "off@x.com"}

    engine = AutomationEngine(db)
    with patch.object(engine, "_check_cooldown", return_value=False):
        results = engine.evaluate(
            test_organization.id, "churn_probability_threshold", context
        )

    assert results == []
    executions = db.query(AutomationExecution).filter(
        AutomationExecution.rule_id == rule.id
    ).all()
    assert len(executions) == 0


# ---------------------------------------------------------------------------
# 5. mode="shadow" rule logs execution but runs no actions
# ---------------------------------------------------------------------------

def test_mode_shadow_logs_execution_without_running_actions(
    db: Session, test_organization: Organization
):
    """A mode='shadow' rule that breaches must log an AutomationExecution with
    status='shadow' and must NOT execute any actions (no Notification rows)."""
    from src.services.automation_engine import AutomationEngine

    rule = _make_rule(
        db, test_organization.id,
        trigger_type="churn_probability_threshold",
        trigger_config={"threshold": 0.7},
        actions=[{"type": "send_notification", "config": {"recipients": "admins"}}],
        mode="shadow",
        name="Shadow Rule",
    )
    context = {"churn_probability": 0.9, "customer_email": "shadow@x.com"}

    engine = AutomationEngine(db)
    with patch.object(engine, "_check_cooldown", return_value=False):
        with patch.object(engine, "_set_cooldown"):
            results = engine.evaluate(
                test_organization.id, "churn_probability_threshold", context
            )

    assert len(results) == 1
    assert results[0]["status"] == "shadow"
    assert results[0]["actions"] == []

    execution = db.query(AutomationExecution).filter(
        AutomationExecution.rule_id == rule.id
    ).first()
    assert execution is not None
    assert execution.status == "shadow"
    assert execution.actions_executed == []

    notifications = db.query(Notification).filter(
        Notification.organization_id == test_organization.id
    ).all()
    assert len(notifications) == 0

    db.refresh(rule)
    assert rule.execution_count == 1
    assert rule.last_executed_at is not None


# ---------------------------------------------------------------------------
# 6. Regression — existing trigger types still resolve (health_score_threshold)
# ---------------------------------------------------------------------------

def test_health_score_threshold_active_rule_still_fires(
    db: Session, test_organization: Organization
):
    """Light regression: an active health_score_threshold rule still fires
    and runs its actions end-to-end through evaluate()."""
    from src.services.automation_engine import AutomationEngine

    rule = _make_rule(
        db, test_organization.id,
        trigger_type="health_score_threshold",
        trigger_config={"threshold": 30, "direction": "below"},
        actions=[{"type": "change_status", "config": {"status": "in_review"}}],
        mode="active",
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
            results = engine.evaluate(
                test_organization.id, "health_score_threshold", context
            )

    assert len(results) == 1
    assert results[0]["status"] == "success"
