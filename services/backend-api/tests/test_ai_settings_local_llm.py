"""
Tests for Feature A: Local LLM support in the AI settings API.

Covers the GET/PATCH /api/v1/settings/ai endpoints:
- GET returns provider, base_url, and model fields
- PATCH accepts local providers (ollama, openai_compatible) with base_url
- PATCH rejects invalid base_url for local providers
- PATCH accepts cloud providers without base_url (unchanged behavior)
- Round-trip: set ollama + base_url, GET returns them

TDD: RED first, then production code.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.models.organization import Organization
from src.models.user import User
from src.models.org_ai_config import OrgAIConfig
from src.api.auth import hash_password, create_access_token


@pytest.fixture
def owner_user_local(db: Session, test_organization: Organization) -> User:
    user = User(
        email="owner_local@test.com",
        password_hash=hash_password("password123"),
        organization_id=test_organization.id,
        role="owner",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def owner_headers_local(owner_user_local: User) -> dict:
    token = create_access_token({
        "user_id": owner_user_local.id,
        "organization_id": owner_user_local.organization_id,
        "role": owner_user_local.role,
    })
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def admin_user_local(db: Session, test_organization: Organization) -> User:
    user = User(
        email="admin_local@test.com",
        password_hash=hash_password("password123"),
        organization_id=test_organization.id,
        role="admin",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def admin_headers_local(admin_user_local: User) -> dict:
    token = create_access_token({
        "user_id": admin_user_local.id,
        "organization_id": admin_user_local.organization_id,
        "role": admin_user_local.role,
    })
    return {"Authorization": f"Bearer {token}"}


class TestGetAISettingsLocalLLM:
    """GET /api/v1/settings/ai must return base_url in the response."""

    def test_get_returns_base_url_field(self, client: TestClient, auth_headers: dict):
        """GET response must include base_url (null by default)."""
        response = client.get("/api/v1/settings/ai", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "base_url" in data, "GET response must include base_url field"

    def test_get_base_url_null_by_default(self, client: TestClient, auth_headers: dict):
        """base_url is null when no local endpoint is configured."""
        response = client.get("/api/v1/settings/ai", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["base_url"] is None

    def test_get_returns_provider_field(self, client: TestClient, auth_headers: dict):
        """GET response must include default_provider field."""
        response = client.get("/api/v1/settings/ai", headers=auth_headers)
        assert response.status_code == 200
        assert "default_provider" in response.json()


class TestUpdateAISettingsLocalProviders:
    """PATCH /api/v1/settings/ai — local provider handling."""

    def test_set_ollama_provider(self, client: TestClient, admin_headers_local: dict):
        """Admin can set provider to 'ollama' with a valid base_url."""
        response = client.patch(
            "/api/v1/settings/ai",
            headers=admin_headers_local,
            json={
                "default_provider": "ollama",
                "base_url": "http://localhost:11434/v1",
            },
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["default_provider"] == "ollama"
        assert data["base_url"] == "http://localhost:11434/v1"

    def test_set_openai_compatible_provider(self, client: TestClient, admin_headers_local: dict):
        """Admin can set provider to 'openai_compatible' with a custom base_url."""
        response = client.patch(
            "/api/v1/settings/ai",
            headers=admin_headers_local,
            json={
                "default_provider": "openai_compatible",
                "base_url": "http://my-inference-server.internal/v1",
            },
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["default_provider"] == "openai_compatible"
        assert data["base_url"] == "http://my-inference-server.internal/v1"

    def test_ollama_invalid_base_url_rejected(self, client: TestClient, admin_headers_local: dict):
        """Local provider with a non-URL base_url must return 422."""
        response = client.patch(
            "/api/v1/settings/ai",
            headers=admin_headers_local,
            json={
                "default_provider": "ollama",
                "base_url": "not-a-valid-url",
            },
        )
        assert response.status_code == 422, (
            f"Expected 422 for invalid base_url, got {response.status_code}: {response.text}"
        )

    def test_openai_compatible_requires_base_url(self, client: TestClient, admin_headers_local: dict):
        """openai_compatible provider without base_url must be rejected (422)."""
        response = client.patch(
            "/api/v1/settings/ai",
            headers=admin_headers_local,
            json={
                "default_provider": "openai_compatible",
                # base_url intentionally omitted
            },
        )
        assert response.status_code == 422, (
            f"Expected 422 when base_url is missing for openai_compatible, got {response.status_code}"
        )

    def test_cloud_provider_accepts_no_base_url(self, client: TestClient, admin_headers_local: dict):
        """Cloud providers (openai/anthropic/google) must still work without base_url."""
        response = client.patch(
            "/api/v1/settings/ai",
            headers=admin_headers_local,
            json={"default_provider": "anthropic"},
        )
        assert response.status_code == 200, response.text
        assert response.json()["default_provider"] == "anthropic"

    def test_setting_cloud_provider_clears_base_url(self, client: TestClient, admin_headers_local: dict):
        """Switching from local to cloud provider should accept clearing base_url."""
        # First set to ollama
        client.patch(
            "/api/v1/settings/ai",
            headers=admin_headers_local,
            json={"default_provider": "ollama", "base_url": "http://localhost:11434/v1"},
        )
        # Then switch to cloud
        response = client.patch(
            "/api/v1/settings/ai",
            headers=admin_headers_local,
            json={"default_provider": "openai", "base_url": None},
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["default_provider"] == "openai"
        assert data["base_url"] is None

    def test_invalid_provider_name_rejected(self, client: TestClient, admin_headers_local: dict):
        """Completely unknown provider names must still be rejected."""
        response = client.patch(
            "/api/v1/settings/ai",
            headers=admin_headers_local,
            json={"default_provider": "totally_unknown_provider"},
        )
        assert response.status_code == 422, response.text

    def test_local_provider_settings_persist(self, client: TestClient, owner_headers_local: dict):
        """Ollama settings must persist and be returned on subsequent GET."""
        # Set ollama
        client.patch(
            "/api/v1/settings/ai",
            headers=owner_headers_local,
            json={
                "default_provider": "ollama",
                "base_url": "http://remote-ollama:11434/v1",
                "model_categorization": "llama3",
            },
        )
        # Verify via GET
        response = client.get("/api/v1/settings/ai", headers=owner_headers_local)
        assert response.status_code == 200
        data = response.json()
        assert data["default_provider"] == "ollama"
        assert data["base_url"] == "http://remote-ollama:11434/v1"
        assert data["models"]["categorization"] == "llama3"

    def test_base_url_stored_for_openai_compatible(self, client: TestClient, admin_headers_local: dict):
        """base_url round-trips correctly for openai_compatible provider."""
        url = "http://vllm.company.internal:8000/v1"
        client.patch(
            "/api/v1/settings/ai",
            headers=admin_headers_local,
            json={"default_provider": "openai_compatible", "base_url": url},
        )
        response = client.get("/api/v1/settings/ai", headers=admin_headers_local)
        assert response.status_code == 200
        assert response.json()["base_url"] == url


class TestOrgAIConfigModelEmbeddings:
    """Model-level: model_embeddings column exists on OrgAIConfig (S1)."""

    def test_column_exists_and_defaults_to_none(self, db: Session, test_organization: Organization):
        config = OrgAIConfig(
            organization_id=test_organization.id,
            default_provider="openai",
            model_categorization="gpt-4o-mini",
            model_analysis="gpt-4o-mini",
            model_insights="gpt-4o-mini",
        )
        db.add(config)
        db.commit()
        db.refresh(config)
        assert config.model_embeddings is None

    def test_column_stores_explicit_override(self, db: Session, test_organization: Organization):
        config = OrgAIConfig(
            organization_id=test_organization.id,
            default_provider="ollama",
            model_categorization="gpt-4o-mini",
            model_analysis="gpt-4o-mini",
            model_insights="gpt-4o-mini",
            model_embeddings="nomic-embed-text",
        )
        db.add(config)
        db.commit()
        db.refresh(config)
        assert config.model_embeddings == "nomic-embed-text"


class TestAISettingsModelEmbeddings:
    """GET/PATCH /api/v1/settings/ai — model_embeddings field (S1)."""

    def test_get_returns_model_embeddings_field_null_by_default(self, client: TestClient, auth_headers: dict):
        response = client.get("/api/v1/settings/ai", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "model_embeddings" in data, "GET response must include model_embeddings field"
        assert data["model_embeddings"] is None

    def test_patch_sets_model_embeddings(self, client: TestClient, admin_headers_local: dict):
        response = client.patch(
            "/api/v1/settings/ai",
            headers=admin_headers_local,
            json={"model_embeddings": "text-embedding-3-large"},
        )
        assert response.status_code == 200, response.text
        assert response.json()["model_embeddings"] == "text-embedding-3-large"

    def test_model_embeddings_round_trips_on_get(self, client: TestClient, owner_headers_local: dict):
        client.patch(
            "/api/v1/settings/ai",
            headers=owner_headers_local,
            json={"model_embeddings": "nomic-embed-text"},
        )
        response = client.get("/api/v1/settings/ai", headers=owner_headers_local)
        assert response.status_code == 200
        assert response.json()["model_embeddings"] == "nomic-embed-text"

    def test_patch_can_clear_model_embeddings(self, client: TestClient, owner_headers_local: dict):
        client.patch(
            "/api/v1/settings/ai",
            headers=owner_headers_local,
            json={"model_embeddings": "nomic-embed-text"},
        )
        response = client.patch(
            "/api/v1/settings/ai",
            headers=owner_headers_local,
            json={"model_embeddings": None},
        )
        assert response.status_code == 200, response.text
        assert response.json()["model_embeddings"] is None
