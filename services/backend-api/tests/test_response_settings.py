"""
Tests for Response Settings endpoints.

TDD order:
1. GET /response-settings — returns org settings
2. PUT /response-settings — updates settings (admin/owner)
3. GET /response-settings/usage — returns usage counters
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.api.auth import hash_password, create_access_token
from src.models.feedback import FeedbackItem
from src.models.feedback_response import FeedbackResponse
from src.models.organization import Organization
from src.models.user import User


# ============================================================================
# Helpers
# ============================================================================

def _member_headers(db: Session, org: Organization) -> dict:
    member = User(
        email="member_settings@example.com",
        password_hash=hash_password("password123"),
        organization_id=org.id,
        role="member",
    )
    db.add(member)
    db.commit()
    db.refresh(member)
    token = create_access_token({"user_id": member.id, "organization_id": member.organization_id, "role": member.role})
    return {"Authorization": f"Bearer {token}"}


# ============================================================================
# 1. GET /api/v1/response-settings
# ============================================================================

class TestGetResponseSettings:
    def test_get_returns_settings(
        self, client: TestClient, auth_headers: dict, db: Session, test_organization: Organization
    ):
        """Should return brand_voice, default_tone, product_name_display, support_email_display."""
        test_organization.brand_voice = "Keep it concise."
        test_organization.default_tone = "professional"
        test_organization.product_name_display = "TestApp"
        test_organization.support_email_display = "help@testapp.com"
        db.commit()

        response = client.get("/api/v1/response-settings", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["brand_voice"] == "Keep it concise."
        assert data["default_tone"] == "professional"
        assert data["product_name_display"] == "TestApp"
        assert data["support_email_display"] == "help@testapp.com"

    def test_get_returns_nulls_when_not_set(
        self, client: TestClient, auth_headers: dict, db: Session, test_organization: Organization
    ):
        """Settings that have not been configured return null."""
        test_organization.brand_voice = None
        test_organization.product_name_display = None
        db.commit()

        response = client.get("/api/v1/response-settings", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["brand_voice"] is None
        assert data["product_name_display"] is None

    def test_get_requires_auth(self, client: TestClient):
        response = client.get("/api/v1/response-settings")
        assert response.status_code in (401, 403)

    def test_get_requires_pro_plan(
        self, client: TestClient, db: Session, test_organization: Organization
    ):
        """Free-plan org gets 403."""
        test_organization.plan = "free"
        db.commit()
        db.refresh(test_organization)

        user = User(
            email="free2@example.com",
            password_hash=hash_password("password123"),
            organization_id=test_organization.id,
            role="admin",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        token = create_access_token({"user_id": user.id, "organization_id": user.organization_id, "role": user.role})
        headers = {"Authorization": f"Bearer {token}"}

        response = client.get("/api/v1/response-settings", headers=headers)
        assert response.status_code == 403

    def test_member_can_read_settings(
        self, client: TestClient, db: Session, test_organization: Organization
    ):
        """Members can read settings (read-only)."""
        headers = _member_headers(db, test_organization)
        response = client.get("/api/v1/response-settings", headers=headers)
        assert response.status_code == 200


# ============================================================================
# 2. PUT /api/v1/response-settings
# ============================================================================

class TestUpdateResponseSettings:
    def test_update_brand_voice(
        self, client: TestClient, auth_headers: dict, db: Session, test_organization: Organization
    ):
        """Admin can update brand_voice."""
        payload = {"brand_voice": "We are developer tools. Keep it technical."}
        response = client.put("/api/v1/response-settings", json=payload, headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["brand_voice"] == "We are developer tools. Keep it technical."

        db.refresh(test_organization)
        assert test_organization.brand_voice == "We are developer tools. Keep it technical."

    def test_update_default_tone(
        self, client: TestClient, auth_headers: dict, db: Session, test_organization: Organization
    ):
        payload = {"default_tone": "empathetic"}
        response = client.put("/api/v1/response-settings", json=payload, headers=auth_headers)

        assert response.status_code == 200
        assert response.json()["default_tone"] == "empathetic"

    def test_update_product_name_and_support_email(
        self, client: TestClient, auth_headers: dict, db: Session, test_organization: Organization
    ):
        payload = {
            "product_name_display": "MyApp Pro",
            "support_email_display": "support@myapp.com",
        }
        response = client.put("/api/v1/response-settings", json=payload, headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["product_name_display"] == "MyApp Pro"
        assert data["support_email_display"] == "support@myapp.com"

    def test_partial_update_preserves_other_fields(
        self, client: TestClient, auth_headers: dict, db: Session, test_organization: Organization
    ):
        """Only provided fields are updated; others remain unchanged."""
        test_organization.brand_voice = "Original voice"
        test_organization.default_tone = "professional"
        db.commit()

        payload = {"default_tone": "friendly"}
        response = client.put("/api/v1/response-settings", json=payload, headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["default_tone"] == "friendly"
        assert data["brand_voice"] == "Original voice"  # unchanged

    def test_update_requires_admin_or_owner(
        self, client: TestClient, db: Session, test_organization: Organization
    ):
        """Members cannot update settings."""
        headers = _member_headers(db, test_organization)
        payload = {"brand_voice": "Hacked!"}
        response = client.put("/api/v1/response-settings", json=payload, headers=headers)
        assert response.status_code == 403

    def test_update_requires_auth(self, client: TestClient):
        response = client.put("/api/v1/response-settings", json={"default_tone": "friendly"})
        assert response.status_code in (401, 403)

    def test_brand_voice_max_length_enforced(
        self, client: TestClient, auth_headers: dict
    ):
        """brand_voice longer than 500 chars should be rejected."""
        payload = {"brand_voice": "x" * 501}
        response = client.put("/api/v1/response-settings", json=payload, headers=auth_headers)
        assert response.status_code == 422


# ============================================================================
# 3. GET /api/v1/response-settings/usage
# ============================================================================

class TestGetResponseUsage:
    def test_usage_returns_correct_fields(
        self, client: TestClient, auth_headers: dict
    ):
        """Should return ai_responses_generated, monthly_limit, templates_used, responses_sent."""
        response = client.get("/api/v1/response-settings/usage", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert "ai_responses_generated" in data
        assert "monthly_limit" in data
        assert "templates_used" in data
        assert "responses_sent" in data

    def test_usage_monthly_limit_pro_plan(
        self, client: TestClient, auth_headers: dict, test_organization: Organization
    ):
        """Pro plan has a monthly limit of 50 AI responses."""
        assert test_organization.plan == "pro"
        response = client.get("/api/v1/response-settings/usage", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["monthly_limit"] == 50

    def test_usage_monthly_limit_enterprise_is_unlimited(
        self, client: TestClient, db: Session, test_organization: Organization
    ):
        """Enterprise plan returns -1 for monthly_limit."""
        test_organization.plan = "enterprise"
        db.commit()
        db.refresh(test_organization)

        user = User(
            email="enterprise@example.com",
            password_hash=hash_password("password123"),
            organization_id=test_organization.id,
            role="admin",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        token = create_access_token({"user_id": user.id, "organization_id": user.organization_id, "role": user.role})
        headers = {"Authorization": f"Bearer {token}"}

        response = client.get("/api/v1/response-settings/usage", headers=headers)
        assert response.status_code == 200
        assert response.json()["monthly_limit"] == -1

    def test_usage_counts_ai_responses_generated(
        self, client: TestClient, auth_headers: dict, db: Session, test_organization: Organization
    ):
        """ai_responses_generated reflects the counter on the org."""
        test_organization.ai_responses_generated = 12
        db.commit()

        response = client.get("/api/v1/response-settings/usage", headers=auth_headers)

        assert response.status_code == 200
        assert response.json()["ai_responses_generated"] == 12

    def test_usage_counts_templates_used_this_period(
        self, client: TestClient, auth_headers: dict, db: Session, test_organization: Organization
    ):
        """templates_used counts FeedbackResponses with source='template' in current period."""
        # Create a feedback item for the org
        feedback = FeedbackItem(
            organization_id=test_organization.id,
            text="Test feedback",
            source="email",
            sentiment_label="positive",
        )
        db.add(feedback)
        db.commit()
        db.refresh(feedback)

        # Create two template-sourced responses
        for _ in range(2):
            fr = FeedbackResponse(
                feedback_id=feedback.id,
                organization_id=test_organization.id,
                response_text="A response",
                channel="clipboard",
                source="template",
                status="copied",
            )
            db.add(fr)
        db.commit()

        response = client.get("/api/v1/response-settings/usage", headers=auth_headers)
        assert response.json()["templates_used"] == 2

    def test_usage_counts_responses_sent_this_period(
        self, client: TestClient, auth_headers: dict, db: Session, test_organization: Organization
    ):
        """responses_sent counts non-clipboard sent responses in current period."""
        feedback = FeedbackItem(
            organization_id=test_organization.id,
            text="Test",
            source="email",
            sentiment_label="negative",
        )
        db.add(feedback)
        db.commit()
        db.refresh(feedback)

        # One sent via Slack, one copied (clipboard should not count)
        fr1 = FeedbackResponse(
            feedback_id=feedback.id,
            organization_id=test_organization.id,
            response_text="Sent response",
            channel="slack",
            source="template",
            status="sent",
        )
        fr2 = FeedbackResponse(
            feedback_id=feedback.id,
            organization_id=test_organization.id,
            response_text="Copied response",
            channel="clipboard",
            source="manual",
            status="copied",
        )
        db.add(fr1)
        db.add(fr2)
        db.commit()

        response = client.get("/api/v1/response-settings/usage", headers=auth_headers)
        assert response.json()["responses_sent"] == 1

    def test_usage_requires_auth(self, client: TestClient):
        response = client.get("/api/v1/response-settings/usage")
        assert response.status_code in (401, 403)
