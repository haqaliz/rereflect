"""
Tests for AutomationRule.mode (off | shadow | active) — execution-state field.

`mode` is the single source of truth for evaluation. `is_active` is kept as a
derived, write-through alias so existing callers keep working.
"""

import pytest
from sqlalchemy.orm import Session

from src.models.automation_rule import AutomationRule
from src.models.organization import Organization


def _make_rule(db: Session, org: Organization, **overrides) -> AutomationRule:
    defaults = dict(
        organization_id=org.id,
        name="Test Rule",
        trigger_type="health_score_threshold",
        trigger_config={"threshold": 50},
        actions=[{"type": "notify", "config": {}}],
    )
    defaults.update(overrides)
    return AutomationRule(**defaults)


def test_default_mode_is_active_and_is_active_true(db: Session, test_organization: Organization):
    rule = _make_rule(db, test_organization)
    db.add(rule)
    db.commit()
    db.refresh(rule)

    assert rule.mode == "active"
    assert rule.is_active is True


def test_setting_mode_off_sets_is_active_false(db: Session, test_organization: Organization):
    rule = _make_rule(db, test_organization)
    db.add(rule)
    db.commit()
    db.refresh(rule)

    rule.mode = "off"
    db.commit()
    db.refresh(rule)

    assert rule.mode == "off"
    assert rule.is_active is False


def test_setting_mode_shadow_sets_is_active_true(db: Session, test_organization: Organization):
    rule = _make_rule(db, test_organization)
    db.add(rule)
    db.commit()
    db.refresh(rule)

    rule.mode = "shadow"
    db.commit()
    db.refresh(rule)

    assert rule.mode == "shadow"
    assert rule.is_active is True


def test_setting_mode_active_sets_is_active_true(db: Session, test_organization: Organization):
    rule = _make_rule(db, test_organization, mode="off")
    db.add(rule)
    db.commit()
    db.refresh(rule)

    rule.mode = "active"
    db.commit()
    db.refresh(rule)

    assert rule.mode == "active"
    assert rule.is_active is True


def test_setting_is_active_false_sets_mode_off(db: Session, test_organization: Organization):
    rule = _make_rule(db, test_organization)
    db.add(rule)
    db.commit()
    db.refresh(rule)

    rule.is_active = False
    db.commit()
    db.refresh(rule)

    assert rule.mode == "off"
    assert rule.is_active is False


def test_setting_is_active_true_from_off_sets_mode_active(db: Session, test_organization: Organization):
    rule = _make_rule(db, test_organization, mode="off")
    db.add(rule)
    db.commit()
    db.refresh(rule)

    rule.is_active = True
    db.commit()
    db.refresh(rule)

    assert rule.mode == "active"
    assert rule.is_active is True


def test_setting_is_active_true_when_shadow_leaves_mode_shadow(db: Session, test_organization: Organization):
    rule = _make_rule(db, test_organization, mode="shadow")
    db.add(rule)
    db.commit()
    db.refresh(rule)

    rule.is_active = True
    db.commit()
    db.refresh(rule)

    assert rule.mode == "shadow"
    assert rule.is_active is True


def test_invalid_mode_raises_value_error(db: Session, test_organization: Organization):
    rule = _make_rule(db, test_organization)
    db.add(rule)
    db.commit()
    db.refresh(rule)

    with pytest.raises(ValueError):
        rule.mode = "paused"


def test_invalid_mode_on_construction_raises_value_error(db: Session, test_organization: Organization):
    with pytest.raises(ValueError):
        _make_rule(db, test_organization, mode="paused")


def test_mode_round_trips_through_db(db: Session, test_organization: Organization):
    rule = _make_rule(db, test_organization, mode="shadow")
    db.add(rule)
    db.commit()
    db.refresh(rule)

    rule_id = rule.id

    fetched = db.query(AutomationRule).filter(AutomationRule.id == rule_id).one()
    assert fetched.mode == "shadow"
    assert fetched.is_active is True
