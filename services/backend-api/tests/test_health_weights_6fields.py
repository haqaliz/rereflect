"""
TDD tests for the 6-weight health-score endpoint extension (crm-health-component).

Tests cover:
- PUT /api/v1/categories/health-weights with crm as the 6th weight
- 6-weight sum=100 accepted, sum≠100 rejected
- crm field persisted to OrgAIConfig.health_weight_crm
- GET returns crm key with default 0

Phase 1 (RED): all tests fail because:
  - categories.py does not yet have the crm field
  - OrgAIConfig does not yet have health_weight_crm
Phase 5 (GREEN): all tests pass after route update.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.models.organization import Organization
from src.models.user import User
from src.models.org_ai_config import OrgAIConfig
from src.api.auth import hash_password, create_access_token


# ---------------------------------------------------------------------------
# Fixtures — owner user with p4 suffix (matches test_health_usage_component)
# ---------------------------------------------------------------------------

@pytest.fixture
def owner_user_p4(db: Session, test_organization: Organization) -> User:
    user = User(
        email="p4_owner_6w@example.com",
        password_hash=hash_password("password123"),
        organization_id=test_organization.id,
        role="owner",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def owner_headers_p4(owner_user_p4: User) -> dict:
    token = create_access_token({
        "user_id": owner_user_p4.id,
        "organization_id": owner_user_p4.organization_id,
        "role": owner_user_p4.role,
    })
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# 6-weight API tests
# ---------------------------------------------------------------------------

class TestHealthWeightsApiSixFields:
    """PUT /api/v1/categories/health-weights: 6-weight set including crm."""

    def test_put_6_fields_summing_100_returns_200(self, client, owner_headers_p4):
        """35+25+20+10+5+5=100 with crm=5 returns 200."""
        response = client.put(
            "/api/v1/categories/health-weights", headers=owner_headers_p4,
            json={"churn": 35, "sentiment": 25, "resolution": 20,
                  "frequency": 10, "usage": 5, "crm": 5},
        )
        assert response.status_code == 200
        assert response.json()["crm"] == 5

    def test_put_6_fields_not_summing_100_returns_422(self, client, owner_headers_p4):
        """35+25+25+15+0+10=110 → 422."""
        response = client.put(
            "/api/v1/categories/health-weights", headers=owner_headers_p4,
            json={"churn": 35, "sentiment": 25, "resolution": 25,
                  "frequency": 15, "usage": 0, "crm": 10},
        )
        assert response.status_code == 422

    def test_put_5_fields_crm_omitted_still_sums_100(self, client, owner_headers_p4):
        """With crm omitted (defaults to 0), existing 5-field=100 body still works."""
        response = client.put(
            "/api/v1/categories/health-weights", headers=owner_headers_p4,
            json={"churn": 35, "sentiment": 25, "resolution": 25,
                  "frequency": 15, "usage": 0},
        )
        assert response.status_code == 200
        assert response.json()["crm"] == 0

    def test_put_crm_weight_persists_to_org_ai_config(
        self, client, owner_headers_p4, db, test_organization
    ):
        """health_weight_crm is written to OrgAIConfig after PUT."""
        client.put(
            "/api/v1/categories/health-weights", headers=owner_headers_p4,
            json={"churn": 30, "sentiment": 25, "resolution": 25,
                  "frequency": 15, "usage": 0, "crm": 5},
        )
        config = db.query(OrgAIConfig).filter_by(
            organization_id=test_organization.id
        ).first()
        assert config is not None
        assert config.health_weight_crm == 5

    def test_get_returns_crm_key_with_default_zero(self, client, owner_headers_p4):
        """GET /api/v1/categories/health-weights returns 'crm': 0 by default."""
        response = client.get(
            "/api/v1/categories/health-weights", headers=owner_headers_p4
        )
        assert response.status_code == 200
        data = response.json()
        assert "crm" in data
        assert data["crm"] == 0

    def test_get_returns_configured_crm_weight(
        self, client, owner_headers_p4, db, test_organization
    ):
        """After PUT crm=8, GET returns crm=8."""
        client.put(
            "/api/v1/categories/health-weights", headers=owner_headers_p4,
            json={"churn": 35, "sentiment": 22, "resolution": 20,
                  "frequency": 15, "usage": 0, "crm": 8},
        )
        response = client.get(
            "/api/v1/categories/health-weights", headers=owner_headers_p4
        )
        assert response.json()["crm"] == 8

    def test_5_field_body_summing_110_still_rejected(
        self, client, owner_headers_p4
    ):
        """Old 5-field body that summed to 110 must still be rejected (crm defaults 0 → total 110)."""
        response = client.put(
            "/api/v1/categories/health-weights", headers=owner_headers_p4,
            json={"churn": 35, "sentiment": 25, "resolution": 25,
                  "frequency": 15, "usage": 10},  # 110, crm=0 → still 110
        )
        assert response.status_code == 422
