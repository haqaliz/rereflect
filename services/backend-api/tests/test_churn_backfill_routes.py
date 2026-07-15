"""
Tests for historical churn-label backfill trigger/cancel routes
(historical-backfill aspect, Phase 6).

Routes (mirrored for both providers):
  POST /api/v1/integrations/{provider}/churn-labels/backfill
  POST /api/v1/integrations/{provider}/churn-labels/backfill/cancel

RBAC/multi-tenancy patterns mirror test_hubspot_sync_endpoint.py and
test_hubspot_churn_label_routes.py. Celery is patched at the `_get_celery_app`
seam (backend convention — unlike the worker's own tests, backend route
tests use unittest.mock.patch for the Celery client, matching
test_hubspot_sync_endpoint.py precedent).
"""
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from src.api.auth import create_access_token, hash_password
from src.models.hubspot_integration import HubSpotIntegration
from src.models.organization import Organization
from src.models.salesforce_integration import SalesforceIntegration
from src.models.user import User


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def owner_user(db: Session, test_organization: Organization) -> User:
    user = User(
        email="bf_owner@test.com",
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
        email="bf_member@test.com",
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
    org = Organization(name="Other Corp", plan="pro")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


@pytest.fixture
def second_org_owner(db: Session, second_org: Organization) -> User:
    user = User(
        email="bf_other_owner@test.com",
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


def _enabled_hubspot_integration(
    db: Session, org_id: int, backfill_status=None
) -> HubSpotIntegration:
    row = HubSpotIntegration(
        organization_id=org_id,
        access_token="encrypted-token-placeholder",
        is_active=True,
        churn_labels_enabled=True,
        churn_label_config={"renewal_pipeline_ids": ["12345"]},
        connected_at=datetime.utcnow(),
        backfill_status=backfill_status,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _enabled_salesforce_integration(
    db: Session, org_id: int, backfill_status=None
) -> SalesforceIntegration:
    row = SalesforceIntegration(
        organization_id=org_id,
        refresh_token="encrypted-refresh-placeholder",
        instance_url="https://example.my.salesforce.com",
        is_active=True,
        churn_labels_enabled=True,
        churn_label_config={"renewal_opportunity_types": ["Renewal"]},
        connected_at=datetime.utcnow(),
        backfill_status=backfill_status,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


# ---------------------------------------------------------------------------
# HubSpot
# ---------------------------------------------------------------------------


class TestHubSpotBackfillTrigger:
    URL = "/api/v1/integrations/hubspot/churn-labels/backfill"
    CELERY_TARGET = "src.api.routes.hubspot_integration._get_celery_app"

    def test_member_forbidden(self, client, db, test_organization, member_headers):
        _enabled_hubspot_integration(db, test_organization.id)
        resp = client.post(self.URL, json={}, headers=member_headers)
        assert resp.status_code == 403

    def test_no_integration_row_returns_404(self, client, db, test_organization, owner_headers):
        resp = client.post(self.URL, json={}, headers=owner_headers)
        assert resp.status_code == 404

    def test_cross_org_row_is_invisible_returns_404(
        self, client, db, test_organization, second_org, second_org_headers
    ):
        """The requesting org has no HubSpot row of its own — another org's
        row (test_organization's) must never be reachable via JWT scoping."""
        _enabled_hubspot_integration(db, test_organization.id)
        resp = client.post(self.URL, json={}, headers=second_org_headers)
        assert resp.status_code == 404

    def test_disabled_churn_labels_returns_400(
        self, client, db, test_organization, owner_headers
    ):
        row = _enabled_hubspot_integration(db, test_organization.id)
        row.churn_labels_enabled = False
        db.commit()
        resp = client.post(self.URL, json={}, headers=owner_headers)
        assert resp.status_code == 400

    def test_empty_renewal_set_returns_400(
        self, client, db, test_organization, owner_headers
    ):
        row = _enabled_hubspot_integration(db, test_organization.id)
        row.churn_label_config = {"renewal_pipeline_ids": []}
        db.commit()
        resp = client.post(self.URL, json={}, headers=owner_headers)
        assert resp.status_code == 400

    def test_already_running_returns_409(
        self, client, db, test_organization, owner_headers
    ):
        _enabled_hubspot_integration(db, test_organization.id, backfill_status="running")
        resp = client.post(self.URL, json={}, headers=owner_headers)
        assert resp.status_code == 409

    def test_months_zero_returns_422(self, client, db, test_organization, owner_headers):
        _enabled_hubspot_integration(db, test_organization.id)
        resp = client.post(self.URL, json={"months": 0}, headers=owner_headers)
        assert resp.status_code == 422

    def test_months_above_max_returns_422(self, client, db, test_organization, owner_headers):
        _enabled_hubspot_integration(db, test_organization.id)
        resp = client.post(self.URL, json={"months": 61}, headers=owner_headers)
        assert resp.status_code == 422

    def test_happy_path_dispatches_task_and_returns_202(
        self, client, db, test_organization, owner_headers
    ):
        integ = _enabled_hubspot_integration(db, test_organization.id)

        with patch(self.CELERY_TARGET) as mock_get_celery:
            mock_celery = MagicMock()
            mock_get_celery.return_value = mock_celery
            resp = client.post(self.URL, json={"months": 36}, headers=owner_headers)

        assert resp.status_code == 202
        body = resp.json()
        assert body["status"] == "queued"
        assert body["backfill_status"] == "running"
        mock_celery.send_task.assert_called_once_with(
            "src.tasks.churn_backfill_task.backfill_churn_suggestions",
            args=[integ.id, 36, "hubspot"],
        )
        db.refresh(integ)
        assert integ.backfill_status == "running"
        assert integ.backfill_error is None

    def test_default_months_is_24_when_omitted(
        self, client, db, test_organization, owner_headers
    ):
        integ = _enabled_hubspot_integration(db, test_organization.id)

        with patch(self.CELERY_TARGET) as mock_get_celery:
            mock_celery = MagicMock()
            mock_get_celery.return_value = mock_celery
            client.post(self.URL, json={}, headers=owner_headers)

        mock_celery.send_task.assert_called_once_with(
            "src.tasks.churn_backfill_task.backfill_churn_suggestions",
            args=[integ.id, 24, "hubspot"],
        )

    def test_broker_failure_returns_502_and_rolls_back_status(
        self, client, db, test_organization, owner_headers
    ):
        integ = _enabled_hubspot_integration(db, test_organization.id)

        with patch(self.CELERY_TARGET) as mock_get_celery:
            mock_get_celery.side_effect = RuntimeError("broker unreachable")
            resp = client.post(self.URL, json={}, headers=owner_headers)

        assert resp.status_code == 502
        db.refresh(integ)
        assert integ.backfill_status == "failed"
        assert integ.backfill_error


class TestHubSpotBackfillCancel:
    URL = "/api/v1/integrations/hubspot/churn-labels/backfill/cancel"

    def test_member_forbidden(self, client, db, test_organization, member_headers):
        _enabled_hubspot_integration(db, test_organization.id, backfill_status="running")
        resp = client.post(self.URL, headers=member_headers)
        assert resp.status_code == 403

    def test_no_integration_returns_404(self, client, db, test_organization, owner_headers):
        resp = client.post(self.URL, headers=owner_headers)
        assert resp.status_code == 404

    def test_not_running_returns_409(self, client, db, test_organization, owner_headers):
        _enabled_hubspot_integration(db, test_organization.id, backfill_status="completed")
        resp = client.post(self.URL, headers=owner_headers)
        assert resp.status_code == 409

    def test_running_flips_to_cancelling(
        self, client, db, test_organization, owner_headers
    ):
        integ = _enabled_hubspot_integration(
            db, test_organization.id, backfill_status="running"
        )
        resp = client.post(self.URL, headers=owner_headers)
        assert resp.status_code == 200
        assert resp.json()["backfill_status"] == "cancelling"
        db.refresh(integ)
        assert integ.backfill_status == "cancelling"


# ---------------------------------------------------------------------------
# Salesforce
# ---------------------------------------------------------------------------


class TestSalesforceBackfillTrigger:
    URL = "/api/v1/integrations/salesforce/churn-labels/backfill"
    CELERY_TARGET = "src.api.routes.salesforce_integration._get_celery_app"

    def test_member_forbidden(self, client, db, test_organization, member_headers):
        _enabled_salesforce_integration(db, test_organization.id)
        resp = client.post(self.URL, json={}, headers=member_headers)
        assert resp.status_code == 403

    def test_no_integration_row_returns_404(self, client, db, test_organization, owner_headers):
        resp = client.post(self.URL, json={}, headers=owner_headers)
        assert resp.status_code == 404

    def test_disabled_churn_labels_returns_400(
        self, client, db, test_organization, owner_headers
    ):
        row = _enabled_salesforce_integration(db, test_organization.id)
        row.churn_labels_enabled = False
        db.commit()
        resp = client.post(self.URL, json={}, headers=owner_headers)
        assert resp.status_code == 400

    def test_empty_renewal_set_returns_400(
        self, client, db, test_organization, owner_headers
    ):
        row = _enabled_salesforce_integration(db, test_organization.id)
        row.churn_label_config = {"renewal_opportunity_types": []}
        db.commit()
        resp = client.post(self.URL, json={}, headers=owner_headers)
        assert resp.status_code == 400

    def test_already_running_returns_409(
        self, client, db, test_organization, owner_headers
    ):
        _enabled_salesforce_integration(
            db, test_organization.id, backfill_status="running"
        )
        resp = client.post(self.URL, json={}, headers=owner_headers)
        assert resp.status_code == 409

    def test_months_out_of_range_returns_422(
        self, client, db, test_organization, owner_headers
    ):
        _enabled_salesforce_integration(db, test_organization.id)
        resp = client.post(self.URL, json={"months": 61}, headers=owner_headers)
        assert resp.status_code == 422

    def test_happy_path_dispatches_task_and_returns_202(
        self, client, db, test_organization, owner_headers
    ):
        integ = _enabled_salesforce_integration(db, test_organization.id)

        with patch(self.CELERY_TARGET) as mock_get_celery:
            mock_celery = MagicMock()
            mock_get_celery.return_value = mock_celery
            resp = client.post(self.URL, json={"months": 12}, headers=owner_headers)

        assert resp.status_code == 202
        body = resp.json()
        assert body["status"] == "queued"
        assert body["backfill_status"] == "running"
        mock_celery.send_task.assert_called_once_with(
            "src.tasks.churn_backfill_task.backfill_churn_suggestions",
            args=[integ.id, 12, "salesforce"],
        )

    def test_broker_failure_returns_502_and_rolls_back_status(
        self, client, db, test_organization, owner_headers
    ):
        integ = _enabled_salesforce_integration(db, test_organization.id)

        with patch(self.CELERY_TARGET) as mock_get_celery:
            mock_get_celery.side_effect = RuntimeError("broker unreachable")
            resp = client.post(self.URL, json={}, headers=owner_headers)

        assert resp.status_code == 502
        db.refresh(integ)
        assert integ.backfill_status == "failed"
        assert integ.backfill_error


class TestSalesforceBackfillCancel:
    URL = "/api/v1/integrations/salesforce/churn-labels/backfill/cancel"

    def test_member_forbidden(self, client, db, test_organization, member_headers):
        _enabled_salesforce_integration(
            db, test_organization.id, backfill_status="running"
        )
        resp = client.post(self.URL, headers=member_headers)
        assert resp.status_code == 403

    def test_no_integration_returns_404(self, client, db, test_organization, owner_headers):
        resp = client.post(self.URL, headers=owner_headers)
        assert resp.status_code == 404

    def test_not_running_returns_409(self, client, db, test_organization, owner_headers):
        _enabled_salesforce_integration(
            db, test_organization.id, backfill_status="idle"
        )
        resp = client.post(self.URL, headers=owner_headers)
        assert resp.status_code == 409

    def test_running_flips_to_cancelling(
        self, client, db, test_organization, owner_headers
    ):
        integ = _enabled_salesforce_integration(
            db, test_organization.id, backfill_status="running"
        )
        resp = client.post(self.URL, headers=owner_headers)
        assert resp.status_code == 200
        assert resp.json()["backfill_status"] == "cancelling"
        db.refresh(integ)
        assert integ.backfill_status == "cancelling"


# ---------------------------------------------------------------------------
# Surfaced on status/churn-labels responses
# ---------------------------------------------------------------------------


class TestBackfillFieldsSurfacedOnStatus:
    def test_hubspot_status_includes_backfill_fields(
        self, client, db, test_organization, owner_headers
    ):
        _enabled_hubspot_integration(
            db, test_organization.id, backfill_status="completed"
        )
        resp = client.get(
            "/api/v1/integrations/hubspot/status", headers=owner_headers
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["backfill_status"] == "completed"
        assert "backfill_progress" in body
        assert "backfill_error" in body

    def test_salesforce_status_includes_backfill_fields(
        self, client, db, test_organization, owner_headers
    ):
        _enabled_salesforce_integration(
            db, test_organization.id, backfill_status="cancelled"
        )
        resp = client.get(
            "/api/v1/integrations/salesforce/status", headers=owner_headers
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["backfill_status"] == "cancelled"
