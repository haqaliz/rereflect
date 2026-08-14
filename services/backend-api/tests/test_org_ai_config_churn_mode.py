"""
TDD tests for per-org-churn-model (churn-predict-seam-resolver, data layer) —
OrgAIConfig.churn_classifier_mode + churn_autopromote_hold.

churn_classifier_mode: 'off' | 'shadow' | 'auto'. Independent of
classifier_mode (sentiment), category_classifier_mode and
urgency_classifier_mode. Field-substituted mirror of
test_org_ai_config_urgency_classifier_mode.py exactly (urgency -> churn).

churn_autopromote_hold: Boolean, default False — per-type "pause
auto-promotion" hold for the churn classifier head, mirroring
urgency_autopromote_hold.
"""

from sqlalchemy.orm import Session

from src.models.org_ai_config import OrgAIConfig
from src.models.organization import Organization


def test_has_churn_classifier_mode_attr():
    assert hasattr(OrgAIConfig(), "churn_classifier_mode")


def test_has_churn_autopromote_hold_attr():
    assert hasattr(OrgAIConfig(), "churn_autopromote_hold")


def test_default_off_orm_insert(db: Session, test_organization: Organization):
    config = OrgAIConfig(organization_id=test_organization.id)
    db.add(config)
    db.commit()
    db.refresh(config)

    assert config.churn_classifier_mode == "off"


def test_default_false_autopromote_hold_orm_insert(db: Session, test_organization: Organization):
    config = OrgAIConfig(organization_id=test_organization.id)
    db.add(config)
    db.commit()
    db.refresh(config)

    assert config.churn_autopromote_hold is False


def test_getattr_fallback_off():
    class _LegacyConfigStub:
        """Stand-in for a pre-migration row with no churn_classifier_mode attribute."""

    legacy = _LegacyConfigStub()
    assert getattr(legacy, "churn_classifier_mode", "off") == "off"


def test_can_set_shadow_auto(db: Session, test_organization: Organization):
    config = OrgAIConfig(organization_id=test_organization.id, churn_classifier_mode="shadow")
    db.add(config)
    db.commit()
    db.refresh(config)
    assert config.churn_classifier_mode == "shadow"

    config.churn_classifier_mode = "auto"
    db.commit()
    db.refresh(config)
    assert config.churn_classifier_mode == "auto"


def test_can_set_autopromote_hold(db: Session, test_organization: Organization):
    config = OrgAIConfig(organization_id=test_organization.id, churn_autopromote_hold=True)
    db.add(config)
    db.commit()
    db.refresh(config)
    assert config.churn_autopromote_hold is True


def test_churn_mode_independent_of_sentiment_category_urgency(db: Session, test_organization: Organization):
    """Setting one field never mutates the others — independent-control principle (PRD Goals)."""
    config = OrgAIConfig(
        organization_id=test_organization.id,
        classifier_mode="auto",
        category_classifier_mode="shadow",
        urgency_classifier_mode="auto",
        churn_classifier_mode="off",
    )
    db.add(config)
    db.commit()
    db.refresh(config)

    assert config.classifier_mode == "auto"
    assert config.category_classifier_mode == "shadow"
    assert config.urgency_classifier_mode == "auto"
    assert config.churn_classifier_mode == "off"

    config.churn_classifier_mode = "shadow"
    db.commit()
    db.refresh(config)

    assert config.classifier_mode == "auto", "classifier_mode must not change when churn_classifier_mode is set"
    assert config.category_classifier_mode == "shadow", "category_classifier_mode must not change when churn_classifier_mode is set"
    assert config.urgency_classifier_mode == "auto", "urgency_classifier_mode must not change when churn_classifier_mode is set"
    assert config.churn_classifier_mode == "shadow"
