"""
TDD tests for Conversations REST API (M2.2).

Tests cover:
- Conversations CRUD: list, create, get, update, soft delete
- Org scoping (multi-tenant isolation)
- Pagination
- Folder filtering
- Validation errors
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.models.user import User
from src.models.organization import Organization
from src.api.auth import hash_password, create_access_token


# =============================================================================
# ADDITIONAL FIXTURES
# =============================================================================


@pytest.fixture
def pro_organization(db: Session) -> Organization:
    """Create a Pro plan organization."""
    org = Organization(name="Pro Company", plan="pro")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


@pytest.fixture
def pro_user(db: Session, pro_organization: Organization) -> User:
    """Create a user in the Pro organization."""
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
def other_organization(db: Session) -> Organization:
    """Create another organization for isolation tests."""
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
# AUTHENTICATION TESTS
# =============================================================================


class TestConversationsAuth:
    def test_list_conversations_requires_auth(self, client: TestClient):
        response = client.get("/api/v1/conversations")
        assert response.status_code == 403

    def test_create_conversation_requires_auth(self, client: TestClient):
        response = client.post("/api/v1/conversations", json={"title": "Test"})
        assert response.status_code == 403

    def test_invalid_token_rejected(self, client: TestClient):
        headers = {"Authorization": "Bearer invalidtoken"}
        response = client.get("/api/v1/conversations", headers=headers)
        assert response.status_code == 401


# =============================================================================
# CREATE CONVERSATION TESTS
# =============================================================================


class TestCreateConversation:
    def test_create_conversation_minimal(self, client: TestClient, pro_auth_headers: dict):
        """Create a conversation with only required fields (auto title)."""
        response = client.post(
            "/api/v1/conversations",
            json={},
            headers=pro_auth_headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert "id" in data
        assert "title" in data
        assert data["is_active"] is True
        assert data["context_scope"] == "all_data"  # default

    def test_create_conversation_returns_public_id(self, client: TestClient, pro_auth_headers: dict):
        """Conversations should have a UUID public_id for URL-safe identification."""
        response = client.post(
            "/api/v1/conversations",
            json={"title": "UUID Test"},
            headers=pro_auth_headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert "public_id" in data
        # Should be a valid UUID string (36 chars with hyphens)
        import uuid
        uuid.UUID(data["public_id"])  # raises ValueError if invalid
        assert len(data["public_id"]) == 36

    def test_public_id_unique_per_conversation(self, client: TestClient, pro_auth_headers: dict):
        """Each conversation should get a unique public_id."""
        r1 = client.post("/api/v1/conversations", json={"title": "Conv 1"}, headers=pro_auth_headers)
        r2 = client.post("/api/v1/conversations", json={"title": "Conv 2"}, headers=pro_auth_headers)
        assert r1.json()["public_id"] != r2.json()["public_id"]

    def test_get_conversation_by_public_id(self, client: TestClient, pro_auth_headers: dict):
        """GET /{public_id} should return conversation detail."""
        r = client.post("/api/v1/conversations", json={"title": "Lookup Test"}, headers=pro_auth_headers)
        public_id = r.json()["public_id"]
        response = client.get(f"/api/v1/conversations/{public_id}", headers=pro_auth_headers)
        assert response.status_code == 200
        assert response.json()["public_id"] == public_id

    def test_delete_conversation_by_public_id(self, client: TestClient, pro_auth_headers: dict):
        """DELETE /{public_id} should soft-delete."""
        r = client.post("/api/v1/conversations", json={"title": "Delete Test"}, headers=pro_auth_headers)
        public_id = r.json()["public_id"]
        response = client.delete(f"/api/v1/conversations/{public_id}", headers=pro_auth_headers)
        assert response.status_code == 204

    def test_create_conversation_with_title(self, client: TestClient, pro_auth_headers: dict):
        response = client.post(
            "/api/v1/conversations",
            json={"title": "My First Conversation"},
            headers=pro_auth_headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "My First Conversation"

    def test_create_conversation_with_context_scope(self, client: TestClient, pro_auth_headers: dict):
        response = client.post(
            "/api/v1/conversations",
            json={"context_scope": "feedbacks"},
            headers=pro_auth_headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["context_scope"] == "feedbacks"

    def test_create_conversation_invalid_scope(self, client: TestClient, pro_auth_headers: dict):
        response = client.post(
            "/api/v1/conversations",
            json={"context_scope": "invalid_scope"},
            headers=pro_auth_headers,
        )
        assert response.status_code == 422

    def test_create_conversation_scoped_to_org(
        self, client: TestClient, pro_auth_headers: dict, other_auth_headers: dict
    ):
        """Conversations are scoped to the org from JWT."""
        r1 = client.post("/api/v1/conversations", json={"title": "Org1 Conv"}, headers=pro_auth_headers)
        assert r1.status_code == 201

        # Other org cannot see it
        r2 = client.get("/api/v1/conversations", headers=other_auth_headers)
        assert r2.status_code == 200
        data = r2.json()
        assert len(data["conversations"]) == 0

    def test_create_conversation_with_folder(
        self, client: TestClient, pro_auth_headers: dict
    ):
        """Create a conversation in a specific folder."""
        # First create a folder
        folder_resp = client.post(
            "/api/v1/conversations/folders",
            json={"name": "Work"},
            headers=pro_auth_headers,
        )
        assert folder_resp.status_code == 201
        folder_id = folder_resp.json()["id"]

        # Create conversation in that folder
        conv_resp = client.post(
            "/api/v1/conversations",
            json={"title": "Work Chat", "folder_id": folder_id},
            headers=pro_auth_headers,
        )
        assert conv_resp.status_code == 201
        assert conv_resp.json()["folder_id"] == folder_id

    def test_create_conversation_invalid_folder_id(
        self, client: TestClient, pro_auth_headers: dict
    ):
        """Providing a folder_id that doesn't belong to this org returns 404."""
        response = client.post(
            "/api/v1/conversations",
            json={"folder_id": 99999},
            headers=pro_auth_headers,
        )
        assert response.status_code == 404


# =============================================================================
# LIST CONVERSATIONS TESTS
# =============================================================================


class TestListConversations:
    def test_list_empty(self, client: TestClient, pro_auth_headers: dict):
        response = client.get("/api/v1/conversations", headers=pro_auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "conversations" in data
        assert "total" in data
        assert "page" in data
        assert "page_size" in data
        assert data["total"] == 0
        assert data["conversations"] == []

    def test_list_returns_org_conversations(
        self, client: TestClient, pro_auth_headers: dict
    ):
        # Create 3 conversations
        for i in range(3):
            client.post(
                "/api/v1/conversations",
                json={"title": f"Conv {i}"},
                headers=pro_auth_headers,
            )

        response = client.get("/api/v1/conversations", headers=pro_auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 3
        assert len(data["conversations"]) == 3

    def test_list_excludes_deleted(
        self, client: TestClient, pro_auth_headers: dict
    ):
        r1 = client.post("/api/v1/conversations", json={"title": "Keep"}, headers=pro_auth_headers)
        r2 = client.post("/api/v1/conversations", json={"title": "Delete"}, headers=pro_auth_headers)
        conv_id = r2.json()["public_id"]

        client.delete(f"/api/v1/conversations/{conv_id}", headers=pro_auth_headers)

        response = client.get("/api/v1/conversations", headers=pro_auth_headers)
        data = response.json()
        assert data["total"] == 1
        assert data["conversations"][0]["title"] == "Keep"

    def test_list_pagination(self, client: TestClient, pro_auth_headers: dict):
        for i in range(5):
            client.post(
                "/api/v1/conversations",
                json={"title": f"Conv {i}"},
                headers=pro_auth_headers,
            )

        r1 = client.get("/api/v1/conversations?page=1&page_size=2", headers=pro_auth_headers)
        r2 = client.get("/api/v1/conversations?page=2&page_size=2", headers=pro_auth_headers)
        r3 = client.get("/api/v1/conversations?page=3&page_size=2", headers=pro_auth_headers)

        assert r1.status_code == 200
        assert len(r1.json()["conversations"]) == 2
        assert r1.json()["total"] == 5

        assert r2.status_code == 200
        assert len(r2.json()["conversations"]) == 2

        assert r3.status_code == 200
        assert len(r3.json()["conversations"]) == 1

    def test_list_filter_by_folder(
        self, client: TestClient, pro_auth_headers: dict
    ):
        folder_resp = client.post(
            "/api/v1/conversations/folders",
            json={"name": "Work"},
            headers=pro_auth_headers,
        )
        folder_id = folder_resp.json()["id"]

        # 2 in folder, 1 without folder
        client.post("/api/v1/conversations", json={"title": "Work 1", "folder_id": folder_id}, headers=pro_auth_headers)
        client.post("/api/v1/conversations", json={"title": "Work 2", "folder_id": folder_id}, headers=pro_auth_headers)
        client.post("/api/v1/conversations", json={"title": "No Folder"}, headers=pro_auth_headers)

        response = client.get(f"/api/v1/conversations?folder_id={folder_id}", headers=pro_auth_headers)
        data = response.json()
        assert data["total"] == 2
        for conv in data["conversations"]:
            assert conv["folder_id"] == folder_id

    def test_list_includes_message_count(
        self, client: TestClient, pro_auth_headers: dict
    ):
        r = client.post("/api/v1/conversations", json={"title": "Test"}, headers=pro_auth_headers)
        response = client.get("/api/v1/conversations", headers=pro_auth_headers)
        conv = response.json()["conversations"][0]
        assert "message_count" in conv


# =============================================================================
# GET CONVERSATION TESTS
# =============================================================================


class TestGetConversation:
    def test_get_conversation_with_messages(
        self, client: TestClient, pro_auth_headers: dict
    ):
        r = client.post("/api/v1/conversations", json={"title": "Test"}, headers=pro_auth_headers)
        public_id = r.json()["public_id"]

        response = client.get(f"/api/v1/conversations/{public_id}", headers=pro_auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["public_id"] == public_id
        assert "messages" in data
        assert isinstance(data["messages"], list)

    def test_get_conversation_not_found(
        self, client: TestClient, pro_auth_headers: dict
    ):
        response = client.get(
            "/api/v1/conversations/00000000-0000-0000-0000-000000000000",
            headers=pro_auth_headers,
        )
        assert response.status_code == 404

    def test_get_conversation_other_org_returns_404(
        self, client: TestClient, pro_auth_headers: dict, other_auth_headers: dict
    ):
        r = client.post("/api/v1/conversations", json={"title": "Test"}, headers=pro_auth_headers)
        public_id = r.json()["public_id"]

        response = client.get(f"/api/v1/conversations/{public_id}", headers=other_auth_headers)
        assert response.status_code == 404

    def test_get_deleted_conversation_returns_404(
        self, client: TestClient, pro_auth_headers: dict
    ):
        r = client.post("/api/v1/conversations", json={"title": "Test"}, headers=pro_auth_headers)
        public_id = r.json()["public_id"]
        client.delete(f"/api/v1/conversations/{public_id}", headers=pro_auth_headers)

        response = client.get(f"/api/v1/conversations/{public_id}", headers=pro_auth_headers)
        assert response.status_code == 404

    def test_get_conversation_messages_pagination(
        self, client: TestClient, pro_auth_headers: dict
    ):
        r = client.post("/api/v1/conversations", json={"title": "Test"}, headers=pro_auth_headers)
        public_id = r.json()["public_id"]

        response = client.get(
            f"/api/v1/conversations/{public_id}?page=1&page_size=10",
            headers=pro_auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "messages" in data
        assert "messages_total" in data


# =============================================================================
# UPDATE CONVERSATION TESTS
# =============================================================================


class TestUpdateConversation:
    def test_update_title(self, client: TestClient, pro_auth_headers: dict):
        r = client.post("/api/v1/conversations", json={"title": "Old Title"}, headers=pro_auth_headers)
        public_id = r.json()["public_id"]

        response = client.patch(
            f"/api/v1/conversations/{public_id}",
            json={"title": "New Title"},
            headers=pro_auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["title"] == "New Title"

    def test_update_context_scope(self, client: TestClient, pro_auth_headers: dict):
        r = client.post("/api/v1/conversations", json={}, headers=pro_auth_headers)
        public_id = r.json()["public_id"]

        response = client.patch(
            f"/api/v1/conversations/{public_id}",
            json={"context_scope": "feedbacks"},
            headers=pro_auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["context_scope"] == "feedbacks"

    def test_update_folder(self, client: TestClient, pro_auth_headers: dict):
        folder_resp = client.post(
            "/api/v1/conversations/folders",
            json={"name": "My Folder"},
            headers=pro_auth_headers,
        )
        folder_id = folder_resp.json()["id"]

        r = client.post("/api/v1/conversations", json={}, headers=pro_auth_headers)
        public_id = r.json()["public_id"]

        response = client.patch(
            f"/api/v1/conversations/{public_id}",
            json={"folder_id": folder_id},
            headers=pro_auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["folder_id"] == folder_id

    def test_update_other_org_conversation_returns_404(
        self, client: TestClient, pro_auth_headers: dict, other_auth_headers: dict
    ):
        r = client.post("/api/v1/conversations", json={"title": "Test"}, headers=pro_auth_headers)
        public_id = r.json()["public_id"]

        response = client.patch(
            f"/api/v1/conversations/{public_id}",
            json={"title": "Hacked"},
            headers=other_auth_headers,
        )
        assert response.status_code == 404

    def test_update_invalid_context_scope(
        self, client: TestClient, pro_auth_headers: dict
    ):
        r = client.post("/api/v1/conversations", json={}, headers=pro_auth_headers)
        public_id = r.json()["public_id"]

        response = client.patch(
            f"/api/v1/conversations/{public_id}",
            json={"context_scope": "not_valid"},
            headers=pro_auth_headers,
        )
        assert response.status_code == 422


# =============================================================================
# DELETE CONVERSATION TESTS
# =============================================================================


class TestDeleteConversation:
    def test_soft_delete_conversation(self, client: TestClient, pro_auth_headers: dict):
        r = client.post("/api/v1/conversations", json={"title": "Test"}, headers=pro_auth_headers)
        public_id = r.json()["public_id"]

        response = client.delete(f"/api/v1/conversations/{public_id}", headers=pro_auth_headers)
        assert response.status_code == 204

        # Should no longer appear in list
        list_resp = client.get("/api/v1/conversations", headers=pro_auth_headers)
        assert list_resp.json()["total"] == 0

    def test_delete_other_org_conversation_returns_404(
        self, client: TestClient, pro_auth_headers: dict, other_auth_headers: dict
    ):
        r = client.post("/api/v1/conversations", json={"title": "Test"}, headers=pro_auth_headers)
        public_id = r.json()["public_id"]

        response = client.delete(f"/api/v1/conversations/{public_id}", headers=other_auth_headers)
        assert response.status_code == 404

    def test_delete_nonexistent_returns_404(
        self, client: TestClient, pro_auth_headers: dict
    ):
        response = client.delete(
            "/api/v1/conversations/00000000-0000-0000-0000-000000000000",
            headers=pro_auth_headers,
        )
        assert response.status_code == 404


# =============================================================================
# TEMPLATE STARTERS TESTS
# =============================================================================


class TestConversationTemplates:
    def test_get_template_starters(self, client: TestClient, pro_auth_headers: dict):
        response = client.get("/api/v1/conversations/templates", headers=pro_auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 6  # PRD specifies 6-8 templates
        for template in data:
            assert "category" in template
            assert "text" in template
