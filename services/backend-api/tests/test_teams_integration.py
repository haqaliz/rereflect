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