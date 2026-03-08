"""
Tests for Linear OAuth flow endpoints.
Covers: connect URL generation, callback token exchange, disconnect, status check.
"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

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


@pytest.fixture
def linear_integration(db: Session, test_organization: Organization):
    """Create a connected Linear integration for the test org."""
    from src.models.linear_integration import LinearIntegration
    integration = LinearIntegration(
        organization_id=test_organization.id,
        access_token="encrypted-token-xyz",
        linear_org_id="linear-org-abc",
        linear_org_name="Acme Linear",
        connected_by_user_id=None,
        is_active=True,
        webhook_secret="webhook-secret-123",
        webhook_id="webhook-uuid-1",
    )
    db.add(integration)
    db.commit()
    db.refresh(integration)
    return integration


# ============================================================================
# Plan Gating Tests
# ============================================================================

class TestLinearPlanGating:
    """Test linear_integration feature gating."""

    def test_linear_feature_available_on_pro_plan(self):
        """Pro plan should have linear_integration feature."""
        from src.config.plans import has_feature
        assert has_feature("pro", "linear_integration") is True

    def test_linear_feature_available_on_business_plan(self):
        """Business plan should have linear_integration feature."""
        from src.config.plans import has_feature
        assert has_feature("business", "linear_integration") is True

    def test_linear_feature_available_on_enterprise_plan(self):
        """Enterprise plan should have linear_integration feature."""
        from src.config.plans import has_feature
        assert has_feature("enterprise", "linear_integration") is True

    def test_linear_feature_not_available_on_free_plan(self):
        """Free plan should NOT have linear_integration feature."""
        from src.config.plans import has_feature
        assert has_feature("free", "linear_integration") is False

    def test_linear_feature_minimum_plan_is_pro(self):
        """linear_integration should map to Pro as minimum plan."""
        from src.config.plans import get_plan_for_feature
        assert get_plan_for_feature("linear_integration") == "pro"


# ============================================================================
# GET /api/v1/integrations/linear/connect Tests
# ============================================================================

class TestLinearOAuthConnect:
    """Tests for GET /api/v1/integrations/linear/connect."""

    @patch("src.api.routes.linear_integration.LINEAR_CLIENT_ID", "test-linear-client-id")
    def test_connect_returns_auth_url(
        self,
        client: TestClient,
        auth_headers: dict,
    ):
        """Should return Linear OAuth URL with correct parameters."""
        response = client.get(
            "/api/v1/integrations/linear/connect",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "auth_url" in data
        assert "state" in data
        assert "linear.app/oauth/authorize" in data["auth_url"]
        assert "test-linear-client-id" in data["auth_url"]

    @patch("src.api.routes.linear_integration.LINEAR_CLIENT_ID", "test-linear-client-id")
    def test_connect_includes_required_scopes(
        self,
        client: TestClient,
        auth_headers: dict,
    ):
        """Should include required OAuth scopes in the URL."""
        response = client.get(
            "/api/v1/integrations/linear/connect",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        # Should request read + write scopes
        assert "scope" in data["auth_url"] or "read" in data["auth_url"]

    def test_connect_requires_auth(self, client: TestClient):
        """Should reject unauthenticated requests."""
        response = client.get("/api/v1/integrations/linear/connect")
        assert response.status_code == 403

    def test_connect_requires_pro_plan(
        self,
        client: TestClient,
        free_auth_headers: dict,
    ):
        """Should reject Free plan users (feature gated)."""
        response = client.get(
            "/api/v1/integrations/linear/connect",
            headers=free_auth_headers,
        )
        assert response.status_code == 403
        data = response.json()
        assert data["detail"]["error"] == "feature_not_available"

    @patch("src.api.routes.linear_integration.LINEAR_CLIENT_ID", "")
    def test_connect_returns_500_when_client_id_not_configured(
        self,
        client: TestClient,
        auth_headers: dict,
    ):
        """Should return 500 when LINEAR_CLIENT_ID is not set."""
        response = client.get(
            "/api/v1/integrations/linear/connect",
            headers=auth_headers,
        )
        assert response.status_code == 500


# ============================================================================
# GET /api/v1/integrations/linear/callback Tests
# ============================================================================

class TestLinearOAuthCallback:
    """Tests for GET /api/v1/integrations/linear/callback."""

    @patch("src.api.routes.linear_integration.LINEAR_CLIENT_ID", "test-client-id")
    @patch("src.api.routes.linear_integration.LINEAR_CLIENT_SECRET", "test-client-secret")
    def test_callback_exchanges_code_for_token(
        self,
        client: TestClient,
        db: Session,
        test_organization: Organization,
        test_user: User,
    ):
        """Should exchange code for token, fetch org info, and create LinearIntegration."""
        from src.api.routes.linear_integration import linear_oauth_states

        test_state = "test-state-abc123"
        linear_oauth_states[test_state] = {
            "organization_id": test_organization.id,
            "user_id": test_user.id,
        }

        mock_token_response = MagicMock()
        mock_token_response.json.return_value = {
            "access_token": "lin_oauth_token_xyz",
            "token_type": "Bearer",
            "scope": "read,write",
        }
        mock_token_response.raise_for_status = MagicMock()

        mock_async_client = AsyncMock()
        mock_async_client.post = AsyncMock(return_value=mock_token_response)
        mock_async_client.__aenter__ = AsyncMock(return_value=mock_async_client)
        mock_async_client.__aexit__ = AsyncMock(return_value=False)

        with patch("src.api.routes.linear_integration.httpx.AsyncClient", return_value=mock_async_client):
            with patch("src.api.routes.linear_integration.LinearClient") as MockLinearClient:
                mock_linear = AsyncMock()
                mock_linear.get_organization = AsyncMock(return_value={
                    "id": "linear-org-123",
                    "name": "Acme Corp",
                })
                mock_linear.create_webhook = AsyncMock(return_value={"id": "webhook-1"})
                MockLinearClient.return_value = mock_linear

                response = client.get(
                    f"/api/v1/integrations/linear/callback?code=authcode123&state={test_state}",
                    follow_redirects=False,
                )

        assert response.status_code == 307
        assert "oauth_success=true" in response.headers["location"]

        from src.models.linear_integration import LinearIntegration
        integration = db.query(LinearIntegration).filter(
            LinearIntegration.organization_id == test_organization.id
        ).first()
        assert integration is not None
        assert integration.is_active is True
        assert integration.linear_org_name == "Acme Corp"

    def test_callback_rejects_invalid_state(self, client: TestClient):
        """Should redirect with error when state is invalid."""
        response = client.get(
            "/api/v1/integrations/linear/callback?code=somecode&state=bad-state-xyz",
            follow_redirects=False,
        )
        assert response.status_code == 307
        assert "oauth_error=invalid_state" in response.headers["location"]

    def test_callback_handles_missing_params(self, client: TestClient):
        """Should redirect with error when code or state is missing."""
        response = client.get(
            "/api/v1/integrations/linear/callback",
            follow_redirects=False,
        )
        assert response.status_code == 307
        assert "oauth_error=missing_params" in response.headers["location"]

    def test_callback_handles_error_param(self, client: TestClient):
        """Should redirect with error when Linear returns an error."""
        response = client.get(
            "/api/v1/integrations/linear/callback?error=access_denied",
            follow_redirects=False,
        )
        assert response.status_code == 307
        assert "oauth_error=access_denied" in response.headers["location"]

    @patch("src.api.routes.linear_integration.LINEAR_CLIENT_ID", "test-client-id")
    @patch("src.api.routes.linear_integration.LINEAR_CLIENT_SECRET", "test-client-secret")
    def test_callback_creates_default_status_mappings(
        self,
        client: TestClient,
        db: Session,
        test_organization: Organization,
        test_user: User,
    ):
        """Should create default status mappings on connect."""
        from src.api.routes.linear_integration import linear_oauth_states

        test_state = "test-state-defaults"
        linear_oauth_states[test_state] = {
            "organization_id": test_organization.id,
            "user_id": test_user.id,
        }

        mock_token_response = MagicMock()
        mock_token_response.json.return_value = {"access_token": "token-123"}
        mock_token_response.raise_for_status = MagicMock()

        mock_async_client = AsyncMock()
        mock_async_client.post = AsyncMock(return_value=mock_token_response)
        mock_async_client.__aenter__ = AsyncMock(return_value=mock_async_client)
        mock_async_client.__aexit__ = AsyncMock(return_value=False)

        with patch("src.api.routes.linear_integration.httpx.AsyncClient", return_value=mock_async_client):
            with patch("src.api.routes.linear_integration.LinearClient") as MockLinearClient:
                mock_linear = AsyncMock()
                mock_linear.get_organization.return_value = {
                    "id": "linear-org-99",
                    "name": "Test Org",
                }
                mock_linear.create_webhook.return_value = {"id": "webhook-99"}
                MockLinearClient.return_value = mock_linear

                response = client.get(
                    f"/api/v1/integrations/linear/callback?code=abc&state={test_state}",
                    follow_redirects=False,
                )

        from src.models.linear_integration import LinearStatusMapping
        mappings = db.query(LinearStatusMapping).filter(
            LinearStatusMapping.organization_id == test_organization.id
        ).all()
        assert len(mappings) > 0
        # Check default mapping: completed → resolved
        completed_mapping = next(
            (m for m in mappings if m.linear_status_type == "completed"), None
        )
        assert completed_mapping is not None
        assert completed_mapping.rereflect_status == "resolved"


# ============================================================================
# DELETE /api/v1/integrations/linear/disconnect Tests
# ============================================================================

class TestLinearDisconnect:
    """Tests for DELETE /api/v1/integrations/linear/disconnect."""

    def test_disconnect_deactivates_integration(
        self,
        client: TestClient,
        auth_headers: dict,
        db: Session,
        linear_integration,
    ):
        """Should set is_active=False on the LinearIntegration."""
        with patch("src.api.routes.linear_integration.LinearClient") as MockLinearClient:
            mock_linear = AsyncMock()
            mock_linear.delete_webhook.return_value = None
            MockLinearClient.return_value = mock_linear

            response = client.delete(
                "/api/v1/integrations/linear/disconnect",
                headers=auth_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        db.refresh(linear_integration)
        assert linear_integration.is_active is False

    def test_disconnect_returns_404_when_not_connected(
        self,
        client: TestClient,
        auth_headers: dict,
    ):
        """Should return 404 when no active Linear integration exists."""
        response = client.delete(
            "/api/v1/integrations/linear/disconnect",
            headers=auth_headers,
        )
        assert response.status_code == 404

    def test_disconnect_requires_auth(self, client: TestClient):
        """Should reject unauthenticated requests."""
        response = client.delete("/api/v1/integrations/linear/disconnect")
        assert response.status_code == 403

    def test_disconnect_attempts_webhook_deletion(
        self,
        client: TestClient,
        auth_headers: dict,
        linear_integration,
    ):
        """Should attempt to delete the Linear webhook on disconnect."""
        with patch("src.api.routes.linear_integration.LinearClient") as MockLinearClient:
            mock_linear = AsyncMock()
            mock_linear.delete_webhook.return_value = None
            MockLinearClient.return_value = mock_linear

            client.delete(
                "/api/v1/integrations/linear/disconnect",
                headers=auth_headers,
            )

            mock_linear.delete_webhook.assert_called_once_with(
                webhook_id="webhook-uuid-1"
            )


# ============================================================================
# GET /api/v1/integrations/linear/status Tests
# ============================================================================

class TestLinearStatus:
    """Tests for GET /api/v1/integrations/linear/status."""

    def test_status_returns_connected_when_active(
        self,
        client: TestClient,
        auth_headers: dict,
        linear_integration,
    ):
        """Should return connected=True and org info when integration is active."""
        response = client.get(
            "/api/v1/integrations/linear/status",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["connected"] is True
        assert data["linear_org_name"] == "Acme Linear"
        assert data["linear_org_id"] == "linear-org-abc"

    def test_status_returns_not_connected_when_no_integration(
        self,
        client: TestClient,
        auth_headers: dict,
    ):
        """Should return connected=False when no integration exists."""
        response = client.get(
            "/api/v1/integrations/linear/status",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["connected"] is False

    def test_status_returns_not_connected_when_inactive(
        self,
        client: TestClient,
        auth_headers: dict,
        db: Session,
        test_organization: Organization,
    ):
        """Should return connected=False when integration is_active=False."""
        from src.models.linear_integration import LinearIntegration
        integration = LinearIntegration(
            organization_id=test_organization.id,
            access_token="token",
            linear_org_id="org-1",
            linear_org_name="Test",
            is_active=False,
            webhook_secret="secret",
        )
        db.add(integration)
        db.commit()

        response = client.get(
            "/api/v1/integrations/linear/status",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["connected"] is False

    def test_status_requires_auth(self, client: TestClient):
        """Should reject unauthenticated requests."""
        response = client.get("/api/v1/integrations/linear/status")
        assert response.status_code == 403
