"""
Phase 1 RED: Tests for churn_classifier_mode in the AI settings GET/PATCH
(services/backend-api/src/api/routes/ai_settings.py).

Mirrors test_ai_settings_classifier_mode.py's structure exactly, one field
substituted (churn_classifier_mode — the per-org churn head, per-org-churn-model
aspect). Same valid values off|shadow|auto, same sklearn deps gate.

Covers:
- GET /api/v1/settings/ai returns churn_classifier_mode (defaults "off")
- PATCH validates against {'off', 'shadow', 'auto'}
- PATCH 'shadow'/'auto' require sklearn deps to be importable (mocked find_spec)
- PATCH 'off' is always allowed regardless of deps
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
def owner_user_churn(db: Session, test_organization: Organization) -> User:
    user = User(
        email="owner_churn@test.com",
        password_hash=hash_password("password123"),
        organization_id=test_organization.id,
        role="owner",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def owner_headers_churn(owner_user_churn: User) -> dict:
    token = create_access_token({
        "user_id": owner_user_churn.id,
        "organization_id": owner_user_churn.organization_id,
        "role": owner_user_churn.role,
    })
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def member_user_churn(db: Session, test_organization: Organization) -> User:
    user = User(
        email="member_churn@test.com",
        password_hash=hash_password("password123"),
        organization_id=test_organization.id,
        role="member",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def member_headers_churn(member_user_churn: User) -> dict:
    token = create_access_token({
        "user_id": member_user_churn.id,
        "organization_id": member_user_churn.organization_id,
        "role": member_user_churn.role,
    })
    return {"Authorization": f"Bearer {token}"}


class TestGetChurnClassifierModeField:
    def test_get_defaults_to_off(self, client: TestClient, owner_headers_churn: dict):
        """No OrgAIConfig row at all -> churn_classifier_mode defaults to 'off'."""
        response = client.get("/api/v1/settings/ai", headers=owner_headers_churn)
        assert response.status_code == 200, response.text
        assert response.json()["churn_classifier_mode"] == "off"

    def test_get_returns_seeded_shadow_value(
        self, client: TestClient, db: Session, test_organization: Organization, owner_headers_churn: dict
    ):
        config = OrgAIConfig(
            organization_id=test_organization.id,
            default_provider="openai",
            model_categorization="gpt-4o-mini",
            model_analysis="gpt-4o-mini",
            model_insights="gpt-4o-mini",
            churn_classifier_mode="shadow",
        )
        db.add(config)
        db.commit()

        response = client.get("/api/v1/settings/ai", headers=owner_headers_churn)
        assert response.status_code == 200, response.text
        assert response.json()["churn_classifier_mode"] == "shadow"


class TestPatchChurnClassifierModeValidation:
    def test_patch_off_always_returns_200(self, client: TestClient, owner_headers_churn: dict):
        response = client.patch(
            "/api/v1/settings/ai",
            json={"churn_classifier_mode": "off"},
            headers=owner_headers_churn,
        )
        assert response.status_code == 200, response.text
        assert response.json()["churn_classifier_mode"] == "off"

    def test_patch_shadow_with_deps_available_returns_200(
        self, client: TestClient, owner_headers_churn: dict
    ):
        with patch(
            "src.api.routes.ai_settings._classifier_deps_available",
            return_value=True,
        ):
            response = client.patch(
                "/api/v1/settings/ai",
                json={"churn_classifier_mode": "shadow"},
                headers=owner_headers_churn,
            )
        assert response.status_code == 200, response.text
        assert response.json()["churn_classifier_mode"] == "shadow"

    def test_patch_auto_with_deps_available_returns_200(
        self, client: TestClient, owner_headers_churn: dict
    ):
        with patch(
            "src.api.routes.ai_settings._classifier_deps_available",
            return_value=True,
        ):
            response = client.patch(
                "/api/v1/settings/ai",
                json={"churn_classifier_mode": "auto"},
                headers=owner_headers_churn,
            )
        assert response.status_code == 200, response.text
        assert response.json()["churn_classifier_mode"] == "auto"

    def test_patch_shadow_without_deps_returns_422(
        self, client: TestClient, owner_headers_churn: dict
    ):
        with patch(
            "src.api.routes.ai_settings._classifier_deps_available",
            return_value=False,
        ):
            response = client.patch(
                "/api/v1/settings/ai",
                json={"churn_classifier_mode": "shadow"},
                headers=owner_headers_churn,
            )
        assert response.status_code == 422, response.text

    def test_patch_auto_without_deps_returns_422(
        self, client: TestClient, owner_headers_churn: dict
    ):
        with patch(
            "src.api.routes.ai_settings._classifier_deps_available",
            return_value=False,
        ):
            response = client.patch(
                "/api/v1/settings/ai",
                json={"churn_classifier_mode": "auto"},
                headers=owner_headers_churn,
            )
        assert response.status_code == 422, response.text

    def test_patch_invalid_value_returns_422(self, client: TestClient, owner_headers_churn: dict):
        response = client.patch(
            "/api/v1/settings/ai",
            json={"churn_classifier_mode": "bogus"},
            headers=owner_headers_churn,
        )
        assert response.status_code == 422, response.text

    def test_patch_omitted_field_leaves_existing_value_unchanged(
        self, client: TestClient, db: Session, test_organization: Organization, owner_headers_churn: dict
    ):
        config = OrgAIConfig(
            organization_id=test_organization.id,
            default_provider="openai",
            model_categorization="gpt-4o-mini",
            model_analysis="gpt-4o-mini",
            model_insights="gpt-4o-mini",
            churn_classifier_mode="shadow",
        )
        db.add(config)
        db.commit()

        # PATCH some unrelated field, omit churn_classifier_mode entirely.
        response = client.patch(
            "/api/v1/settings/ai",
            json={"model_categorization": "gpt-4o"},
            headers=owner_headers_churn,
        )
        assert response.status_code == 200, response.text
        assert response.json()["churn_classifier_mode"] == "shadow"

    def test_patch_persists_and_round_trips_via_get(self, client: TestClient, owner_headers_churn: dict):
        with patch(
            "src.api.routes.ai_settings._classifier_deps_available",
            return_value=True,
        ):
            patch_resp = client.patch(
                "/api/v1/settings/ai",
                json={"churn_classifier_mode": "shadow"},
                headers=owner_headers_churn,
            )
        assert patch_resp.status_code == 200, patch_resp.text

        get_resp = client.get("/api/v1/settings/ai", headers=owner_headers_churn)
        assert get_resp.status_code == 200, get_resp.text
        assert get_resp.json()["churn_classifier_mode"] == "shadow"

    def test_patch_requires_admin_or_owner(self, client: TestClient, member_headers_churn: dict):
        response = client.patch(
            "/api/v1/settings/ai",
            json={"churn_classifier_mode": "off"},
            headers=member_headers_churn,
        )
        assert response.status_code == 403
