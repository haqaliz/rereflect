"""
Tests for changelog API endpoints.
"""

import pytest
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.models.organization import Organization
from src.models.changelog_entry import ChangelogEntry
from src.models.user import User
from src.api.auth import hash_password, create_access_token


@pytest.fixture
def system_admin_user(db: Session, test_organization: Organization) -> User:
    user = User(
        email="sysadmin@changelog.com",
        password_hash=hash_password("password123"),
        organization_id=test_organization.id,
        role="owner",
        is_system_admin=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def system_admin_headers(system_admin_user: User) -> dict:
    token = create_access_token({
        "user_id": system_admin_user.id,
        "organization_id": system_admin_user.organization_id,
        "role": system_admin_user.role,
    })
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def regular_user(db: Session, test_organization: Organization) -> User:
    user = User(
        email="regular@changelog.com",
        password_hash=hash_password("password123"),
        organization_id=test_organization.id,
        role="member",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def regular_headers(regular_user: User) -> dict:
    token = create_access_token({
        "user_id": regular_user.id,
        "organization_id": regular_user.organization_id,
        "role": regular_user.role,
    })
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def changelog_entries(db: Session):
    """Create multiple changelog entries for testing."""
    now = datetime.utcnow()
    entries = [
        ChangelogEntry(
            commit_hash="abc1234567890123456789012345678901234567",
            title="Add user authentication",
            description="Implemented JWT-based auth with login and signup",
            entry_type="feature",
            is_breaking=False,
            is_hidden=False,
            committed_at=now - timedelta(days=1),
        ),
        ChangelogEntry(
            commit_hash="def1234567890123456789012345678901234567",
            title="Fix login redirect loop",
            description=None,
            entry_type="fix",
            is_breaking=False,
            is_hidden=False,
            committed_at=now - timedelta(days=3),
        ),
        ChangelogEntry(
            commit_hash="ghi1234567890123456789012345678901234567",
            title="Remove legacy API v0 endpoints",
            description="All v0 endpoints have been removed",
            entry_type="breaking_change",
            is_breaking=True,
            is_hidden=False,
            committed_at=now - timedelta(days=5),
        ),
        ChangelogEntry(
            commit_hash="jkl1234567890123456789012345678901234567",
            title="Refactor database queries",
            description=None,
            entry_type="improvement",
            is_breaking=False,
            is_hidden=True,  # Hidden entry
            committed_at=now - timedelta(days=10),
        ),
        ChangelogEntry(
            commit_hash="mno1234567890123456789012345678901234567",
            title="Update dependencies",
            description=None,
            entry_type="chore",
            is_breaking=False,
            is_hidden=False,
            committed_at=now - timedelta(days=40),
        ),
    ]
    for entry in entries:
        db.add(entry)
    db.commit()
    for entry in entries:
        db.refresh(entry)
    return entries


class TestPublicChangelog:
    """Tests for GET /api/v1/changelog (public, no auth)."""

    def test_list_returns_visible_entries_only(
        self, client: TestClient, changelog_entries
    ):
        """Should not return hidden entries."""
        response = client.get("/api/v1/changelog")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 4  # 5 total - 1 hidden
        assert len(data["items"]) == 4
        # Verify hidden entry is not included
        titles = [item["title"] for item in data["items"]]
        assert "Refactor database queries" not in titles

    def test_list_ordered_by_committed_at_desc(
        self, client: TestClient, changelog_entries
    ):
        """Should return entries in reverse chronological order."""
        response = client.get("/api/v1/changelog")
        assert response.status_code == 200
        data = response.json()
        assert data["items"][0]["title"] == "Add user authentication"
        assert data["items"][-1]["title"] == "Update dependencies"

    def test_filter_by_entry_type(
        self, client: TestClient, changelog_entries
    ):
        """Should filter by entry_type."""
        response = client.get("/api/v1/changelog?entry_type=fix")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["title"] == "Fix login redirect loop"

    def test_filter_by_days_7(
        self, client: TestClient, changelog_entries
    ):
        """Should filter entries from last 7 days."""
        response = client.get("/api/v1/changelog?days=7")
        assert response.status_code == 200
        data = response.json()
        # Only entries within last 7 days (1d, 3d, 5d ago)
        assert data["total"] == 3
        titles = [item["title"] for item in data["items"]]
        assert "Update dependencies" not in titles  # 40 days ago

    def test_filter_by_days_30(
        self, client: TestClient, changelog_entries
    ):
        """Should filter entries from last 30 days."""
        response = client.get("/api/v1/changelog?days=30")
        assert response.status_code == 200
        data = response.json()
        # 1d, 3d, 5d ago (not 10d hidden, not 40d)
        assert data["total"] == 3

    def test_pagination_with_limit(
        self, client: TestClient, changelog_entries
    ):
        """Should respect limit parameter."""
        response = client.get("/api/v1/changelog?limit=2")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2
        assert data["total"] == 4  # Total visible count
        assert data["has_more"] is True

    def test_pagination_with_offset(
        self, client: TestClient, changelog_entries
    ):
        """Should respect offset parameter."""
        response = client.get("/api/v1/changelog?limit=2&offset=2")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2
        assert data["has_more"] is False

    def test_no_auth_required(
        self, client: TestClient, changelog_entries
    ):
        """Should work without authentication."""
        response = client.get("/api/v1/changelog")
        assert response.status_code == 200

    def test_empty_list(self, client: TestClient):
        """Should return empty list when no entries exist."""
        response = client.get("/api/v1/changelog")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert len(data["items"]) == 0
        assert data["has_more"] is False

    def test_response_shape(
        self, client: TestClient, changelog_entries
    ):
        """Should return properly shaped entry objects."""
        response = client.get("/api/v1/changelog")
        assert response.status_code == 200
        data = response.json()
        entry = data["items"][0]
        assert "id" in entry
        assert "title" in entry
        assert "description" in entry
        assert "entry_type" in entry
        assert "is_breaking" in entry
        assert "committed_at" in entry
        # Public endpoint should NOT expose is_hidden
        assert "is_hidden" not in entry


class TestAdminChangelog:
    """Tests for admin changelog endpoints."""

    def test_admin_list_includes_hidden(
        self, client: TestClient, system_admin_headers: dict, changelog_entries
    ):
        """Should return all entries including hidden ones."""
        response = client.get("/api/v1/changelog/admin", headers=system_admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 5  # All 5 including hidden
        titles = [item["title"] for item in data["items"]]
        assert "Refactor database queries" in titles

    def test_admin_list_includes_is_hidden_field(
        self, client: TestClient, system_admin_headers: dict, changelog_entries
    ):
        """Should include is_hidden field in admin response."""
        response = client.get("/api/v1/changelog/admin", headers=system_admin_headers)
        assert response.status_code == 200
        data = response.json()
        for item in data["items"]:
            assert "is_hidden" in item

    def test_admin_list_requires_system_admin(
        self, client: TestClient, regular_headers: dict, changelog_entries
    ):
        """Should return 403 for non-system-admin users."""
        response = client.get("/api/v1/changelog/admin", headers=regular_headers)
        assert response.status_code == 403

    def test_admin_list_requires_auth(
        self, client: TestClient, changelog_entries
    ):
        """Should return 403 without auth."""
        response = client.get("/api/v1/changelog/admin")
        assert response.status_code == 403

    def test_update_entry(
        self, client: TestClient, system_admin_headers: dict, changelog_entries
    ):
        """Should update entry fields."""
        entry_id = changelog_entries[0].id
        response = client.patch(
            f"/api/v1/changelog/admin/{entry_id}",
            headers=system_admin_headers,
            json={
                "title": "Updated title",
                "description": "Updated description",
                "entry_type": "improvement",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Updated title"
        assert data["description"] == "Updated description"
        assert data["entry_type"] == "improvement"

    def test_hide_entry(
        self, client: TestClient, system_admin_headers: dict, changelog_entries
    ):
        """Should toggle entry visibility."""
        entry_id = changelog_entries[0].id
        response = client.patch(
            f"/api/v1/changelog/admin/{entry_id}",
            headers=system_admin_headers,
            json={"is_hidden": True},
        )
        assert response.status_code == 200
        assert response.json()["is_hidden"] is True

    def test_update_requires_system_admin(
        self, client: TestClient, regular_headers: dict, changelog_entries
    ):
        """Should return 403 for non-system-admin."""
        entry_id = changelog_entries[0].id
        response = client.patch(
            f"/api/v1/changelog/admin/{entry_id}",
            headers=regular_headers,
            json={"title": "Hacked"},
        )
        assert response.status_code == 403

    def test_delete_entry(
        self, client: TestClient, system_admin_headers: dict, changelog_entries
    ):
        """Should hard delete an entry."""
        entry_id = changelog_entries[0].id
        response = client.delete(
            f"/api/v1/changelog/admin/{entry_id}",
            headers=system_admin_headers,
        )
        assert response.status_code == 200

        # Verify it's gone
        response = client.get("/api/v1/changelog/admin", headers=system_admin_headers)
        data = response.json()
        ids = [item["id"] for item in data["items"]]
        assert entry_id not in ids

    def test_delete_requires_system_admin(
        self, client: TestClient, regular_headers: dict, changelog_entries
    ):
        """Should return 403 for non-system-admin."""
        entry_id = changelog_entries[0].id
        response = client.delete(
            f"/api/v1/changelog/admin/{entry_id}",
            headers=regular_headers,
        )
        assert response.status_code == 403

    def test_update_nonexistent_entry(
        self, client: TestClient, system_admin_headers: dict
    ):
        """Should return 404 for non-existent entry."""
        response = client.patch(
            "/api/v1/changelog/admin/99999",
            headers=system_admin_headers,
            json={"title": "Nope"},
        )
        assert response.status_code == 404

    def test_delete_nonexistent_entry(
        self, client: TestClient, system_admin_headers: dict
    ):
        """Should return 404 for non-existent entry."""
        response = client.delete(
            "/api/v1/changelog/admin/99999",
            headers=system_admin_headers,
        )
        assert response.status_code == 404
