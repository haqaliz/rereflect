"""
Data-model test for the per-type auto-promotion hold flags on OrgAIConfig
(classifier-model-versioning-rollback, aspect data-model-and-migration / PRD M1).

A held (org, classifier_type) is what makes a manual rollback durable against the
weekly retrain job. The three flags default to False so existing installs behave
exactly as before.
"""

from src.models.organization import Organization
from src.models.org_ai_config import OrgAIConfig


def _make_org(db, name="Acme"):
    org = Organization(name=name, plan="free")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def test_autopromote_hold_flags_default_false(db):
    org = _make_org(db)
    config = OrgAIConfig(organization_id=org.id)
    db.add(config)
    db.commit()
    db.refresh(config)

    assert config.sentiment_autopromote_hold is False
    assert config.category_autopromote_hold is False
    assert config.urgency_autopromote_hold is False


def test_autopromote_hold_flags_are_settable_per_type(db):
    org = _make_org(db)
    config = OrgAIConfig(
        organization_id=org.id,
        sentiment_autopromote_hold=True,
    )
    db.add(config)
    db.commit()
    db.refresh(config)

    # Setting one type's hold never implies the others.
    assert config.sentiment_autopromote_hold is True
    assert config.category_autopromote_hold is False
    assert config.urgency_autopromote_hold is False
