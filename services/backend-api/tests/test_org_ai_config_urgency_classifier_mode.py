"""
TDD tests for per-org-urgency-classifier (urgency-classifier-head,
data-and-config aspect) — OrgAIConfig.urgency_classifier_mode.

'off' | 'shadow' | 'auto'. Independent of `classifier_mode` (sentiment) and
`category_classifier_mode`. Field-substituted mirror of
test_org_ai_config_category_classifier_mode.py exactly (category -> urgency).
"""

from sqlalchemy.orm import Session

from src.models.org_ai_config import OrgAIConfig
from src.models.organization import Organization


def test_has_urgency_classifier_mode_attr():
    assert hasattr(OrgAIConfig(), "urgency_classifier_mode")


def test_default_off_orm_insert(db: Session, test_organization: Organization):
    config = OrgAIConfig(organization_id=test_organization.id)
    db.add(config)
    db.commit()
    db.refresh(config)

    assert config.urgency_classifier_mode == "off"


def test_getattr_fallback_off():
    class _LegacyConfigStub:
        """Stand-in for a pre-migration row with no urgency_classifier_mode attribute."""

    legacy = _LegacyConfigStub()
    assert getattr(legacy, "urgency_classifier_mode", "off") == "off"


def test_can_set_shadow_auto(db: Session, test_organization: Organization):
    config = OrgAIConfig(organization_id=test_organization.id, urgency_classifier_mode="shadow")
    db.add(config)
    db.commit()
    db.refresh(config)
    assert config.urgency_classifier_mode == "shadow"

    config.urgency_classifier_mode = "auto"
    db.commit()
    db.refresh(config)
    assert config.urgency_classifier_mode == "auto"


def test_urgency_mode_independent_of_sentiment_and_category_classifier_mode(
    db: Session, test_organization: Organization
):
    """Setting one field never mutates the others — independent-control principle (PRD Goals)."""
    config = OrgAIConfig(
        organization_id=test_organization.id,
        classifier_mode="auto",
        category_classifier_mode="shadow",
        urgency_classifier_mode="off",
    )
    db.add(config)
    db.commit()
    db.refresh(config)

    assert config.classifier_mode == "auto"
    assert config.category_classifier_mode == "shadow"
    assert config.urgency_classifier_mode == "off"

    config.urgency_classifier_mode = "shadow"
    db.commit()
    db.refresh(config)

    assert config.classifier_mode == "auto", "classifier_mode must not change when urgency_classifier_mode is set"
    assert config.category_classifier_mode == "shadow", "category_classifier_mode must not change when urgency_classifier_mode is set"
    assert config.urgency_classifier_mode == "shadow"
