"""
Tests for Salesforce writeback config/status API routes (writeback-config-api
aspect of salesforce-crm-writeback).

Routes:
  PATCH /api/v1/integrations/salesforce/writeback       — configure opt-in + field
  GET   /api/v1/integrations/salesforce/status          — extended w/ 6 writeback fields
  POST  /api/v1/integrations/salesforce/writeback/test   — on-demand field validation

RBAC/multi-tenancy patterns + test structure mirror
tests/test_hubspot_writeback_routes.py.
"""
import os
from datetime import datetime
from unittest.mock import patch, MagicMock

import pytest
from sqlalchemy.orm import Session

from src.models.organization import Organization
from src.models.user import User
from src.models.salesforce_integration import SalesforceIntegration
from src.models.crm_enrichment import CrmEnrichment
from src.api.auth import hash_password, create_access_token

VALIDATE_TARGET = "src.api.routes.salesforce_integration.validate_writeback_field"
GET_CELERY_TARGET = "src.api.routes.salesforce_integration._get_celery_app"

# Valid 32-byte Fernet key for tests only (mirrors test_salesforce_routes.py).
TEST_FERNET_KEY = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="


@pytest.fixture(autouse=True)
def _fernet_key_env():
    """Ensure LLM_ENCRYPTION_KEY is set for the whole module (fixture setup
    encrypts a token, and route handlers decrypt it)."""
    with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
        yield


# ──────────────────────────── Fixtures ────────────────────────────────────────

@pytest.fixture
def owner_user(db: Session, test_organization: Organization) -> User:
    user = User(
        email="sf_wb_owner@test.com",
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
        email="sf_wb_member@test.com",
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


# ──────────────────────────── PATCH /writeback ────────────────────────────────

class TestPatchWriteback:
    def test_enable_without_field_name_returns_422(
        self, client, connected_integration, owner_headers
    ):
        resp = client.patch(
            "/api/v1/integrations/salesforce/writeback",
            json={"enabled": True},
            headers=owner_headers,
        )
        assert resp.status_code == 422

    def test_enable_without_field_name_stays_disabled(
        self, client, db, test_organization, connected_integration, owner_headers
    ):
        client.patch(
            "/api/v1/integrations/salesforce/writeback",
            json={"enabled": True},
            headers=owner_headers,
        )
        db.expire_all()
        row = db.query(SalesforceIntegration).filter_by(
            organization_id=test_organization.id
        ).first()
        assert row.writeback_enabled is False

    def test_enable_with_invalid_field_returns_400_with_reason(
        self, client, connected_integration, owner_headers
    ):
        with patch(VALIDATE_TARGET, return_value=(False, "field_not_found")):
            resp = client.patch(
                "/api/v1/integrations/salesforce/writeback",
                json={"enabled": True, "field_name": "Bad_Field__c"},
                headers=owner_headers,
            )
        assert resp.status_code == 400
        assert resp.json()["detail"]["reason"] == "field_not_found"

    def test_enable_with_invalid_field_stays_disabled(
        self, client, db, test_organization, connected_integration, owner_headers
    ):
        with patch(VALIDATE_TARGET, return_value=(False, "wrong_type")):
            client.patch(
                "/api/v1/integrations/salesforce/writeback",
                json={"enabled": True, "field_name": "Name"},
                headers=owner_headers,
            )
        db.expire_all()
        row = db.query(SalesforceIntegration).filter_by(
            organization_id=test_organization.id
        ).first()
        assert row.writeback_enabled is False
        assert row.writeback_field_name is None

    def test_enable_with_valid_field_returns_200(
        self, client, connected_integration, owner_headers
    ):
        with patch(VALIDATE_TARGET, return_value=(True, None)):
            resp = client.patch(
                "/api/v1/integrations/salesforce/writeback",
                json={"enabled": True, "field_name": "Rereflect_Health_Score__c"},
                headers=owner_headers,
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["writeback_enabled"] is True
        assert body["writeback_field_name"] == "Rereflect_Health_Score__c"

    def test_enable_with_valid_field_persists(
        self, client, db, test_organization, connected_integration, owner_headers
    ):
        with patch(VALIDATE_TARGET, return_value=(True, None)):
            client.patch(
                "/api/v1/integrations/salesforce/writeback",
                json={"enabled": True, "field_name": "Rereflect_Health_Score__c"},
                headers=owner_headers,
            )
        db.expire_all()
        row = db.query(SalesforceIntegration).filter_by(
            organization_id=test_organization.id
        ).first()
        assert row.writeback_enabled is True
        assert row.writeback_field_name == "Rereflect_Health_Score__c"

    def test_enable_with_valid_field_clears_error_status(
        self, client, db, test_organization, connected_integration, owner_headers
    ):
        connected_integration.last_writeback_status = "error"
        connected_integration.last_writeback_error = "some previous failure"
        db.commit()

        with patch(VALIDATE_TARGET, return_value=(True, None)):
            resp = client.patch(
                "/api/v1/integrations/salesforce/writeback",
                json={"enabled": True, "field_name": "Rereflect_Health_Score__c"},
                headers=owner_headers,
            )
        assert resp.status_code == 200
        db.expire_all()
        row = db.query(SalesforceIntegration).filter_by(
            organization_id=test_organization.id
        ).first()
        assert row.last_writeback_error is None

    def test_disable_returns_200_without_field_name(
        self, client, db, test_organization, connected_integration, owner_headers
    ):
        connected_integration.writeback_enabled = True
        connected_integration.writeback_field_name = "Rereflect_Health_Score__c"
        db.commit()

        resp = client.patch(
            "/api/v1/integrations/salesforce/writeback",
            json={"enabled": False},
            headers=owner_headers,
        )
        assert resp.status_code == 200
        db.expire_all()
        row = db.query(SalesforceIntegration).filter_by(
            organization_id=test_organization.id
        ).first()
        assert row.writeback_enabled is False

    def test_disable_does_not_call_validator(
        self, client, connected_integration, owner_headers
    ):
        with patch(VALIDATE_TARGET) as mock_validate:
            resp = client.patch(
                "/api/v1/integrations/salesforce/writeback",
                json={"enabled": False},
                headers=owner_headers,
            )
        assert resp.status_code == 200
        mock_validate.assert_not_called()

    def test_no_integration_returns_404(self, client, owner_headers):
        resp = client.patch(
            "/api/v1/integrations/salesforce/writeback",
            json={"enabled": False},
            headers=owner_headers,
        )
        assert resp.status_code == 404

    def test_member_gets_403(self, client, connected_integration, member_headers):
        resp = client.patch(
            "/api/v1/integrations/salesforce/writeback",
            json={"enabled": False},
            headers=member_headers,
        )
        assert resp.status_code == 403


# ──────────────────────────── GET /status extension ───────────────────────────

class TestStatusIncludesWriteback:
    def test_status_includes_writeback_fields(
        self, client, db, test_organization, connected_integration, owner_headers
    ):
        connected_integration.writeback_enabled = True
        connected_integration.writeback_field_name = "Rereflect_Health_Score__c"
        connected_integration.last_writeback_status = "ok"
        connected_integration.contacts_written = 3
        db.commit()

        resp = client.get(
            "/api/v1/integrations/salesforce/status",
            headers=owner_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["writeback_enabled"] is True
        assert body["writeback_field_name"] == "Rereflect_Health_Score__c"
        assert body["last_writeback_status"] == "ok"
        assert body["contacts_written"] == 3
        assert "last_writeback_at" in body
        assert "last_writeback_error" in body

    def test_status_disconnected_defaults(self, client, owner_headers):
        resp = client.get(
            "/api/v1/integrations/salesforce/status",
            headers=owner_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["writeback_enabled"] is False
        assert body["contacts_written"] == 0


# ──────────────────────────── Backfill-on-enable ──────────────────────────────

class TestBackfillOnEnable:
    """Enabling writeback enqueues a bounded backfill push for every matched
    crm_enrichment row (provider='salesforce') for this org."""

    def _make_enrichment(self, db, org_id, email, provider="salesforce"):
        now = datetime.utcnow()
        row = CrmEnrichment(
            organization_id=org_id,
            customer_email=email,
            provider=provider,
            last_synced_at=now,
            created_at=now,
            updated_at=now,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    def test_enable_enqueues_push_per_matched_customer(
        self, client, db, test_organization, connected_integration, owner_headers
    ):
        for i in range(3):
            self._make_enrichment(db, test_organization.id, f"cust{i}@example.com")

        with patch(VALIDATE_TARGET, return_value=(True, None)), \
             patch(GET_CELERY_TARGET) as mock_get_celery:
            mock_celery = MagicMock()
            mock_get_celery.return_value = mock_celery

            resp = client.patch(
                "/api/v1/integrations/salesforce/writeback",
                json={"enabled": True, "field_name": "Rereflect_Health_Score__c"},
                headers=owner_headers,
            )

        assert resp.status_code == 200
        calls = mock_celery.send_task.call_args_list
        assert len(calls) == 3
        task_names = {c.args[0] for c in calls}
        assert task_names == {"src.tasks.salesforce_writeback.push_health_to_salesforce"}
        emails = {c.kwargs["args"][1] for c in calls}
        assert emails == {"cust0@example.com", "cust1@example.com", "cust2@example.com"}

    def test_enable_skips_rows_from_other_provider(
        self, client, db, test_organization, connected_integration, owner_headers
    ):
        self._make_enrichment(db, test_organization.id, "matched@example.com", provider="salesforce")
        self._make_enrichment(db, test_organization.id, "hubspot-only@example.com", provider="hubspot")

        with patch(VALIDATE_TARGET, return_value=(True, None)), \
             patch(GET_CELERY_TARGET) as mock_get_celery:
            mock_celery = MagicMock()
            mock_get_celery.return_value = mock_celery

            client.patch(
                "/api/v1/integrations/salesforce/writeback",
                json={"enabled": True, "field_name": "Rereflect_Health_Score__c"},
                headers=owner_headers,
            )

        calls = mock_celery.send_task.call_args_list
        assert len(calls) == 1
        assert calls[0].kwargs["args"][1] == "matched@example.com"

    def test_disable_does_not_enqueue_backfill(
        self, client, db, test_organization, connected_integration, owner_headers
    ):
        connected_integration.writeback_enabled = True
        connected_integration.writeback_field_name = "Rereflect_Health_Score__c"
        db.commit()
        self._make_enrichment(db, test_organization.id, "cust@example.com")

        with patch(GET_CELERY_TARGET) as mock_get_celery:
            mock_celery = MagicMock()
            mock_get_celery.return_value = mock_celery

            resp = client.patch(
                "/api/v1/integrations/salesforce/writeback",
                json={"enabled": False},
                headers=owner_headers,
            )

        assert resp.status_code == 200
        mock_get_celery.assert_not_called()

    def test_backfill_bounded_at_cap(
        self, client, db, test_organization, connected_integration, owner_headers
    ):
        for i in range(3):
            self._make_enrichment(db, test_organization.id, f"cap{i}@example.com")

        with patch(VALIDATE_TARGET, return_value=(True, None)), \
             patch(GET_CELERY_TARGET) as mock_get_celery, \
             patch("src.api.routes.salesforce_integration.WRITEBACK_BACKFILL_CAP", 2):
            mock_celery = MagicMock()
            mock_get_celery.return_value = mock_celery

            resp = client.patch(
                "/api/v1/integrations/salesforce/writeback",
                json={"enabled": True, "field_name": "Rereflect_Health_Score__c"},
                headers=owner_headers,
            )

        assert resp.status_code == 200
        assert mock_celery.send_task.call_count == 2

    def test_backfill_failure_does_not_break_response(
        self, client, db, test_organization, connected_integration, owner_headers
    ):
        self._make_enrichment(db, test_organization.id, "cust@example.com")

        with patch(VALIDATE_TARGET, return_value=(True, None)), \
             patch(GET_CELERY_TARGET, side_effect=RuntimeError("broker down")):
            resp = client.patch(
                "/api/v1/integrations/salesforce/writeback",
                json={"enabled": True, "field_name": "Rereflect_Health_Score__c"},
                headers=owner_headers,
            )

        assert resp.status_code == 200
        assert resp.json()["writeback_enabled"] is True


# ──────────────────────────── POST /writeback/test ────────────────────────────

class TestWritebackTestEndpoint:
    def test_valid_field_returns_ok(self, client, connected_integration, owner_headers):
        with patch(VALIDATE_TARGET, return_value=(True, None)):
            resp = client.post(
                "/api/v1/integrations/salesforce/writeback/test",
                json={"field_name": "Rereflect_Health_Score__c"},
                headers=owner_headers,
            )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_invalid_field_returns_reason(self, client, connected_integration, owner_headers):
        with patch(VALIDATE_TARGET, return_value=(False, "field_not_found")):
            resp = client.post(
                "/api/v1/integrations/salesforce/writeback/test",
                json={"field_name": "Bad_Field__c"},
                headers=owner_headers,
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is False
        assert body["reason"] == "field_not_found"

    def test_no_integration_returns_400(self, client, owner_headers):
        resp = client.post(
            "/api/v1/integrations/salesforce/writeback/test",
            json={"field_name": "Rereflect_Health_Score__c"},
            headers=owner_headers,
        )
        assert resp.status_code == 400

    def test_member_gets_403(self, client, connected_integration, member_headers):
        resp = client.post(
            "/api/v1/integrations/salesforce/writeback/test",
            json={"field_name": "Rereflect_Health_Score__c"},
            headers=member_headers,
        )
        assert resp.status_code == 403
