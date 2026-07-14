"""
Unit tests for src/services/custom_category_service.py.

Covers the ``rules_referencing_category`` helper (Phase 2 — delete/rename
warning lookup). CRUD behavior itself is characterization-tested end-to-end
via tests/test_categories.py (internal) and tests/test_public_api_categories.py
(public); this file focuses on the rule-reference helper in isolation.
"""

import pytest
from sqlalchemy.orm import Session

from src.models.automation_rule import AutomationRule
from src.models.organization import Organization
from src.services.custom_category_service import rules_referencing_category


def _make_rule(
    db: Session,
    org_id: int,
    *,
    name: str,
    categories: list[str],
    trigger_type: str = "feedback_category_match",
    is_active: bool = True,
) -> AutomationRule:
    rule = AutomationRule(
        organization_id=org_id,
        name=name,
        trigger_type=trigger_type,
        trigger_config={"categories": categories},
        actions=[{"type": "send_notification", "config": {"channel": "email"}}],
        is_active=is_active,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


class TestRulesReferencingCategory:
    def test_no_rules_returns_empty(self, db: Session, test_organization: Organization):
        assert rules_referencing_category(db, test_organization.id, "Billing") == []

    def test_active_rule_referencing_name_returns_rule_name(
        self, db: Session, test_organization: Organization
    ):
        _make_rule(db, test_organization.id, name="Billing escalation", categories=["Billing"])

        result = rules_referencing_category(db, test_organization.id, "Billing")
        assert result == ["Billing escalation"]

    def test_rule_not_referencing_name_excluded(
        self, db: Session, test_organization: Organization
    ):
        _make_rule(db, test_organization.id, name="Other rule", categories=["Onboarding"])

        assert rules_referencing_category(db, test_organization.id, "Billing") == []

    def test_inactive_rule_excluded(self, db: Session, test_organization: Organization):
        _make_rule(
            db,
            test_organization.id,
            name="Inactive billing rule",
            categories=["Billing"],
            is_active=False,
        )

        assert rules_referencing_category(db, test_organization.id, "Billing") == []

    def test_non_matching_trigger_type_excluded(
        self, db: Session, test_organization: Organization
    ):
        _make_rule(
            db,
            test_organization.id,
            name="Health score rule",
            categories=["Billing"],
            trigger_type="health_score_threshold",
        )

        assert rules_referencing_category(db, test_organization.id, "Billing") == []

    def test_other_org_rule_excluded(self, db: Session, test_organization: Organization):
        other_org = Organization(name="Other Org", plan="pro")
        db.add(other_org)
        db.commit()
        db.refresh(other_org)

        _make_rule(db, other_org.id, name="Other org's rule", categories=["Billing"])

        assert rules_referencing_category(db, test_organization.id, "Billing") == []

    def test_multiple_active_rules_returns_all_names(
        self, db: Session, test_organization: Organization
    ):
        _make_rule(db, test_organization.id, name="Rule A", categories=["Billing", "Refunds"])
        _make_rule(db, test_organization.id, name="Rule B", categories=["Billing"])

        result = rules_referencing_category(db, test_organization.id, "Billing")
        assert sorted(result) == ["Rule A", "Rule B"]
