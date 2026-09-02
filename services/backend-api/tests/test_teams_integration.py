"""
Tests for the Microsoft Teams integration (backend connector).

Teams is webhook-only, like Discord: the webhook URL carries its own
credential, so there is no OAuth flow. These tests pin the validator, the
MessageCard sender contract and the route bookkeeping, mirroring the Discord
coverage in test_integrations.py.
"""

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.orm import Session

from src.models.integration import Integration
from src.models.organization import Organization

CLASSIC_WEBHOOK_URL = (
    "https://outlook.office.com/webhook/"
    "11111111-2222-3333-4444-555555555555@11111111-2222-3333-4444-555555555555/"
    "IncomingWebhook/11111111222233334444555555555555/11111111-2222-3333-4444-555555555555"
)
WORKFLOWS_WEBHOOK_URL = (
    "https://acme.webhook.office.com/webhookb2/"
    "11111111-2222-3333-4444-555555555555@11111111-2222-3333-4444-555555555555/"
    "IncomingWebhook/11111111222233334444555555555555/11111111-2222-3333-4444-555555555555"
)


class TestTeamsWebhookRequestModels:
    """TeamsWebhookCreateRequest / TeamsTestRequest validation."""

    def test_accepts_classic_outlook_office_url(self):
        from src.api.routes.integrations import TeamsWebhookCreateRequest

        model = TeamsWebhookCreateRequest(
            name="Classic Teams",
            webhook_url=CLASSIC_WEBHOOK_URL,
            triggers=["urgent"],
        )

        assert model.webhook_url == CLASSIC_WEBHOOK_URL

    def test_accepts_workflows_webhook_office_url(self):
        from src.api.routes.integrations import TeamsWebhookCreateRequest

        model = TeamsWebhookCreateRequest(
            name="Workflows Teams",
            webhook_url=WORKFLOWS_WEBHOOK_URL,
            triggers=["urgent"],
        )

        assert model.webhook_url == WORKFLOWS_WEBHOOK_URL

    def test_rejects_arbitrary_host_with_message_naming_accepted_hosts(self):
        from src.api.routes.integrations import TeamsWebhookCreateRequest

        with pytest.raises(ValidationError) as exc_info:
            TeamsWebhookCreateRequest(
                name="Not Teams",
                webhook_url="https://example.com/x",
                triggers=["urgent"],
            )

        message = str(exc_info.value)
        assert "outlook.office.com/webhook" in message
        assert "webhookb2" in message

    def test_test_request_requires_integration_id(self):
        from src.api.routes.integrations import TeamsTestRequest

        model = TeamsTestRequest(integration_id=42)

        assert model.integration_id == 42


class TestCreateTeamsWebhook:
    """POST /api/v1/integrations/teams/webhook endpoint."""

    def test_create_teams_webhook_success(
        self, client: TestClient, auth_headers: dict, db: Session,
        test_organization: Organization,
    ):
        response = client.post(
            "/api/v1/integrations/teams/webhook",
            headers=auth_headers,
            json={
                "name": "Eng Alerts",
                "webhook_url": CLASSIC_WEBHOOK_URL,
                "triggers": ["urgent"],
                "included_fields": ["text", "sentiment"],
                "digest_time": "09:00",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Eng Alerts"
        assert data["type"] == "teams"
        assert data["is_active"] is True
        assert data["integration_type"] == "webhook"

        integration = db.query(Integration).filter(
            Integration.organization_id == test_organization.id,
            Integration.type == "teams",
        ).first()
        assert integration is not None
        assert integration.config == {
            "webhook_url": CLASSIC_WEBHOOK_URL,
            "integration_type": "webhook",
        }

    def test_create_teams_webhook_accepts_workflows_url(
        self, client: TestClient, auth_headers: dict
    ):
        response = client.post(
            "/api/v1/integrations/teams/webhook",
            headers=auth_headers,
            json={
                "name": "Workflows",
                "webhook_url": WORKFLOWS_WEBHOOK_URL,
                "triggers": ["urgent"],
            },
        )

        assert response.status_code == 201

    def test_create_teams_webhook_rejects_arbitrary_host(
        self, client: TestClient, auth_headers: dict
    ):
        response = client.post(
            "/api/v1/integrations/teams/webhook",
            headers=auth_headers,
            json={
                "name": "Not Teams",
                "webhook_url": "https://example.com/x",
                "triggers": ["urgent"],
            },
        )

        assert response.status_code == 422
        message = str(response.json()["detail"])
        assert "outlook.office.com/webhook" in message
        assert "webhookb2" in message

    def test_member_cannot_create_teams_webhook(
        self, client: TestClient, db: Session, test_organization: Organization
    ):
        from src.api.auth import hash_password, create_access_token
        from src.models.user import User

        member = User(
            email="teams-member@example.com",
            password_hash=hash_password("password123"),
            organization_id=test_organization.id,
            role="member",
        )
        db.add(member)
        db.commit()
        token = create_access_token({
            "user_id": member.id,
            "organization_id": member.organization_id,
            "role": member.role,
        })

        response = client.post(
            "/api/v1/integrations/teams/webhook",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "name": "Member Attempt",
                "webhook_url": CLASSIC_WEBHOOK_URL,
                "triggers": ["urgent"],
            },
        )

        assert response.status_code == 403


class TestTeamsMessageCard:
    """build_teams_message_card / send_teams_message backend contract."""

    def test_build_teams_message_card_shape(self):
        from src.api.routes.integrations import build_teams_message_card

        card = build_teams_message_card(
            "Rereflect test message",
            "Your integration is working correctly.",
            summary="Summary",
        )

        assert card == {
            "@type": "MessageCard",
            "@context": "http://schema.org/extensions",
            "summary": "Summary",
            "title": "Rereflect test message",
            "text": "Your integration is working correctly.",
            "themeColor": "6264A7",
        }

    def test_build_teams_message_card_summary_defaults_to_title(self):
        from src.api.routes.integrations import build_teams_message_card

        card = build_teams_message_card("My Title", "Body text")

        assert card["summary"] == "My Title"

    def test_send_teams_message_posts_message_card(self):
        import httpx
        from unittest.mock import MagicMock, patch

        from src.api.routes.integrations import send_teams_message

        mock_response = MagicMock()
        mock_response.text = "ok"
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.post.return_value = (
                mock_response
            )
            result = send_teams_message(
                WORKFLOWS_WEBHOOK_URL,
                title="Rereflect test message",
                text="Your integration is working correctly.",
                summary="Summary",
            )

        assert result["success"] is True
        assert result["response"] == "ok"
        post_kwargs = mock_client.return_value.__enter__.return_value.post.call_args.kwargs
        assert post_kwargs["json"] == {
            "@type": "MessageCard",
            "@context": "http://schema.org/extensions",
            "summary": "Summary",
            "title": "Rereflect test message",
            "text": "Your integration is working correctly.",
            "themeColor": "6264A7",
        }
        assert mock_client.return_value.__enter__.return_value.post.call_args.args[0] == WORKFLOWS_WEBHOOK_URL

    def test_send_teams_message_never_raises_on_http_error(self):
        import httpx
        from unittest.mock import patch

        from src.api.routes.integrations import send_teams_message

        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.post.side_effect = (
                httpx.HTTPError("boom")
            )
            result = send_teams_message(
                CLASSIC_WEBHOOK_URL,
                title="Rereflect test message",
                text="Your integration is working correctly.",
            )

        assert result["success"] is False
        assert "boom" in result["error"]