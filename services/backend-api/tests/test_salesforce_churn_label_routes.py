"""
Tests for Salesforce CRM-sourced churn-label config API routes
(org-config-api-and-ui aspect, Phase 3 — symmetric with
tests/test_hubspot_churn_label_routes.py, spec AC12).

Routes:
  PATCH /api/v1/integrations/salesforce/churn-labels           — opt-in + renewal set
  GET   /api/v1/integrations/salesforce/churn-labels/options   — live picker options
  GET   /api/v1/integrations/salesforce/status                 — extended w/ churn-label fields

One patched seam (`src.api.routes.salesforce_integration.fetch_renewal_options`)
stands in for the live CRM call — no httpx, no Celery, no network.
"""
import os
from datetime import datetime
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

from src.api.auth import create_access_token, hash_password
from src.models.organization import Organization
from src.models.salesforce_integration import SalesforceIntegration
from src.models.user import User

FETCH_TARGET = "src.api.routes.salesforce_integration.fetch_renewal_options"

TEST_FERNET_KEY = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="

FAKE_OPPORTUNITY_TYPES = [
    {"id": "Renewal", "label": "Renewal"},
    {"id": "Existing Business", "label": "Existing Business"},
]


@pytest.fixture(autouse=True)
def _fernet_key_env():
    with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
        yield


# ──────────────────────────── Fixtures ────────────────────────────────────────

@pytest.fixture
def owner_user(db: Session, test_organization: Organization) -> User:
    user = User(
        email="sf_cl_owner@test.com",
        password_hash=hash_password("pw"),
        organization_id=test_organization.id,
        role="owner",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def owner_headers(owner_user: User) -> dict:
    token = create_access_token({
        "user_id": owner_user.id,
        "organization_id": owner_user.organization_id,
        "role": owner_user.role,
    })
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def member_user(db: Session, test_organization: Organization) -> User:
    user = User(
        email="sf_cl_member@test.com",
        password_hash=hash_password("pw"),
        organization_id=test_organization.id,
        role="member",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def member_headers(member_user: User) -> dict:
    token = create_access_token({
        "user_id": member_user.id,
        "organization_id": member_user.organization_id,
        "role": member_user.role,
    })
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def second_org(db: Session) -> Organization:
    org = Organization(name="Other Corp SF", plan="pro")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


@pytest.fixture
def second_org_owner(db: Session, second_org: Organization) -> User:
    user = User(
        email="sf_cl_other_owner@test.com",
        password_hash=hash_password("pw"),
        organization_id=second_org.id,
        role="owner",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def second_org_headers(second_org_owner: User) -> dict:
    token = create_access_token({
        "user_id": second_org_owner.id,
        "organization_id": second_org_owner.organization_id,
        "role": second_org_owner.role,
    })
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def connected_integration(db: Session, test_organization: Organization) -> SalesforceIntegration:
    from src.utils.encryption import encrypt_api_key

    row = SalesforceIntegration(
        organization_id=test_organization.id,
        refresh_token=encrypt_api_key("sentinel-refresh-token-value"),
        instance_url="https://acme.my.salesforce.com",
        sf_org_id="00Dxx0000001gPFEAY",
        token_hint="...abcd",
        connected_at=datetime.utcnow(),
        is_active=True,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@pytest.fixture
def inactive_integration(db: Session, test_organization: Organization) -> SalesforceIntegration:
    from src.utils.encryption import encrypt_api_key

    row = SalesforceIntegration(
        organization_id=test_organization.id,
        refresh_token=encrypt_api_key("sentinel-refresh-token-value"),
        instance_url="https://acme.my.salesforce.com",
        sf_org_id="00Dxx0000001gPFEAY",
        token_hint="...abcd",
        connected_at=datetime.utcnow(),
        is_active=False,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


# ──────────────────────────── PATCH /churn-labels ─────────────────────────────

class TestPatchChurnLabels:
    def test_enable_with_valid_opportunity_type_returns_200(
        self, client, connected_integration, owner_headers
    ):
        with patch(FETCH_TARGET, return_value=(FAKE_OPPORTUNITY_TYPES, None)):
            resp = client.patch(
                "/api/v1/integrations/salesforce/churn-labels",
                json={"enabled": True, "config": {"renewal_opportunity_types": ["Renewal"]}},
                headers=owner_headers,
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["churn_labels_enabled"] is True
        assert body["churn_label_config"] == {"renewal_opportunity_types": ["Renewal"]}

    def test_enable_with_valid_opportunity_type_persists(
        self, client, db, test_organization, connected_integration, owner_headers
    ):
        with patch(FETCH_TARGET, return_value=(FAKE_OPPORTUNITY_TYPES, None)):
            client.patch(
                "/api/v1/integrations/salesforce/churn-labels",
                json={"enabled": True, "config": {"renewal_opportunity_types": ["Renewal"]}},
                headers=owner_headers,
            )
        db.expire_all()
        row = db.query(SalesforceIntegration).filter_by(
            organization_id=test_organization.id
        ).first()
        assert row.churn_labels_enabled is True
        assert row.churn_label_config == {"renewal_opportunity_types": ["Renewal"]}

    def test_unknown_opportunity_type_returns_422_with_offending_id(
        self, client, connected_integration, owner_headers
    ):
        with patch(FETCH_TARGET, return_value=(FAKE_OPPORTUNITY_TYPES, None)):
            resp = client.patch(
                "/api/v1/integrations/salesforce/churn-labels",
                json={"enabled": True, "config": {"renewal_opportunity_types": ["Nope"]}},
                headers=owner_headers,
            )
        assert resp.status_code == 422
        assert "Nope" in resp.text

    def test_unknown_opportunity_type_leaves_row_unchanged(
        self, client, db, test_organization, connected_integration, owner_headers
    ):
        with patch(FETCH_TARGET, return_value=(FAKE_OPPORTUNITY_TYPES, None)):
            client.patch(
                "/api/v1/integrations/salesforce/churn-labels",
                json={"enabled": True, "config": {"renewal_opportunity_types": ["Nope"]}},
                headers=owner_headers,
            )
        db.expire_all()
        row = db.query(SalesforceIntegration).filter_by(
            organization_id=test_organization.id
        ).first()
        assert row.churn_labels_enabled is False
        assert row.churn_label_config is None

    def test_unknown_config_key_returns_422(self, client, connected_integration, owner_headers):
        resp = client.patch(
            "/api/v1/integrations/salesforce/churn-labels",
            json={"enabled": True, "config": {"bogus_key": ["Renewal"]}},
            headers=owner_headers,
        )
        assert resp.status_code == 422

    def test_non_list_config_value_returns_422(self, client, connected_integration, owner_headers):
        resp = client.patch(
            "/api/v1/integrations/salesforce/churn-labels",
            json={"enabled": True, "config": {"renewal_opportunity_types": "Renewal"}},
            headers=owner_headers,
        )
        assert resp.status_code == 422

    def test_non_string_config_member_returns_422(self, client, connected_integration, owner_headers):
        resp = client.patch(
            "/api/v1/integrations/salesforce/churn-labels",
            json={"enabled": True, "config": {"renewal_opportunity_types": [123]}},
            headers=owner_headers,
        )
        assert resp.status_code == 422

    def test_shape_errors_never_call_fetch_renewal_options(
        self, client, connected_integration, owner_headers
    ):
        with patch(FETCH_TARGET) as mock_fetch:
            resp = client.patch(
                "/api/v1/integrations/salesforce/churn-labels",
                json={"enabled": True, "config": {"bogus_key": ["Renewal"]}},
                headers=owner_headers,
            )
        assert resp.status_code == 422
        mock_fetch.assert_not_called()

    def test_disable_with_no_config_returns_200_and_disables(
        self, client, db, test_organization, connected_integration, owner_headers
    ):
        connected_integration.churn_labels_enabled = True
        connected_integration.churn_label_config = {"renewal_opportunity_types": ["Renewal"]}
        db.commit()

        resp = client.patch(
            "/api/v1/integrations/salesforce/churn-labels",
            json={"enabled": False},
            headers=owner_headers,
        )
        assert resp.status_code == 200
        db.expire_all()
        row = db.query(SalesforceIntegration).filter_by(
            organization_id=test_organization.id
        ).first()
        assert row.churn_labels_enabled is False

    def test_disable_leaves_existing_config_intact(
        self, client, db, test_organization, connected_integration, owner_headers
    ):
        connected_integration.churn_labels_enabled = True
        connected_integration.churn_label_config = {"renewal_opportunity_types": ["Renewal"]}
        db.commit()

        client.patch(
            "/api/v1/integrations/salesforce/churn-labels",
            json={"enabled": False},
            headers=owner_headers,
        )
        db.expire_all()
        row = db.query(SalesforceIntegration).filter_by(
            organization_id=test_organization.id
        ).first()
        assert row.churn_label_config == {"renewal_opportunity_types": ["Renewal"]}

    def test_enable_with_empty_renewal_list_returns_200_not_422(
        self, client, connected_integration, owner_headers
    ):
        with patch(FETCH_TARGET) as mock_fetch:
            resp = client.patch(
                "/api/v1/integrations/salesforce/churn-labels",
                json={"enabled": True, "config": {"renewal_opportunity_types": []}},
                headers=owner_headers,
            )
        assert resp.status_code == 200
        mock_fetch.assert_not_called()

    def test_enable_with_absent_config_returns_200_not_422(
        self, client, connected_integration, owner_headers
    ):
        with patch(FETCH_TARGET) as mock_fetch:
            resp = client.patch(
                "/api/v1/integrations/salesforce/churn-labels",
                json={"enabled": True},
                headers=owner_headers,
            )
        assert resp.status_code == 200
        mock_fetch.assert_not_called()

    def test_enable_with_empty_list_never_invents_all_types_default(
        self, client, db, test_organization, connected_integration, owner_headers
    ):
        with patch(FETCH_TARGET) as mock_fetch:
            client.patch(
                "/api/v1/integrations/salesforce/churn-labels",
                json={"enabled": True, "config": {"renewal_opportunity_types": []}},
                headers=owner_headers,
            )
        db.expire_all()
        row = db.query(SalesforceIntegration).filter_by(
            organization_id=test_organization.id
        ).first()
        assert row.churn_label_config == {"renewal_opportunity_types": []}
        mock_fetch.assert_not_called()

    def test_no_integration_row_returns_404(self, client, owner_headers):
        resp = client.patch(
            "/api/v1/integrations/salesforce/churn-labels",
            json={"enabled": True, "config": {"renewal_opportunity_types": []}},
            headers=owner_headers,
        )
        assert resp.status_code == 404

    def test_inactive_integration_returns_400(
        self, client, inactive_integration, owner_headers
    ):
        resp = client.patch(
            "/api/v1/integrations/salesforce/churn-labels",
            json={"enabled": True, "config": {"renewal_opportunity_types": []}},
            headers=owner_headers,
        )
        assert resp.status_code == 400

    def test_fetch_options_failure_returns_502_not_500(
        self, client, connected_integration, owner_headers
    ):
        with patch(FETCH_TARGET, return_value=([], "options_fetch_failed")):
            resp = client.patch(
                "/api/v1/integrations/salesforce/churn-labels",
                json={"enabled": True, "config": {"renewal_opportunity_types": ["Renewal"]}},
                headers=owner_headers,
            )
        assert resp.status_code == 502

    def test_member_gets_403(self, client, connected_integration, member_headers):
        resp = client.patch(
            "/api/v1/integrations/salesforce/churn-labels",
            json={"enabled": False},
            headers=member_headers,
        )
        assert resp.status_code == 403

    def test_cannot_write_another_orgs_integration(
        self, client, connected_integration, second_org_headers
    ):
        resp = client.patch(
            "/api/v1/integrations/salesforce/churn-labels",
            json={"enabled": True, "config": {"renewal_opportunity_types": []}},
            headers=second_org_headers,
        )
        assert resp.status_code == 404

    def test_response_never_leaks_refresh_or_access_token(
        self, client, connected_integration, owner_headers
    ):
        with patch(FETCH_TARGET, return_value=(FAKE_OPPORTUNITY_TYPES, None)):
            resp = client.patch(
                "/api/v1/integrations/salesforce/churn-labels",
                json={"enabled": True, "config": {"renewal_opportunity_types": ["Renewal"]}},
                headers=owner_headers,
            )
        assert "refresh_token" not in resp.text
        assert "access_token" not in resp.text
        assert "sentinel-refresh-token-value" not in resp.text


# ──────────────────────────── GET /churn-labels/options ───────────────────────

class TestGetChurnLabelOptions:
    def test_returns_options_from_fake(self, client, connected_integration, owner_headers):
        with patch(FETCH_TARGET, return_value=(FAKE_OPPORTUNITY_TYPES, None)):
            resp = client.get(
                "/api/v1/integrations/salesforce/churn-labels/options",
                headers=owner_headers,
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["provider"] == "salesforce"
        assert body["options"] == FAKE_OPPORTUNITY_TYPES

    def test_no_active_integration_returns_404(self, client, owner_headers):
        resp = client.get(
            "/api/v1/integrations/salesforce/churn-labels/options",
            headers=owner_headers,
        )
        assert resp.status_code == 404

    def test_inactive_integration_returns_404(
        self, client, inactive_integration, owner_headers
    ):
        resp = client.get(
            "/api/v1/integrations/salesforce/churn-labels/options",
            headers=owner_headers,
        )
        assert resp.status_code == 404

    def test_fetch_failure_returns_502(self, client, connected_integration, owner_headers):
        with patch(FETCH_TARGET, return_value=([], "options_fetch_failed")):
            resp = client.get(
                "/api/v1/integrations/salesforce/churn-labels/options",
                headers=owner_headers,
            )
        assert resp.status_code == 502

    def test_member_gets_403(self, client, connected_integration, member_headers):
        resp = client.get(
            "/api/v1/integrations/salesforce/churn-labels/options",
            headers=member_headers,
        )
        assert resp.status_code == 403

    def test_response_never_leaks_refresh_or_access_token(
        self, client, connected_integration, owner_headers
    ):
        with patch(FETCH_TARGET, return_value=(FAKE_OPPORTUNITY_TYPES, None)):
            resp = client.get(
                "/api/v1/integrations/salesforce/churn-labels/options",
                headers=owner_headers,
            )
        assert "refresh_token" not in resp.text
        assert "access_token" not in resp.text
        assert "sentinel-refresh-token-value" not in resp.text


# ──────────────────────────── GET /status extension ───────────────────────────

class TestStatusIncludesChurnLabels:
    def test_status_includes_churn_label_fields(
        self, client, db, test_organization, connected_integration, owner_headers
    ):
        connected_integration.churn_labels_enabled = True
        connected_integration.churn_label_config = {"renewal_opportunity_types": ["Renewal"]}
        db.commit()

        resp = client.get(
            "/api/v1/integrations/salesforce/status",
            headers=owner_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["churn_labels_enabled"] is True
        assert body["churn_label_config"] == {"renewal_opportunity_types": ["Renewal"]}
        assert body["suggestions_created"] == 0
        assert body["last_harvest_at"] is None
        assert body["last_harvest_status"] is None
        assert body["last_harvest_error"] is None

    def test_status_disconnected_defaults(self, client, owner_headers):
        resp = client.get(
            "/api/v1/integrations/salesforce/status",
            headers=owner_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["churn_labels_enabled"] is False
        assert body["suggestions_created"] == 0

    def test_status_never_leaks_refresh_or_access_token(
        self, client, connected_integration, owner_headers
    ):
        resp = client.get(
            "/api/v1/integrations/salesforce/status",
            headers=owner_headers,
        )
        assert "refresh_token" not in resp.text
        assert "access_token" not in resp.text
        assert "sentinel-refresh-token-value" not in resp.text

    def test_suggestions_created_counts_org_and_provider_scoped_rows(
        self, client, db, test_organization, connected_integration, owner_headers, second_org
    ):
        from src.models.churn_label_suggestion import ChurnLabelSuggestion

        db.add(ChurnLabelSuggestion(
            organization_id=test_organization.id,
            customer_email="a@example.com",
            provider="salesforce",
            external_opportunity_id="opp-1",
            suggested_churned_at=datetime.utcnow(),
        ))
        db.add(ChurnLabelSuggestion(
            organization_id=test_organization.id,
            customer_email="b@example.com",
            provider="hubspot",
            external_opportunity_id="deal-1",
            suggested_churned_at=datetime.utcnow(),
        ))
        db.add(ChurnLabelSuggestion(
            organization_id=second_org.id,
            customer_email="c@example.com",
            provider="salesforce",
            external_opportunity_id="opp-2",
            suggested_churned_at=datetime.utcnow(),
        ))
        db.commit()

        resp = client.get(
            "/api/v1/integrations/salesforce/status",
            headers=owner_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["suggestions_created"] == 1
