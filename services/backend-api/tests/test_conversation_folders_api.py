"""
TDD tests for Conversation Folders REST API (M2.2).

Tests cover:
- Folders CRUD: list, create, update, delete
- Org scoping
- Plan gating (Pro+ required)
- Move conversations to null folder on folder delete
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.models.user import User
from src.models.organization import Organization
from src.api.auth import hash_password, create_access_token


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def pro_organization(db: Session) -> Organization:
    org = Organization(name="Pro Company", plan="pro")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


@pytest.fixture
def pro_user(db: Session, pro_organization: Organization) -> User:
    user = User(
        email="pro@example.com",
        password_hash=hash_password("password123"),
        organization_id=pro_organization.id,
        role="owner",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def pro_auth_headers(pro_user: User) -> dict:
    token = create_access_token({
        "user_id": pro_user.id,
        "organization_id": pro_user.organization_id,
        "role": pro_user.role,
    })
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def free_organization(db: Session) -> Organization:
    org = Organization(name="Free Company", plan="free")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


@pytest.fixture
def free_user(db: Session, free_organization: Organization) -> User:
    user = User(
        email="free@example.com",
        password_hash=hash_password("password123"),
        organization_id=free_organization.id,
        role="owner",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def free_auth_headers(free_user: User) -> dict:
    token = create_access_token({
        "user_id": free_user.id,
        "organization_id": free_user.organization_id,
        "role": free_user.role,
    })
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def other_organization(db: Session) -> Organization:
    org = Organization(name="Other Company", plan="pro")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


@pytest.fixture
def other_user(db: Session, other_organization: Organization) -> User:
    user = User(
        email="other@example.com",
        password_hash=hash_password("password123"),
        organization_id=other_organization.id,
        role="owner",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def other_auth_headers(other_user: User) -> dict:
    token = create_access_token({
        "user_id": other_user.id,
        "organization_id": other_user.organization_id,
        "role": other_user.role,
    })
    return {"Authorization": f"Bearer {token}"}


# =============================================================================
# CREATE FOLDER TESTS
# =============================================================================


class TestCreateFolder:
    def test_create_folder_pro_plan(self, client: TestClient, pro_auth_headers: dict):
        response = client.post(
            "/api/v1/conversations/folders",
            json={"name": "Work"},
            headers=pro_auth_headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Work"
        assert "id" in data
        assert "sort_order" in data
        assert "created_at" in data

    def test_create_folder_free_plan_forbidden(
        self, client: TestClient, free_auth_headers: dict
    ):
        """Free plan cannot create folders (Pro+ required per PRD §8.2)."""
        response = client.post(
            "/api/v1/conversations/folders",
            json={"name": "My Folder"},
            headers=free_auth_headers,
        )
        assert response.status_code == 403

    def test_create_folder_with_sort_order(
        self, client: TestClient, pro_auth_headers: dict
    ):
        response = client.post(
            "/api/v1/conversations/folders",
            json={"name": "Priority", "sort_order": 5},
            headers=pro_auth_headers,
        )
        assert response.status_code == 201
        assert response.json()["sort_order"] == 5

    def test_create_folder_missing_name(
        self, client: TestClient, pro_auth_headers: dict
    ):
        response = client.post(
            "/api/v1/conversations/folders",
            json={},
            headers=pro_auth_headers,
        )
        assert response.status_code == 422

    def test_create_folder_name_too_long(
        self, client: TestClient, pro_auth_headers: dict
    ):
        response = client.post(
            "/api/v1/conversations/folders",
            json={"name": "A" * 101},
            headers=pro_auth_headers,
        )
        assert response.status_code == 422

    def test_create_folder_requires_auth(self, client: TestClient):
        response = client.post("/api/v1/conversations/folders", json={"name": "Test"})
        assert response.status_code == 403


# =============================================================================
# LIST FOLDERS TESTS
# =============================================================================


class TestListFolders:
    def test_list_empty_folders(
        self, client: TestClient, pro_auth_headers: dict
    ):
        response = client.get("/api/v1/conversations/folders", headers=pro_auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 0

    def test_list_folders_returns_org_folders(
        self, client: TestClient, pro_auth_headers: dict
    ):
        client.post("/api/v1/conversations/folders", json={"name": "Work"}, headers=pro_auth_headers)
        client.post("/api/v1/conversations/folders", json={"name": "Personal"}, headers=pro_auth_headers)

        response = client.get("/api/v1/conversations/folders", headers=pro_auth_headers)
        data = response.json()
        assert len(data) == 2
        names = [f["name"] for f in data]
        assert "Work" in names
        assert "Personal" in names

    def test_list_folders_includes_conversation_count(
        self, client: TestClient, pro_auth_headers: dict
    ):
        folder_resp = client.post(
            "/api/v1/conversations/folders",
            json={"name": "Work"},
            headers=pro_auth_headers,
        )
        folder_id = folder_resp.json()["id"]

        # Create 2 conversations in this folder
        client.post("/api/v1/conversations", json={"title": "Conv 1", "folder_id": folder_id}, headers=pro_auth_headers)
        client.post("/api/v1/conversations", json={"title": "Conv 2", "folder_id": folder_id}, headers=pro_auth_headers)

        response = client.get("/api/v1/conversations/folders", headers=pro_auth_headers)
        folder = next(f for f in response.json() if f["id"] == folder_id)
        assert folder["conversation_count"] == 2

    def test_list_folders_scoped_to_org(
        self, client: TestClient, pro_auth_headers: dict, other_auth_headers: dict
    ):
        client.post("/api/v1/conversations/folders", json={"name": "Work"}, headers=pro_auth_headers)

        response = client.get("/api/v1/conversations/folders", headers=other_auth_headers)
        assert response.json() == []

    def test_list_folders_free_plan_allowed(
        self, client: TestClient, free_auth_headers: dict
    ):
        """Free users can list folders (even though they can't create them)."""
        response = client.get("/api/v1/conversations/folders", headers=free_auth_headers)
        assert response.status_code == 200


# =============================================================================
# UPDATE FOLDER TESTS
# =============================================================================


class TestUpdateFolder:
    def test_rename_folder(self, client: TestClient, pro_auth_headers: dict):
        r = client.post(
            "/api/v1/conversations/folders",
            json={"name": "Old Name"},
            headers=pro_auth_headers,
        )
        folder_id = r.json()["id"]

        response = client.patch(
            f"/api/v1/conversations/folders/{folder_id}",
            json={"name": "New Name"},
            headers=pro_auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["name"] == "New Name"

    def test_update_folder_sort_order(
        self, client: TestClient, pro_auth_headers: dict
    ):
        r = client.post(
            "/api/v1/conversations/folders",
            json={"name": "Work"},
            headers=pro_auth_headers,
        )
        folder_id = r.json()["id"]

        response = client.patch(
            f"/api/v1/conversations/folders/{folder_id}",
            json={"sort_order": 10},
            headers=pro_auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["sort_order"] == 10

    def test_update_other_org_folder_returns_404(
        self, client: TestClient, pro_auth_headers: dict, other_auth_headers: dict
    ):
        r = client.post(
            "/api/v1/conversations/folders",
            json={"name": "Work"},
            headers=pro_auth_headers,
        )
        folder_id = r.json()["id"]

        response = client.patch(
            f"/api/v1/conversations/folders/{folder_id}",
            json={"name": "Hacked"},
            headers=other_auth_headers,
        )
        assert response.status_code == 404

    def test_update_nonexistent_folder_returns_404(
        self, client: TestClient, pro_auth_headers: dict
    ):
        response = client.patch(
            "/api/v1/conversations/folders/99999",
            json={"name": "Test"},
            headers=pro_auth_headers,
        )
        assert response.status_code == 404

    def test_update_folder_name_too_long(
        self, client: TestClient, pro_auth_headers: dict
    ):
        r = client.post(
            "/api/v1/conversations/folders",
            json={"name": "Work"},
            headers=pro_auth_headers,
        )
        folder_id = r.json()["id"]

        response = client.patch(
            f"/api/v1/conversations/folders/{folder_id}",
            json={"name": "A" * 101},
            headers=pro_auth_headers,
        )
        assert response.status_code == 422


# =============================================================================
# DELETE FOLDER TESTS
# =============================================================================


class TestDeleteFolder:
    def test_delete_folder(self, client: TestClient, pro_auth_headers: dict):
        r = client.post(
            "/api/v1/conversations/folders",
            json={"name": "Work"},
            headers=pro_auth_headers,
        )
        folder_id = r.json()["id"]

        response = client.delete(
            f"/api/v1/conversations/folders/{folder_id}",
            headers=pro_auth_headers,
        )
        assert response.status_code == 204

        # Folder no longer listed
        folders = client.get("/api/v1/conversations/folders", headers=pro_auth_headers)
        assert len(folders.json()) == 0

    def test_delete_folder_moves_conversations_to_null(
        self, client: TestClient, pro_auth_headers: dict
    ):
        """When a folder is deleted, its conversations should have folder_id=null."""
        folder_resp = client.post(
            "/api/v1/conversations/folders",
            json={"name": "Work"},
            headers=pro_auth_headers,
        )
        folder_id = folder_resp.json()["id"]

        conv_resp = client.post(
            "/api/v1/conversations",
            json={"title": "Work Chat", "folder_id": folder_id},
            headers=pro_auth_headers,
        )
        conv_id = conv_resp.json()["id"]

        # Delete folder
        client.delete(
            f"/api/v1/conversations/folders/{folder_id}",
            headers=pro_auth_headers,
        )

        # Conversation should still exist but with folder_id=null
        conv = client.get(f"/api/v1/conversations/{conv_id}", headers=pro_auth_headers)
        assert conv.status_code == 200
        assert conv.json()["folder_id"] is None

    def test_delete_other_org_folder_returns_404(
        self, client: TestClient, pro_auth_headers: dict, other_auth_headers: dict
    ):
        r = client.post(
            "/api/v1/conversations/folders",
            json={"name": "Work"},
            headers=pro_auth_headers,
        )
        folder_id = r.json()["id"]

        response = client.delete(
            f"/api/v1/conversations/folders/{folder_id}",
            headers=other_auth_headers,
        )
        assert response.status_code == 404

    def test_delete_nonexistent_folder_returns_404(
        self, client: TestClient, pro_auth_headers: dict
    ):
        response = client.delete(
            "/api/v1/conversations/folders/99999",
            headers=pro_auth_headers,
        )
        assert response.status_code == 404
