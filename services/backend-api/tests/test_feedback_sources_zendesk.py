"""
TDD tests for registering `zendesk` as a selectable feedback-source type.

Zendesk brings its own auth (like Linear/Jira) so it must be:
- listed in GET /api/v1/feedback-sources/types with requires_integration=False,
  available=True
- accepted as a valid `source_type` on POST /api/v1/feedback-sources (no
  feature-gating branch, no integration_id/provider_config hydration)
- creatable on a FREE-plan org (unlocked, no plan gate)

No inbound ingestion / worker behaviour is covered here.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.models.organization import Organization
from src.models.user import User
from src.api.auth import hash_password, create_access_token


@pytest.fixture
def free_org(db: Session) -> Organization:
    org = Organization(name="Free Zendesk Source Org", plan="free")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


@pytest.fixture
def free_user_headers(db: Session, free_org: Organization) -> dict:
    user = User(
        email="zendesk-free-user@test.com",
        password_hash=hash_password("password123"),
        organization_id=free_org.id,
        role="admin",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_access_token({
        "user_id": user.id,
        "organization_id": free_org.id,
        "role": user.role,
    })
    return {"Authorization": f"Bearer {token}"}


class TestZendeskSourceTypeListed:

    def test_types_endpoint_includes_zendesk(self, client: TestClient, free_user_headers: dict):
        response = client.get("/api/v1/feedback-sources/types", headers=free_user_headers)
        assert response.status_code == 200
        types = {entry["type"] for entry in response.json()}
        assert "zendesk" in types

    def test_zendesk_entry_requires_no_integration(self, client: TestClient, free_user_headers: dict):
        response = client.get("/api/v1/feedback-sources/types", headers=free_user_headers)
        zendesk_entry = next(e for e in response.json() if e["type"] == "zendesk")
        assert zendesk_entry["requires_integration"] is False

    def test_zendesk_entry_is_available(self, client: TestClient, free_user_headers: dict):
        response = client.get("/api/v1/feedback-sources/types", headers=free_user_headers)
        zendesk_entry = next(e for e in response.json() if e["type"] == "zendesk")
        assert zendesk_entry["available"] is True


class TestCreateZendeskFeedbackSource:

    def test_free_plan_org_can_create_zendesk_source(self, client: TestClient, free_user_headers: dict):
        """No plan gate blocks `zendesk` source creation on a FREE-plan org."""
        response = client.post(
            "/api/v1/feedback-sources/",
            json={"source_type": "zendesk", "name": "My Zendesk Source"},
            headers=free_user_headers,
        )
        assert response.status_code == 201

    def test_created_zendesk_source_has_expected_fields(self, client: TestClient, free_user_headers: dict):
        response = client.post(
            "/api/v1/feedback-sources/",
            json={"source_type": "zendesk", "name": "My Zendesk Source"},
            headers=free_user_headers,
        )
        data = response.json()
        assert data["source_type"] == "zendesk"
        assert data["integration_id"] is None

    def test_bogus_source_type_is_rejected(self, client: TestClient, free_user_headers: dict):
        """A source_type outside `valid_types` must still be rejected (existing
        validation behaviour returns 400, not 201)."""
        response = client.post(
            "/api/v1/feedback-sources/",
            json={"source_type": "not_a_real_source", "name": "Bogus"},
            headers=free_user_headers,
        )
        assert response.status_code == 400
