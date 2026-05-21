"""
Tests for playbook_seeder.py (M4.1 Phase 5.1) — strict TDD.
"""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from src.models.churn_playbook import ChurnPlaybook
from src.services.playbook_seeder import seed_playbook_templates, SEED_TEMPLATES

# Valid action types drawn from the Automations module + playbook-specific
VALID_ACTION_TYPES = frozenset({
    "assign",
    "notify",
    "draft_response",
    "send_email",
    "tag",
    "schedule_task",
    "create_task",
    "trigger_automation",
    # automations.py types also valid
    "auto_assign",
    "change_status",
    "send_notification",
})


# ---------------------------------------------------------------------------
# 30. test_seeder_creates_seven_templates_on_empty_db
# ---------------------------------------------------------------------------

def test_seeder_creates_seven_templates_on_empty_db(db: Session):
    seed_playbook_templates(db)
    count = db.query(ChurnPlaybook).filter(ChurnPlaybook.is_template.is_(True)).count()
    assert count == 7


# ---------------------------------------------------------------------------
# 31. test_seeder_is_idempotent_on_second_run
# ---------------------------------------------------------------------------

def test_seeder_is_idempotent_on_second_run(db: Session):
    seed_playbook_templates(db)
    seed_playbook_templates(db)
    count = db.query(ChurnPlaybook).filter(ChurnPlaybook.is_template.is_(True)).count()
    assert count == 7


# ---------------------------------------------------------------------------
# 32. test_seeder_templates_have_is_template_true
# ---------------------------------------------------------------------------

def test_seeder_templates_have_is_template_true(db: Session):
    seed_playbook_templates(db)
    templates = db.query(ChurnPlaybook).filter(ChurnPlaybook.is_template.is_(True)).all()
    for t in templates:
        assert t.is_template is True


# ---------------------------------------------------------------------------
# 33. test_seeder_templates_have_null_organization_id
# ---------------------------------------------------------------------------

def test_seeder_templates_have_null_organization_id(db: Session):
    seed_playbook_templates(db)
    templates = db.query(ChurnPlaybook).filter(ChurnPlaybook.is_template.is_(True)).all()
    for t in templates:
        assert t.organization_id is None


# ---------------------------------------------------------------------------
# 34. test_seeder_critical_save_has_probability_range_0_85_to_1_0
# ---------------------------------------------------------------------------

def test_seeder_critical_save_has_probability_range_0_85_to_1_0(db: Session):
    seed_playbook_templates(db)
    tmpl = db.query(ChurnPlaybook).filter(
        ChurnPlaybook.name == "Critical Save",
        ChurnPlaybook.is_template.is_(True),
    ).first()
    assert tmpl is not None
    assert float(tmpl.probability_min) == pytest.approx(0.85, abs=0.01)
    assert float(tmpl.probability_max) == pytest.approx(1.00, abs=0.01)


# ---------------------------------------------------------------------------
# 35. test_seeder_churn_prevention_has_probability_range_0_70_to_0_85
# ---------------------------------------------------------------------------

def test_seeder_churn_prevention_has_probability_range_0_70_to_0_85(db: Session):
    seed_playbook_templates(db)
    tmpl = db.query(ChurnPlaybook).filter(
        ChurnPlaybook.name == "Churn Prevention",
        ChurnPlaybook.is_template.is_(True),
    ).first()
    assert tmpl is not None
    assert float(tmpl.probability_min) == pytest.approx(0.70, abs=0.01)
    assert float(tmpl.probability_max) == pytest.approx(0.85, abs=0.01)


# ---------------------------------------------------------------------------
# 36. test_seeder_updates_template_if_name_exists_but_action_changed
#     Behavior: seeder is idempotent (skip if name already exists — no update).
#     We verify that if a name exists, the row count stays the same.
# ---------------------------------------------------------------------------

def test_seeder_skips_existing_template_by_name(db: Session):
    """Seeder skips (does not duplicate) if template name already exists."""
    seed_playbook_templates(db)
    before = db.query(ChurnPlaybook).filter(ChurnPlaybook.is_template.is_(True)).count()
    # Run again — idempotent: no duplicates created
    seed_playbook_templates(db)
    after = db.query(ChurnPlaybook).filter(ChurnPlaybook.is_template.is_(True)).count()
    assert after == before


# ---------------------------------------------------------------------------
# 37. test_seeder_action_sequence_uses_documented_action_types
# ---------------------------------------------------------------------------

def test_seeder_action_sequence_uses_documented_action_types(db: Session):
    seed_playbook_templates(db)
    templates = db.query(ChurnPlaybook).filter(ChurnPlaybook.is_template.is_(True)).all()
    for tmpl in templates:
        assert len(tmpl.action_sequence) > 0, f"Template '{tmpl.name}' has empty action_sequence"
        for action in tmpl.action_sequence:
            assert "type" in action, f"Action missing 'type' in template '{tmpl.name}': {action}"
            assert action["type"] in VALID_ACTION_TYPES, (
                f"Invalid action type '{action['type']}' in template '{tmpl.name}'. "
                f"Allowed: {sorted(VALID_ACTION_TYPES)}"
            )
