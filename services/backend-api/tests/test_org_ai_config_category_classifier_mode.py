"""
TDD tests for per-org-category-classifier (M5.2 v2) — OrgAIConfig.category_classifier_mode.

'off' | 'shadow' | 'auto'. NULL/unrecognized will be treated as 'off' by the
predict-seam aspect's per-type resolve_classifier branch (out of scope here) —
this file locks the contract at the data layer only, mirroring
test_org_ai_config_classifier_mode.py exactly (sentiment -> category).
"""

from sqlalchemy.orm import Session

from src.models.org_ai_config import OrgAIConfig
from src.models.organization import Organization


def test_has_category_classifier_mode_attr():
    assert hasattr(OrgAIConfig(), "category_classifier_mode")


def test_default_off_orm_insert(db: Session, test_organization: Organization):
    config = OrgAIConfig(organization_id=test_organization.id)
    db.add(config)
    db.commit()
    db.refresh(config)

    assert config.category_classifier_mode == "off"


def test_getattr_fallback_off():
    class _LegacyConfigStub:
        """Stand-in for a pre-migration row with no category_classifier_mode attribute."""

    legacy = _LegacyConfigStub()
    assert getattr(legacy, "category_classifier_mode", "off") == "off"


def test_can_set_shadow_auto(db: Session, test_organization: Organization):
    config = OrgAIConfig(organization_id=test_organization.id, category_classifier_mode="shadow")
    db.add(config)
    db.commit()
    db.refresh(config)
    assert config.category_classifier_mode == "shadow"

    config.category_classifier_mode = "auto"
    db.commit()
    db.refresh(config)
    assert config.category_classifier_mode == "auto"


def test_category_mode_independent_of_sentiment_classifier_mode(db: Session, test_organization: Organization):
    """Setting one field never mutates the other — independent-control principle (PRD Goals)."""
    config = OrgAIConfig(
        organization_id=test_organization.id,
        classifier_mode="auto",
        category_classifier_mode="off",
    )
    db.add(config)
    db.commit()
    db.refresh(config)

    assert config.classifier_mode == "auto"
    assert config.category_classifier_mode == "off"

    config.category_classifier_mode = "shadow"
    db.commit()
    db.refresh(config)

    assert config.classifier_mode == "auto", "classifier_mode must not change when category_classifier_mode is set"
    assert config.category_classifier_mode == "shadow"
