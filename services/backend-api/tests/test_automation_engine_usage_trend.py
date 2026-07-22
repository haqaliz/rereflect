"""
TDD tests for AutomationEngine — usage_trend trigger (trigger-registration,
Phase 2) — strict TDD (RED first).

Edge-triggered semantics: fire only on a strictly-worsening transition
(stable(0) < declining(1) < sharp_decline(2)) into a state configured in
cfg["states"]. insufficient_history has no rank and never fires, in either
direction (PRD M2 / E3 warm-up guard).

Run:
    cd services/backend-api && ./venv/bin/pytest tests/test_automation_engine_usage_trend.py -v
"""

from sqlalchemy.orm import Session

from src.models.automation_rule import AutomationRule
from src.models.organization import Organization


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_rule(
    db: Session,
    org_id: int,
    trigger_config: dict,
    mode: str = "active",
) -> AutomationRule:
    rule = AutomationRule(
        organization_id=org_id,
        name="Usage Trend Rule",
        trigger_type="usage_trend",
        trigger_config=trigger_config,
        actions=[],
        mode=mode,
        cooldown_hours=24,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


# ---------------------------------------------------------------------------
# AC1 — firing transitions when the target state is configured
# ---------------------------------------------------------------------------

def test_stable_to_declining_fires_when_declining_configured(
    db: Session, test_organization: Organization
):
    from src.services.automation_engine import AutomationEngine

    rule = _make_rule(
        db, test_organization.id,
        trigger_config={"states": ["declining", "sharp_decline"]},
    )
    engine = AutomationEngine(db)
    context = {
        "old_trend_state": "stable",
        "new_trend_state": "declining",
        "customer_email": "c@x.com",
    }
    assert engine._check_trigger(rule, context) is True


def test_stable_to_sharp_decline_fires_when_sharp_decline_configured(
    db: Session, test_organization: Organization
):
    from src.services.automation_engine import AutomationEngine

    rule = _make_rule(
        db, test_organization.id,
        trigger_config={"states": ["declining", "sharp_decline"]},
    )
    engine = AutomationEngine(db)
    context = {
        "old_trend_state": "stable",
        "new_trend_state": "sharp_decline",
        "customer_email": "c@x.com",
    }
    assert engine._check_trigger(rule, context) is True


def test_declining_to_sharp_decline_fires_when_sharp_decline_configured(
    db: Session, test_organization: Organization
):
    from src.services.automation_engine import AutomationEngine

    rule = _make_rule(
        db, test_organization.id,
        trigger_config={"states": ["sharp_decline"]},
    )
    engine = AutomationEngine(db)
    context = {
        "old_trend_state": "declining",
        "new_trend_state": "sharp_decline",
        "customer_email": "c@x.com",
    }
    assert engine._check_trigger(rule, context) is True


# ---------------------------------------------------------------------------
# AC2 — same-state transition does not fire
# ---------------------------------------------------------------------------

def test_declining_to_declining_does_not_fire(
    db: Session, test_organization: Organization
):
    from src.services.automation_engine import AutomationEngine

    rule = _make_rule(
        db, test_organization.id,
        trigger_config={"states": ["declining", "sharp_decline"]},
    )
    engine = AutomationEngine(db)
    context = {
        "old_trend_state": "declining",
        "new_trend_state": "declining",
        "customer_email": "c@x.com",
    }
    assert engine._check_trigger(rule, context) is False


# ---------------------------------------------------------------------------
# AC3 — insufficient_history in either direction never fires. This includes
# the specific warm-up guard case insufficient_history -> sharp_decline.
# ---------------------------------------------------------------------------

def test_insufficient_history_to_sharp_decline_does_not_fire_warmup_guard(
    db: Session, test_organization: Organization
):
    """Warm-up guard (PRD E3): a customer's baseline classification landing
    directly on sharp_decline must NOT fire the trigger."""
    from src.services.automation_engine import AutomationEngine

    rule = _make_rule(
        db, test_organization.id,
        trigger_config={"states": ["declining", "sharp_decline"]},
    )
    engine = AutomationEngine(db)
    context = {
        "old_trend_state": "insufficient_history",
        "new_trend_state": "sharp_decline",
        "customer_email": "c@x.com",
    }
    assert engine._check_trigger(rule, context) is False


def test_stable_to_insufficient_history_does_not_fire(
    db: Session, test_organization: Organization
):
    from src.services.automation_engine import AutomationEngine

    rule = _make_rule(
        db, test_organization.id,
        trigger_config={"states": ["declining", "sharp_decline"]},
    )
    engine = AutomationEngine(db)
    context = {
        "old_trend_state": "stable",
        "new_trend_state": "insufficient_history",
        "customer_email": "c@x.com",
    }
    assert engine._check_trigger(rule, context) is False


# ---------------------------------------------------------------------------
# AC4 — improvements never fire
# ---------------------------------------------------------------------------

def test_sharp_decline_to_declining_does_not_fire(
    db: Session, test_organization: Organization
):
    from src.services.automation_engine import AutomationEngine

    rule = _make_rule(
        db, test_organization.id,
        trigger_config={"states": ["declining", "sharp_decline"]},
    )
    engine = AutomationEngine(db)
    context = {
        "old_trend_state": "sharp_decline",
        "new_trend_state": "declining",
        "customer_email": "c@x.com",
    }
    assert engine._check_trigger(rule, context) is False


def test_declining_to_stable_does_not_fire(
    db: Session, test_organization: Organization
):
    from src.services.automation_engine import AutomationEngine

    rule = _make_rule(
        db, test_organization.id,
        trigger_config={"states": ["declining", "sharp_decline"]},
    )
    engine = AutomationEngine(db)
    context = {
        "old_trend_state": "declining",
        "new_trend_state": "stable",
        "customer_email": "c@x.com",
    }
    assert engine._check_trigger(rule, context) is False


# ---------------------------------------------------------------------------
# AC5 — missing / None old or new state never fires, never raises
# ---------------------------------------------------------------------------

def test_missing_old_trend_state_does_not_fire(
    db: Session, test_organization: Organization
):
    from src.services.automation_engine import AutomationEngine

    rule = _make_rule(
        db, test_organization.id,
        trigger_config={"states": ["declining", "sharp_decline"]},
    )
    engine = AutomationEngine(db)
    context = {"new_trend_state": "sharp_decline", "customer_email": "c@x.com"}
    assert engine._check_trigger(rule, context) is False


def test_missing_new_trend_state_does_not_fire(
    db: Session, test_organization: Organization
):
    from src.services.automation_engine import AutomationEngine

    rule = _make_rule(
        db, test_organization.id,
        trigger_config={"states": ["declining", "sharp_decline"]},
    )
    engine = AutomationEngine(db)
    context = {"old_trend_state": "stable", "customer_email": "c@x.com"}
    assert engine._check_trigger(rule, context) is False


def test_none_old_and_new_trend_state_does_not_fire(
    db: Session, test_organization: Organization
):
    from src.services.automation_engine import AutomationEngine

    rule = _make_rule(
        db, test_organization.id,
        trigger_config={"states": ["declining", "sharp_decline"]},
    )
    engine = AutomationEngine(db)
    context = {
        "old_trend_state": None,
        "new_trend_state": None,
        "customer_email": "c@x.com",
    }
    assert engine._check_trigger(rule, context) is False


# ---------------------------------------------------------------------------
# Worsening transition, but new_state not in cfg["states"] — must not fire
# ---------------------------------------------------------------------------

def test_worsening_transition_not_in_configured_states_does_not_fire(
    db: Session, test_organization: Organization
):
    """stable -> declining is strictly worsening, but the rule is only
    configured for sharp_decline — must not fire."""
    from src.services.automation_engine import AutomationEngine

    rule = _make_rule(
        db, test_organization.id,
        trigger_config={"states": ["sharp_decline"]},
    )
    engine = AutomationEngine(db)
    context = {
        "old_trend_state": "stable",
        "new_trend_state": "declining",
        "customer_email": "c@x.com",
    }
    assert engine._check_trigger(rule, context) is False


# ---------------------------------------------------------------------------
# AC7 — other trigger types unaffected (regression smoke check)
# ---------------------------------------------------------------------------

def test_churn_probability_threshold_still_dispatches(
    db: Session, test_organization: Organization
):
    from src.services.automation_engine import AutomationEngine

    rule = AutomationRule(
        organization_id=test_organization.id,
        name="Churn Rule",
        trigger_type="churn_probability_threshold",
        trigger_config={"threshold": 0.7},
        actions=[],
        mode="active",
        cooldown_hours=24,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)

    engine = AutomationEngine(db)
    context = {"churn_probability": 0.9, "customer_email": "c@x.com"}
    assert engine._check_trigger(rule, context) is True
