"""
TDD tests for ChurnLabelSuggestion SQLAlchemy model (crm-churn-labels, data-model aspect).

Model on test_jira_status_sync_migration.py — same fixtures, model-level asserts,
no raw DDL.

See docs/planning/crm-churn-labels/data-model/plan_20260715.md
"""
from datetime import datetime

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.models.base import Base
from src.models.organization import Organization
from src.models.user import User


class TestChurnLabelSuggestionModel:

    def test_table_registered(self, db: Session):
        from src.models.churn_label_suggestion import ChurnLabelSuggestion  # noqa: F401

        assert "churn_label_suggestions" in Base.metadata.tables

    def test_status_defaults_pending(
        self, db: Session, test_organization: Organization
    ):
        from src.models.churn_label_suggestion import ChurnLabelSuggestion

        suggestion = ChurnLabelSuggestion(
            organization_id=test_organization.id,
            customer_email="acme@example.com",
            provider="hubspot",
            external_opportunity_id="deal-1",
            suggested_churned_at=datetime.utcnow(),
        )
        db.add(suggestion)
        db.commit()
        db.refresh(suggestion)

        assert suggestion.status == "pending"

    def test_nullable_fields_default_none(
        self, db: Session, test_organization: Organization
    ):
        from src.models.churn_label_suggestion import ChurnLabelSuggestion

        suggestion = ChurnLabelSuggestion(
            organization_id=test_organization.id,
            customer_email="acme@example.com",
            provider="hubspot",
            external_opportunity_id="deal-2",
            suggested_churned_at=datetime.utcnow(),
        )
        db.add(suggestion)
        db.commit()
        db.refresh(suggestion)

        assert suggestion.evidence is None
        assert suggestion.reviewed_by_user_id is None
        assert suggestion.reviewed_at is None
        assert suggestion.churn_event_id is None

    def test_evidence_json_round_trips(
        self, db: Session, test_organization: Organization
    ):
        from src.models.churn_label_suggestion import ChurnLabelSuggestion

        evidence = {"name": "Acme Renewal", "amount": 1200}
        suggestion = ChurnLabelSuggestion(
            organization_id=test_organization.id,
            customer_email="acme@example.com",
            provider="salesforce",
            external_opportunity_id="opp-1",
            suggested_churned_at=datetime.utcnow(),
            evidence=evidence,
        )
        db.add(suggestion)
        db.commit()
        db.refresh(suggestion)

        assert suggestion.evidence == evidence

    def test_unique_org_provider_ext_enforced(
        self, db: Session, test_organization: Organization
    ):
        from src.models.churn_label_suggestion import ChurnLabelSuggestion

        kwargs = dict(
            organization_id=test_organization.id,
            customer_email="acme@example.com",
            provider="hubspot",
            external_opportunity_id="deal-dupe",
            suggested_churned_at=datetime.utcnow(),
        )
        db.add(ChurnLabelSuggestion(**kwargs))
        db.commit()

        db.add(ChurnLabelSuggestion(**kwargs))
        with pytest.raises(IntegrityError):
            db.commit()

    def test_same_triple_different_org_commits(
        self, db: Session, test_organization: Organization
    ):
        from src.models.churn_label_suggestion import ChurnLabelSuggestion

        other_org = Organization(name="Other Co", plan="pro")
        db.add(other_org)
        db.commit()
        db.refresh(other_org)

        db.add(
            ChurnLabelSuggestion(
                organization_id=test_organization.id,
                customer_email="acme@example.com",
                provider="hubspot",
                external_opportunity_id="deal-shared",
                suggested_churned_at=datetime.utcnow(),
            )
        )
        db.commit()

        db.add(
            ChurnLabelSuggestion(
                organization_id=other_org.id,
                customer_email="acme@example.com",
                provider="hubspot",
                external_opportunity_id="deal-shared",
                suggested_churned_at=datetime.utcnow(),
            )
        )
        db.commit()  # must not raise

    def test_status_list_is_source_of_truth(self):
        from src.models.churn_label_suggestion import CHURN_SUGGESTION_STATUSES

        assert CHURN_SUGGESTION_STATUSES == ["pending", "confirmed", "rejected"]

    def test_no_db_check_on_status(
        self, db: Session, test_organization: Organization
    ):
        from src.models.churn_label_suggestion import ChurnLabelSuggestion

        suggestion = ChurnLabelSuggestion(
            organization_id=test_organization.id,
            customer_email="acme@example.com",
            provider="hubspot",
            external_opportunity_id="deal-bogus",
            suggested_churned_at=datetime.utcnow(),
            status="bogus",
        )
        db.add(suggestion)
        db.commit()  # must not raise — no DB CHECK constraint (house convention)
        db.refresh(suggestion)

        assert suggestion.status == "bogus"
