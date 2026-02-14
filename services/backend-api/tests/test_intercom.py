"""Tests for Intercom integration endpoints."""
import pytest
import hmac
import hashlib
import json
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.models.integration import Integration
from src.models.organization import Organization
from src.models.user import User
from src.api.auth import hash_password, create_access_token


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def free_organization(db: Session) -> Organization:
    """Create a test organization on the Free plan."""
    org = Organization(name="Free Company", plan="free")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


@pytest.fixture
def free_user(db: Session, free_organization: Organization) -> User:
    """Create a user on a Free plan org."""
    user = User(
        email="free@example.com",
        password_hash=hash_password("password123"),
        organization_id=free_organization.id,
        role="admin",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def free_auth_headers(free_user: User) -> dict:
    """Auth headers for a Free plan user."""
    token = create_access_token({
        "user_id": free_user.id,
        "organization_id": free_user.organization_id,
        "role": free_user.role,
    })
    return {"Authorization": f"Bearer {token}"}


# ============================================================================
# Plan Gating Tests
# ============================================================================

class TestIntercomPlanGating:
    """Test intercom_integration feature gating."""

    def test_intercom_feature_available_on_pro_plan(self):
        """Pro plan should have intercom_integration feature."""
        from src.config.plans import has_feature
        assert has_feature("pro", "intercom_integration") is True

    def test_intercom_feature_available_on_business_plan(self):
        """Business plan should have intercom_integration feature."""
        from src.config.plans import has_feature
        assert has_feature("business", "intercom_integration") is True

    def test_intercom_feature_available_on_enterprise_plan(self):
        """Enterprise plan should have intercom_integration feature."""
        from src.config.plans import has_feature
        assert has_feature("enterprise", "intercom_integration") is True

    def test_intercom_feature_not_available_on_free_plan(self):
        """Free plan should NOT have intercom_integration feature."""
        from src.config.plans import has_feature
        assert has_feature("free", "intercom_integration") is False

    def test_intercom_feature_minimum_plan_is_pro(self):
        """intercom_integration should map to Pro as minimum plan."""
        from src.config.plans import get_plan_for_feature
        assert get_plan_for_feature("intercom_integration") == "pro"


# ============================================================================
# OAuth Connect Tests
# ============================================================================

class TestIntercomOAuthConnect:
    """Tests for GET /api/v1/integrations/intercom/oauth/connect"""

    @patch("src.api.routes.integrations.INTERCOM_CLIENT_ID", "test-client-id")
    def test_oauth_connect_returns_auth_url(
        self,
        client: TestClient,
        auth_headers: dict,
    ):
        """Should return Intercom OAuth URL with correct parameters."""
        response = client.get(
            "/api/v1/integrations/intercom/oauth/connect?name=My+Intercom",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "auth_url" in data
        assert "state" in data
        assert "app.intercom.com/oauth" in data["auth_url"]
        assert "client_id=test-client-id" in data["auth_url"]

    def test_oauth_connect_requires_auth(self, client: TestClient):
        """Should reject unauthenticated requests."""
        response = client.get(
            "/api/v1/integrations/intercom/oauth/connect?name=Test",
        )
        assert response.status_code == 403

    def test_oauth_connect_requires_pro_plan(
        self,
        client: TestClient,
        free_auth_headers: dict,
    ):
        """Should reject Free plan users (feature gated)."""
        response = client.get(
            "/api/v1/integrations/intercom/oauth/connect?name=Test",
            headers=free_auth_headers,
        )
        assert response.status_code == 403
        data = response.json()
        assert data["detail"]["error"] == "feature_not_available"


# ============================================================================
# OAuth Callback Tests
# ============================================================================

class TestIntercomOAuthCallback:
    """Tests for GET /api/v1/integrations/intercom/oauth/callback"""

    @patch("src.api.routes.integrations.INTERCOM_CLIENT_ID", "test-client-id")
    @patch("src.api.routes.integrations.INTERCOM_CLIENT_SECRET", "test-client-secret")
    def test_callback_exchanges_code_for_token(
        self,
        client: TestClient,
        db: Session,
        test_organization: Organization,
    ):
        """Should exchange code for token, fetch workspace info, and create integration."""
        from src.api.routes.integrations import oauth_states

        # Pre-populate state
        test_state = "test-state-abc123"
        oauth_states[test_state] = {
            "organization_id": test_organization.id,
            "name": "My Intercom",
            "provider": "intercom",
        }

        # Mock the httpx.Client calls
        mock_token_response = MagicMock()
        mock_token_response.json.return_value = {"token": "xyztoken123"}
        mock_token_response.raise_for_status = MagicMock()

        mock_me_response = MagicMock()
        mock_me_response.json.return_value = {
            "id": "admin_123",
            "app": {"name": "Test Workspace", "id_code": "ws_abc"},
        }
        mock_me_response.raise_for_status = MagicMock()

        mock_client_instance = MagicMock()
        mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
        mock_client_instance.__exit__ = MagicMock(return_value=False)
        # First call: token exchange, second call: /me
        mock_client_instance.post.return_value = mock_token_response
        mock_client_instance.get.return_value = mock_me_response

        with patch("src.api.routes.integrations.httpx.Client", return_value=mock_client_instance):
            response = client.get(
                f"/api/v1/integrations/intercom/oauth/callback?code=authcode123&state={test_state}",
                follow_redirects=False,
            )

        # Should redirect to frontend with success
        assert response.status_code == 307
        assert "oauth_success=true" in response.headers["location"]

        # Verify integration was created in DB
        integration = db.query(Integration).filter(
            Integration.type == "intercom",
            Integration.organization_id == test_organization.id,
        ).first()
        assert integration is not None
        assert integration.name == "My Intercom"
        assert integration.oauth_access_token == "xyztoken123"
        assert integration.config["workspace_name"] == "Test Workspace"
        assert integration.config["admin_id"] == "admin_123"

    def test_callback_rejects_invalid_state(self, client: TestClient):
        """Should redirect with error when state is invalid."""
        response = client.get(
            "/api/v1/integrations/intercom/oauth/callback?code=somecode&state=bad-state",
            follow_redirects=False,
        )
        assert response.status_code == 307
        assert "oauth_error=invalid_state" in response.headers["location"]

    def test_callback_handles_error_param(self, client: TestClient):
        """Should redirect with error when Intercom returns an error."""
        response = client.get(
            "/api/v1/integrations/intercom/oauth/callback?error=access_denied",
            follow_redirects=False,
        )
        assert response.status_code == 307
        assert "oauth_error=access_denied" in response.headers["location"]

    def test_callback_handles_missing_params(self, client: TestClient):
        """Should redirect with error when code or state is missing."""
        response = client.get(
            "/api/v1/integrations/intercom/oauth/callback",
            follow_redirects=False,
        )
        assert response.status_code == 307
        assert "oauth_error=missing_params" in response.headers["location"]


# ============================================================================
# Webhook Receiver Tests
# ============================================================================

def _make_intercom_signature(body: bytes, secret: str) -> str:
    """Helper to compute Intercom HMAC-SHA1 signature."""
    digest = hmac.new(secret.encode(), body, hashlib.sha1).hexdigest()
    return f"sha1={digest}"


class TestIntercomWebhook:
    """Tests for POST /api/v1/webhooks/intercom/events"""

    @patch("src.api.routes.source_webhooks.INTERCOM_CLIENT_SECRET", "webhook-secret")
    @patch("src.api.routes.source_webhooks.queue_source_event", return_value="task-123")
    def test_webhook_verifies_signature(
        self,
        mock_queue: MagicMock,
        client: TestClient,
    ):
        """Should accept valid HMAC-SHA1 signature."""
        payload = {
            "topic": "conversation.user.created",
            "data": {
                "item": {
                    "type": "conversation",
                    "id": "conv_001",
                    "conversation_message": {"body": "Help me!"},
                }
            },
        }
        body = json.dumps(payload).encode()
        sig = _make_intercom_signature(body, "webhook-secret")

        response = client.post(
            "/api/v1/webhooks/intercom/events",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature": sig,
            },
        )
        assert response.status_code == 200
        assert response.json()["status"] == "queued"
        mock_queue.assert_called_once()

    @patch("src.api.routes.source_webhooks.INTERCOM_CLIENT_SECRET", "webhook-secret")
    def test_webhook_rejects_invalid_signature(self, client: TestClient):
        """Should reject requests with invalid signature."""
        payload = {"topic": "conversation.user.created", "data": {"item": {"id": "conv_001"}}}
        body = json.dumps(payload).encode()

        response = client.post(
            "/api/v1/webhooks/intercom/events",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature": "sha1=badsignature",
            },
        )
        assert response.status_code == 401

    @patch("src.api.routes.source_webhooks.INTERCOM_CLIENT_SECRET", "webhook-secret")
    @patch("src.api.routes.source_webhooks.queue_source_event", return_value="task-456")
    def test_webhook_processes_conversation_created(
        self,
        mock_queue: MagicMock,
        client: TestClient,
    ):
        """Should queue conversation.user.created events."""
        payload = {
            "topic": "conversation.user.created",
            "data": {
                "item": {
                    "type": "conversation",
                    "id": "conv_100",
                    "conversation_message": {"body": "I need help with billing."},
                }
            },
        }
        body = json.dumps(payload).encode()
        sig = _make_intercom_signature(body, "webhook-secret")

        response = client.post(
            "/api/v1/webhooks/intercom/events",
            content=body,
            headers={"Content-Type": "application/json", "X-Hub-Signature": sig},
        )
        assert response.status_code == 200
        mock_queue.assert_called_once_with(
            source_type="intercom",
            external_event_id="conv_100",
            event_type="conversation.user.created",
            event_data=payload["data"],
            provider_context={"conversation_id": "conv_100", "workspace_id": None},
        )

    @patch("src.api.routes.source_webhooks.INTERCOM_CLIENT_SECRET", "webhook-secret")
    @patch("src.api.routes.source_webhooks.queue_source_event", return_value="task-789")
    def test_webhook_processes_conversation_replied(
        self,
        mock_queue: MagicMock,
        client: TestClient,
    ):
        """Should queue conversation.user.replied events."""
        payload = {
            "topic": "conversation.user.replied",
            "data": {
                "item": {
                    "type": "conversation",
                    "id": "conv_200",
                    "conversation_parts": {"conversation_parts": [{"body": "Still broken"}]},
                }
            },
        }
        body = json.dumps(payload).encode()
        sig = _make_intercom_signature(body, "webhook-secret")

        response = client.post(
            "/api/v1/webhooks/intercom/events",
            content=body,
            headers={"Content-Type": "application/json", "X-Hub-Signature": sig},
        )
        assert response.status_code == 200
        mock_queue.assert_called_once()
        call_kwargs = mock_queue.call_args
        assert call_kwargs[1]["event_type"] == "conversation.user.replied"

    @patch("src.api.routes.source_webhooks.INTERCOM_CLIENT_SECRET", "webhook-secret")
    @patch("src.api.routes.source_webhooks.queue_source_event", return_value="task-rating")
    def test_webhook_processes_rating_added(
        self,
        mock_queue: MagicMock,
        client: TestClient,
    ):
        """Should queue conversation.rating.added events."""
        payload = {
            "topic": "conversation.rating.added",
            "data": {
                "item": {
                    "type": "conversation",
                    "id": "conv_300",
                    "conversation_rating": {"rating": 5, "remark": "Great support!"},
                }
            },
        }
        body = json.dumps(payload).encode()
        sig = _make_intercom_signature(body, "webhook-secret")

        response = client.post(
            "/api/v1/webhooks/intercom/events",
            content=body,
            headers={"Content-Type": "application/json", "X-Hub-Signature": sig},
        )
        assert response.status_code == 200
        mock_queue.assert_called_once()

    @patch("src.api.routes.source_webhooks.INTERCOM_CLIENT_SECRET", "webhook-secret")
    def test_webhook_ignores_unsupported_topic(self, client: TestClient):
        """Should ignore topics we don't handle."""
        payload = {
            "topic": "user.unsubscribed",
            "data": {"item": {"id": "user_999"}},
        }
        body = json.dumps(payload).encode()
        sig = _make_intercom_signature(body, "webhook-secret")

        response = client.post(
            "/api/v1/webhooks/intercom/events",
            content=body,
            headers={"Content-Type": "application/json", "X-Hub-Signature": sig},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "ignored"


# ============================================================================
# Intercom Write-Back Service Tests
# ============================================================================

class TestIntercomService:
    """Tests for Intercom write-back service."""

    @patch("src.services.intercom_service.httpx.Client")
    def test_add_note_to_conversation(self, MockClient):
        """Should POST a note to the Intercom conversation reply endpoint."""
        from src.services.intercom_service import add_note_to_conversation

        mock_instance = MagicMock()
        MockClient.return_value.__enter__ = MagicMock(return_value=mock_instance)
        MockClient.return_value.__exit__ = MagicMock(return_value=False)
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_instance.post.return_value = mock_response

        result = add_note_to_conversation(
            access_token="test-token",
            conversation_id="conv_123",
            admin_id="admin_1",
            note_body="Feedback categorized as pain point.",
        )
        assert result is True
        mock_instance.post.assert_called_once()
        call_args = mock_instance.post.call_args
        assert "conv_123" in call_args[0][0]
        assert call_args[1]["json"]["message_type"] == "note"

    @patch("src.services.intercom_service.httpx.Client")
    def test_close_conversation(self, MockClient):
        """Should POST a close message to the Intercom conversation parts endpoint."""
        from src.services.intercom_service import close_conversation

        mock_instance = MagicMock()
        MockClient.return_value.__enter__ = MagicMock(return_value=mock_instance)
        MockClient.return_value.__exit__ = MagicMock(return_value=False)
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_instance.post.return_value = mock_response

        result = close_conversation(
            access_token="test-token",
            conversation_id="conv_456",
            admin_id="admin_2",
        )
        assert result is True
        mock_instance.post.assert_called_once()
        call_args = mock_instance.post.call_args
        assert "conv_456" in call_args[0][0]
        assert call_args[1]["json"]["message_type"] == "close"

    @patch("src.services.intercom_service.httpx.Client")
    def test_get_admin_id(self, MockClient):
        """Should GET /me and return the admin ID."""
        from src.services.intercom_service import get_admin_id

        mock_instance = MagicMock()
        MockClient.return_value.__enter__ = MagicMock(return_value=mock_instance)
        MockClient.return_value.__exit__ = MagicMock(return_value=False)
        mock_response = MagicMock()
        mock_response.json.return_value = {"id": "admin_99", "type": "admin"}
        mock_response.raise_for_status = MagicMock()
        mock_instance.get.return_value = mock_response

        admin_id = get_admin_id("test-token")
        assert admin_id == "admin_99"

    @patch("src.services.intercom_service.httpx.Client")
    def test_get_admin_id_returns_none_on_error(self, MockClient):
        """Should return None if the API call fails."""
        from src.services.intercom_service import get_admin_id

        mock_instance = MagicMock()
        MockClient.return_value.__enter__ = MagicMock(return_value=mock_instance)
        MockClient.return_value.__exit__ = MagicMock(return_value=False)
        import httpx
        mock_instance.get.side_effect = httpx.HTTPError("Connection failed")

        admin_id = get_admin_id("bad-token")
        assert admin_id is None

    @patch("src.services.intercom_service.httpx.Client")
    def test_add_note_returns_false_on_error(self, MockClient):
        """Should return False if the note API call fails."""
        from src.services.intercom_service import add_note_to_conversation

        mock_instance = MagicMock()
        MockClient.return_value.__enter__ = MagicMock(return_value=mock_instance)
        MockClient.return_value.__exit__ = MagicMock(return_value=False)
        import httpx
        mock_instance.post.side_effect = httpx.HTTPError("Connection failed")

        result = add_note_to_conversation("token", "conv_1", "admin_1", "note")
        assert result is False
