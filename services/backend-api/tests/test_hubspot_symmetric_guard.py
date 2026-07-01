"""
Tests for the symmetric one-CRM guard + shared purge on hubspot_integration.py
(Phase 5 of salesforce-connection aspect).

Ensures the collision cannot be created from the HubSpot side either:
connecting HubSpot while Salesforce is active must be blocked (409), and
disconnecting HubSpot must purge that provider's crm_enrichment rows too.
"""
import os
from datetime import datetime
from unittest.mock import patch, MagicMock

import pytest
from sqlalchemy.orm import Session

from src.models.organization import Organization
from src.models.user import User
from src.models.hubspot_integration import HubSpotIntegration
from src.models.salesforce_integration import SalesforceIntegration
from src.models.crm_enrichment import CrmEnrichment
from src.api.auth import hash_password, create_access_token

TEST_FERNET_KEY = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
VALID_TOKEN = "pat-na1-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
PORTAL_RESPONSE = {
    "portalId": 12345678,
    "timeZone": "America/New_York",
    "companyCurrency": "USD",
    "additionalCurrencies": [],
    "utcOffset": "-05:00",
}


@pytest.fixture
def owner_user(db: Session, test_organization: Organization) -> User:
    user = User(
        email="hsg_owner@test.com",
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


def hubspot_ping_ok():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = PORTAL_RESPONSE
    mock_resp.raise_for_status = MagicMock()
    mock = MagicMock()
    mock.__enter__ = MagicMock(return_value=mock)
    mock.__exit__ = MagicMock(return_value=False)
    mock.get = MagicMock(return_value=mock_resp)
    return mock


class TestHubSpotConnectSymmetricGuard:
    def test_connect_blocked_when_salesforce_active(
        self, client, db, test_organization, owner_headers
    ):
        db.add(SalesforceIntegration(
            organization_id=test_organization.id,
            refresh_token="enc",
            connected_at=datetime.utcnow(),
            is_active=True,
        ))
        db.commit()

        with patch("src.api.routes.hubspot_integration.httpx.Client",
                   return_value=hubspot_ping_ok()):
            with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
                resp = client.post(
                    "/api/v1/integrations/hubspot/connect",
                    json={"access_token": VALID_TOKEN},
                    headers=owner_headers,
                )
        assert resp.status_code == 409

    def test_connect_not_blocked_when_salesforce_inactive(
        self, client, db, test_organization, owner_headers
    ):
        db.add(SalesforceIntegration(
            organization_id=test_organization.id,
            refresh_token="enc",
            connected_at=datetime.utcnow(),
            is_active=False,
        ))
        db.commit()

        with patch("src.api.routes.hubspot_integration.httpx.Client",
                   return_value=hubspot_ping_ok()):
            with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
                resp = client.post(
                    "/api/v1/integrations/hubspot/connect",
                    json={"access_token": VALID_TOKEN},
                    headers=owner_headers,
                )
        assert resp.status_code == 200

    def test_connect_not_blocked_when_nothing_else_connected(
        self, client, owner_headers
    ):
        with patch("src.api.routes.hubspot_integration.httpx.Client",
                   return_value=hubspot_ping_ok()):
            with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
                resp = client.post(
                    "/api/v1/integrations/hubspot/connect",
                    json={"access_token": VALID_TOKEN},
                    headers=owner_headers,
                )
        assert resp.status_code == 200


class TestHubSpotDisconnectPurge:
    def test_disconnect_purges_hubspot_rows_and_recomputes(
        self, client, db, test_organization, owner_headers
    ):
        db.add(HubSpotIntegration(
            organization_id=test_organization.id,
            access_token="enc",
            connected_at=datetime.utcnow(),
            is_active=True,
        ))
        db.add(CrmEnrichment(
            organization_id=test_organization.id,
            customer_email="hs-customer@test.com",
            provider="hubspot",
            last_synced_at=datetime.utcnow(),
        ))
        db.add(CrmEnrichment(
            organization_id=test_organization.id,
            customer_email="sf-customer@test.com",
            provider="salesforce",
            last_synced_at=datetime.utcnow(),
        ))
        db.commit()

        with patch(
            "src.services.health_score_service.update_customer_health"
        ) as mock_update:
            resp = client.delete(
                "/api/v1/integrations/hubspot/disconnect",
                headers=owner_headers,
            )
        assert resp.status_code == 200

        db.expire_all()
        remaining = db.query(CrmEnrichment).filter_by(
            organization_id=test_organization.id
        ).all()
        assert len(remaining) == 1
        assert remaining[0].provider == "salesforce"
        mock_update.assert_called_once()
        assert mock_update.call_args.args[1] == "hs-customer@test.com"
