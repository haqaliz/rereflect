"""
Tests for POST /api/v1/feedback/{id}/responses/send endpoint.

TDD order:
1. Clipboard channel — saves status='copied', returns success=True
2. Send via Slack — dispatches to response_sender, saves status accordingly
3. Send via email — dispatches when customer_email present
4. Send failure — saves status='send_failed' with error_message
5. Missing feedback → 404
6. Auth checks
7. Variable resolution service unit tests
"""

import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.models.feedback import FeedbackItem
from src.models.feedback_response import FeedbackResponse
from src.models.organization import Organization
from src.models.user import User


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def feedback_item(db: Session, test_organization: Organization) -> FeedbackItem:
    item = FeedbackItem(
        organization_id=test_organization.id,
        text="The export button crashes every time.",
        source="slack",
        sentiment_label="negative",
        is_urgent=False,
        pain_point_category="Bug Report",
        churn_risk_score=30,
        customer_email="customer@example.com",
        source_metadata={"channel_id": "C123", "thread_ts": "1234567890.000100"},
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def _send_payload(
    channel: str = "clipboard",
    source: str = "template",
    template_id: int = None,
    tone: str = None,
    response_text: str = "Thank you for your feedback!",
) -> dict:
    return {
        "response_text": response_text,
        "channel": channel,
        "source": source,
        "template_id": template_id,
        "tone": tone,
    }


# ============================================================================
# Clipboard channel
# ============================================================================

class TestSendViaClipboard:
    def test_clipboard_saves_with_copied_status(
        self,
        client: TestClient,
        auth_headers: dict,
        db: Session,
        feedback_item: FeedbackItem,
        test_organization: Organization,
    ):
        response = client.post(
            f"/api/v1/feedback/{feedback_item.id}/responses/send",
            json=_send_payload(channel="clipboard", source="template", template_id=1),
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["channel"] == "clipboard"
        assert data["error"] is None

        # Verify the record in DB
        db.expire_all()
        record = (
            db.query(FeedbackResponse)
            .filter(FeedbackResponse.feedback_id == feedback_item.id)
            .first()
        )
        assert record is not None
        assert record.status == "copied"
        assert record.channel == "clipboard"
        assert record.source == "template"
        assert record.template_id == 1

    def test_clipboard_returns_response_id(
        self,
        client: TestClient,
        auth_headers: dict,
        feedback_item: FeedbackItem,
    ):
        response = client.post(
            f"/api/v1/feedback/{feedback_item.id}/responses/send",
            json=_send_payload(channel="clipboard"),
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data["response_id"], int)
        assert data["response_id"] > 0

    def test_manual_source_saved_correctly(
        self,
        client: TestClient,
        auth_headers: dict,
        db: Session,
        feedback_item: FeedbackItem,
    ):
        response = client.post(
            f"/api/v1/feedback/{feedback_item.id}/responses/send",
            json=_send_payload(channel="clipboard", source="manual"),
            headers=auth_headers,
        )
        assert response.status_code == 200

        db.expire_all()
        record = db.query(FeedbackResponse).filter(
            FeedbackResponse.feedback_id == feedback_item.id
        ).first()
        assert record.source == "manual"

    def test_ai_generated_source_saved_with_tone(
        self,
        client: TestClient,
        auth_headers: dict,
        db: Session,
        feedback_item: FeedbackItem,
    ):
        response = client.post(
            f"/api/v1/feedback/{feedback_item.id}/responses/send",
            json=_send_payload(channel="clipboard", source="ai_generated", tone="empathetic"),
            headers=auth_headers,
        )
        assert response.status_code == 200

        db.expire_all()
        record = db.query(FeedbackResponse).filter(
            FeedbackResponse.feedback_id == feedback_item.id
        ).first()
        assert record.source == "ai_generated"
        assert record.tone == "empathetic"


# ============================================================================
# Send via Slack
# ============================================================================

class TestSendViaSlack:
    def test_slack_success_saves_sent_status(
        self,
        client: TestClient,
        auth_headers: dict,
        db: Session,
        feedback_item: FeedbackItem,
    ):
        """When Slack send succeeds, status should be 'sent'."""
        with patch(
            "src.api.routes.feedback_responses._get_integration_token",
            return_value="slack-token-xyz",
        ):
            with patch(
                "src.services.response_sender.send_via_slack",
                new_callable=AsyncMock,
                return_value={"success": True, "error": None},
            ):
                response = client.post(
                    f"/api/v1/feedback/{feedback_item.id}/responses/send",
                    json=_send_payload(channel="slack", source="template"),
                    headers=auth_headers,
                )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["channel"] == "slack"

        db.expire_all()
        record = db.query(FeedbackResponse).filter(
            FeedbackResponse.feedback_id == feedback_item.id
        ).first()
        assert record.status == "sent"
        assert record.error_message is None

    def test_slack_failure_saves_send_failed_status(
        self,
        client: TestClient,
        auth_headers: dict,
        db: Session,
        feedback_item: FeedbackItem,
    ):
        """When Slack send fails, status should be 'send_failed' with error_message."""
        with patch(
            "src.api.routes.feedback_responses._get_integration_token",
            return_value="slack-token-xyz",
        ):
            with patch(
                "src.services.response_sender.send_via_slack",
                new_callable=AsyncMock,
                return_value={"success": False, "error": "token_revoked"},
            ):
                response = client.post(
                    f"/api/v1/feedback/{feedback_item.id}/responses/send",
                    json=_send_payload(channel="slack", source="ai_generated"),
                    headers=auth_headers,
                )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert data["error"] == "token_revoked"

        db.expire_all()
        record = db.query(FeedbackResponse).filter(
            FeedbackResponse.feedback_id == feedback_item.id
        ).first()
        assert record.status == "send_failed"
        assert record.error_message == "token_revoked"

    def test_slack_no_integration_token(
        self,
        client: TestClient,
        auth_headers: dict,
        feedback_item: FeedbackItem,
    ):
        """When no Slack integration is connected, should save as send_failed."""
        with patch(
            "src.api.routes.feedback_responses._get_integration_token",
            return_value=None,
        ):
            response = client.post(
                f"/api/v1/feedback/{feedback_item.id}/responses/send",
                json=_send_payload(channel="slack", source="template"),
                headers=auth_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "not connected" in data["error"].lower()


# ============================================================================
# Send via Email
# ============================================================================

class TestSendViaEmail:
    def test_email_send_success(
        self,
        client: TestClient,
        auth_headers: dict,
        db: Session,
        feedback_item: FeedbackItem,
    ):
        """Should send email to customer_email and return success."""
        with patch(
            "src.services.response_sender.send_via_email",
            new_callable=AsyncMock,
            return_value={"success": True, "error": None},
        ):
            response = client.post(
                f"/api/v1/feedback/{feedback_item.id}/responses/send",
                json=_send_payload(channel="email", source="template"),
                headers=auth_headers,
            )

        assert response.status_code == 200
        assert response.json()["success"] is True

    def test_email_fails_when_no_customer_email(
        self,
        client: TestClient,
        auth_headers: dict,
        db: Session,
        test_organization: Organization,
    ):
        """Feedback without customer_email should result in send_failed."""
        fb = FeedbackItem(
            organization_id=test_organization.id,
            text="No email feedback",
            source="email",
            sentiment_label="neutral",
            customer_email=None,
        )
        db.add(fb)
        db.commit()
        db.refresh(fb)

        response = client.post(
            f"/api/v1/feedback/{fb.id}/responses/send",
            json=_send_payload(channel="email", source="manual"),
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "email" in data["error"].lower()


# ============================================================================
# Error cases
# ============================================================================

class TestSendErrors:
    def test_send_returns_404_for_missing_feedback(
        self, client: TestClient, auth_headers: dict
    ):
        response = client.post(
            "/api/v1/feedback/99999/responses/send",
            json=_send_payload(),
            headers=auth_headers,
        )
        assert response.status_code == 404

    def test_send_requires_auth(self, client: TestClient, feedback_item: FeedbackItem):
        response = client.post(
            f"/api/v1/feedback/{feedback_item.id}/responses/send",
            json=_send_payload(),
        )
        assert response.status_code in (401, 403)

    def test_send_requires_pro_plan(
        self, client: TestClient, db: Session, test_organization: Organization, feedback_item: FeedbackItem
    ):
        from src.api.auth import hash_password, create_access_token

        test_organization.plan = "free"
        db.commit()
        db.refresh(test_organization)

        free_user = User(
            email="free_send@example.com",
            password_hash=hash_password("password123"),
            organization_id=test_organization.id,
            role="admin",
        )
        db.add(free_user)
        db.commit()
        db.refresh(free_user)
        token = create_access_token({
            "user_id": free_user.id,
            "organization_id": free_user.organization_id,
            "role": free_user.role,
        })
        headers = {"Authorization": f"Bearer {token}"}

        response = client.post(
            f"/api/v1/feedback/{feedback_item.id}/responses/send",
            json=_send_payload(),
            headers=headers,
        )
        assert response.status_code == 403


# ============================================================================
# Variable resolution unit tests
# ============================================================================

class TestResolveVariables:
    def test_resolves_customer_name_from_source_metadata(
        self, db: Session, test_organization: Organization
    ):
        from src.services.response_generator import resolve_variables

        feedback = FeedbackItem(
            organization_id=test_organization.id,
            text="Something is broken.",
            source="slack",
            sentiment_label="negative",
            source_metadata={"author_name": "Sarah Chen"},
        )
        db.add(feedback)
        db.commit()
        db.refresh(feedback)

        test_organization.product_name_display = "Rereflect"
        db.commit()

        result = resolve_variables(
            "Hi {{customer_name}}, we got your report for {{product_name}}.",
            feedback,
            test_organization,
            user=None,
        )
        assert "Sarah Chen" in result
        assert "Rereflect" in result

    def test_resolves_feedback_excerpt_to_200_chars(
        self, db: Session, test_organization: Organization
    ):
        from src.services.response_generator import resolve_variables

        long_text = "a" * 300
        feedback = FeedbackItem(
            organization_id=test_organization.id,
            text=long_text,
            source="email",
            sentiment_label="neutral",
        )
        db.add(feedback)
        db.commit()
        db.refresh(feedback)

        result = resolve_variables("{{feedback_excerpt}}", feedback, test_organization)
        assert result == "a" * 200

    def test_unknown_variable_resolves_to_empty_string(
        self, db: Session, test_organization: Organization
    ):
        from src.services.response_generator import resolve_variables

        feedback = FeedbackItem(
            organization_id=test_organization.id,
            text="Hello.",
            source="email",
            sentiment_label="neutral",
        )
        db.add(feedback)
        db.commit()
        db.refresh(feedback)

        result = resolve_variables("{{unknown_var}} text", feedback, test_organization)
        assert result == " text"

    def test_resolves_agent_name_from_user_email(
        self, db: Session, test_organization: Organization, test_user: User
    ):
        from src.services.response_generator import resolve_variables

        feedback = FeedbackItem(
            organization_id=test_organization.id,
            text="Hello.",
            source="email",
            sentiment_label="neutral",
        )
        db.add(feedback)
        db.commit()
        db.refresh(feedback)

        result = resolve_variables("Thanks, {{agent_name}}", feedback, test_organization, user=test_user)
        # Email is test@example.com → agent_name = "test"
        assert "test" in result

    def test_resolves_support_email_from_org_settings(
        self, db: Session, test_organization: Organization
    ):
        from src.services.response_generator import resolve_variables

        test_organization.support_email_display = "help@myapp.com"
        db.commit()

        feedback = FeedbackItem(
            organization_id=test_organization.id,
            text="Issue here.",
            source="email",
            sentiment_label="negative",
        )
        db.add(feedback)
        db.commit()
        db.refresh(feedback)

        result = resolve_variables("Contact {{support_email}}", feedback, test_organization)
        assert "help@myapp.com" in result
