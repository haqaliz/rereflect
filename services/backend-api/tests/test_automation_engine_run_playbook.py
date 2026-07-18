"""
TDD tests for AutomationEngine — run_playbook action (churn-triggered-playbooks, task 3).

An `active` automation rule can auto-run a designated churn playbook by
reusing the EXISTING playbook execution pipeline: create a
ChurnPlaybookExecution row + enqueue the existing Celery task
("tasks.churn_playbooks.run_playbook").

Run:
    cd services/backend-api && source venv/bin/activate
    pytest tests/test_automation_engine_run_playbook.py -v
"""

from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from src.models.automation_rule import AutomationRule
from src.models.automation_execution import AutomationExecution
from src.models.churn_playbook import ChurnPlaybook, ChurnPlaybookExecution
from src.models.organization import Organization


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_rule(
    db: Session,
    org_id: int,
    actions: list,
    mode: str = "active",
    trigger_type: str = "churn_probability_threshold",
    trigger_config: dict | None = None,
    cooldown_hours: int = 24,
    name: str = "Run Playbook Rule",
) -> AutomationRule:
    rule = AutomationRule(
        organization_id=org_id,
        name=name,
        trigger_type=trigger_type,
        trigger_config=trigger_config or {"threshold": 0.7},
        actions=actions,
        mode=mode,
        cooldown_hours=cooldown_hours,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


def _make_playbook(
    db: Session,
    org_id: int | None,
    *,
    is_active: bool = True,
    name: str = "Test Playbook",
) -> ChurnPlaybook:
    playbook = ChurnPlaybook(
        organization_id=org_id,
        name=name,
        description="A test playbook",
        probability_min=Decimal("0.50"),
        probability_max=Decimal("1.00"),
        action_sequence=[{"type": "send_notification", "config": {}}],
        is_template=org_id is None,
        is_active=is_active,
    )
    db.add(playbook)
    db.commit()
    db.refresh(playbook)
    return playbook


def _other_organization(db: Session) -> Organization:
    org = Organization(name="Other Company", plan="pro")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


# ---------------------------------------------------------------------------
# 1. Active rule with run_playbook action fires end-to-end
# ---------------------------------------------------------------------------

@patch("src.background.celery_client.get_celery_app")
def test_run_playbook_action_creates_execution_and_dispatches(
    mock_get_celery_app, db: Session, test_organization: Organization
):
    from src.services.automation_engine import AutomationEngine

    mock_app = MagicMock()
    mock_get_celery_app.return_value = mock_app

    playbook = _make_playbook(db, test_organization.id)
    rule = _make_rule(
        db, test_organization.id,
        actions=[{"type": "run_playbook", "config": {"playbook_id": playbook.id}}],
    )
    context = {"churn_probability": 0.9, "customer_email": "c@x.com"}

    engine = AutomationEngine(db)
    with patch.object(engine, "_check_cooldown", return_value=False):
        with patch.object(engine, "_set_cooldown"):
            results = engine.evaluate(
                test_organization.id, "churn_probability_threshold", context
            )

    assert len(results) == 1
    assert results[0]["status"] == "success"
    action_result = results[0]["actions"][0]
    assert action_result["type"] == "run_playbook"
    assert action_result["error"] is None

    executions = db.query(ChurnPlaybookExecution).all()
    assert len(executions) == 1
    execution = executions[0]
    assert execution.playbook_id == playbook.id
    assert execution.organization_id == test_organization.id
    assert execution.customer_email == "c@x.com"
    assert execution.triggered_by == "auto_probability"
    assert execution.triggered_by_user_id is None
    assert execution.status == "queued"

    assert action_result["result"] == {
        "execution_id": execution.id,
        "playbook_id": playbook.id,
    }

    mock_app.send_task.assert_called_once_with(
        "tasks.churn_playbooks.run_playbook", args=[execution.id]
    )


# ---------------------------------------------------------------------------
# 2. Missing playbook_id → error, no execution row, no dispatch
# ---------------------------------------------------------------------------

@patch("src.background.celery_client.get_celery_app")
def test_run_playbook_missing_playbook_id_errors_without_side_effects(
    mock_get_celery_app, db: Session, test_organization: Organization
):
    from src.services.automation_engine import AutomationEngine

    mock_app = MagicMock()
    mock_get_celery_app.return_value = mock_app

    rule = _make_rule(
        db, test_organization.id,
        actions=[{"type": "run_playbook", "config": {}}],
    )
    context = {"churn_probability": 0.9, "customer_email": "c@x.com"}

    engine = AutomationEngine(db)
    with patch.object(engine, "_check_cooldown", return_value=False):
        with patch.object(engine, "_set_cooldown"):
            results = engine.evaluate(
                test_organization.id, "churn_probability_threshold", context
            )

    assert len(results) == 1
    action_result = results[0]["actions"][0]
    assert action_result["error"] == "missing playbook_id"
    assert action_result["result"] is None

    assert db.query(ChurnPlaybookExecution).count() == 0
    mock_app.send_task.assert_not_called()


# ---------------------------------------------------------------------------
# 3. No customer_email in context → error, no execution row
# ---------------------------------------------------------------------------

@patch("src.background.celery_client.get_celery_app")
def test_run_playbook_no_customer_email_errors_without_execution_row(
    mock_get_celery_app, db: Session, test_organization: Organization
):
    from src.services.automation_engine import AutomationEngine

    mock_app = MagicMock()
    mock_get_celery_app.return_value = mock_app

    playbook = _make_playbook(db, test_organization.id)
    rule = _make_rule(
        db, test_organization.id,
        actions=[{"type": "run_playbook", "config": {"playbook_id": playbook.id}}],
    )
    # Directly exercise the action handler with an empty customer_email context,
    # bypassing trigger/cooldown machinery which is covered elsewhere.
    engine = AutomationEngine(db)
    result = engine._execute_run_playbook(
        {"playbook_id": playbook.id}, {"customer_email": ""}, rule
    )

    assert result["error"] == "no customer_email in context"
    assert result["result"] is None
    assert db.query(ChurnPlaybookExecution).count() == 0
    mock_app.send_task.assert_not_called()


# ---------------------------------------------------------------------------
# 4. Playbook belonging to another org → error, no execution row
# ---------------------------------------------------------------------------

@patch("src.background.celery_client.get_celery_app")
def test_run_playbook_wrong_org_errors_without_execution_row(
    mock_get_celery_app, db: Session, test_organization: Organization
):
    from src.services.automation_engine import AutomationEngine

    mock_app = MagicMock()
    mock_get_celery_app.return_value = mock_app

    other_org = _other_organization(db)
    playbook = _make_playbook(db, other_org.id)
    rule = _make_rule(
        db, test_organization.id,
        actions=[{"type": "run_playbook", "config": {"playbook_id": playbook.id}}],
    )
    context = {"churn_probability": 0.9, "customer_email": "c@x.com"}

    engine = AutomationEngine(db)
    with patch.object(engine, "_check_cooldown", return_value=False):
        with patch.object(engine, "_set_cooldown"):
            results = engine.evaluate(
                test_organization.id, "churn_probability_threshold", context
            )

    action_result = results[0]["actions"][0]
    assert action_result["error"] == "playbook not found / inactive / wrong org"
    assert action_result["result"] is None
    assert db.query(ChurnPlaybookExecution).count() == 0
    mock_app.send_task.assert_not_called()


# ---------------------------------------------------------------------------
# 5. Inactive playbook → error, no execution row
# ---------------------------------------------------------------------------

@patch("src.background.celery_client.get_celery_app")
def test_run_playbook_inactive_errors_without_execution_row(
    mock_get_celery_app, db: Session, test_organization: Organization
):
    from src.services.automation_engine import AutomationEngine

    mock_app = MagicMock()
    mock_get_celery_app.return_value = mock_app

    playbook = _make_playbook(db, test_organization.id, is_active=False)
    rule = _make_rule(
        db, test_organization.id,
        actions=[{"type": "run_playbook", "config": {"playbook_id": playbook.id}}],
    )
    context = {"churn_probability": 0.9, "customer_email": "c@x.com"}

    engine = AutomationEngine(db)
    with patch.object(engine, "_check_cooldown", return_value=False):
        with patch.object(engine, "_set_cooldown"):
            results = engine.evaluate(
                test_organization.id, "churn_probability_threshold", context
            )

    action_result = results[0]["actions"][0]
    assert action_result["error"] == "playbook not found / inactive / wrong org"
    assert action_result["result"] is None
    assert db.query(ChurnPlaybookExecution).count() == 0
    mock_app.send_task.assert_not_called()


# ---------------------------------------------------------------------------
# 6. System-template playbook (organization_id IS NULL) → allowed
# ---------------------------------------------------------------------------

@patch("src.background.celery_client.get_celery_app")
def test_run_playbook_system_template_allowed(
    mock_get_celery_app, db: Session, test_organization: Organization
):
    from src.services.automation_engine import AutomationEngine

    mock_app = MagicMock()
    mock_get_celery_app.return_value = mock_app

    playbook = _make_playbook(db, None, name="System Template")
    rule = _make_rule(
        db, test_organization.id,
        actions=[{"type": "run_playbook", "config": {"playbook_id": playbook.id}}],
    )
    context = {"churn_probability": 0.9, "customer_email": "c@x.com"}

    engine = AutomationEngine(db)
    with patch.object(engine, "_check_cooldown", return_value=False):
        with patch.object(engine, "_set_cooldown"):
            results = engine.evaluate(
                test_organization.id, "churn_probability_threshold", context
            )

    action_result = results[0]["actions"][0]
    assert action_result["error"] is None

    executions = db.query(ChurnPlaybookExecution).all()
    assert len(executions) == 1
    assert executions[0].playbook_id == playbook.id
    assert executions[0].organization_id == test_organization.id
    mock_app.send_task.assert_called_once()


# ---------------------------------------------------------------------------
# 7. Shadow-mode rule with run_playbook action → no execution row, no dispatch
# ---------------------------------------------------------------------------

@patch("src.background.celery_client.get_celery_app")
def test_run_playbook_shadow_mode_no_execution_row(
    mock_get_celery_app, db: Session, test_organization: Organization
):
    from src.services.automation_engine import AutomationEngine

    mock_app = MagicMock()
    mock_get_celery_app.return_value = mock_app

    playbook = _make_playbook(db, test_organization.id)
    rule = _make_rule(
        db, test_organization.id,
        actions=[{"type": "run_playbook", "config": {"playbook_id": playbook.id}}],
        mode="shadow",
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

    assert db.query(ChurnPlaybookExecution).count() == 0
    mock_app.send_task.assert_not_called()

    execution = db.query(AutomationExecution).filter(
        AutomationExecution.rule_id == rule.id
    ).first()
    assert execution is not None
    assert execution.status == "shadow"
