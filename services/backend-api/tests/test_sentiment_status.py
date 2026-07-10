"""
Phase 3 RED: Tests for GET /api/v1/settings/ai/sentiment/status.

Never raises to the caller — mirrors GET /embeddings/status. Covers all 4
states: no config, explicit vader, transformer with deps present, transformer
with deps absent.

TDD: RED first, then production code.
"""

import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.models.organization import Organization
from src.models.user import User
from src.models.org_ai_config import OrgAIConfig
from src.api.auth import hash_password, create_access_token


@pytest.fixture
def member_user_sent_status(db: Session, test_organization: Organization) -> User:
    user = User(
        email="member_sent_status@test.com",
        password_hash=hash_password("password123"),
        organization_id=test_organization.id,
        role="member",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def member_headers_sent_status(member_user_sent_status: User) -> dict:
    token = create_access_token({
        "user_id": member_user_sent_status.id,
        "organization_id": member_user_sent_status.organization_id,
        "role": member_user_sent_status.role,
    })
    return {"Authorization": f"Bearer {token}"}


class TestSentimentStatus:
    def test_no_config_returns_vader_available_true(
        self, client: TestClient, member_headers_sent_status: dict
    ):
        response = client.get("/api/v1/settings/ai/sentiment/status", headers=member_headers_sent_status)
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["provider"] == "vader"
        assert data["available"] is True
        assert data["model"] is None

    def test_explicit_vader_returns_available_true_model_none(
        self, client: TestClient, db: Session, test_organization: Organization, member_headers_sent_status: dict
    ):
        config = OrgAIConfig(
            organization_id=test_organization.id,
            default_provider="openai",
            model_categorization="gpt-4o-mini",
            model_analysis="gpt-4o-mini",
            model_insights="gpt-4o-mini",
            sentiment_provider="vader",
        )
        db.add(config)
        db.commit()

        response = client.get("/api/v1/settings/ai/sentiment/status", headers=member_headers_sent_status)
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["provider"] == "vader"
        assert data["available"] is True
        assert data["model"] is None

    def test_transformer_with_deps_available_returns_true(
        self, client: TestClient, db: Session, test_organization: Organization, member_headers_sent_status: dict
    ):
        config = OrgAIConfig(
            organization_id=test_organization.id,
            default_provider="openai",
            model_categorization="gpt-4o-mini",
            model_analysis="gpt-4o-mini",
            model_insights="gpt-4o-mini",
            sentiment_provider="transformer",
        )
        db.add(config)
        db.commit()

        with patch(
            "src.api.routes.ai_settings._sentiment_transformer_deps_available",
            return_value=True,
        ):
            response = client.get("/api/v1/settings/ai/sentiment/status", headers=member_headers_sent_status)

        assert response.status_code == 200, response.text
        data = response.json()
        assert data["provider"] == "transformer"
        assert data["available"] is True
        assert data["model"] is not None

    def test_transformer_without_deps_returns_available_false(
        self, client: TestClient, db: Session, test_organization: Organization, member_headers_sent_status: dict
    ):
        config = OrgAIConfig(
            organization_id=test_organization.id,
            default_provider="openai",
            model_categorization="gpt-4o-mini",
            model_analysis="gpt-4o-mini",
            model_insights="gpt-4o-mini",
            sentiment_provider="transformer",
        )
        db.add(config)
        db.commit()

        with patch(
            "src.api.routes.ai_settings._sentiment_transformer_deps_available",
            return_value=False,
        ):
            response = client.get("/api/v1/settings/ai/sentiment/status", headers=member_headers_sent_status)

        assert response.status_code == 200, response.text
        data = response.json()
        assert data["provider"] == "transformer"
        assert data["available"] is False

    def test_never_raises_on_malformed_config(
        self, client: TestClient, db: Session, test_organization: Organization, member_headers_sent_status: dict
    ):
        """A row with an unrecognized sentiment_provider value must still 200, not 500."""
        config = OrgAIConfig(
            organization_id=test_organization.id,
            default_provider="openai",
            model_categorization="gpt-4o-mini",
            model_analysis="gpt-4o-mini",
            model_insights="gpt-4o-mini",
            sentiment_provider="nonsense",
        )
        db.add(config)
        db.commit()

        response = client.get("/api/v1/settings/ai/sentiment/status", headers=member_headers_sent_status)
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["provider"] == "vader"
        assert data["available"] is True

    def test_requires_auth(self, client: TestClient):
        response = client.get("/api/v1/settings/ai/sentiment/status")
        assert response.status_code == 403
