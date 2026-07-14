"""
Tests for custom categories API endpoints.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.models.organization import Organization
from src.models.user import User
from src.models.custom_category import CustomCategory
from src.api.auth import hash_password, create_access_token


@pytest.fixture
def owner_user(db: Session, test_organization: Organization) -> User:
    """Create an owner user for category management."""
    user = User(
        email="owner@test.com",
        password_hash=hash_password("password123"),
        organization_id=test_organization.id,
        role="owner",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def owner_headers(owner_user: User) -> dict:
    token = create_access_token({
        "user_id": owner_user.id,
        "organization_id": owner_user.organization_id,
        "role": owner_user.role,
    })
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def member_user(db: Session, test_organization: Organization) -> User:
    """Create a member user (no admin privileges)."""
    user = User(
        email="member@test.com",
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
    token = create_access_token({
        "user_id": member_user.id,
        "organization_id": member_user.organization_id,
        "role": member_user.role,
    })
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def sample_category(db: Session, test_organization: Organization) -> CustomCategory:
    """Create a sample custom category."""
    cat = CustomCategory(
        organization_id=test_organization.id,
        name="onboarding_issues",
        description="Problems during onboarding",
        category_type="pain_point",
    )
    db.add(cat)
    db.commit()
    db.refresh(cat)
    return cat


class TestListCustomCategories:
    def test_list_empty(self, client: TestClient, auth_headers: dict):
        """Should return empty list when no custom categories exist."""
        response = client.get("/api/v1/categories/custom", headers=auth_headers)
        assert response.status_code == 200
        assert response.json() == []

    def test_list_with_categories(self, client: TestClient, auth_headers: dict, sample_category):
        """Should return custom categories for the org."""
        response = client.get("/api/v1/categories/custom", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == "onboarding_issues"
        assert data[0]["category_type"] == "pain_point"

    def test_filter_by_type(self, client: TestClient, auth_headers: dict, db, test_organization):
        """Should filter categories by type."""
        for cat_type in ["pain_point", "feature_request"]:
            db.add(CustomCategory(
                organization_id=test_organization.id,
                name=f"test_{cat_type}",
                category_type=cat_type,
            ))
        db.commit()

        response = client.get(
            "/api/v1/categories/custom?category_type=pain_point",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["category_type"] == "pain_point"

    def test_requires_auth(self, client: TestClient):
        """Should require authentication."""
        response = client.get("/api/v1/categories/custom")
        assert response.status_code == 403


class TestCreateCustomCategory:
    def test_create_success(self, client: TestClient, owner_headers: dict):
        """Should create a custom category."""
        response = client.post(
            "/api/v1/categories/custom",
            headers=owner_headers,
            json={
                "name": "api_requests",
                "description": "API-related feature requests",
                "category_type": "feature_request",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "api_requests"
        assert data["category_type"] == "feature_request"
        assert data["is_active"] is True

    def test_rejects_duplicate_name(self, client: TestClient, owner_headers: dict, sample_category):
        """Should reject duplicate category name within same org and type."""
        response = client.post(
            "/api/v1/categories/custom",
            headers=owner_headers,
            json={
                "name": "onboarding_issues",
                "category_type": "pain_point",
            },
        )
        assert response.status_code == 409

    def test_allows_same_name_different_type(self, client: TestClient, owner_headers: dict, sample_category):
        """Should allow same name in different category type."""
        response = client.post(
            "/api/v1/categories/custom",
            headers=owner_headers,
            json={
                "name": "onboarding_issues",
                "category_type": "feature_request",
            },
        )
        assert response.status_code == 201

    def test_member_cannot_create(self, client: TestClient, member_headers: dict):
        """Members should not be able to create categories."""
        response = client.post(
            "/api/v1/categories/custom",
            headers=member_headers,
            json={
                "name": "test_cat",
                "category_type": "general",
            },
        )
        assert response.status_code == 403

    def test_validates_category_type(self, client: TestClient, owner_headers: dict):
        """Should reject invalid category_type."""
        response = client.post(
            "/api/v1/categories/custom",
            headers=owner_headers,
            json={
                "name": "test",
                "category_type": "invalid_type",
            },
        )
        assert response.status_code == 422


class TestUpdateCustomCategory:
    def test_update_name(self, client: TestClient, owner_headers: dict, sample_category):
        """Should update category name."""
        response = client.patch(
            f"/api/v1/categories/custom/{sample_category.id}",
            headers=owner_headers,
            json={"name": "updated_name"},
        )
        assert response.status_code == 200
        assert response.json()["name"] == "updated_name"

    def test_toggle_active(self, client: TestClient, owner_headers: dict, sample_category):
        """Should toggle category active status."""
        response = client.patch(
            f"/api/v1/categories/custom/{sample_category.id}",
            headers=owner_headers,
            json={"is_active": False},
        )
        assert response.status_code == 200
        assert response.json()["is_active"] is False

    def test_not_found(self, client: TestClient, owner_headers: dict):
        """Should return 404 for non-existent category."""
        response = client.patch(
            "/api/v1/categories/custom/9999",
            headers=owner_headers,
            json={"name": "new_name"},
        )
        assert response.status_code == 404

    def test_rejects_duplicate_rename(
        self, client: TestClient, owner_headers: dict, sample_category, db, test_organization
    ):
        """Renaming to a name already used by another category (same org+type) -> 409.

        Characterization test locking existing behavior before extracting the
        shared custom_category_service.
        """
        other = CustomCategory(
            organization_id=test_organization.id,
            name="billing_issues",
            category_type="pain_point",
        )
        db.add(other)
        db.commit()
        db.refresh(other)

        response = client.patch(
            f"/api/v1/categories/custom/{other.id}",
            headers=owner_headers,
            json={"name": sample_category.name},
        )
        assert response.status_code == 409

    def test_other_org_returns_404(
        self, client: TestClient, owner_headers: dict, db
    ):
        """PATCHing a category belonging to a different org -> 404 (not leaked)."""
        other_org = Organization(name="Other Org", plan="pro")
        db.add(other_org)
        db.commit()
        db.refresh(other_org)

        other_cat = CustomCategory(
            organization_id=other_org.id,
            name="other_org_cat",
            category_type="pain_point",
        )
        db.add(other_cat)
        db.commit()
        db.refresh(other_cat)

        response = client.patch(
            f"/api/v1/categories/custom/{other_cat.id}",
            headers=owner_headers,
            json={"name": "hacked"},
        )
        assert response.status_code == 404

    def test_member_cannot_update(self, client: TestClient, member_headers: dict, sample_category):
        """Members should not be able to update categories."""
        response = client.patch(
            f"/api/v1/categories/custom/{sample_category.id}",
            headers=member_headers,
            json={"name": "hacked"},
        )
        assert response.status_code == 403


class TestDeleteCustomCategory:
    def test_delete_success(self, client: TestClient, owner_headers: dict, sample_category, db):
        """Should delete a category."""
        response = client.delete(
            f"/api/v1/categories/custom/{sample_category.id}",
            headers=owner_headers,
        )
        assert response.status_code == 204

        # Verify deleted from DB
        cat = db.query(CustomCategory).filter(CustomCategory.id == sample_category.id).first()
        assert cat is None

    def test_not_found(self, client: TestClient, owner_headers: dict):
        """Should return 404 for non-existent category."""
        response = client.delete(
            "/api/v1/categories/custom/9999",
            headers=owner_headers,
        )
        assert response.status_code == 404

    def test_member_cannot_delete(self, client: TestClient, member_headers: dict, sample_category):
        """Members should not be able to delete categories."""
        response = client.delete(
            f"/api/v1/categories/custom/{sample_category.id}",
            headers=member_headers,
        )
        assert response.status_code == 403
