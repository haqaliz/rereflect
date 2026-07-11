"""
TDD tests for category_classifier_mode in the AI settings GET/PATCH
(services/backend-api/src/api/routes/ai_settings.py).

Field-substituted mirror of test_ai_settings_classifier_mode.py exactly
(classifier_mode -> category_classifier_mode); same valid values
(off|shadow|auto), same sklearn dependency guard, since the category head
reuses VALID_CLASSIFIER_MODES and _classifier_deps_available unchanged.

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
def owner_user_cat_classifier(db: Session, test_organization: Organization) -> User:
    user = User(
        email="owner_cat_classifier@test.com",
        password_hash=hash_password("password123"),
        organization_id=test_organization.id,
        role="owner",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def owner_headers_cat_classifier(owner_user_cat_classifier: User) -> dict:
    token = create_access_token({
        "user_id": owner_user_cat_classifier.id,
        "organization_id": owner_user_cat_classifier.organization_id,
        "role": owner_user_cat_classifier.role,
    })
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def member_user_cat_classifier(db: Session, test_organization: Organization) -> User:
    user = User(
        email="member_cat_classifier@test.com",
        password_hash=hash_password("password123"),
        organization_id=test_organization.id,
        role="member",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def member_headers_cat_classifier(member_user_cat_classifier: User) -> dict:
    token = create_access_token({
        "user_id": member_user_cat_classifier.id,
        "organization_id": member_user_cat_classifier.organization_id,
        "role": member_user_cat_classifier.role,
    })
    return {"Authorization": f"Bearer {token}"}


class TestGetCategoryClassifierModeField:
    def test_get_defaults_to_off(self, client: TestClient, owner_headers_cat_classifier: dict):
        response = client.get("/api/v1/settings/ai", headers=owner_headers_cat_classifier)
        assert response.status_code == 200, response.text
        assert response.json()["category_classifier_mode"] == "off"

    def test_get_returns_seeded_shadow_value(
        self, client: TestClient, db: Session, test_organization: Organization, owner_headers_cat_classifier: dict
    ):
        config = OrgAIConfig(
            organization_id=test_organization.id,
            default_provider="openai",
            model_categorization="gpt-4o-mini",
            model_analysis="gpt-4o-mini",
            model_insights="gpt-4o-mini",
            category_classifier_mode="shadow",
        )
        db.add(config)
        db.commit()

        response = client.get("/api/v1/settings/ai", headers=owner_headers_cat_classifier)
        assert response.status_code == 200, response.text
        assert response.json()["category_classifier_mode"] == "shadow"


class TestPatchCategoryClassifierModeValidation:
    def test_patch_off_always_returns_200(self, client: TestClient, owner_headers_cat_classifier: dict):
        response = client.patch(
            "/api/v1/settings/ai",
            json={"category_classifier_mode": "off"},
            headers=owner_headers_cat_classifier,
        )
        assert response.status_code == 200, response.text
        assert response.json()["category_classifier_mode"] == "off"

    def test_patch_shadow_with_deps_available_returns_200(
        self, client: TestClient, owner_headers_cat_classifier: dict
    ):
        with patch(
            "src.api.routes.ai_settings._classifier_deps_available",
            return_value=True,
        ):
            response = client.patch(
                "/api/v1/settings/ai",
                json={"category_classifier_mode": "shadow"},
                headers=owner_headers_cat_classifier,
            )
        assert response.status_code == 200, response.text
        assert response.json()["category_classifier_mode"] == "shadow"

    def test_patch_auto_with_deps_available_returns_200(
        self, client: TestClient, owner_headers_cat_classifier: dict
    ):
        with patch(
            "src.api.routes.ai_settings._classifier_deps_available",
            return_value=True,
        ):
            response = client.patch(
                "/api/v1/settings/ai",
                json={"category_classifier_mode": "auto"},
                headers=owner_headers_cat_classifier,
            )
        assert response.status_code == 200, response.text
        assert response.json()["category_classifier_mode"] == "auto"

    def test_patch_shadow_without_deps_returns_422(
        self, client: TestClient, owner_headers_cat_classifier: dict
    ):
        with patch(
            "src.api.routes.ai_settings._classifier_deps_available",
            return_value=False,
        ):
            response = client.patch(
                "/api/v1/settings/ai",
                json={"category_classifier_mode": "shadow"},
                headers=owner_headers_cat_classifier,
            )
        assert response.status_code == 422, response.text

    def test_patch_auto_without_deps_returns_422(
        self, client: TestClient, owner_headers_cat_classifier: dict
    ):
        with patch(
            "src.api.routes.ai_settings._classifier_deps_available",
            return_value=False,
        ):
            response = client.patch(
                "/api/v1/settings/ai",
                json={"category_classifier_mode": "auto"},
                headers=owner_headers_cat_classifier,
            )
        assert response.status_code == 422, response.text

    def test_patch_invalid_value_returns_422(self, client: TestClient, owner_headers_cat_classifier: dict):
        response = client.patch(
            "/api/v1/settings/ai",
            json={"category_classifier_mode": "bogus"},
            headers=owner_headers_cat_classifier,
        )
        assert response.status_code == 422, response.text

    def test_patch_omitted_field_leaves_existing_value_unchanged(
        self, client: TestClient, db: Session, test_organization: Organization, owner_headers_cat_classifier: dict
    ):
        config = OrgAIConfig(
            organization_id=test_organization.id,
            default_provider="openai",
            model_categorization="gpt-4o-mini",
            model_analysis="gpt-4o-mini",
            model_insights="gpt-4o-mini",
            category_classifier_mode="shadow",
        )
        db.add(config)
        db.commit()

        response = client.patch(
            "/api/v1/settings/ai",
            json={"model_categorization": "gpt-4o"},
            headers=owner_headers_cat_classifier,
        )
        assert response.status_code == 200, response.text
        assert response.json()["category_classifier_mode"] == "shadow"

    def test_patch_persists_and_round_trips_via_get(self, client: TestClient, owner_headers_cat_classifier: dict):
        with patch(
            "src.api.routes.ai_settings._classifier_deps_available",
            return_value=True,
        ):
            patch_resp = client.patch(
                "/api/v1/settings/ai",
                json={"category_classifier_mode": "shadow"},
                headers=owner_headers_cat_classifier,
            )
        assert patch_resp.status_code == 200, patch_resp.text

        get_resp = client.get("/api/v1/settings/ai", headers=owner_headers_cat_classifier)
        assert get_resp.status_code == 200, get_resp.text
        assert get_resp.json()["category_classifier_mode"] == "shadow"

    def test_patch_requires_admin_or_owner(self, client: TestClient, member_headers_cat_classifier: dict):
        response = client.patch(
            "/api/v1/settings/ai",
            json={"category_classifier_mode": "off"},
            headers=member_headers_cat_classifier,
        )
        assert response.status_code == 403


class TestCategoryModeIndependentOfSentimentClassifierMode:
    """PRD 'independent control' goal, exercised at the API boundary."""

    def test_patching_category_mode_does_not_change_classifier_mode(
        self, client: TestClient, db: Session, test_organization: Organization, owner_headers_cat_classifier: dict
    ):
        config = OrgAIConfig(
            organization_id=test_organization.id,
            default_provider="openai",
            model_categorization="gpt-4o-mini",
            model_analysis="gpt-4o-mini",
            model_insights="gpt-4o-mini",
            classifier_mode="auto",
        )
        db.add(config)
        db.commit()

        with patch(
            "src.api.routes.ai_settings._classifier_deps_available",
            return_value=True,
        ):
            response = client.patch(
                "/api/v1/settings/ai",
                json={"category_classifier_mode": "shadow"},
                headers=owner_headers_cat_classifier,
            )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["category_classifier_mode"] == "shadow"
        assert body["classifier_mode"] == "auto", "classifier_mode must be untouched by a category_classifier_mode PATCH"
