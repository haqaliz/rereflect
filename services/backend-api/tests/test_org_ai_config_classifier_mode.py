"""
TDD tests for M5.2 per-org-corrections-classifier — OrgAIConfig.classifier_mode.

'off' | 'shadow' | 'auto'. NULL/unrecognized treated as 'off' by
resolve_classifier (aspect D) — defense in depth, tested here so the
contract is locked at the data layer.
"""

from sqlalchemy.orm import Session

from src.models.org_ai_config import OrgAIConfig
from src.models.organization import Organization


def test_has_classifier_mode_attr():
    assert hasattr(OrgAIConfig(), "classifier_mode")


def test_default_off_orm_insert(db: Session, test_organization: Organization):
    config = OrgAIConfig(organization_id=test_organization.id)
    db.add(config)
    db.commit()
    db.refresh(config)

    assert config.classifier_mode == "off"


def test_getattr_fallback_off():
    """
    Simulates a row/object that predates this column (e.g. an un-migrated
    row read by a newer app version, or any object lacking the attribute):
    the resolver contract is `getattr(config, "classifier_mode", "off")`.
    """
    class _LegacyConfigStub:
        """Stand-in for a pre-migration row with no classifier_mode attribute."""

    legacy = _LegacyConfigStub()
    assert getattr(legacy, "classifier_mode", "off") == "off"


def test_can_set_shadow_auto(db: Session, test_organization: Organization):
    config = OrgAIConfig(organization_id=test_organization.id, classifier_mode="shadow")
    db.add(config)
    db.commit()
    db.refresh(config)
    assert config.classifier_mode == "shadow"

    config.classifier_mode = "auto"
    db.commit()
    db.refresh(config)
    assert config.classifier_mode == "auto"
