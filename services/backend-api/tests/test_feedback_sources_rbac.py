"""
RBAC tests for feedback-sources routes.

Per the permission matrix, integration management is Owner/Admin only, so the
three WRITE routes (POST /, PATCH /{source_id}, DELETE /{source_id}) must
return 403 for `member`-role users. All GET routes stay member-open because
they back member-reachable pages.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.models import FeedbackSource
from src.models.organization import Organization
from src.models.user import User
from src.api.auth import hash_password, create_access_token


@pytest.fixture
def member_user(db: Session, test_organization: Organization) -> User:
    user = User(
        email="fs_rbac_member@test.com",
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
def existing_source(db: Session, test_organization: Organization) -> FeedbackSource:
    source = FeedbackSource(
        organization_id=test_organization.id,
        source_type="webhook",
        name="RBAC Test Source",
        provider_config={"webhook_id": "rbac-test-webhook"},
        triggers={},
        field_mapping={},
        auto_import=True,
    )
    db.add(source)
    db.commit()
    db.refresh(source)
    return source


class TestFeedbackSourcesWriteRbac:

    def test_member_cannot_create_feedback_source(self, client: TestClient, member_headers: dict):
        response = client.post(
            "/api/v1/feedback-sources/",
            json={"source_type": "webhook", "name": "Member Attempt"},
            headers=member_headers,
        )
        assert response.status_code == 403

    def test_member_cannot_update_feedback_source(
        self, client: TestClient, member_headers: dict, existing_source: FeedbackSource
    ):
        response = client.patch(
            f"/api/v1/feedback-sources/{existing_source.id}",
            json={"name": "Hijacked Name"},
            headers=member_headers,
        )
        assert response.status_code == 403

    def test_member_cannot_delete_feedback_source(
        self, client: TestClient, member_headers: dict, existing_source: FeedbackSource
    ):
        response = client.delete(
            f"/api/v1/feedback-sources/{existing_source.id}",
            headers=member_headers,
        )
        assert response.status_code == 403


class TestFeedbackSourcesReadStaysOpen:

    def test_member_can_list_feedback_sources(self, client: TestClient, member_headers: dict):
        response = client.get("/api/v1/feedback-sources/", headers=member_headers)
        assert response.status_code == 200
