"""
Phase 3 RED: Tests for sentiment_provider in the AI settings GET/PATCH
(services/backend-api/src/api/routes/ai_settings.py).

Covers:
- GET /api/v1/settings/ai returns sentiment_provider (defaults "vader")
- PATCH validates against {'vader', 'transformer'}
- PATCH requires transformer deps to be importable (mocked find_spec)
- PATCH omitted field leaves existing value untouched (model_fields_set)
- PATCH round-trips via GET
- PATCH requires admin/owner

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
def owner_user_sentiment(db: Session, test_organization: Organization) -> User:
    user = User(
        email="owner_sentiment@test.com",
        password_hash=hash_password("password123"),
        organization_id=test_organization.id,
        role="owner",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def owner_headers_sentiment(owner_user_sentiment: User) -> dict:
    token = create_access_token({
        "user_id": owner_user_sentiment.id,
        "organization_id": owner_user_sentiment.organization_id,
        "role": owner_user_sentiment.role,
    })
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def member_user_sentiment(db: Session, test_organization: Organization) -> User:
    user = User(
        email="member_sentiment@test.com",
        password_hash=hash_password("password123"),
        organization_id=test_organization.id,
        role="member",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def member_headers_sentiment(member_user_sentiment: User) -> dict:
    token = create_access_token({
        "user_id": member_user_sentiment.id,
        "organization_id": member_user_sentiment.organization_id,
        "role": member_user_sentiment.role,
    })
    return {"Authorization": f"Bearer {token}"}


class TestGetSentimentProviderField:
    def test_get_returns_sentiment_provider_field(
        self, client: TestClient, db: Session, test_organization: Organization, owner_headers_sentiment: dict
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

        response = client.get("/api/v1/settings/ai", headers=owner_headers_sentiment)
        assert response.status_code == 200, response.text
        assert response.json()["sentiment_provider"] == "transformer"

    def test_get_defaults_to_vader(self, client: TestClient, owner_headers_sentiment: dict):
        """No OrgAIConfig row at all -> sentiment_provider defaults to 'vader'."""
        response = client.get("/api/v1/settings/ai", headers=owner_headers_sentiment)
        assert response.status_code == 200, response.text
        assert response.json()["sentiment_provider"] == "vader"


class TestPatchSentimentProviderValidation:
    def test_patch_valid_vader_returns_200(self, client: TestClient, owner_headers_sentiment: dict):
        response = client.patch(
            "/api/v1/settings/ai",
            json={"sentiment_provider": "vader"},
            headers=owner_headers_sentiment,
        )
        assert response.status_code == 200, response.text
        assert response.json()["sentiment_provider"] == "vader"

    def test_patch_valid_transformer_with_deps_available_returns_200(
        self, client: TestClient, owner_headers_sentiment: dict
    ):
        with patch(
            "src.api.routes.ai_settings._sentiment_transformer_deps_available",
            return_value=True,
        ):
            response = client.patch(
                "/api/v1/settings/ai",
                json={"sentiment_provider": "transformer"},
                headers=owner_headers_sentiment,
            )
        assert response.status_code == 200, response.text
        assert response.json()["sentiment_provider"] == "transformer"

    def test_patch_transformer_without_deps_returns_422(
        self, client: TestClient, owner_headers_sentiment: dict
    ):
        with patch(
            "src.api.routes.ai_settings._sentiment_transformer_deps_available",
            return_value=False,
        ):
            response = client.patch(
                "/api/v1/settings/ai",
                json={"sentiment_provider": "transformer"},
                headers=owner_headers_sentiment,
            )
        assert response.status_code == 422, response.text

    def test_patch_invalid_value_returns_422(self, client: TestClient, owner_headers_sentiment: dict):
        response = client.patch(
            "/api/v1/settings/ai",
            json={"sentiment_provider": "bogus"},
            headers=owner_headers_sentiment,
        )
        assert response.status_code == 422, response.text

    def test_patch_omitted_field_leaves_existing_value_unchanged(
        self, client: TestClient, db: Session, test_organization: Organization, owner_headers_sentiment: dict
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

        # PATCH some unrelated field, omit sentiment_provider entirely.
        response = client.patch(
            "/api/v1/settings/ai",
            json={"model_categorization": "gpt-4o"},
            headers=owner_headers_sentiment,
        )
        assert response.status_code == 200, response.text
        assert response.json()["sentiment_provider"] == "transformer"

    def test_patch_persists_and_round_trips_via_get(self, client: TestClient, owner_headers_sentiment: dict):
        with patch(
            "src.api.routes.ai_settings._sentiment_transformer_deps_available",
            return_value=True,
        ):
            patch_resp = client.patch(
                "/api/v1/settings/ai",
                json={"sentiment_provider": "transformer"},
                headers=owner_headers_sentiment,
            )
        assert patch_resp.status_code == 200, patch_resp.text

        get_resp = client.get("/api/v1/settings/ai", headers=owner_headers_sentiment)
        assert get_resp.status_code == 200, get_resp.text
        assert get_resp.json()["sentiment_provider"] == "transformer"

    def test_patch_requires_admin_or_owner(self, client: TestClient, member_headers_sentiment: dict):
        response = client.patch(
            "/api/v1/settings/ai",
            json={"sentiment_provider": "vader"},
            headers=member_headers_sentiment,
        )
        assert response.status_code == 403
