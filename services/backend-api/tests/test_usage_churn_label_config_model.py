"""
TDD tests for usage-decline-churn-labels (config-and-migration aspect) —
OrgAIConfig.usage_churn_labels_mode + OrgAIConfig.usage_churn_label_config.

'off' | 'shadow' | 'active' — NOT the classifier off/shadow/auto triple (see
plan.md §2): this column gates writing rows into the churn-suggestion review
queue, mirroring AutomationRule.mode, not the sklearn-backed classifiers.

Default-deny (AC1): a freshly-constructed/flushed OrgAIConfig has
usage_churn_labels_mode == 'off' and usage_churn_label_config is None.
"""

from sqlalchemy.orm import Session

from src.models.org_ai_config import OrgAIConfig
from src.models.organization import Organization


def test_has_usage_churn_labels_mode_attr():
    assert hasattr(OrgAIConfig(), "usage_churn_labels_mode")


def test_has_usage_churn_label_config_attr():
    assert hasattr(OrgAIConfig(), "usage_churn_label_config")


def test_default_off_orm_insert(db: Session, test_organization: Organization):
    config = OrgAIConfig(organization_id=test_organization.id)
    db.add(config)
    db.commit()
    db.refresh(config)

    assert config.usage_churn_labels_mode == "off"
    assert config.usage_churn_label_config is None


def test_getattr_fallback_off():
    class _LegacyConfigStub:
        """Stand-in for a pre-migration row with no usage_churn_labels_mode attribute."""

    legacy = _LegacyConfigStub()
    assert getattr(legacy, "usage_churn_labels_mode", "off") == "off"


def test_can_set_shadow_active(db: Session, test_organization: Organization):
    config = OrgAIConfig(organization_id=test_organization.id, usage_churn_labels_mode="shadow")
    db.add(config)
    db.commit()
    db.refresh(config)
    assert config.usage_churn_labels_mode == "shadow"

    config.usage_churn_labels_mode = "active"
    db.commit()
    db.refresh(config)
    assert config.usage_churn_labels_mode == "active"


def test_can_set_usage_churn_label_config_json(db: Session, test_organization: Organization):
    config = OrgAIConfig(
        organization_id=test_organization.id,
        usage_churn_label_config={"sustain_days": 7},
    )
    db.add(config)
    db.commit()
    db.refresh(config)
    assert config.usage_churn_label_config == {"sustain_days": 7}
