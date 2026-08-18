"""
Tests for integrations endpoints.
"""

import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from unittest.mock import patch, MagicMock

from src.models import FeedbackSource
from src.models.integration import Integration
from src.models.user import User
from src.models.organization import Organization
from src.api.auth import hash_password, create_access_token
from src.utils.encryption import encrypt_api_key, decrypt_api_key

TEST_FERNET_KEY = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="


@pytest.fixture
def member_user(db: Session, test_organization: Organization) -> User:
    """Create a member-role user in the test org."""
    user = User(
        email="member@example.com",
        password_hash=hash_password("password123"),
        organization_id=test_organization.id,
        role="member",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def member_headers(member_user: User) -> dict:
    """Auth headers for a member-role user."""
    token = create_access_token({
        "user_id": member_user.id,
        "organization_id": member_user.organization_id,
        "role": member_user.role,
    })
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def test_integration(db: Session, test_organization: Organization) -> Integration:
    """Create a test Slack integration."""
    integration = Integration(
        organization_id=test_organization.id,
        type="slack",
        name="Test Slack Channel",
        config={
            "webhook_url": "https://hooks.slack.com/services/TEST/WEBHOOK/URL",
            "integration_type": "webhook"
        },
        triggers=["urgent", "negative"],
        included_fields=["text", "sentiment"],
        is_active=True,
    )
    db.add(integration)
    db.commit()
    db.refresh(integration)
    return integration


class TestListIntegrations:
    """Tests for GET /api/v1/integrations endpoint."""

    def test_list_integrations_empty(
        self,
        client: TestClient,
        auth_headers: dict
    ):
        """Test listing integrations when none exist."""
        response = client.get(
            "/api/v1/integrations/",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert "integrations" in data
        assert "total" in data
        assert data["total"] == 0
        assert len(data["integrations"]) == 0

    def test_list_integrations_success(
        self,
        client: TestClient,
        auth_headers: dict,
        test_integration: Integration
    ):
        """Test listing integrations when one exists."""
        response = client.get(
            "/api/v1/integrations/",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["integrations"]) == 1
        assert data["integrations"][0]["name"] == "Test Slack Channel"
        assert data["integrations"][0]["type"] == "slack"

    def test_list_integrations_unauthorized(self, client: TestClient):
        """Test listing integrations without authentication fails."""
        response = client.get("/api/v1/integrations/")
        assert response.status_code == 403  # Returns 403 Forbidden


class TestCreateSlackWebhook:
    """Tests for POST /api/v1/integrations/slack/webhook endpoint."""

    def test_create_slack_webhook_success(
        self,
        client: TestClient,
        auth_headers: dict,
        db: Session
    ):
        """Test creating a Slack webhook integration."""
        response = client.post(
            "/api/v1/integrations/slack/webhook",
            headers=auth_headers,
            json={
                "name": "My Alerts Channel",
                "webhook_url": "https://hooks.slack.com/services/T123/B456/xyz789",
                "triggers": ["urgent"],
                "included_fields": ["text", "sentiment", "pain_point_category"],
                "digest_time": "09:00"
            }
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "My Alerts Channel"
        assert data["type"] == "slack"
        assert data["is_active"] is True
        assert "urgent" in data["triggers"]
        assert "text" in data["included_fields"]

    def test_create_slack_webhook_invalid_url(
        self,
        client: TestClient,
        auth_headers: dict
    ):
        """Test creating webhook with invalid URL fails."""
        response = client.post(
            "/api/v1/integrations/slack/webhook",
            headers=auth_headers,
            json={
                "name": "Invalid Webhook",
                "webhook_url": "https://example.com/not-slack",
                "triggers": ["urgent"]
            }
        )

        assert response.status_code == 422  # Validation error

    def test_create_slack_webhook_invalid_trigger(
        self,
        client: TestClient,
        auth_headers: dict
    ):
        """Test creating webhook with invalid trigger fails."""
        response = client.post(
            "/api/v1/integrations/slack/webhook",
            headers=auth_headers,
            json={
                "name": "Invalid Trigger",
                "webhook_url": "https://hooks.slack.com/services/T123/B456/xyz789",
                "triggers": ["invalid_trigger"]
            }
        )

        assert response.status_code == 422  # Validation error

    def test_create_slack_webhook_unauthorized(self, client: TestClient):
        """Test creating webhook without authentication fails."""
        response = client.post(
            "/api/v1/integrations/slack/webhook",
            json={
                "name": "Test",
                "webhook_url": "https://hooks.slack.com/services/T123/B456/xyz789"
            }
        )
        assert response.status_code == 403  # Returns 403 Forbidden


class TestGetIntegration:
    """Tests for GET /api/v1/integrations/{id} endpoint."""

    def test_get_integration_success(
        self,
        client: TestClient,
        auth_headers: dict,
        test_integration: Integration
    ):
        """Test getting a single integration."""
        response = client.get(
            f"/api/v1/integrations/{test_integration.id}",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == test_integration.id
        assert data["name"] == test_integration.name

    def test_get_integration_not_found(
        self,
        client: TestClient,
        auth_headers: dict
    ):
        """Test getting non-existent integration fails."""
        response = client.get(
            "/api/v1/integrations/99999",
            headers=auth_headers
        )
        assert response.status_code == 404


class TestUpdateIntegration:
    """Tests for PATCH /api/v1/integrations/{id} endpoint."""

    def test_update_integration_success(
        self,
        client: TestClient,
        auth_headers: dict,
        test_integration: Integration
    ):
        """Test updating an integration."""
        response = client.patch(
            f"/api/v1/integrations/{test_integration.id}",
            headers=auth_headers,
            json={
                "name": "Updated Channel Name",
                "triggers": ["all"],
                "is_active": False
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Channel Name"
        assert data["triggers"] == ["all"]
        assert data["is_active"] is False

    def test_update_integration_not_found(
        self,
        client: TestClient,
        auth_headers: dict
    ):
        """Test updating non-existent integration fails."""
        response = client.patch(
            "/api/v1/integrations/99999",
            headers=auth_headers,
            json={"name": "Updated"}
        )
        assert response.status_code == 404


class TestDeleteIntegration:
    """Tests for DELETE /api/v1/integrations/{id} endpoint."""

    def test_delete_integration_success(
        self,
        client: TestClient,
        auth_headers: dict,
        test_integration: Integration,
        db: Session
    ):
        """Test deleting an integration."""
        integration_id = test_integration.id
        response = client.delete(
            f"/api/v1/integrations/{integration_id}",
            headers=auth_headers
        )

        assert response.status_code == 204

        # Verify deleted from database
        integration = db.query(Integration).filter(Integration.id == integration_id).first()
        assert integration is None

    def test_delete_integration_not_found(
        self,
        client: TestClient,
        auth_headers: dict
    ):
        """Test deleting non-existent integration fails."""
        response = client.delete(
            "/api/v1/integrations/99999",
            headers=auth_headers
        )
        assert response.status_code == 404


class TestDiscordWebhookIntegration:
    """Discord as an outbound alert destination.

    Discord's webhook API requires a body containing `content` or `embeds`;
    posting Rereflect's own envelope (what the generic webhook feature does)
    returns 400. These tests pin the provider registration and the payload
    shape that fix that.
    """

    def test_create_discord_webhook_success(
        self, client: TestClient, auth_headers: dict, db: Session
    ):
        """A discord.com webhook URL creates a type='discord' integration."""
        response = client.post(
            "/api/v1/integrations/discord/webhook",
            headers=auth_headers,
            json={
                "name": "Eng Alerts",
                "webhook_url": "https://discord.com/api/webhooks/123/abcXYZ",
                "triggers": ["urgent"],
                "included_fields": ["text", "sentiment"],
                "digest_time": "09:00",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Eng Alerts"
        assert data["type"] == "discord"
        assert data["is_active"] is True

    def test_create_discord_webhook_accepts_legacy_discordapp_host(
        self, client: TestClient, auth_headers: dict
    ):
        """discordapp.com is the legacy host and is still issued by old servers."""
        response = client.post(
            "/api/v1/integrations/discord/webhook",
            headers=auth_headers,
            json={
                "name": "Legacy Host",
                "webhook_url": "https://discordapp.com/api/webhooks/123/abcXYZ",
                "triggers": ["urgent"],
            },
        )

        assert response.status_code == 201

    def test_create_discord_webhook_rejects_slack_url(
        self, client: TestClient, auth_headers: dict
    ):
        """A Slack URL pasted into the Discord form must fail at save time."""
        response = client.post(
            "/api/v1/integrations/discord/webhook",
            headers=auth_headers,
            json={
                "name": "Wrong Provider",
                "webhook_url": "https://hooks.slack.com/services/T1/B2/xyz",
                "triggers": ["urgent"],
            },
        )

        assert response.status_code == 422

    def test_create_discord_webhook_rejects_arbitrary_host(
        self, client: TestClient, auth_headers: dict
    ):
        """Any non-Discord host is rejected, mirroring the Slack validator."""
        response = client.post(
            "/api/v1/integrations/discord/webhook",
            headers=auth_headers,
            json={
                "name": "Not Discord",
                "webhook_url": "https://example.com/api/webhooks/123/abc",
                "triggers": ["urgent"],
            },
        )

        assert response.status_code == 422

    def test_discord_test_route_posts_embeds(
        self, client: TestClient, auth_headers: dict, db: Session,
        test_organization: Organization
    ):
        """The Test button must post a body containing `embeds`.

        A Discord payload with neither `content` nor `embeds` is the 400 this
        whole feature exists to fix, so the shape is asserted, not just the
        status code.
        """
        from unittest.mock import patch

        integration = Integration(
            organization_id=test_organization.id,
            type="discord",
            name="Discord Test Target",
            config={
                "webhook_url": "https://discord.com/api/webhooks/123/abcXYZ",
                "integration_type": "webhook",
            },
            triggers=["urgent"],
            included_fields=["text"],
            is_active=True,
        )
        db.add(integration)
        db.commit()
        db.refresh(integration)

        # Patched at the DEFINITION site: the route imports it from this module.
        with patch(
            "src.api.routes.integrations.send_discord_message"
        ) as mock_send:
            mock_send.return_value = {"success": True, "response": "ok"}
            response = client.post(
                "/api/v1/integrations/discord/test",
                headers=auth_headers,
                json={"integration_id": integration.id},
            )

        assert response.status_code == 200
        assert mock_send.called
        kwargs = mock_send.call_args.kwargs
        assert kwargs.get("embeds"), "Discord payload must carry embeds"


class TestSignatureVerificationConfiguredField:
    """GET /api/v1/integrations/ surfaces whether inbound webhook signatures
    are verified for slack/intercom integrations, so a self-hoster can see
    unsigned ingestion in the UI rather than needing to read logs.
    """

    def test_slack_integration_reports_configured_when_secret_set(
        self, client: TestClient, auth_headers: dict,
        test_integration: Integration, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setattr("src.api.routes.integrations.SLACK_SIGNING_SECRET", "shh")

        response = client.get("/api/v1/integrations/", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()["integrations"][0]
        assert data["type"] == "slack"
        assert data["signature_verification_configured"] is True

    def test_slack_integration_reports_unconfigured_when_secret_unset(
        self, client: TestClient, auth_headers: dict,
        test_integration: Integration, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setattr("src.api.routes.integrations.SLACK_SIGNING_SECRET", "")

        response = client.get("/api/v1/integrations/", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()["integrations"][0]
        assert data["signature_verification_configured"] is False

    def test_intercom_integration_reports_configured_when_secret_set(
        self, client: TestClient, auth_headers: dict, db: Session,
        test_organization: Organization, monkeypatch: pytest.MonkeyPatch
    ):
        integration = Integration(
            organization_id=test_organization.id,
            type="intercom",
            name="Intercom Bridge",
            config={"integration_type": "oauth", "workspace_id": "abc123"},
            triggers=["urgent"],
            is_active=True,
        )
        db.add(integration)
        db.commit()
        monkeypatch.setattr("src.api.routes.integrations.INTERCOM_CLIENT_SECRET", "shh")

        response = client.get("/api/v1/integrations/", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()["integrations"][0]
        assert data["type"] == "intercom"
        assert data["signature_verification_configured"] is True

    def test_intercom_integration_reports_unconfigured_when_secret_unset(
        self, client: TestClient, auth_headers: dict, db: Session,
        test_organization: Organization, monkeypatch: pytest.MonkeyPatch
    ):
        integration = Integration(
            organization_id=test_organization.id,
            type="intercom",
            name="Intercom Bridge",
            config={"integration_type": "oauth", "workspace_id": "abc123"},
            triggers=["urgent"],
            is_active=True,
        )
        db.add(integration)
        db.commit()
        monkeypatch.setattr("src.api.routes.integrations.INTERCOM_CLIENT_SECRET", "")

        response = client.get("/api/v1/integrations/", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()["integrations"][0]
        assert data["signature_verification_configured"] is False

    def test_discord_integration_always_reports_configured(
        self, client: TestClient, auth_headers: dict, db: Session,
        test_organization: Organization, monkeypatch: pytest.MonkeyPatch
    ):
        """Discord carries its credential in the webhook URL — there is no
        inbound signature to verify, so it must never show the warning."""
        integration = Integration(
            organization_id=test_organization.id,
            type="discord",
            name="Discord Alerts",
            config={
                "webhook_url": "https://discord.com/api/webhooks/123/abcXYZ",
                "integration_type": "webhook",
            },
            triggers=["urgent"],
            is_active=True,
        )
        db.add(integration)
        db.commit()
        monkeypatch.setattr("src.api.routes.integrations.SLACK_SIGNING_SECRET", "")
        monkeypatch.setattr("src.api.routes.integrations.INTERCOM_CLIENT_SECRET", "")

        response = client.get("/api/v1/integrations/", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()["integrations"][0]
        assert data["type"] == "discord"
        assert data["signature_verification_configured"] is True


    def test_send_discord_message_returns_dict_and_never_raises(self):
        """Backend contract: returns {'success': bool}, never raises.

        The worker's send_discord_message_webhook deliberately does the
        opposite. Mixing the two inverts failure semantics silently.
        """
        from unittest.mock import patch
        import httpx

        from src.api.routes.integrations import send_discord_message

        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.post.side_effect = (
                httpx.HTTPError("boom")
            )
            result = send_discord_message(
                webhook_url="https://discord.com/api/webhooks/1/x",
                embeds=[{"title": "t"}],
                content="fallback",
            )

        assert result["success"] is False
        assert "boom" in result["error"]


class TestMemberRoleForbidden:
    """Members must be forbidden from managing integrations (Owner/Admin only).

    The RBAC matrix reserves integration management for Owner and Admin.
    Every JWT-authenticated integrations route must reject a member token
    with 403 before any handler logic runs.
    """

    def test_member_cannot_list_integrations(
        self, client: TestClient, member_headers: dict
    ):
        response = client.get("/api/v1/integrations/", headers=member_headers)
        assert response.status_code == 403

    def test_member_cannot_create_slack_webhook(
        self, client: TestClient, member_headers: dict
    ):
        response = client.post(
            "/api/v1/integrations/slack/webhook",
            headers=member_headers,
            json={
                "name": "Member Attempt",
                "webhook_url": "https://hooks.slack.com/services/T123/B456/xyz789",
                "triggers": ["urgent"],
            },
        )
        assert response.status_code == 403

    def test_member_cannot_create_discord_webhook(
        self, client: TestClient, member_headers: dict
    ):
        response = client.post(
            "/api/v1/integrations/discord/webhook",
            headers=member_headers,
            json={
                "name": "Member Attempt",
                "webhook_url": "https://discord.com/api/webhooks/123/abcXYZ",
                "triggers": ["urgent"],
            },
        )
        assert response.status_code == 403

    def test_member_cannot_test_discord_integration(
        self,
        client: TestClient,
        member_headers: dict,
        db: Session,
        test_organization: Organization,
    ):
        from unittest.mock import patch

        integration = Integration(
            organization_id=test_organization.id,
            type="discord",
            name="Discord Target",
            config={
                "webhook_url": "https://discord.com/api/webhooks/123/abcXYZ",
                "integration_type": "webhook",
            },
            triggers=["urgent"],
            is_active=True,
        )
        db.add(integration)
        db.commit()
        db.refresh(integration)

        with patch("src.api.routes.integrations.send_discord_message") as mock_send:
            mock_send.return_value = {"success": True, "response": "ok"}
            response = client.post(
                "/api/v1/integrations/discord/test",
                headers=member_headers,
                json={"integration_id": integration.id},
            )
        assert response.status_code == 403
        mock_send.assert_not_called()

    def test_member_cannot_get_integration(
        self,
        client: TestClient,
        member_headers: dict,
        test_integration: Integration,
    ):
        response = client.get(
            f"/api/v1/integrations/{test_integration.id}",
            headers=member_headers,
        )
        assert response.status_code == 403

    def test_member_cannot_update_integration(
        self,
        client: TestClient,
        member_headers: dict,
        test_integration: Integration,
    ):
        response = client.patch(
            f"/api/v1/integrations/{test_integration.id}",
            headers=member_headers,
            json={"name": "Member Update"},
        )
        assert response.status_code == 403

    def test_member_cannot_delete_integration(
        self,
        client: TestClient,
        member_headers: dict,
        test_integration: Integration,
    ):
        response = client.delete(
            f"/api/v1/integrations/{test_integration.id}",
            headers=member_headers,
        )
        assert response.status_code == 403

    def test_member_cannot_test_slack_integration(
        self,
        client: TestClient,
        member_headers: dict,
        test_integration: Integration,
    ):
        from unittest.mock import patch

        with patch("src.api.routes.integrations.send_slack_message") as mock_send:
            mock_send.return_value = {"success": True, "response": "ok"}
            response = client.post(
                "/api/v1/integrations/slack/test",
                headers=member_headers,
                json={"integration_id": test_integration.id},
            )
        assert response.status_code == 403
        mock_send.assert_not_called()

    def test_member_cannot_view_integration_logs(
        self,
        client: TestClient,
        member_headers: dict,
        test_integration: Integration,
    ):
        response = client.get(
            f"/api/v1/integrations/{test_integration.id}/logs",
            headers=member_headers,
        )
        assert response.status_code == 403

    def test_member_cannot_get_template_variables(
        self, client: TestClient, member_headers: dict
    ):
        response = client.get(
            "/api/v1/integrations/slack/template-variables",
            headers=member_headers,
        )
        assert response.status_code == 403

    def test_member_cannot_start_slack_oauth(
        self,
        client: TestClient,
        member_headers: dict,
        monkeypatch: pytest.MonkeyPatch,
    ):
        monkeypatch.setattr(
            "src.api.routes.integrations.SLACK_CLIENT_ID", "test-client-id"
        )
        response = client.get(
            "/api/v1/integrations/slack/oauth/connect?name=Member+Attempt",
            headers=member_headers,
        )
        assert response.status_code == 403

    def test_member_cannot_start_intercom_oauth(
        self,
        client: TestClient,
        member_headers: dict,
        monkeypatch: pytest.MonkeyPatch,
    ):
        monkeypatch.setattr(
            "src.api.routes.integrations.INTERCOM_CLIENT_ID", "test-client-id"
        )
        response = client.get(
            "/api/v1/integrations/intercom/oauth/connect?name=Member+Attempt",
            headers=member_headers,
        )
        assert response.status_code == 403


class TestTemplateVariablesAuth:
    """GET /api/v1/integrations/slack/template-variables is no longer public.

    Previously the route had no auth dependency at all (200 without a token).
    It is an integration-management surface, so the RBAC fix puts it behind
    JWT + admin/or-owner like the rest of the module.
    """

    def test_template_variables_requires_auth(self, client: TestClient):
        response = client.get("/api/v1/integrations/slack/template-variables")
        assert response.status_code == 403
        assert response.json()["detail"] == "Not authenticated"


class TestSlackOAuthCallback:
    """Tests for GET /api/v1/integrations/slack/oauth/callback."""

    @patch("src.api.routes.integrations.SLACK_CLIENT_ID", "test-client-id")
    @patch("src.api.routes.integrations.SLACK_CLIENT_SECRET", "test-client-secret")
    def test_callback_stores_encrypted_token(
        self,
        client: TestClient,
        db: Session,
        test_organization: Organization,
    ):
        """Should store the OAuth token encrypted at rest, never plaintext."""
        from src.services.oauth_state import sign_oauth_state

        test_state = sign_oauth_state(test_organization.id, "My Slack")

        mock_token_response = MagicMock()
        mock_token_response.json.return_value = {
            "ok": True,
            "access_token": "xoxb-raw-token-123",
            "team": {"id": "T123", "name": "Test Team"},
            "bot_user_id": "B123",
            "incoming_webhook": {"channel_id": "C123", "channel": "#feedback"},
        }
        mock_token_response.raise_for_status = MagicMock()

        mock_client_instance = MagicMock()
        mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
        mock_client_instance.__exit__ = MagicMock(return_value=False)
        mock_client_instance.post.return_value = mock_token_response

        with patch("src.api.routes.integrations.httpx.Client", return_value=mock_client_instance):
            with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
                response = client.get(
                    f"/api/v1/integrations/slack/oauth/callback?code=authcode123&state={test_state}",
                    follow_redirects=False,
                )

        assert response.status_code == 307
        assert "oauth_success=true" in response.headers["location"]

        integration = db.query(Integration).filter(
            Integration.type == "slack",
            Integration.organization_id == test_organization.id,
        ).first()
        assert integration is not None
        with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
            stored_token = integration.oauth_access_token
            assert stored_token != "xoxb-raw-token-123"
            assert decrypt_api_key(stored_token) == "xoxb-raw-token-123"

    @patch("src.api.routes.integrations.SLACK_CLIENT_ID", "test-client-id")
    @patch("src.api.routes.integrations.SLACK_CLIENT_SECRET", "test-client-secret")
    @patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": ""})
    def test_callback_missing_key_returns_422(
        self,
        client: TestClient,
        db: Session,
        test_organization: Organization,
    ):
        """Should reject with 422 (never silently store plaintext) when LLM_ENCRYPTION_KEY is unset."""
        from src.services.oauth_state import sign_oauth_state

        test_state = sign_oauth_state(test_organization.id, "My Slack")

        mock_token_response = MagicMock()
        mock_token_response.json.return_value = {
            "ok": True,
            "access_token": "xoxb-raw-token-123",
            "team": {"id": "T123", "name": "Test Team"},
        }
        mock_token_response.raise_for_status = MagicMock()

        mock_client_instance = MagicMock()
        mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
        mock_client_instance.__exit__ = MagicMock(return_value=False)
        mock_client_instance.post.return_value = mock_token_response

        with patch("src.api.routes.integrations.httpx.Client", return_value=mock_client_instance):
            response = client.get(
                f"/api/v1/integrations/slack/oauth/callback?code=authcode123&state={test_state}",
                follow_redirects=False,
            )

        assert response.status_code == 422
        assert "LLM_ENCRYPTION_KEY" in response.json()["detail"]


class TestSlackOAuthCallbackStateless:
    """The Slack OAuth callback is stateless: signed-state, no process dict.

    The state is HMAC-signed with the app secret; a forged/expired state
    must fail closed to the same invalid_state redirect the old dict-pop
    path produced.
    """

    @patch("src.api.routes.integrations.SLACK_CLIENT_ID", "test-client-id")
    @patch("src.api.routes.integrations.SLACK_CLIENT_SECRET", "test-client-secret")
    def test_callback_rejects_tampered_state(
        self,
        client: TestClient,
        test_organization: Organization,
    ):
        """A state with a valid shape but a tampered payload → invalid_state."""
        from src.services.oauth_state import sign_oauth_state
        from src.services.oauth_state import verify_oauth_state

        state = sign_oauth_state(test_organization.id, "My Slack")
        assert verify_oauth_state(state) is not None  # sanity: our state is valid

        payload_b64, _, sig = state.rpartition(".")
        forged = f"{payload_b64}x.{sig}"
        response = client.get(
            f"/api/v1/integrations/slack/oauth/callback?code=authcode123&state={forged}",
            follow_redirects=False,
        )
        assert response.status_code == 307
        assert "oauth_error=invalid_state" in response.headers["location"]

    @patch("src.api.routes.integrations.SLACK_CLIENT_ID", "test-client-id")
    @patch("src.api.routes.integrations.SLACK_CLIENT_SECRET", "test-client-secret")
    def test_callback_rejects_expired_state(
        self,
        client: TestClient,
        test_organization: Organization,
    ):
        """An expired (TTL-elapsed) state → invalid_state, never accepted."""
        from src.services.oauth_state import sign_oauth_state

        with patch("src.services.oauth_state.time.time", return_value=1_000_000_000):
            state = sign_oauth_state(test_organization.id, "My Slack")

        response = client.get(
            f"/api/v1/integrations/slack/oauth/callback?code=authcode123&state={state}",
            follow_redirects=False,
        )
        assert response.status_code == 307
        assert "oauth_error=invalid_state" in response.headers["location"]


def _make_oauth_slack_integration(
    db: Session,
    org: Organization,
    token: str,
) -> Integration:
    """Create a Slack OAuth integration with the given stored token."""
    integration = Integration(
        organization_id=org.id,
        type="slack",
        name="OAuth Slack",
        config={"integration_type": "oauth", "channel_id": "C123", "workspace_id": "T123"},
        oauth_access_token=token,
        triggers=["urgent"],
        is_active=True,
    )
    db.add(integration)
    db.commit()
    db.refresh(integration)
    return integration


class TestSlackIntegrationOAuthRead:
    """POST /api/v1/integrations/slack/test must send the DECRYPTED token.

    Regression for the truthiness trap: a ciphertext token is truthy, so an
    OAuth integration passes the `if not access_token` guard — the route must
    decrypt before handing the token to send_slack_message_oauth.
    """

    def test_oauth_test_sends_decrypted_token(
        self,
        client: TestClient,
        auth_headers: dict,
        db: Session,
        test_organization: Organization,
    ):
        with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
            integration = _make_oauth_slack_integration(
                db, test_organization, encrypt_api_key("xoxb-raw-token-123")
            )
            stored_token = integration.oauth_access_token

            with patch("src.api.routes.integrations.send_slack_message_oauth") as mock_send:
                mock_send.return_value = {"success": True, "response": "ok"}
                response = client.post(
                    "/api/v1/integrations/slack/test",
                    headers=auth_headers,
                    json={"integration_id": integration.id},
                )

        assert response.status_code == 200
        assert mock_send.called
        sent_token = mock_send.call_args.args[0]
        assert sent_token == "xoxb-raw-token-123"
        assert sent_token != stored_token

    def test_oauth_test_corrupt_token_returns_400(
        self,
        client: TestClient,
        auth_headers: dict,
        db: Session,
        test_organization: Organization,
    ):
        integration = _make_oauth_slack_integration(
            db, test_organization, "not-a-valid-fernet-token"
        )

        with patch("src.api.routes.integrations.send_slack_message_oauth") as mock_send:
            response = client.post(
                "/api/v1/integrations/slack/test",
                headers=auth_headers,
                json={"integration_id": integration.id},
            )

        assert response.status_code == 400
        assert "decrypt" in response.json()["detail"].lower()
        mock_send.assert_not_called()

    def test_oauth_test_missing_key_returns_400(
        self,
        client: TestClient,
        auth_headers: dict,
        db: Session,
        test_organization: Organization,
    ):
        with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
            integration = _make_oauth_slack_integration(
                db, test_organization, encrypt_api_key("xoxb-raw-token-123")
            )

        with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": ""}):
            with patch("src.api.routes.integrations.send_slack_message_oauth") as mock_send:
                response = client.post(
                    "/api/v1/integrations/slack/test",
                    headers=auth_headers,
                    json={"integration_id": integration.id},
                )

        assert response.status_code == 400
        assert "LLM_ENCRYPTION_KEY" in response.json()["detail"]
        mock_send.assert_not_called()


class TestListSlackChannelsRead:
    """GET /api/v1/feedback-sources/{source_id}/slack/channels must send the
    DECRYPTED token in the Authorization header.
    """

    def _make_source(
        self, db: Session, org: Organization, integration: Integration
    ) -> FeedbackSource:
        source = FeedbackSource(
            organization_id=org.id,
            source_type="slack",
            name="Slack Source",
            integration_id=integration.id,
            provider_config={},
            triggers={},
            field_mapping={},
            auto_import=True,
        )
        db.add(source)
        db.commit()
        db.refresh(source)
        return source

    def test_list_channels_sends_decrypted_bearer(
        self,
        client: TestClient,
        auth_headers: dict,
        db: Session,
        test_organization: Organization,
    ):
        with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
            integration = _make_oauth_slack_integration(
                db, test_organization, encrypt_api_key("xoxb-raw-token-123")
            )
            stored_token = integration.oauth_access_token
            source = self._make_source(db, test_organization, integration)

            mock_response = MagicMock()
            mock_response.json.return_value = {
                "ok": True,
                "channels": [{"id": "C123", "name": "general", "is_private": False}],
                "response_metadata": {"next_cursor": None},
            }
            mock_client_instance = MagicMock()
            mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
            mock_client_instance.__exit__ = MagicMock(return_value=False)
            mock_client_instance.get.return_value = mock_response

            with patch("httpx.Client", return_value=mock_client_instance):
                response = client.get(
                    f"/api/v1/feedback-sources/{source.id}/slack/channels",
                    headers=auth_headers,
                )

        assert response.status_code == 200
        assert response.json()[0]["id"] == "C123"
        sent_headers = mock_client_instance.get.call_args.kwargs["headers"]
        assert sent_headers["Authorization"] == "Bearer xoxb-raw-token-123"
        assert sent_headers["Authorization"] != f"Bearer {stored_token}"

    def test_list_channels_corrupt_token_returns_400(
        self,
        client: TestClient,
        auth_headers: dict,
        db: Session,
        test_organization: Organization,
    ):
        integration = _make_oauth_slack_integration(
            db, test_organization, "not-a-valid-fernet-token"
        )
        source = self._make_source(db, test_organization, integration)

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "ok": True,
            "channels": [],
            "response_metadata": {"next_cursor": None},
        }
        mock_client_instance = MagicMock()
        mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
        mock_client_instance.__exit__ = MagicMock(return_value=False)
        mock_client_instance.get.return_value = mock_response

        with patch("httpx.Client", return_value=mock_client_instance) as mock_client:
            response = client.get(
                f"/api/v1/feedback-sources/{source.id}/slack/channels",
                headers=auth_headers,
            )

        assert response.status_code == 400
        assert "decrypt" in response.json()["detail"].lower()
        mock_client.assert_not_called()

    def test_list_channels_missing_key_returns_400(
        self,
        client: TestClient,
        auth_headers: dict,
        db: Session,
        test_organization: Organization,
    ):
        with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": TEST_FERNET_KEY}):
            integration = _make_oauth_slack_integration(
                db, test_organization, encrypt_api_key("xoxb-raw-token-123")
            )
        source = self._make_source(db, test_organization, integration)

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "ok": True,
            "channels": [],
            "response_metadata": {"next_cursor": None},
        }
        mock_client_instance = MagicMock()
        mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
        mock_client_instance.__exit__ = MagicMock(return_value=False)
        mock_client_instance.get.return_value = mock_response

        with patch.dict(os.environ, {"LLM_ENCRYPTION_KEY": ""}):
            with patch("httpx.Client", return_value=mock_client_instance) as mock_client:
                response = client.get(
                    f"/api/v1/feedback-sources/{source.id}/slack/channels",
                    headers=auth_headers,
                )

        assert response.status_code == 400
        assert "LLM_ENCRYPTION_KEY" in response.json()["detail"]
        mock_client.assert_not_called()
