"""
Tests for GET /api/v1/settings/ai/embeddings/status (S3 backend).

Covers:
- Unconfigured org (no OrgAIConfig / no key) → configured=False, never 500s.
- openai_compatible + base_url (keyless local) → configured=True.
- system_templates_embedded counts system QueryTemplateMapping rows tagged
  with the active provider.

TDD: RED first, then production code.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.models.organization import Organization
from src.models.user import User
from src.models.org_ai_config import OrgAIConfig
from src.models.query_template import QueryTemplate
from src.models.query_template_mapping import QueryTemplateMapping
from src.api.auth import hash_password, create_access_token


@pytest.fixture
def member_user_embed(db: Session, test_organization: Organization) -> User:
    user = User(
        email="member_embed@test.com",
        password_hash=hash_password("password123"),
        organization_id=test_organization.id,
        role="member",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def member_headers_embed(member_user_embed: User) -> dict:
    token = create_access_token({
        "user_id": member_user_embed.id,
        "organization_id": member_user_embed.organization_id,
        "role": member_user_embed.role,
    })
    return {"Authorization": f"Bearer {token}"}


class TestEmbeddingsStatusUnconfigured:
    def test_no_org_ai_config_returns_unconfigured(self, client: TestClient, member_headers_embed: dict):
        """No OrgAIConfig row at all → configured=False, never 500s."""
        response = client.get("/api/v1/settings/ai/embeddings/status", headers=member_headers_embed)
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["configured"] is False
        assert data["dimension"] is None
        assert data["system_templates_embedded"] == 0

    def test_openai_provider_without_byok_key_returns_unconfigured(
        self, client: TestClient, db: Session, test_organization: Organization, member_headers_embed: dict
    ):
        """Cloud provider configured but no BYOK key → configured=False."""
        config = OrgAIConfig(
            organization_id=test_organization.id,
            default_provider="openai",
            model_categorization="gpt-4o-mini",
            model_analysis="gpt-4o-mini",
            model_insights="gpt-4o-mini",
        )
        db.add(config)
        db.commit()

        response = client.get("/api/v1/settings/ai/embeddings/status", headers=member_headers_embed)
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["provider"] == "openai"
        assert data["configured"] is False


class TestEmbeddingsStatusConfiguredLocal:
    def test_openai_compatible_with_base_url_is_configured(
        self, client: TestClient, db: Session, test_organization: Organization, member_headers_embed: dict
    ):
        """openai_compatible + base_url is keyless and resolves without a BYOK key."""
        config = OrgAIConfig(
            organization_id=test_organization.id,
            default_provider="openai_compatible",
            base_url="http://localhost:11434/v1",
            model_categorization="gpt-4o-mini",
            model_analysis="gpt-4o-mini",
            model_insights="gpt-4o-mini",
        )
        db.add(config)
        db.commit()

        response = client.get("/api/v1/settings/ai/embeddings/status", headers=member_headers_embed)
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["configured"] is True
        assert data["provider"] == "openai_compatible"


class TestEmbeddingsStatusSystemTemplatesEmbedded:
    def test_counts_only_active_provider_system_mappings(
        self, client: TestClient, db: Session, test_organization: Organization, member_headers_embed: dict
    ):
        """system_templates_embedded counts system-template mappings for the active provider only."""
        config = OrgAIConfig(
            organization_id=test_organization.id,
            default_provider="openai",
            model_categorization="gpt-4o-mini",
            model_analysis="gpt-4o-mini",
            model_insights="gpt-4o-mini",
        )
        db.add(config)

        template = QueryTemplate(
            organization_id=None,
            sql_query="SELECT 1",
            description="system template",
            created_by="system",
        )
        db.add(template)
        db.commit()
        db.refresh(template)

        db.add_all([
            QueryTemplateMapping(
                template_id=template.id,
                question_pattern="how many feedbacks",
                embedding_provider="openai",
                embedding_dimension=1536,
            ),
            QueryTemplateMapping(
                template_id=template.id,
                question_pattern="count feedbacks",
                embedding_provider="openai",
                embedding_dimension=1536,
            ),
            QueryTemplateMapping(
                template_id=template.id,
                question_pattern="combien de retours",
                embedding_provider="google",
                embedding_dimension=768,
            ),
        ])
        db.commit()

        response = client.get("/api/v1/settings/ai/embeddings/status", headers=member_headers_embed)
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["system_templates_embedded"] == 2

    def test_requires_auth(self, client: TestClient):
        response = client.get("/api/v1/settings/ai/embeddings/status")
        assert response.status_code == 403
