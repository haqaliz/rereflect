"""
TDD tests for usage_churn_labels_mode + usage_churn_label_config in the AI
settings GET/PATCH (services/backend-api/src/api/routes/ai_settings.py).

Field-substituted mirror of test_ai_settings_urgency_classifier_mode.py, with
a DELIBERATE divergence pinned by tests: valid values are off|shadow|active
(NOT off|shadow|auto like the three neighbouring classifier-mode columns),
and there is no scikit-learn dependency gate. See plan_20260723.md section 2.

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
def owner_user_usage_churn_labels(db: Session, test_organization: Organization) -> User:
    user = User(
        email="owner_usage_churn_labels@test.com",
        password_hash=hash_password("password123"),
        organization_id=test_organization.id,
        role="owner",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def owner_headers_usage_churn_labels(owner_user_usage_churn_labels: User) -> dict:
    token = create_access_token({
        "user_id": owner_user_usage_churn_labels.id,
        "organization_id": owner_user_usage_churn_labels.organization_id,
        "role": owner_user_usage_churn_labels.role,
    })
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def member_user_usage_churn_labels(db: Session, test_organization: Organization) -> User:
    user = User(
        email="member_usage_churn_labels@test.com",
        password_hash=hash_password("password123"),
        organization_id=test_organization.id,
        role="member",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def member_headers_usage_churn_labels(member_user_usage_churn_labels: User) -> dict:
    token = create_access_token({
        "user_id": member_user_usage_churn_labels.id,
        "organization_id": member_user_usage_churn_labels.organization_id,
        "role": member_user_usage_churn_labels.role,
    })
    return {"Authorization": f"Bearer {token}"}


class TestGetUsageChurnLabelsModeField:
    def test_get_defaults_to_off(self, client: TestClient, owner_headers_usage_churn_labels: dict):
        response = client.get("/api/v1/settings/ai", headers=owner_headers_usage_churn_labels)
        assert response.status_code == 200, response.text
        assert response.json()["usage_churn_labels_mode"] == "off"

    def test_get_with_no_org_ai_config_row_reads_off(
        self, client: TestClient, owner_headers_usage_churn_labels: dict
    ):
        """Org with NO OrgAIConfig row at all must still read 'off', not 500."""
        response = client.get("/api/v1/settings/ai", headers=owner_headers_usage_churn_labels)
        assert response.status_code == 200, response.text
        assert response.json()["usage_churn_labels_mode"] == "off"

    def test_get_returns_seeded_shadow_value(
        self, client: TestClient, db: Session, test_organization: Organization, owner_headers_usage_churn_labels: dict
    ):
        config = OrgAIConfig(
            organization_id=test_organization.id,
            default_provider="openai",
            model_categorization="gpt-4o-mini",
            model_analysis="gpt-4o-mini",
            model_insights="gpt-4o-mini",
            usage_churn_labels_mode="shadow",
        )
        db.add(config)
        db.commit()

        response = client.get("/api/v1/settings/ai", headers=owner_headers_usage_churn_labels)
        assert response.status_code == 200, response.text
        assert response.json()["usage_churn_labels_mode"] == "shadow"


class TestPatchUsageChurnLabelsModeValidation:
    @pytest.mark.parametrize("mode", ["off", "shadow", "active"])
    def test_patch_valid_modes_return_200(
        self, client: TestClient, owner_headers_usage_churn_labels: dict, mode: str
    ):
        response = client.patch(
            "/api/v1/settings/ai",
            json={"usage_churn_labels_mode": mode},
            headers=owner_headers_usage_churn_labels,
        )
        assert response.status_code == 200, response.text
        assert response.json()["usage_churn_labels_mode"] == mode

    def test_patch_auto_returns_422(self, client: TestClient, owner_headers_usage_churn_labels: dict):
        """Deliberate divergence from the sibling classifier-mode columns:
        'auto' is the sibling-column value and must be rejected here."""
        response = client.patch(
            "/api/v1/settings/ai",
            json={"usage_churn_labels_mode": "auto"},
            headers=owner_headers_usage_churn_labels,
        )
        assert response.status_code == 422, response.text

    def test_patch_garbage_value_returns_422(self, client: TestClient, owner_headers_usage_churn_labels: dict):
        response = client.patch(
            "/api/v1/settings/ai",
            json={"usage_churn_labels_mode": "bogus"},
            headers=owner_headers_usage_churn_labels,
        )
        assert response.status_code == 422, response.text

    def test_patch_shadow_does_not_require_sklearn(
        self, client: TestClient, owner_headers_usage_churn_labels: dict
    ):
        """This feature needs no ML dependency at all — _classifier_deps_available
        must NOT be consulted for this field."""
        with patch(
            "src.api.routes.ai_settings._classifier_deps_available",
            return_value=False,
        ):
            response = client.patch(
                "/api/v1/settings/ai",
                json={"usage_churn_labels_mode": "shadow"},
                headers=owner_headers_usage_churn_labels,
            )
        assert response.status_code == 200, response.text
        assert response.json()["usage_churn_labels_mode"] == "shadow"

    def test_patch_requires_admin_or_owner(self, client: TestClient, member_headers_usage_churn_labels: dict):
        response = client.patch(
            "/api/v1/settings/ai",
            json={"usage_churn_labels_mode": "off"},
            headers=member_headers_usage_churn_labels,
        )
        assert response.status_code == 403

    def test_patch_persists_and_round_trips_via_get(
        self, client: TestClient, owner_headers_usage_churn_labels: dict
    ):
        patch_resp = client.patch(
            "/api/v1/settings/ai",
            json={"usage_churn_labels_mode": "active"},
            headers=owner_headers_usage_churn_labels,
        )
        assert patch_resp.status_code == 200, patch_resp.text

        get_resp = client.get("/api/v1/settings/ai", headers=owner_headers_usage_churn_labels)
        assert get_resp.status_code == 200, get_resp.text
        assert get_resp.json()["usage_churn_labels_mode"] == "active"


class TestPatchUsageChurnLabelConfigValidation:
    def test_patch_sustain_days_default_valid_returns_200(
        self, client: TestClient, owner_headers_usage_churn_labels: dict
    ):
        response = client.patch(
            "/api/v1/settings/ai",
            json={"usage_churn_label_config": {"sustain_days": 7}},
            headers=owner_headers_usage_churn_labels,
        )
        assert response.status_code == 200, response.text
        assert response.json()["usage_churn_label_config"] == {"sustain_days": 7}

    @pytest.mark.parametrize("sustain_days", [0, -1, 91])
    def test_patch_sustain_days_out_of_bounds_returns_422(
        self, client: TestClient, owner_headers_usage_churn_labels: dict, sustain_days
    ):
        response = client.patch(
            "/api/v1/settings/ai",
            json={"usage_churn_label_config": {"sustain_days": sustain_days}},
            headers=owner_headers_usage_churn_labels,
        )
        assert response.status_code == 422, response.text

    def test_patch_sustain_days_bool_true_returns_422(
        self, client: TestClient, owner_headers_usage_churn_labels: dict
    ):
        """isinstance(True, int) is True in Python — must be explicitly rejected."""
        response = client.patch(
            "/api/v1/settings/ai",
            json={"usage_churn_label_config": {"sustain_days": True}},
            headers=owner_headers_usage_churn_labels,
        )
        assert response.status_code == 422, response.text

    def test_patch_sustain_days_boundary_min_returns_200(
        self, client: TestClient, owner_headers_usage_churn_labels: dict
    ):
        response = client.patch(
            "/api/v1/settings/ai",
            json={"usage_churn_label_config": {"sustain_days": 1}},
            headers=owner_headers_usage_churn_labels,
        )
        assert response.status_code == 200, response.text

    def test_patch_sustain_days_boundary_max_returns_200(
        self, client: TestClient, owner_headers_usage_churn_labels: dict
    ):
        response = client.patch(
            "/api/v1/settings/ai",
            json={"usage_churn_label_config": {"sustain_days": 90}},
            headers=owner_headers_usage_churn_labels,
        )
        assert response.status_code == 200, response.text

    def test_patch_unknown_key_returns_422(
        self, client: TestClient, owner_headers_usage_churn_labels: dict
    ):
        response = client.patch(
            "/api/v1/settings/ai",
            json={"usage_churn_label_config": {"sustain_days": 7, "bogus_key": "x"}},
            headers=owner_headers_usage_churn_labels,
        )
        assert response.status_code == 422, response.text

    def test_patch_config_persists_and_round_trips_via_get(
        self, client: TestClient, owner_headers_usage_churn_labels: dict
    ):
        patch_resp = client.patch(
            "/api/v1/settings/ai",
            json={"usage_churn_label_config": {"sustain_days": 14}},
            headers=owner_headers_usage_churn_labels,
        )
        assert patch_resp.status_code == 200, patch_resp.text

        get_resp = client.get("/api/v1/settings/ai", headers=owner_headers_usage_churn_labels)
        assert get_resp.status_code == 200, get_resp.text
        assert get_resp.json()["usage_churn_label_config"] == {"sustain_days": 14}
