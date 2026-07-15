"""
TDD tests for churn_labels_enabled / churn_label_config columns on both CRM
integration models (crm-churn-labels, data-model aspect, Phase 3).

Model on test_jira_status_sync_migration.py — same fixtures, model-level
asserts, no raw DDL.

See docs/planning/crm-churn-labels/data-model/plan_20260715.md
"""
from datetime import datetime

from sqlalchemy.orm import Session

from src.models.organization import Organization


class TestHubSpotIntegrationChurnLabelColumns:

    def test_churn_labels_enabled_defaults_false(
        self, db: Session, test_organization: Organization
    ):
        from src.models.hubspot_integration import HubSpotIntegration

        integration = HubSpotIntegration(
            organization_id=test_organization.id,
            access_token="encrypted_x",
            connected_at=datetime.utcnow(),
        )
        db.add(integration)
        db.commit()
        db.refresh(integration)

        assert integration.churn_labels_enabled is False

    def test_churn_label_config_accepts_dict(
        self, db: Session, test_organization: Organization
    ):
        from src.models.hubspot_integration import HubSpotIntegration

        config = {"renewal_pipelines": ["default"]}
        integration = HubSpotIntegration(
            organization_id=test_organization.id,
            access_token="encrypted_x",
            connected_at=datetime.utcnow(),
            churn_label_config=config,
        )
        db.add(integration)
        db.commit()
        db.refresh(integration)

        assert integration.churn_label_config == config


class TestSalesforceIntegrationChurnLabelColumns:

    def test_churn_labels_enabled_defaults_false(
        self, db: Session, test_organization: Organization
    ):
        from src.models.salesforce_integration import SalesforceIntegration

        integration = SalesforceIntegration(
            organization_id=test_organization.id,
            refresh_token="encrypted_x",
            connected_at=datetime.utcnow(),
        )
        db.add(integration)
        db.commit()
        db.refresh(integration)

        assert integration.churn_labels_enabled is False

    def test_churn_label_config_accepts_dict(
        self, db: Session, test_organization: Organization
    ):
        from src.models.salesforce_integration import SalesforceIntegration

        config = {"renewal_pipelines": ["default"]}
        integration = SalesforceIntegration(
            organization_id=test_organization.id,
            refresh_token="encrypted_x",
            connected_at=datetime.utcnow(),
            churn_label_config=config,
        )
        db.add(integration)
        db.commit()
        db.refresh(integration)

        assert integration.churn_label_config == config
