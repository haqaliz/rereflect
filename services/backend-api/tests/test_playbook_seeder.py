"""
Tests for playbook_seeder.py (M4.1 Phase 5.1) — strict TDD.
"""

from __future__ import annotations

import logging

import pytest
from sqlalchemy.orm import Session

from src.models.churn_playbook import ChurnPlaybook
from src.models.organization import Organization
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


# ---------------------------------------------------------------------------
# 38. AC2 — New-Customer Save's trigger_automation names a real automation
# ---------------------------------------------------------------------------

def test_seed_data_new_customer_save_trigger_automation_names_at_risk_outreach():
    tmpl = next(t for t in SEED_TEMPLATES if t["name"] == "New-Customer Save")
    trigger = next(a for a in tmpl["action_sequence"] if a["type"] == "trigger_automation")
    assert trigger["config"] == {"automation_name": "At-Risk Customer Outreach"}


def test_seeder_new_customer_save_trigger_automation_targets_at_risk_outreach(db: Session):
    seed_playbook_templates(db)
    tmpl = db.query(ChurnPlaybook).filter(
        ChurnPlaybook.name == "New-Customer Save",
        ChurnPlaybook.is_template.is_(True),
    ).first()
    assert tmpl is not None
    trigger = next(a for a in tmpl.action_sequence if a["type"] == "trigger_automation")
    assert trigger["config"] == {"automation_name": "At-Risk Customer Outreach"}


# ---------------------------------------------------------------------------
# 39. AC1 — pristine-row convergence (cloned/org rows untouched, idempotent)
# ---------------------------------------------------------------------------

# The pre-convergence action_sequence stored by older installs.
OLD_NEW_CUSTOMER_SAVE_ACTION_SEQUENCE = [
    {"type": "trigger_automation", "config": {"automation_name": "onboarding_playbook"}},
    {"type": "assign", "config": {"role": "cs_lead", "strategy": "round_robin"}},
    {"type": "draft_response", "config": {"tone": "friendly", "template_hint": "welcome_and_save"}},
]


def _seed_data_for(name: str):
    return next(t for t in SEED_TEMPLATES if t["name"] == name)


def test_seeder_converges_pristine_row_and_skips_cloned_and_org_owned_rows(
    db: Session, test_organization: Organization
):
    pristine = ChurnPlaybook(
        organization_id=None,
        name="New-Customer Save",
        description="stale pre-convergence description",
        probability_min=0.40,
        probability_max=1.00,
        action_sequence=OLD_NEW_CUSTOMER_SAVE_ACTION_SEQUENCE,
        is_template=True,
        is_active=True,
    )
    db.add(pristine)
    db.commit()
    db.refresh(pristine)

    cloned_sequence = [
        {"type": "send_email", "config": {"template": "custom", "recipient": "customer"}},
    ]
    cloned = ChurnPlaybook(
        organization_id=None,
        name="Critical Save",
        description="operator clone with a custom sequence",
        probability_min=0.85,
        probability_max=1.00,
        action_sequence=cloned_sequence,
        is_template=True,
        is_active=True,
        source_template_id=pristine.id,
    )

    org_sequence = [
        {"type": "notify", "config": {"channel": "dashboard", "message": "org custom"}},
    ]
    org_owned = ChurnPlaybook(
        organization_id=test_organization.id,
        name="Churn Prevention",
        description="org-owned playbook reusing a template name",
        probability_min=0.70,
        probability_max=0.85,
        action_sequence=org_sequence,
        is_template=True,
        is_active=True,
    )
    db.add_all([cloned, org_owned])
    db.commit()

    seed_playbook_templates(db)

    converged = db.query(ChurnPlaybook).filter(ChurnPlaybook.id == pristine.id).first()
    seed_data = _seed_data_for("New-Customer Save")
    assert converged.action_sequence == seed_data["action_sequence"]
    assert converged.description == seed_data["description"]

    untouched_clone = db.query(ChurnPlaybook).filter(ChurnPlaybook.id == cloned.id).first()
    assert untouched_clone.action_sequence == cloned_sequence
    assert untouched_clone.description == "operator clone with a custom sequence"

    untouched_org = db.query(ChurnPlaybook).filter(ChurnPlaybook.id == org_owned.id).first()
    assert untouched_org.action_sequence == org_sequence
    assert untouched_org.description == "org-owned playbook reusing a template name"


def test_seeder_second_run_performs_no_updates(
    db: Session, caplog: pytest.LogCaptureFixture
):
    seed_playbook_templates(db)

    tmpl = db.query(ChurnPlaybook).filter(
        ChurnPlaybook.name == "New-Customer Save",
        ChurnPlaybook.is_template.is_(True),
    ).first()
    tmpl.action_sequence = OLD_NEW_CUSTOMER_SAVE_ACTION_SEQUENCE
    db.commit()

    def snapshot():
        rows = db.query(ChurnPlaybook).filter(ChurnPlaybook.is_template.is_(True)).all()
        return {r.name: (r.action_sequence, r.description) for r in rows}

    with caplog.at_level(logging.INFO, logger="src.services.playbook_seeder"):
        seed_playbook_templates(db)
    assert "updated 1 system template" in caplog.text

    after_first = snapshot()

    caplog.clear()
    with caplog.at_level(logging.INFO, logger="src.services.playbook_seeder"):
        seed_playbook_templates(db)
    assert "updated" not in caplog.text
    assert snapshot() == after_first
