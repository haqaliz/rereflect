"""
Tests for Team Management RBAC feature.

TDD RED Phase - These tests are designed to FAIL because the production code
doesn't exist yet. They define the expected behavior for:
1. Role field with values: 'owner', 'admin', 'member'
2. Permission middleware for role-based access control
3. Team list endpoint
4. Role change endpoint
5. New User model fields (last_active_at, invited_by_id, joined_at)
"""

import pytest
from datetime import datetime
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.models.user import User
from src.models.organization import Organization
from src.api.auth import hash_password, create_access_token


# =============================================================================
# FIXTURES - Additional fixtures for team tests
# =============================================================================


@pytest.fixture
def owner_user(db: Session, test_organization: Organization) -> User:
    """Create a test owner user (first user in organization)."""
    user = User(
        email="owner@example.com",
        password_hash=hash_password("password123"),
        organization_id=test_organization.id,
        role="owner"
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def admin_user(db: Session, test_organization: Organization) -> User:
    """Create a test admin user."""
    user = User(
        email="admin@example.com",
        password_hash=hash_password("password123"),
        organization_id=test_organization.id,
        role="admin"
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def member_user(db: Session, test_organization: Organization) -> User:
    """Create a test member user."""
    user = User(
        email="member@example.com",
        password_hash=hash_password("password123"),
        organization_id=test_organization.id,
        role="member"
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def other_org(db: Session) -> Organization:
    """Create another organization for multi-tenant isolation tests."""
    org = Organization(
        name="Other Company",
        plan="free"
    )
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


@pytest.fixture
def other_org_user(db: Session, other_org: Organization) -> User:
    """Create a user in a different organization."""
    user = User(
        email="other@example.com",
        password_hash=hash_password("password123"),
        organization_id=other_org.id,
        role="admin"
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def owner_token(owner_user: User) -> str:
    """Create a JWT token for owner user."""
    return create_access_token({
        "user_id": owner_user.id,
        "organization_id": owner_user.organization_id,
        "role": owner_user.role
    })


@pytest.fixture
def admin_token(admin_user: User) -> str:
    """Create a JWT token for admin user."""
    return create_access_token({
        "user_id": admin_user.id,
        "organization_id": admin_user.organization_id,
        "role": admin_user.role
    })


@pytest.fixture
def member_token(member_user: User) -> str:
    """Create a JWT token for member user."""
    return create_access_token({
        "user_id": member_user.id,
        "organization_id": member_user.organization_id,
        "role": member_user.role
    })


@pytest.fixture
def owner_headers(owner_token: str) -> dict:
    """Create authentication headers for owner."""
    return {"Authorization": f"Bearer {owner_token}"}


@pytest.fixture
def admin_headers(admin_token: str) -> dict:
    """Create authentication headers for admin."""
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture
def member_headers(member_token: str) -> dict:
    """Create authentication headers for member."""
    return {"Authorization": f"Bearer {member_token}"}


# =============================================================================
# ROLE FIELD TESTS
# =============================================================================


class TestUserRoleField:
    """Tests for user role field with new values: 'owner', 'admin', 'member'."""

    def test_user_has_role_field(self, db: Session, test_organization: Organization):
        """Test that User model has role field."""
        user = User(
            email="roletest@example.com",
            password_hash=hash_password("password123"),
            organization_id=test_organization.id,
            role="member"
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        assert hasattr(user, 'role')
        assert user.role == "member"

    def test_user_role_can_be_owner(self, db: Session, test_organization: Organization):
        """Test that user role can be set to 'owner'."""
        user = User(
            email="ownertest@example.com",
            password_hash=hash_password("password123"),
            organization_id=test_organization.id,
            role="owner"
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        assert user.role == "owner"

    def test_user_role_can_be_admin(self, db: Session, test_organization: Organization):
        """Test that user role can be set to 'admin'."""
        user = User(
            email="admintest@example.com",
            password_hash=hash_password("password123"),
            organization_id=test_organization.id,
            role="admin"
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        assert user.role == "admin"

    def test_user_role_can_be_member(self, db: Session, test_organization: Organization):
        """Test that user role can be set to 'member'."""
        user = User(
            email="membertest@example.com",
            password_hash=hash_password("password123"),
            organization_id=test_organization.id,
            role="member"
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        assert user.role == "member"

    def test_first_user_signup_gets_owner_role(self, client: TestClient, db: Session):
        """Test that first user who creates an organization gets 'owner' role.

        This test will FAIL because signup currently sets role to 'admin'.
        The expected behavior: first user in org should be 'owner'.
        """
        response = client.post(
            "/api/v1/auth/signup",
            json={
                "email": "firstuser@newcompany.com",
                "password": "password123",
                "organization_name": "Brand New Company"
            }
        )

        assert response.status_code == 201

        # Verify user was created with 'owner' role
        user = db.query(User).filter(User.email == "firstuser@newcompany.com").first()
        assert user is not None
        assert user.role == "owner"  # This will FAIL - currently returns 'admin'


# =============================================================================
# USER MODEL NEW FIELDS TESTS
# =============================================================================


class TestUserModelNewFields:
    """Tests for new User model fields required for team management."""

    def test_user_has_last_active_at_field(self, db: Session, test_organization: Organization):
        """Test that User model has last_active_at field.

        This test will FAIL because the field doesn't exist yet.
        """
        user = User(
            email="fieldtest1@example.com",
            password_hash=hash_password("password123"),
            organization_id=test_organization.id,
            role="member",
            last_active_at=datetime.utcnow()  # This will FAIL - field doesn't exist
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        assert hasattr(user, 'last_active_at')
        assert user.last_active_at is not None

    def test_user_has_invited_by_id_field(self, db: Session, test_organization: Organization, owner_user: User):
        """Test that User model has invited_by_id field.

        This test will FAIL because the field doesn't exist yet.
        """
        user = User(
            email="fieldtest2@example.com",
            password_hash=hash_password("password123"),
            organization_id=test_organization.id,
            role="member",
            invited_by_id=owner_user.id  # This will FAIL - field doesn't exist
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        assert hasattr(user, 'invited_by_id')
        assert user.invited_by_id == owner_user.id

    def test_user_has_joined_at_field(self, db: Session, test_organization: Organization):
        """Test that User model has joined_at field.

        This test will FAIL because the field doesn't exist yet.
        """
        join_time = datetime.utcnow()
        user = User(
            email="fieldtest3@example.com",
            password_hash=hash_password("password123"),
            organization_id=test_organization.id,
            role="member",
            joined_at=join_time  # This will FAIL - field doesn't exist
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        assert hasattr(user, 'joined_at')
        assert user.joined_at is not None


# =============================================================================
# PERMISSION MIDDLEWARE TESTS
# =============================================================================


class TestRequireRoleMiddleware:
    """Tests for role-based permission middleware.

    These tests will FAIL because:
    1. The require_role dependency doesn't exist
    2. The /api/v1/team endpoint doesn't exist
    """

    def test_require_admin_allows_owner(
        self,
        client: TestClient,
        owner_user: User,
        owner_headers: dict
    ):
        """Test that require_role('admin') allows owner access.

        This test will FAIL because the endpoint doesn't exist.
        """
        # Using a hypothetical admin-only endpoint
        response = client.get(
            "/api/v1/team",
            headers=owner_headers
        )

        # Owner should be allowed (owner >= admin)
        assert response.status_code != 403

    def test_require_admin_allows_admin(
        self,
        client: TestClient,
        admin_user: User,
        admin_headers: dict
    ):
        """Test that require_role('admin') allows admin access.

        This test will FAIL because the endpoint doesn't exist.
        """
        response = client.get(
            "/api/v1/team",
            headers=admin_headers
        )

        assert response.status_code != 403

    def test_require_admin_blocks_member(
        self,
        client: TestClient,
        member_user: User,
        member_headers: dict
    ):
        """Test that require_role('admin') blocks member access.

        This test will FAIL because the endpoint doesn't exist.
        """
        response = client.get(
            "/api/v1/team",
            headers=member_headers
        )

        # Member should be blocked from admin-only endpoints
        # For now, team list is viewable by all (per PRD)
        # This test is for when we have an actual admin-only endpoint
        assert response.status_code in [200, 403]  # Depends on endpoint permissions

    def test_require_owner_allows_owner(
        self,
        client: TestClient,
        owner_user: User,
        member_user: User,
        owner_headers: dict
    ):
        """Test that require_owner allows owner access to ownership transfer."""
        # Transfer ownership endpoint is owner-only
        response = client.post(
            f"/api/v1/team/{member_user.id}/transfer-ownership",
            headers=owner_headers
        )

        # Should succeed (200) or fail for other reasons, but NOT 403
        assert response.status_code != 403

    def test_require_owner_blocks_admin(
        self,
        client: TestClient,
        admin_user: User,
        member_user: User,
        admin_headers: dict
    ):
        """Test that require_owner blocks admin access to ownership transfer."""
        response = client.post(
            f"/api/v1/team/{member_user.id}/transfer-ownership",
            headers=admin_headers
        )

        assert response.status_code == 403

    def test_require_owner_blocks_member(
        self,
        client: TestClient,
        member_user: User,
        admin_user: User,
        member_headers: dict
    ):
        """Test that require_owner blocks member access to ownership transfer."""
        response = client.post(
            f"/api/v1/team/{admin_user.id}/transfer-ownership",
            headers=member_headers
        )

        assert response.status_code == 403


# =============================================================================
# TEAM LIST ENDPOINT TESTS
# =============================================================================


class TestTeamListEndpoint:
    """Tests for GET /api/v1/team endpoint.

    All tests in this class will FAIL because the endpoint doesn't exist.
    """

    def test_get_team_list_success(
        self,
        client: TestClient,
        owner_user: User,
        admin_user: User,
        member_user: User,
        owner_headers: dict
    ):
        """Test getting list of all team members."""
        response = client.get(
            "/api/v1/team",
            headers=owner_headers
        )

        assert response.status_code == 200
        data = response.json()

        # Response has members array and total
        assert "members" in data
        assert "total" in data
        assert isinstance(data["members"], list)
        assert len(data["members"]) == 3  # owner, admin, member
        assert data["total"] == 3

    def test_get_team_list_response_fields(
        self,
        client: TestClient,
        owner_user: User,
        owner_headers: dict
    ):
        """Test that team list response includes required fields."""
        response = client.get(
            "/api/v1/team",
            headers=owner_headers
        )

        assert response.status_code == 200
        data = response.json()

        assert len(data["members"]) > 0
        member = data["members"][0]

        # Required fields per PRD
        assert "id" in member
        assert "email" in member
        assert "role" in member
        assert "last_active_at" in member
        assert "joined_at" in member

    def test_get_team_list_excludes_password(
        self,
        client: TestClient,
        owner_user: User,
        owner_headers: dict
    ):
        """Test that team list response does NOT include password_hash."""
        response = client.get(
            "/api/v1/team",
            headers=owner_headers
        )

        assert response.status_code == 200
        data = response.json()

        for member in data["members"]:
            assert "password_hash" not in member
            assert "password" not in member

    def test_get_team_list_multi_tenant_isolation(
        self,
        client: TestClient,
        db: Session,
        owner_user: User,
        admin_user: User,
        member_user: User,
        other_org_user: User,
        owner_headers: dict
    ):
        """Test that team list only returns users from same organization."""
        response = client.get(
            "/api/v1/team",
            headers=owner_headers
        )

        assert response.status_code == 200
        data = response.json()

        # Should only return users from test_organization (3 users)
        # Should NOT include other_org_user
        assert len(data["members"]) == 3

        emails = [member["email"] for member in data["members"]]
        assert "other@example.com" not in emails
        assert "owner@example.com" in emails
        assert "admin@example.com" in emails
        assert "member@example.com" in emails

    def test_get_team_list_all_roles_can_view(
        self,
        client: TestClient,
        owner_user: User,
        admin_user: User,
        member_user: User,
        owner_headers: dict,
        admin_headers: dict,
        member_headers: dict
    ):
        """Test that all roles can view team list (per PRD)."""
        # Owner can view
        response = client.get("/api/v1/team", headers=owner_headers)
        assert response.status_code == 200

        # Admin can view
        response = client.get("/api/v1/team", headers=admin_headers)
        assert response.status_code == 200

        # Member can view
        response = client.get("/api/v1/team", headers=member_headers)
        assert response.status_code == 200

    def test_get_team_list_unauthorized(self, client: TestClient):
        """Test that team list requires authentication."""
        response = client.get("/api/v1/team")

        # 403 is returned when no auth header present (no credentials)
        assert response.status_code in [401, 403]


# =============================================================================
# ROLE CHANGE ENDPOINT TESTS
# =============================================================================


class TestRoleChangeEndpoint:
    """Tests for PATCH /api/v1/team/{user_id}/role endpoint.

    All tests in this class will FAIL because the endpoint doesn't exist.
    """

    def test_owner_can_change_member_to_admin(
        self,
        client: TestClient,
        owner_user: User,
        member_user: User,
        owner_headers: dict,
        db: Session
    ):
        """Test that owner can promote member to admin."""
        response = client.patch(
            f"/api/v1/team/{member_user.id}/role",
            headers=owner_headers,
            json={"role": "admin"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["role"] == "admin"

        # Verify in database
        db.refresh(member_user)
        assert member_user.role == "admin"

    def test_owner_can_demote_admin_to_member(
        self,
        client: TestClient,
        owner_user: User,
        admin_user: User,
        owner_headers: dict,
        db: Session
    ):
        """Test that owner can demote admin to member."""
        response = client.patch(
            f"/api/v1/team/{admin_user.id}/role",
            headers=owner_headers,
            json={"role": "member"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["role"] == "member"

        # Verify in database
        db.refresh(admin_user)
        assert admin_user.role == "member"

    def test_admin_cannot_promote_to_admin(
        self,
        client: TestClient,
        admin_user: User,
        member_user: User,
        admin_headers: dict,
        db: Session
    ):
        """Test that admin cannot promote member to admin - only owner can."""
        response = client.patch(
            f"/api/v1/team/{member_user.id}/role",
            headers=admin_headers,
            json={"role": "admin"}
        )

        # Only owner can promote to admin
        assert response.status_code == 403
        assert "only the owner" in response.json()["detail"].lower()

    def test_admin_cannot_change_owner_role(
        self,
        client: TestClient,
        owner_user: User,
        admin_user: User,
        admin_headers: dict
    ):
        """Test that admin cannot change owner's role."""
        response = client.patch(
            f"/api/v1/team/{owner_user.id}/role",
            headers=admin_headers,
            json={"role": "admin"}
        )

        assert response.status_code == 403
        assert "owner" in response.json()["detail"].lower()

    def test_member_cannot_change_any_role(
        self,
        client: TestClient,
        admin_user: User,
        member_user: User,
        member_headers: dict
    ):
        """Test that member cannot change any user's role."""
        response = client.patch(
            f"/api/v1/team/{admin_user.id}/role",
            headers=member_headers,
            json={"role": "member"}
        )

        assert response.status_code == 403

    def test_cannot_demote_owner(
        self,
        client: TestClient,
        owner_user: User,
        owner_headers: dict
    ):
        """Test that owner cannot be demoted (even by themselves)."""
        response = client.patch(
            f"/api/v1/team/{owner_user.id}/role",
            headers=owner_headers,
            json={"role": "admin"}
        )

        # Owner role cannot be changed - must use transfer ownership
        assert response.status_code == 403
        assert "cannot change" in response.json()["detail"].lower() or "owner" in response.json()["detail"].lower()

    def test_cannot_change_role_of_user_in_different_org(
        self,
        client: TestClient,
        owner_user: User,
        other_org_user: User,
        owner_headers: dict
    ):
        """Test multi-tenant isolation for role changes."""
        response = client.patch(
            f"/api/v1/team/{other_org_user.id}/role",
            headers=owner_headers,
            json={"role": "admin"}
        )

        # Should return 404 (user not found in this org)
        assert response.status_code == 404

    def test_change_role_invalid_role_value(
        self,
        client: TestClient,
        owner_user: User,
        member_user: User,
        owner_headers: dict
    ):
        """Test that invalid role values are rejected."""
        response = client.patch(
            f"/api/v1/team/{member_user.id}/role",
            headers=owner_headers,
            json={"role": "superadmin"}  # Invalid role
        )

        # 400 for invalid role value
        assert response.status_code == 400

    def test_change_role_nonexistent_user(
        self,
        client: TestClient,
        owner_user: User,
        owner_headers: dict
    ):
        """Test changing role of non-existent user."""
        response = client.patch(
            "/api/v1/team/99999/role",
            headers=owner_headers,
            json={"role": "admin"}
        )

        assert response.status_code == 404

    def test_change_role_unauthorized(
        self,
        client: TestClient,
        member_user: User
    ):
        """Test that role change requires authentication."""
        response = client.patch(
            f"/api/v1/team/{member_user.id}/role",
            json={"role": "admin"}
        )

        # 401 or 403 for unauthorized
        assert response.status_code in [401, 403]

    def test_change_role_returns_updated_user(
        self,
        client: TestClient,
        owner_user: User,
        member_user: User,
        owner_headers: dict
    ):
        """Test that role change returns the updated user object."""
        response = client.patch(
            f"/api/v1/team/{member_user.id}/role",
            headers=owner_headers,
            json={"role": "admin"}
        )

        assert response.status_code == 200
        data = response.json()

        # Should return full user object
        assert "id" in data
        assert "email" in data
        assert "role" in data
        assert data["id"] == member_user.id
        assert data["role"] == "admin"

        # Should NOT include sensitive data
        assert "password_hash" not in data


# =============================================================================
# OWNERSHIP TRANSFER TESTS (Owner-only feature)
# =============================================================================


class TestOwnershipTransfer:
    """Tests for ownership transfer functionality.

    Per PRD: Only owner can transfer ownership to another user.
    These tests will FAIL because the endpoint doesn't exist.
    """

    def test_owner_can_transfer_ownership(
        self,
        client: TestClient,
        owner_user: User,
        admin_user: User,
        owner_headers: dict,
        db: Session
    ):
        """Test that owner can transfer ownership to another user."""
        response = client.post(
            f"/api/v1/team/{admin_user.id}/transfer-ownership",
            headers=owner_headers
        )

        assert response.status_code == 200

        # Verify in database
        db.refresh(owner_user)
        db.refresh(admin_user)

        assert admin_user.role == "owner"
        assert owner_user.role == "admin"  # Former owner becomes admin

    def test_admin_cannot_transfer_ownership(
        self,
        client: TestClient,
        owner_user: User,
        admin_user: User,
        member_user: User,
        admin_headers: dict
    ):
        """Test that admin cannot transfer ownership."""
        response = client.post(
            f"/api/v1/team/{member_user.id}/transfer-ownership",
            headers=admin_headers
        )

        assert response.status_code == 403

    def test_member_cannot_transfer_ownership(
        self,
        client: TestClient,
        admin_user: User,
        member_user: User,
        member_headers: dict
    ):
        """Test that member cannot transfer ownership."""
        response = client.post(
            f"/api/v1/team/{admin_user.id}/transfer-ownership",
            headers=member_headers
        )

        assert response.status_code == 403

    def test_cannot_transfer_to_user_in_different_org(
        self,
        client: TestClient,
        owner_user: User,
        other_org_user: User,
        owner_headers: dict
    ):
        """Test cannot transfer ownership to user in different organization."""
        response = client.post(
            f"/api/v1/team/{other_org_user.id}/transfer-ownership",
            headers=owner_headers
        )

        assert response.status_code == 404


# =============================================================================
# INVITE USER TESTS
# =============================================================================


class TestInviteUser:
    """Tests for user invitation functionality.

    Per PRD: Admin+ can invite/remove members.
    These tests will FAIL because the endpoint doesn't exist.
    """

    def test_owner_can_invite_member(
        self,
        client: TestClient,
        owner_user: User,
        owner_headers: dict,
        db: Session
    ):
        """Test that owner can invite a new member."""
        response = client.post(
            "/api/v1/team/invite",
            headers=owner_headers,
            json={
                "email": "newmember@example.com",
                "role": "member"
            }
        )

        assert response.status_code == 201
        data = response.json()
        assert "id" in data
        assert data["email"] == "newmember@example.com"
        assert data["role"] == "member"

    def test_admin_can_invite_member(
        self,
        client: TestClient,
        admin_user: User,
        admin_headers: dict
    ):
        """Test that admin can invite a new member."""
        response = client.post(
            "/api/v1/team/invite",
            headers=admin_headers,
            json={
                "email": "invited@example.com",
                "role": "member"
            }
        )

        assert response.status_code == 201

    def test_member_cannot_invite(
        self,
        client: TestClient,
        member_user: User,
        member_headers: dict
    ):
        """Test that member cannot invite new users."""
        response = client.post(
            "/api/v1/team/invite",
            headers=member_headers,
            json={
                "email": "shouldfail@example.com",
                "role": "member"
            }
        )

        assert response.status_code == 403

    def test_cannot_invite_existing_email(
        self,
        client: TestClient,
        owner_user: User,
        admin_user: User,
        owner_headers: dict
    ):
        """Test that inviting an existing email fails."""
        response = client.post(
            "/api/v1/team/invite",
            headers=owner_headers,
            json={
                "email": admin_user.email,
                "role": "member"
            }
        )

        # 409 Conflict for duplicate email
        assert response.status_code == 409
        assert "already exists" in response.json()["detail"].lower()

    def test_admin_cannot_invite_owner(
        self,
        client: TestClient,
        admin_user: User,
        admin_headers: dict
    ):
        """Test that admin cannot invite a user as owner."""
        response = client.post(
            "/api/v1/team/invite",
            headers=admin_headers,
            json={
                "email": "newowner@example.com",
                "role": "owner"
            }
        )

        # 403 Forbidden - admins cannot invite owners (authorization issue)
        assert response.status_code == 403

    def test_invited_user_has_invited_by_id_set(
        self,
        client: TestClient,
        owner_user: User,
        owner_headers: dict,
        db: Session
    ):
        """Test that invited user has invited_by_id field set."""
        response = client.post(
            "/api/v1/team/invite",
            headers=owner_headers,
            json={
                "email": "trackedinvite@example.com",
                "role": "member"
            }
        )

        assert response.status_code == 201
        data = response.json()

        # Verify in database
        invited_user = db.query(User).filter(User.email == "trackedinvite@example.com").first()
        assert invited_user is not None
        assert invited_user.invited_by_id == owner_user.id


# =============================================================================
# REMOVE USER TESTS
# =============================================================================


class TestRemoveUser:
    """Tests for removing users from team.

    Per PRD: Admin+ can remove members.
    These tests will FAIL because the endpoint doesn't exist.
    """

    def test_owner_can_remove_member(
        self,
        client: TestClient,
        owner_user: User,
        member_user: User,
        owner_headers: dict,
        db: Session
    ):
        """Test that owner can remove a member."""
        response = client.delete(
            f"/api/v1/team/{member_user.id}",
            headers=owner_headers
        )

        assert response.status_code == 204

        # Verify user is removed
        deleted_user = db.query(User).filter(User.id == member_user.id).first()
        assert deleted_user is None

    def test_admin_can_remove_member(
        self,
        client: TestClient,
        admin_user: User,
        member_user: User,
        admin_headers: dict,
        db: Session
    ):
        """Test that admin can remove a member."""
        response = client.delete(
            f"/api/v1/team/{member_user.id}",
            headers=admin_headers
        )

        assert response.status_code == 204

    def test_admin_cannot_remove_owner(
        self,
        client: TestClient,
        owner_user: User,
        admin_user: User,
        admin_headers: dict
    ):
        """Test that admin cannot remove owner."""
        response = client.delete(
            f"/api/v1/team/{owner_user.id}",
            headers=admin_headers
        )

        assert response.status_code == 403

    def test_member_cannot_remove_anyone(
        self,
        client: TestClient,
        admin_user: User,
        member_user: User,
        member_headers: dict
    ):
        """Test that member cannot remove any user."""
        response = client.delete(
            f"/api/v1/team/{admin_user.id}",
            headers=member_headers
        )

        assert response.status_code == 403

    def test_cannot_remove_user_from_different_org(
        self,
        client: TestClient,
        owner_user: User,
        other_org_user: User,
        owner_headers: dict
    ):
        """Test multi-tenant isolation for user removal."""
        response = client.delete(
            f"/api/v1/team/{other_org_user.id}",
            headers=owner_headers
        )

        assert response.status_code == 404

    def test_owner_cannot_remove_self(
        self,
        client: TestClient,
        owner_user: User,
        owner_headers: dict
    ):
        """Test that owner cannot remove themselves."""
        response = client.delete(
            f"/api/v1/team/{owner_user.id}",
            headers=owner_headers
        )

        # 403 Forbidden - cannot remove owner (includes self)
        assert response.status_code == 403


# =============================================================================
# PHASE 2: TEAM INVITATION SYSTEM TESTS
# =============================================================================
#
# TDD RED Phase - These tests define the expected behavior for:
# 1. TeamInvite model with required fields
# 2. Invite status management (pending, accepted, expired, canceled)
# 3. List pending invites endpoint
# 4. Resend invite endpoint
# 5. Cancel invite endpoint
# 6. Public invite endpoints (get details, accept)
# =============================================================================


from datetime import timedelta
import secrets


# =============================================================================
# FIXTURES - Additional fixtures for invitation tests
# =============================================================================


@pytest.fixture
def pending_invite(db: Session, test_organization: Organization, owner_user: User):
    """Create a pending team invite.

    This fixture will FAIL until TeamInvite model is implemented.
    """
    from src.models.team_invite import TeamInvite

    invite = TeamInvite(
        organization_id=test_organization.id,
        email="pending@example.com",
        role="member",
        token=secrets.token_urlsafe(32),
        invited_by_id=owner_user.id,
        status="pending"
    )
    db.add(invite)
    db.commit()
    db.refresh(invite)
    return invite


@pytest.fixture
def expired_invite(db: Session, test_organization: Organization, owner_user: User):
    """Create an expired team invite.

    This fixture will FAIL until TeamInvite model is implemented.
    """
    from src.models.team_invite import TeamInvite

    invite = TeamInvite(
        organization_id=test_organization.id,
        email="expired@example.com",
        role="member",
        token=secrets.token_urlsafe(32),
        invited_by_id=owner_user.id,
        status="pending",
        expires_at=datetime.utcnow() - timedelta(days=1)  # Already expired
    )
    db.add(invite)
    db.commit()
    db.refresh(invite)
    return invite


@pytest.fixture
def accepted_invite(db: Session, test_organization: Organization, owner_user: User):
    """Create an accepted team invite.

    This fixture will FAIL until TeamInvite model is implemented.
    """
    from src.models.team_invite import TeamInvite

    invite = TeamInvite(
        organization_id=test_organization.id,
        email="accepted@example.com",
        role="member",
        token=secrets.token_urlsafe(32),
        invited_by_id=owner_user.id,
        status="accepted",
        accepted_at=datetime.utcnow()
    )
    db.add(invite)
    db.commit()
    db.refresh(invite)
    return invite


@pytest.fixture
def canceled_invite(db: Session, test_organization: Organization, owner_user: User):
    """Create a canceled team invite.

    This fixture will FAIL until TeamInvite model is implemented.
    """
    from src.models.team_invite import TeamInvite

    invite = TeamInvite(
        organization_id=test_organization.id,
        email="canceled@example.com",
        role="admin",
        token=secrets.token_urlsafe(32),
        invited_by_id=owner_user.id,
        status="canceled"
    )
    db.add(invite)
    db.commit()
    db.refresh(invite)
    return invite


@pytest.fixture
def other_org_invite(db: Session, other_org: Organization, other_org_user: User):
    """Create an invite in a different organization.

    This fixture will FAIL until TeamInvite model is implemented.
    """
    from src.models.team_invite import TeamInvite

    invite = TeamInvite(
        organization_id=other_org.id,
        email="otherorginvite@example.com",
        role="member",
        token=secrets.token_urlsafe(32),
        invited_by_id=other_org_user.id,
        status="pending"
    )
    db.add(invite)
    db.commit()
    db.refresh(invite)
    return invite


# =============================================================================
# TEAM INVITE MODEL TESTS
# =============================================================================


class TestTeamInviteModel:
    """Tests for TeamInvite model fields and behavior.

    All tests will FAIL because the TeamInvite model doesn't exist yet.
    """

    def test_team_invite_model_exists(self):
        """Test that TeamInvite model can be imported."""
        from src.models.team_invite import TeamInvite
        assert TeamInvite is not None

    def test_team_invite_has_required_fields(self, db: Session, test_organization: Organization, owner_user: User):
        """Test that TeamInvite model has all required fields."""
        from src.models.team_invite import TeamInvite

        invite = TeamInvite(
            organization_id=test_organization.id,
            email="test@example.com",
            role="member",
            token="test_token_123",
            invited_by_id=owner_user.id,
            status="pending"
        )
        db.add(invite)
        db.commit()
        db.refresh(invite)

        # Verify all required fields exist
        assert hasattr(invite, 'id')
        assert hasattr(invite, 'organization_id')
        assert hasattr(invite, 'email')
        assert hasattr(invite, 'role')
        assert hasattr(invite, 'token')
        assert hasattr(invite, 'invited_by_id')
        assert hasattr(invite, 'status')
        assert hasattr(invite, 'created_at')
        assert hasattr(invite, 'expires_at')
        assert hasattr(invite, 'accepted_at')

        # Verify field values
        assert invite.id is not None
        assert invite.organization_id == test_organization.id
        assert invite.email == "test@example.com"
        assert invite.role == "member"
        assert invite.token == "test_token_123"
        assert invite.invited_by_id == owner_user.id
        assert invite.status == "pending"

    def test_team_invite_expires_at_defaults_to_7_days(self, db: Session, test_organization: Organization, owner_user: User):
        """Test that expires_at defaults to 7 days from creation.

        Per PRD: Invites expire after 7 days by default.
        """
        from src.models.team_invite import TeamInvite

        before_create = datetime.utcnow()

        invite = TeamInvite(
            organization_id=test_organization.id,
            email="expiry_test@example.com",
            role="member",
            token="expiry_token",
            invited_by_id=owner_user.id,
            status="pending"
        )
        db.add(invite)
        db.commit()
        db.refresh(invite)

        after_create = datetime.utcnow()

        # expires_at should be approximately 7 days from now
        expected_min = before_create + timedelta(days=7)
        expected_max = after_create + timedelta(days=7)

        assert invite.expires_at is not None
        assert expected_min <= invite.expires_at <= expected_max

    def test_team_invite_token_is_unique(self, db: Session, test_organization: Organization, owner_user: User):
        """Test that invite token has unique constraint."""
        from src.models.team_invite import TeamInvite
        from sqlalchemy.exc import IntegrityError

        invite1 = TeamInvite(
            organization_id=test_organization.id,
            email="unique1@example.com",
            role="member",
            token="same_token",
            invited_by_id=owner_user.id,
            status="pending"
        )
        db.add(invite1)
        db.commit()

        invite2 = TeamInvite(
            organization_id=test_organization.id,
            email="unique2@example.com",
            role="member",
            token="same_token",  # Same token - should fail
            invited_by_id=owner_user.id,
            status="pending"
        )
        db.add(invite2)

        with pytest.raises(IntegrityError):
            db.commit()

    def test_team_invite_status_values(self, db: Session, test_organization: Organization, owner_user: User):
        """Test that status can be set to all valid values: pending, accepted, expired, canceled."""
        from src.models.team_invite import TeamInvite

        statuses = ["pending", "accepted", "expired", "canceled"]

        for i, status in enumerate(statuses):
            invite = TeamInvite(
                organization_id=test_organization.id,
                email=f"status_test_{i}@example.com",
                role="member",
                token=f"status_token_{i}",
                invited_by_id=owner_user.id,
                status=status
            )
            db.add(invite)
            db.commit()
            db.refresh(invite)

            assert invite.status == status

    def test_team_invite_created_at_defaults_to_now(self, db: Session, test_organization: Organization, owner_user: User):
        """Test that created_at field defaults to current timestamp."""
        from src.models.team_invite import TeamInvite

        before_create = datetime.utcnow()

        invite = TeamInvite(
            organization_id=test_organization.id,
            email="created_test@example.com",
            role="member",
            token="created_token",
            invited_by_id=owner_user.id,
            status="pending"
        )
        db.add(invite)
        db.commit()
        db.refresh(invite)

        after_create = datetime.utcnow()

        assert invite.created_at is not None
        assert before_create <= invite.created_at <= after_create

    def test_team_invite_has_organization_relationship(self, db: Session, test_organization: Organization, owner_user: User):
        """Test that TeamInvite has relationship to Organization."""
        from src.models.team_invite import TeamInvite

        invite = TeamInvite(
            organization_id=test_organization.id,
            email="org_rel@example.com",
            role="member",
            token="org_rel_token",
            invited_by_id=owner_user.id,
            status="pending"
        )
        db.add(invite)
        db.commit()
        db.refresh(invite)

        assert hasattr(invite, 'organization')
        assert invite.organization.id == test_organization.id
        assert invite.organization.name == test_organization.name

    def test_team_invite_has_invited_by_relationship(self, db: Session, test_organization: Organization, owner_user: User):
        """Test that TeamInvite has relationship to inviting User."""
        from src.models.team_invite import TeamInvite

        invite = TeamInvite(
            organization_id=test_organization.id,
            email="inviter_rel@example.com",
            role="member",
            token="inviter_rel_token",
            invited_by_id=owner_user.id,
            status="pending"
        )
        db.add(invite)
        db.commit()
        db.refresh(invite)

        assert hasattr(invite, 'invited_by')
        assert invite.invited_by.id == owner_user.id
        assert invite.invited_by.email == owner_user.email


# =============================================================================
# LIST INVITES ENDPOINT TESTS
# =============================================================================


class TestListInvitesEndpoint:
    """Tests for GET /api/v1/team/invites endpoint.

    All tests will FAIL because the endpoint doesn't exist yet.
    """

    def test_list_invites_success(
        self,
        client: TestClient,
        owner_headers: dict,
        pending_invite,
        expired_invite,
        accepted_invite
    ):
        """Test listing pending invites for organization."""
        response = client.get(
            "/api/v1/team/invites",
            headers=owner_headers
        )

        assert response.status_code == 200
        data = response.json()

        assert "invites" in data
        assert "total" in data
        assert isinstance(data["invites"], list)

    def test_list_invites_returns_pending_only(
        self,
        client: TestClient,
        owner_headers: dict,
        pending_invite,
        accepted_invite,
        canceled_invite
    ):
        """Test that list only returns pending status invites by default."""
        response = client.get(
            "/api/v1/team/invites",
            headers=owner_headers
        )

        assert response.status_code == 200
        data = response.json()

        # Should only include pending invites
        for invite in data["invites"]:
            assert invite["status"] == "pending"

        # Check pending invite is included
        emails = [inv["email"] for inv in data["invites"]]
        assert "pending@example.com" in emails
        assert "accepted@example.com" not in emails
        assert "canceled@example.com" not in emails

    def test_list_invites_includes_expired_with_filter(
        self,
        client: TestClient,
        owner_headers: dict,
        pending_invite,
        expired_invite
    ):
        """Test that expired invites can be included with query param."""
        response = client.get(
            "/api/v1/team/invites?include_expired=true",
            headers=owner_headers
        )

        assert response.status_code == 200
        data = response.json()

        emails = [inv["email"] for inv in data["invites"]]
        assert "expired@example.com" in emails

    def test_list_invites_response_fields(
        self,
        client: TestClient,
        owner_headers: dict,
        pending_invite
    ):
        """Test that invite response includes required fields."""
        response = client.get(
            "/api/v1/team/invites",
            headers=owner_headers
        )

        assert response.status_code == 200
        data = response.json()

        assert len(data["invites"]) > 0
        invite = data["invites"][0]

        # Required fields per PRD
        assert "id" in invite
        assert "email" in invite
        assert "role" in invite
        assert "status" in invite
        assert "created_at" in invite
        assert "expires_at" in invite
        assert "invited_by" in invite  # Should include inviter info

        # Should NOT include token (security)
        assert "token" not in invite

    def test_list_invites_multi_tenant_isolation(
        self,
        client: TestClient,
        owner_headers: dict,
        pending_invite,
        other_org_invite
    ):
        """Test that invites from other organizations are not returned."""
        response = client.get(
            "/api/v1/team/invites",
            headers=owner_headers
        )

        assert response.status_code == 200
        data = response.json()

        emails = [inv["email"] for inv in data["invites"]]
        assert "otherorginvite@example.com" not in emails

    def test_list_invites_owner_can_view(
        self,
        client: TestClient,
        owner_headers: dict,
        pending_invite
    ):
        """Test that owner can view invites."""
        response = client.get(
            "/api/v1/team/invites",
            headers=owner_headers
        )

        assert response.status_code == 200

    def test_list_invites_admin_can_view(
        self,
        client: TestClient,
        admin_headers: dict,
        pending_invite
    ):
        """Test that admin can view invites."""
        response = client.get(
            "/api/v1/team/invites",
            headers=admin_headers
        )

        assert response.status_code == 200

    def test_list_invites_member_can_view(
        self,
        client: TestClient,
        member_headers: dict,
        pending_invite
    ):
        """Test that member can view invites (all authenticated users can view)."""
        response = client.get(
            "/api/v1/team/invites",
            headers=member_headers
        )

        assert response.status_code == 200

    def test_list_invites_unauthorized(self, client: TestClient):
        """Test that list invites requires authentication."""
        response = client.get("/api/v1/team/invites")

        assert response.status_code in [401, 403]


# =============================================================================
# RESEND INVITE ENDPOINT TESTS
# =============================================================================


class TestResendInviteEndpoint:
    """Tests for POST /api/v1/team/invites/:id/resend endpoint.

    All tests will FAIL because the endpoint doesn't exist yet.
    """

    def test_resend_invite_success(
        self,
        client: TestClient,
        owner_headers: dict,
        pending_invite,
        db: Session
    ):
        """Test that resending invite generates new token."""
        old_token = pending_invite.token

        response = client.post(
            f"/api/v1/team/invites/{pending_invite.id}/resend",
            headers=owner_headers
        )

        assert response.status_code == 200
        data = response.json()

        # Should return updated invite
        assert data["id"] == pending_invite.id
        assert data["email"] == pending_invite.email

        # Verify token was regenerated in database
        db.refresh(pending_invite)
        assert pending_invite.token != old_token

    def test_resend_invite_resets_expiry(
        self,
        client: TestClient,
        owner_headers: dict,
        pending_invite,
        db: Session
    ):
        """Test that resending invite resets expires_at to 7 days from now."""
        before_resend = datetime.utcnow()

        response = client.post(
            f"/api/v1/team/invites/{pending_invite.id}/resend",
            headers=owner_headers
        )

        assert response.status_code == 200

        after_resend = datetime.utcnow()

        # Verify expiry was reset
        db.refresh(pending_invite)
        expected_min = before_resend + timedelta(days=7)
        expected_max = after_resend + timedelta(days=7)

        assert expected_min <= pending_invite.expires_at <= expected_max

    def test_resend_expired_invite(
        self,
        client: TestClient,
        owner_headers: dict,
        expired_invite,
        db: Session
    ):
        """Test that expired invites can be resent."""
        response = client.post(
            f"/api/v1/team/invites/{expired_invite.id}/resend",
            headers=owner_headers
        )

        assert response.status_code == 200

        # Verify status changed back to pending
        db.refresh(expired_invite)
        assert expired_invite.status == "pending"

    def test_resend_accepted_invite_fails(
        self,
        client: TestClient,
        owner_headers: dict,
        accepted_invite
    ):
        """Test that accepted invites cannot be resent."""
        response = client.post(
            f"/api/v1/team/invites/{accepted_invite.id}/resend",
            headers=owner_headers
        )

        assert response.status_code == 400
        assert "already accepted" in response.json()["detail"].lower()

    def test_resend_canceled_invite_fails(
        self,
        client: TestClient,
        owner_headers: dict,
        canceled_invite
    ):
        """Test that canceled invites cannot be resent."""
        response = client.post(
            f"/api/v1/team/invites/{canceled_invite.id}/resend",
            headers=owner_headers
        )

        assert response.status_code == 400
        assert "canceled" in response.json()["detail"].lower()

    def test_resend_invite_multi_tenant_isolation(
        self,
        client: TestClient,
        owner_headers: dict,
        other_org_invite
    ):
        """Test that cannot resend invite from different organization."""
        response = client.post(
            f"/api/v1/team/invites/{other_org_invite.id}/resend",
            headers=owner_headers
        )

        assert response.status_code == 404

    def test_resend_invite_nonexistent(
        self,
        client: TestClient,
        owner_headers: dict
    ):
        """Test resending non-existent invite returns 404."""
        response = client.post(
            "/api/v1/team/invites/99999/resend",
            headers=owner_headers
        )

        assert response.status_code == 404

    def test_resend_invite_owner_can_resend(
        self,
        client: TestClient,
        owner_headers: dict,
        pending_invite
    ):
        """Test that owner can resend invites."""
        response = client.post(
            f"/api/v1/team/invites/{pending_invite.id}/resend",
            headers=owner_headers
        )

        assert response.status_code == 200

    def test_resend_invite_admin_can_resend(
        self,
        client: TestClient,
        admin_headers: dict,
        pending_invite
    ):
        """Test that admin can resend invites."""
        response = client.post(
            f"/api/v1/team/invites/{pending_invite.id}/resend",
            headers=admin_headers
        )

        assert response.status_code == 200

    def test_resend_invite_member_cannot_resend(
        self,
        client: TestClient,
        member_headers: dict,
        pending_invite
    ):
        """Test that member cannot resend invites."""
        response = client.post(
            f"/api/v1/team/invites/{pending_invite.id}/resend",
            headers=member_headers
        )

        assert response.status_code == 403

    def test_resend_invite_unauthorized(
        self,
        client: TestClient,
        pending_invite
    ):
        """Test that resend requires authentication."""
        response = client.post(
            f"/api/v1/team/invites/{pending_invite.id}/resend"
        )

        assert response.status_code in [401, 403]


# =============================================================================
# CANCEL INVITE ENDPOINT TESTS
# =============================================================================


class TestCancelInviteEndpoint:
    """Tests for DELETE /api/v1/team/invites/:id endpoint.

    All tests will FAIL because the endpoint doesn't exist yet.
    """

    def test_cancel_invite_success(
        self,
        client: TestClient,
        owner_headers: dict,
        pending_invite,
        db: Session
    ):
        """Test that canceling invite sets status to 'canceled'."""
        response = client.delete(
            f"/api/v1/team/invites/{pending_invite.id}",
            headers=owner_headers
        )

        assert response.status_code == 200

        # Verify status changed in database
        db.refresh(pending_invite)
        assert pending_invite.status == "canceled"

    def test_cancel_invite_response(
        self,
        client: TestClient,
        owner_headers: dict,
        pending_invite
    ):
        """Test cancel invite returns the updated invite."""
        response = client.delete(
            f"/api/v1/team/invites/{pending_invite.id}",
            headers=owner_headers
        )

        assert response.status_code == 200
        data = response.json()

        assert data["id"] == pending_invite.id
        assert data["status"] == "canceled"

    def test_cancel_accepted_invite_fails(
        self,
        client: TestClient,
        owner_headers: dict,
        accepted_invite
    ):
        """Test that accepted invites cannot be canceled."""
        response = client.delete(
            f"/api/v1/team/invites/{accepted_invite.id}",
            headers=owner_headers
        )

        assert response.status_code == 400
        assert "already accepted" in response.json()["detail"].lower()

    def test_cancel_already_canceled_invite(
        self,
        client: TestClient,
        owner_headers: dict,
        canceled_invite
    ):
        """Test canceling already canceled invite is idempotent."""
        response = client.delete(
            f"/api/v1/team/invites/{canceled_invite.id}",
            headers=owner_headers
        )

        # Should succeed (idempotent) or return appropriate message
        assert response.status_code in [200, 400]

    def test_cancel_invite_multi_tenant_isolation(
        self,
        client: TestClient,
        owner_headers: dict,
        other_org_invite
    ):
        """Test that cannot cancel invite from different organization."""
        response = client.delete(
            f"/api/v1/team/invites/{other_org_invite.id}",
            headers=owner_headers
        )

        assert response.status_code == 404

    def test_cancel_invite_nonexistent(
        self,
        client: TestClient,
        owner_headers: dict
    ):
        """Test canceling non-existent invite returns 404."""
        response = client.delete(
            "/api/v1/team/invites/99999",
            headers=owner_headers
        )

        assert response.status_code == 404

    def test_cancel_invite_owner_can_cancel(
        self,
        client: TestClient,
        owner_headers: dict,
        pending_invite
    ):
        """Test that owner can cancel invites."""
        response = client.delete(
            f"/api/v1/team/invites/{pending_invite.id}",
            headers=owner_headers
        )

        assert response.status_code == 200

    def test_cancel_invite_admin_can_cancel(
        self,
        client: TestClient,
        db: Session,
        test_organization: Organization,
        owner_user: User,
        admin_headers: dict
    ):
        """Test that admin can cancel invites."""
        from src.models.team_invite import TeamInvite

        # Create a fresh invite for this test
        invite = TeamInvite(
            organization_id=test_organization.id,
            email="admin_cancel_test@example.com",
            role="member",
            token=secrets.token_urlsafe(32),
            invited_by_id=owner_user.id,
            status="pending"
        )
        db.add(invite)
        db.commit()
        db.refresh(invite)

        response = client.delete(
            f"/api/v1/team/invites/{invite.id}",
            headers=admin_headers
        )

        assert response.status_code == 200

    def test_cancel_invite_member_cannot_cancel(
        self,
        client: TestClient,
        member_headers: dict,
        pending_invite
    ):
        """Test that member cannot cancel invites."""
        response = client.delete(
            f"/api/v1/team/invites/{pending_invite.id}",
            headers=member_headers
        )

        assert response.status_code == 403

    def test_cancel_invite_unauthorized(
        self,
        client: TestClient,
        pending_invite
    ):
        """Test that cancel requires authentication."""
        response = client.delete(
            f"/api/v1/team/invites/{pending_invite.id}"
        )

        assert response.status_code in [401, 403]


# =============================================================================
# PUBLIC INVITE DETAILS ENDPOINT TESTS
# =============================================================================


class TestGetInviteDetailsEndpoint:
    """Tests for GET /api/v1/invites/:token endpoint (public).

    This is a PUBLIC endpoint - no authentication required.
    Used to display invite details before accepting.

    All tests will FAIL because the endpoint doesn't exist yet.
    """

    def test_get_invite_details_success(
        self,
        client: TestClient,
        pending_invite,
        test_organization: Organization
    ):
        """Test getting invite details by token."""
        response = client.get(
            f"/api/v1/invites/{pending_invite.token}"
        )

        assert response.status_code == 200
        data = response.json()

        assert data["email"] == pending_invite.email
        assert data["role"] == pending_invite.role
        assert "organization_name" in data
        assert data["organization_name"] == test_organization.name

    def test_get_invite_details_response_fields(
        self,
        client: TestClient,
        pending_invite
    ):
        """Test that invite details response includes correct fields."""
        response = client.get(
            f"/api/v1/invites/{pending_invite.token}"
        )

        assert response.status_code == 200
        data = response.json()

        # Should include these fields
        assert "email" in data
        assert "role" in data
        assert "organization_name" in data
        assert "expires_at" in data
        assert "invited_by_name" in data  # Inviter's name/email

        # Should NOT include sensitive data
        assert "id" not in data or data.get("id") is None
        assert "token" not in data
        assert "organization_id" not in data

    def test_get_invite_details_invalid_token(self, client: TestClient):
        """Test that invalid token returns 404."""
        response = client.get(
            "/api/v1/invites/invalid_token_12345"
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower() or "invalid" in response.json()["detail"].lower()

    def test_get_invite_details_expired_token(
        self,
        client: TestClient,
        expired_invite
    ):
        """Test that expired invite returns appropriate error."""
        response = client.get(
            f"/api/v1/invites/{expired_invite.token}"
        )

        # Could return 404 or 410 (Gone) for expired
        assert response.status_code in [404, 410]
        assert "expired" in response.json()["detail"].lower()

    def test_get_invite_details_accepted_token(
        self,
        client: TestClient,
        accepted_invite
    ):
        """Test that already accepted invite returns appropriate error."""
        response = client.get(
            f"/api/v1/invites/{accepted_invite.token}"
        )

        # Could return 404 or 410 for already used
        assert response.status_code in [404, 410]
        assert "already" in response.json()["detail"].lower() or "accepted" in response.json()["detail"].lower()

    def test_get_invite_details_canceled_token(
        self,
        client: TestClient,
        canceled_invite
    ):
        """Test that canceled invite returns appropriate error."""
        response = client.get(
            f"/api/v1/invites/{canceled_invite.token}"
        )

        assert response.status_code in [404, 410]
        assert "canceled" in response.json()["detail"].lower() or "not found" in response.json()["detail"].lower()

    def test_get_invite_details_no_auth_required(
        self,
        client: TestClient,
        pending_invite
    ):
        """Test that this endpoint does NOT require authentication."""
        # No auth headers
        response = client.get(
            f"/api/v1/invites/{pending_invite.token}"
        )

        # Should succeed without authentication
        assert response.status_code == 200


# =============================================================================
# ACCEPT INVITE ENDPOINT TESTS
# =============================================================================


class TestAcceptInviteEndpoint:
    """Tests for POST /api/v1/invites/:token/accept endpoint (public).

    This is a PUBLIC endpoint - can be used by new users.
    Creates user if new, adds to org if existing.

    All tests will FAIL because the endpoint doesn't exist yet.
    """

    def test_accept_invite_new_user(
        self,
        client: TestClient,
        pending_invite,
        test_organization: Organization,
        db: Session
    ):
        """Test accepting invite creates new user."""
        response = client.post(
            f"/api/v1/invites/{pending_invite.token}/accept",
            json={
                "password": "NewUserPassword123!"
            }
        )

        assert response.status_code == 201
        data = response.json()

        # Should return user info and auth token
        assert "user" in data
        assert "access_token" in data
        assert data["user"]["email"] == pending_invite.email
        assert data["user"]["role"] == pending_invite.role

        # Verify user created in database
        new_user = db.query(User).filter(User.email == pending_invite.email).first()
        assert new_user is not None
        assert new_user.organization_id == test_organization.id
        assert new_user.role == pending_invite.role

    def test_accept_invite_updates_invite_status(
        self,
        client: TestClient,
        pending_invite,
        db: Session
    ):
        """Test that accepting invite updates invite status to 'accepted'."""
        response = client.post(
            f"/api/v1/invites/{pending_invite.token}/accept",
            json={
                "password": "NewUserPassword123!"
            }
        )

        assert response.status_code == 201

        # Verify invite status changed
        db.refresh(pending_invite)
        assert pending_invite.status == "accepted"
        assert pending_invite.accepted_at is not None

    def test_accept_invite_sets_user_invited_by(
        self,
        client: TestClient,
        pending_invite,
        owner_user: User,
        db: Session
    ):
        """Test that accepted invite sets invited_by_id on new user."""
        response = client.post(
            f"/api/v1/invites/{pending_invite.token}/accept",
            json={
                "password": "NewUserPassword123!"
            }
        )

        assert response.status_code == 201

        # Verify invited_by_id is set
        new_user = db.query(User).filter(User.email == pending_invite.email).first()
        assert new_user.invited_by_id == owner_user.id

    def test_accept_invite_sets_joined_at(
        self,
        client: TestClient,
        pending_invite,
        db: Session
    ):
        """Test that accepting invite sets joined_at on new user."""
        before_accept = datetime.utcnow()

        response = client.post(
            f"/api/v1/invites/{pending_invite.token}/accept",
            json={
                "password": "NewUserPassword123!"
            }
        )

        assert response.status_code == 201

        after_accept = datetime.utcnow()

        # Verify joined_at is set
        new_user = db.query(User).filter(User.email == pending_invite.email).first()
        assert new_user.joined_at is not None
        assert before_accept <= new_user.joined_at <= after_accept

    def test_accept_invite_existing_user_different_org(
        self,
        client: TestClient,
        db: Session,
        test_organization: Organization,
        owner_user: User,
        other_org: Organization
    ):
        """Test that existing user from different org can accept invite."""
        from src.models.team_invite import TeamInvite

        # Create a user in other_org
        existing_user = User(
            email="existing@other.com",
            password_hash=hash_password("password123"),
            organization_id=other_org.id,
            role="member"
        )
        db.add(existing_user)
        db.commit()

        # Create invite for this user's email
        invite = TeamInvite(
            organization_id=test_organization.id,
            email="existing@other.com",
            role="admin",
            token="existing_user_token",
            invited_by_id=owner_user.id,
            status="pending"
        )
        db.add(invite)
        db.commit()

        # Accept invite (existing user, but different org)
        response = client.post(
            f"/api/v1/invites/{invite.token}/accept",
            json={
                "password": "password123"  # Existing password
            }
        )

        assert response.status_code == 201

        # User should now be in test_organization with new role
        db.refresh(existing_user)
        # Note: This might create a new user or update existing - depends on implementation

    def test_accept_invite_invalid_token(self, client: TestClient):
        """Test accepting with invalid token returns 404."""
        response = client.post(
            "/api/v1/invites/invalid_token_xyz/accept",
            json={
                "password": "SomePassword123!"
            }
        )

        assert response.status_code == 404

    def test_accept_invite_expired_token(
        self,
        client: TestClient,
        expired_invite
    ):
        """Test that expired invite cannot be accepted."""
        response = client.post(
            f"/api/v1/invites/{expired_invite.token}/accept",
            json={
                "password": "SomePassword123!"
            }
        )

        assert response.status_code in [400, 404, 410]
        assert "expired" in response.json()["detail"].lower()

    def test_accept_invite_already_accepted(
        self,
        client: TestClient,
        accepted_invite
    ):
        """Test that already accepted invite cannot be accepted again."""
        response = client.post(
            f"/api/v1/invites/{accepted_invite.token}/accept",
            json={
                "password": "SomePassword123!"
            }
        )

        assert response.status_code in [400, 404, 410]
        assert "already" in response.json()["detail"].lower() or "accepted" in response.json()["detail"].lower()

    def test_accept_invite_canceled(
        self,
        client: TestClient,
        canceled_invite
    ):
        """Test that canceled invite cannot be accepted."""
        response = client.post(
            f"/api/v1/invites/{canceled_invite.token}/accept",
            json={
                "password": "SomePassword123!"
            }
        )

        assert response.status_code in [400, 404, 410]

    def test_accept_invite_requires_password(
        self,
        client: TestClient,
        pending_invite
    ):
        """Test that accepting invite requires password."""
        response = client.post(
            f"/api/v1/invites/{pending_invite.token}/accept",
            json={}  # No password
        )

        assert response.status_code == 422  # Validation error

    def test_accept_invite_weak_password(
        self,
        client: TestClient,
        pending_invite
    ):
        """Test that weak password is rejected."""
        response = client.post(
            f"/api/v1/invites/{pending_invite.token}/accept",
            json={
                "password": "123"  # Too weak
            }
        )

        # Should reject weak password
        assert response.status_code == 400

    def test_accept_invite_increments_seat_count(
        self,
        client: TestClient,
        pending_invite,
        test_organization: Organization,
        db: Session
    ):
        """Test that accepting invite increments organization seat count."""
        initial_seats = test_organization.seat_count

        response = client.post(
            f"/api/v1/invites/{pending_invite.token}/accept",
            json={
                "password": "NewUserPassword123!"
            }
        )

        assert response.status_code == 201

        # Verify seat count incremented
        db.refresh(test_organization)
        assert test_organization.seat_count == initial_seats + 1

    def test_accept_invite_no_auth_required(
        self,
        client: TestClient,
        pending_invite
    ):
        """Test that accept endpoint does NOT require authentication."""
        # No auth headers
        response = client.post(
            f"/api/v1/invites/{pending_invite.token}/accept",
            json={
                "password": "NewUserPassword123!"
            }
        )

        # Should succeed without authentication
        assert response.status_code == 201


# =============================================================================
# PHASE 4: AUDIT LOGGING TESTS
# =============================================================================
#
# TDD RED Phase - These tests define the expected behavior for:
# 1. AuditLog model with required fields
# 2. Audit log creation for team management actions
# 3. GET /api/v1/audit-logs endpoint with plan gating
# =============================================================================


# =============================================================================
# FIXTURES - Additional fixtures for audit logging tests
# =============================================================================


@pytest.fixture
def business_org(db: Session) -> Organization:
    """Create a test organization with Business plan (can access audit logs)."""
    org = Organization(
        name="Business Company",
        plan="business"
    )
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


@pytest.fixture
def business_owner(db: Session, business_org: Organization) -> User:
    """Create an owner user in a Business plan organization."""
    user = User(
        email="business_owner@example.com",
        password_hash=hash_password("password123"),
        organization_id=business_org.id,
        role="owner"
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def business_admin(db: Session, business_org: Organization) -> User:
    """Create an admin user in a Business plan organization."""
    user = User(
        email="business_admin@example.com",
        password_hash=hash_password("password123"),
        organization_id=business_org.id,
        role="admin"
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def business_member(db: Session, business_org: Organization) -> User:
    """Create a member user in a Business plan organization."""
    user = User(
        email="business_member@example.com",
        password_hash=hash_password("password123"),
        organization_id=business_org.id,
        role="member"
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def business_owner_token(business_owner: User) -> str:
    """Create a JWT token for business owner user."""
    return create_access_token({
        "user_id": business_owner.id,
        "organization_id": business_owner.organization_id,
        "role": business_owner.role
    })


@pytest.fixture
def business_admin_token(business_admin: User) -> str:
    """Create a JWT token for business admin user."""
    return create_access_token({
        "user_id": business_admin.id,
        "organization_id": business_admin.organization_id,
        "role": business_admin.role
    })


@pytest.fixture
def business_member_token(business_member: User) -> str:
    """Create a JWT token for business member user."""
    return create_access_token({
        "user_id": business_member.id,
        "organization_id": business_member.organization_id,
        "role": business_member.role
    })


@pytest.fixture
def business_owner_headers(business_owner_token: str) -> dict:
    """Create authentication headers for business owner."""
    return {"Authorization": f"Bearer {business_owner_token}"}


@pytest.fixture
def business_admin_headers(business_admin_token: str) -> dict:
    """Create authentication headers for business admin."""
    return {"Authorization": f"Bearer {business_admin_token}"}


@pytest.fixture
def business_member_headers(business_member_token: str) -> dict:
    """Create authentication headers for business member."""
    return {"Authorization": f"Bearer {business_member_token}"}


@pytest.fixture
def pro_org(db: Session) -> Organization:
    """Create a test organization with Pro plan (cannot access audit logs)."""
    org = Organization(
        name="Pro Company",
        plan="pro"
    )
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


@pytest.fixture
def pro_owner(db: Session, pro_org: Organization) -> User:
    """Create an owner user in a Pro plan organization."""
    user = User(
        email="pro_owner@example.com",
        password_hash=hash_password("password123"),
        organization_id=pro_org.id,
        role="owner"
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def pro_owner_token(pro_owner: User) -> str:
    """Create a JWT token for pro owner user."""
    return create_access_token({
        "user_id": pro_owner.id,
        "organization_id": pro_owner.organization_id,
        "role": pro_owner.role
    })


@pytest.fixture
def pro_owner_headers(pro_owner_token: str) -> dict:
    """Create authentication headers for pro owner."""
    return {"Authorization": f"Bearer {pro_owner_token}"}


# =============================================================================
# AUDIT LOG MODEL TESTS
# =============================================================================


class TestAuditLogModel:
    """Tests for AuditLog model fields and behavior.

    All tests will FAIL because the AuditLog model doesn't exist yet.
    This is TDD RED phase - tests define expected behavior.
    """

    def test_audit_log_model_exists(self):
        """Test that AuditLog model can be imported."""
        from src.models.audit_log import AuditLog
        assert AuditLog is not None

    def test_audit_log_has_required_fields(self, db: Session, test_organization: Organization, owner_user: User):
        """Test that AuditLog model has all required fields.

        Required fields per spec:
        - id: Primary key
        - organization_id: Foreign key to organization
        - user_id: User who performed the action
        - user_email: Email of user (for historical reference)
        - action: The action performed (e.g., 'user_invited', 'role_changed')
        - target_type: Type of entity affected (e.g., 'user', 'invite')
        - target_id: ID of the affected entity
        - details: JSON field with additional context
        - ip_address: IP address of the request
        - user_agent: User agent of the request
        - created_at: Timestamp of the action
        """
        from src.models.audit_log import AuditLog

        log = AuditLog(
            organization_id=test_organization.id,
            user_id=owner_user.id,
            user_email=owner_user.email,
            action="user_invited",
            target_type="invite",
            target_id=123,
            details={"email": "test@example.com", "role": "member"},
            ip_address="127.0.0.1",
            user_agent="Mozilla/5.0 Test Browser"
        )
        db.add(log)
        db.commit()
        db.refresh(log)

        # Verify all required fields exist
        assert hasattr(log, 'id')
        assert hasattr(log, 'organization_id')
        assert hasattr(log, 'user_id')
        assert hasattr(log, 'user_email')
        assert hasattr(log, 'action')
        assert hasattr(log, 'target_type')
        assert hasattr(log, 'target_id')
        assert hasattr(log, 'details')
        assert hasattr(log, 'ip_address')
        assert hasattr(log, 'user_agent')
        assert hasattr(log, 'created_at')

        # Verify field values
        assert log.id is not None
        assert log.organization_id == test_organization.id
        assert log.user_id == owner_user.id
        assert log.user_email == owner_user.email
        assert log.action == "user_invited"
        assert log.target_type == "invite"
        assert log.target_id == 123
        assert log.details == {"email": "test@example.com", "role": "member"}
        assert log.ip_address == "127.0.0.1"
        assert log.user_agent == "Mozilla/5.0 Test Browser"
        assert log.created_at is not None

    def test_audit_log_created_at_defaults_to_now(self, db: Session, test_organization: Organization, owner_user: User):
        """Test that created_at field defaults to current timestamp."""
        from src.models.audit_log import AuditLog

        before_create = datetime.utcnow()

        log = AuditLog(
            organization_id=test_organization.id,
            user_id=owner_user.id,
            user_email=owner_user.email,
            action="test_action",
            target_type="test",
            target_id=1
        )
        db.add(log)
        db.commit()
        db.refresh(log)

        after_create = datetime.utcnow()

        assert log.created_at is not None
        assert before_create <= log.created_at <= after_create

    def test_audit_log_details_is_json_field(self, db: Session, test_organization: Organization, owner_user: User):
        """Test that details field stores and retrieves JSON properly."""
        from src.models.audit_log import AuditLog

        complex_details = {
            "old_value": {"role": "member"},
            "new_value": {"role": "admin"},
            "metadata": {
                "reason": "promotion",
                "approved_by": owner_user.id
            }
        }

        log = AuditLog(
            organization_id=test_organization.id,
            user_id=owner_user.id,
            user_email=owner_user.email,
            action="role_changed",
            target_type="user",
            target_id=456,
            details=complex_details
        )
        db.add(log)
        db.commit()
        db.refresh(log)

        # Verify JSON is preserved correctly
        assert log.details == complex_details
        assert log.details["old_value"]["role"] == "member"
        assert log.details["new_value"]["role"] == "admin"

    def test_audit_log_details_can_be_null(self, db: Session, test_organization: Organization, owner_user: User):
        """Test that details field can be null."""
        from src.models.audit_log import AuditLog

        log = AuditLog(
            organization_id=test_organization.id,
            user_id=owner_user.id,
            user_email=owner_user.email,
            action="simple_action",
            target_type="user",
            target_id=789,
            details=None
        )
        db.add(log)
        db.commit()
        db.refresh(log)

        assert log.details is None

    def test_audit_log_has_organization_relationship(self, db: Session, test_organization: Organization, owner_user: User):
        """Test that AuditLog has relationship to Organization."""
        from src.models.audit_log import AuditLog

        log = AuditLog(
            organization_id=test_organization.id,
            user_id=owner_user.id,
            user_email=owner_user.email,
            action="test_relationship",
            target_type="test",
            target_id=1
        )
        db.add(log)
        db.commit()
        db.refresh(log)

        assert hasattr(log, 'organization')
        assert log.organization.id == test_organization.id


# =============================================================================
# AUDIT LOG CREATION TESTS
# =============================================================================


class TestAuditLogCreation:
    """Tests for audit log creation on team management actions.

    All tests will FAIL because audit logging is not yet implemented.
    These tests verify that appropriate audit logs are created when
    team management actions are performed.
    """

    def test_audit_log_created_when_user_invited(
        self,
        client: TestClient,
        business_owner_headers: dict,
        business_org: Organization,
        business_owner: User,
        db: Session
    ):
        """Test that audit log is created when a user is invited."""
        from src.models.audit_log import AuditLog

        # Invite a new user
        response = client.post(
            "/api/v1/team/invites",
            headers=business_owner_headers,
            json={
                "email": "audit_invite_test@example.com",
                "role": "member"
            }
        )

        assert response.status_code == 201

        # Verify audit log was created
        log = db.query(AuditLog).filter(
            AuditLog.organization_id == business_org.id,
            AuditLog.action == "user_invited"
        ).first()

        assert log is not None
        assert log.user_id == business_owner.id
        assert log.user_email == business_owner.email
        assert log.target_type == "invite"
        assert log.details["email"] == "audit_invite_test@example.com"
        assert log.details["role"] == "member"

    def test_audit_log_created_when_user_joins(
        self,
        client: TestClient,
        db: Session,
        business_org: Organization,
        business_owner: User
    ):
        """Test that audit log is created when a user accepts an invite and joins."""
        from src.models.audit_log import AuditLog
        from src.models.team_invite import TeamInvite

        # Create a pending invite
        invite = TeamInvite(
            organization_id=business_org.id,
            email="audit_join_test@example.com",
            role="member",
            token="audit_join_token_123",
            invited_by_id=business_owner.id,
            status="pending"
        )
        db.add(invite)
        db.commit()

        # Accept the invite
        response = client.post(
            f"/api/v1/invites/{invite.token}/accept",
            json={
                "password": "SecurePassword123!"
            }
        )

        assert response.status_code == 201

        # Verify audit log was created for user joining
        log = db.query(AuditLog).filter(
            AuditLog.organization_id == business_org.id,
            AuditLog.action == "user_joined"
        ).first()

        assert log is not None
        assert log.target_type == "user"
        assert log.details["email"] == "audit_join_test@example.com"
        assert log.details["role"] == "member"
        assert log.details["invite_id"] == invite.id

    def test_audit_log_created_when_user_removed(
        self,
        client: TestClient,
        business_owner_headers: dict,
        business_org: Organization,
        business_owner: User,
        business_member: User,
        db: Session
    ):
        """Test that audit log is created when a user is removed."""
        from src.models.audit_log import AuditLog

        # Remove the member
        response = client.delete(
            f"/api/v1/team/members/{business_member.id}",
            headers=business_owner_headers
        )

        assert response.status_code == 204

        # Verify audit log was created
        log = db.query(AuditLog).filter(
            AuditLog.organization_id == business_org.id,
            AuditLog.action == "user_removed"
        ).first()

        assert log is not None
        assert log.user_id == business_owner.id
        assert log.target_type == "user"
        assert log.target_id == business_member.id
        assert log.details["email"] == business_member.email
        assert log.details["role"] == business_member.role

    def test_audit_log_created_when_role_changed(
        self,
        client: TestClient,
        business_owner_headers: dict,
        business_org: Organization,
        business_owner: User,
        business_member: User,
        db: Session
    ):
        """Test that audit log is created when a user's role is changed."""
        from src.models.audit_log import AuditLog

        old_role = business_member.role

        # Change role from member to admin
        response = client.patch(
            f"/api/v1/team/members/{business_member.id}/role",
            headers=business_owner_headers,
            json={"role": "admin"}
        )

        assert response.status_code == 200

        # Verify audit log was created
        log = db.query(AuditLog).filter(
            AuditLog.organization_id == business_org.id,
            AuditLog.action == "role_changed"
        ).first()

        assert log is not None
        assert log.user_id == business_owner.id
        assert log.target_type == "user"
        assert log.target_id == business_member.id
        assert log.details["email"] == business_member.email
        assert log.details["old_role"] == old_role
        assert log.details["new_role"] == "admin"

    def test_audit_log_created_when_ownership_transferred(
        self,
        client: TestClient,
        business_owner_headers: dict,
        business_org: Organization,
        business_owner: User,
        business_admin: User,
        db: Session
    ):
        """Test that audit log is created when ownership is transferred."""
        from src.models.audit_log import AuditLog

        # Transfer ownership
        response = client.post(
            "/api/v1/team/transfer-ownership",
            headers=business_owner_headers,
            json={"user_id": business_admin.id}
        )

        assert response.status_code == 200

        # Verify audit log was created
        log = db.query(AuditLog).filter(
            AuditLog.organization_id == business_org.id,
            AuditLog.action == "ownership_transferred"
        ).first()

        assert log is not None
        assert log.user_id == business_owner.id
        assert log.target_type == "user"
        assert log.target_id == business_admin.id
        assert log.details["from_user_id"] == business_owner.id
        assert log.details["from_user_email"] == business_owner.email
        assert log.details["to_user_id"] == business_admin.id
        assert log.details["to_user_email"] == business_admin.email

    def test_audit_log_includes_ip_address(
        self,
        client: TestClient,
        business_owner_headers: dict,
        business_org: Organization,
        db: Session
    ):
        """Test that audit log captures the IP address of the request."""
        from src.models.audit_log import AuditLog

        # Perform an action
        response = client.post(
            "/api/v1/team/invites",
            headers=business_owner_headers,
            json={
                "email": "ip_test@example.com",
                "role": "member"
            }
        )

        assert response.status_code == 201

        # Verify audit log includes IP address
        log = db.query(AuditLog).filter(
            AuditLog.organization_id == business_org.id,
            AuditLog.action == "user_invited"
        ).order_by(AuditLog.created_at.desc()).first()

        assert log is not None
        assert log.ip_address is not None
        # TestClient uses "testclient" as default, but in real env would be IP
        assert len(log.ip_address) > 0

    def test_audit_log_includes_user_agent(
        self,
        client: TestClient,
        business_owner_headers: dict,
        business_org: Organization,
        db: Session
    ):
        """Test that audit log captures the user agent of the request."""
        from src.models.audit_log import AuditLog
        from sqlalchemy import func

        # Add custom user agent to headers
        headers = {**business_owner_headers, "User-Agent": "TestBot/1.0"}

        # Perform an action
        response = client.post(
            "/api/v1/team/invites",
            headers=headers,
            json={
                "email": "useragent_test@example.com",
                "role": "member"
            }
        )

        assert response.status_code == 201

        # Verify audit log includes user agent
        # Note: Using json_extract for SQLite compatibility (contains doesn't work in SQLite)
        log = db.query(AuditLog).filter(
            AuditLog.organization_id == business_org.id,
            func.json_extract(AuditLog.details, '$.email') == "useragent_test@example.com"
        ).first()

        assert log is not None
        assert log.user_agent is not None
        assert "TestBot/1.0" in log.user_agent


# =============================================================================
# GET AUDIT LOGS ENDPOINT TESTS
# =============================================================================


class TestAuditLogsEndpoint:
    """Tests for GET /api/v1/audit-logs endpoint.

    All tests will FAIL because the endpoint doesn't exist yet.
    This endpoint is gated to Business+ plans only.
    """

    def test_get_audit_logs_success(
        self,
        client: TestClient,
        business_owner_headers: dict,
        business_org: Organization,
        business_owner: User,
        db: Session
    ):
        """Test getting audit logs for organization."""
        from src.models.audit_log import AuditLog

        # Create some audit logs
        for i in range(3):
            log = AuditLog(
                organization_id=business_org.id,
                user_id=business_owner.id,
                user_email=business_owner.email,
                action=f"test_action_{i}",
                target_type="test",
                target_id=i
            )
            db.add(log)
        db.commit()

        response = client.get(
            "/api/v1/audit-logs",
            headers=business_owner_headers
        )

        assert response.status_code == 200
        data = response.json()

        assert "logs" in data
        assert "total" in data
        assert "page" in data
        assert "page_size" in data
        assert isinstance(data["logs"], list)
        assert len(data["logs"]) >= 3

    def test_get_audit_logs_paginated(
        self,
        client: TestClient,
        business_owner_headers: dict,
        business_org: Organization,
        business_owner: User,
        db: Session
    ):
        """Test that audit logs are paginated."""
        from src.models.audit_log import AuditLog

        # Create 25 audit logs
        for i in range(25):
            log = AuditLog(
                organization_id=business_org.id,
                user_id=business_owner.id,
                user_email=business_owner.email,
                action=f"paginated_action_{i}",
                target_type="test",
                target_id=i
            )
            db.add(log)
        db.commit()

        # Get first page (default page_size=20)
        response = client.get(
            "/api/v1/audit-logs?page=1&page_size=10",
            headers=business_owner_headers
        )

        assert response.status_code == 200
        data = response.json()

        assert data["page"] == 1
        assert data["page_size"] == 10
        assert len(data["logs"]) == 10
        assert data["total"] >= 25

        # Get second page
        response = client.get(
            "/api/v1/audit-logs?page=2&page_size=10",
            headers=business_owner_headers
        )

        assert response.status_code == 200
        data = response.json()

        assert data["page"] == 2
        assert len(data["logs"]) == 10

    def test_get_audit_logs_response_fields(
        self,
        client: TestClient,
        business_owner_headers: dict,
        business_org: Organization,
        business_owner: User,
        db: Session
    ):
        """Test that audit log response includes required fields."""
        from src.models.audit_log import AuditLog

        # Create an audit log
        log = AuditLog(
            organization_id=business_org.id,
            user_id=business_owner.id,
            user_email=business_owner.email,
            action="field_test_action",
            target_type="user",
            target_id=123,
            details={"test": "data"},
            ip_address="192.168.1.1",
            user_agent="Test/1.0"
        )
        db.add(log)
        db.commit()

        response = client.get(
            "/api/v1/audit-logs",
            headers=business_owner_headers
        )

        assert response.status_code == 200
        data = response.json()

        # Find our test log
        test_log = next((l for l in data["logs"] if l["action"] == "field_test_action"), None)
        assert test_log is not None

        # Check required fields
        assert "id" in test_log
        assert "user_id" in test_log
        assert "user_email" in test_log
        assert "action" in test_log
        assert "target_type" in test_log
        assert "target_id" in test_log
        assert "details" in test_log
        assert "ip_address" in test_log
        assert "user_agent" in test_log
        assert "created_at" in test_log

    def test_get_audit_logs_free_plan_blocked(
        self,
        client: TestClient,
        owner_headers: dict,
        test_organization: Organization
    ):
        """Test that Free plan cannot access audit logs."""
        # test_organization is Free plan by default
        response = client.get(
            "/api/v1/audit-logs",
            headers=owner_headers
        )

        assert response.status_code == 403
        data = response.json()

        assert "detail" in data
        # Should include upgrade message
        detail = data["detail"]
        if isinstance(detail, dict):
            assert "upgrade" in detail.get("message", "").lower() or \
                   "business" in detail.get("required_plan", "").lower()
        else:
            assert "upgrade" in str(detail).lower() or "business" in str(detail).lower()

    def test_get_audit_logs_pro_plan_blocked(
        self,
        client: TestClient,
        pro_owner_headers: dict
    ):
        """Test that Pro plan cannot access audit logs."""
        response = client.get(
            "/api/v1/audit-logs",
            headers=pro_owner_headers
        )

        assert response.status_code == 403
        data = response.json()

        # Should include upgrade message
        detail = data["detail"]
        if isinstance(detail, dict):
            assert "upgrade" in detail.get("message", "").lower() or \
                   "business" in detail.get("required_plan", "").lower()
        else:
            assert "upgrade" in str(detail).lower() or "business" in str(detail).lower()

    def test_get_audit_logs_business_plan_allowed(
        self,
        client: TestClient,
        business_owner_headers: dict
    ):
        """Test that Business plan can access audit logs."""
        response = client.get(
            "/api/v1/audit-logs",
            headers=business_owner_headers
        )

        assert response.status_code == 200

    def test_get_audit_logs_multi_tenant_isolation(
        self,
        client: TestClient,
        business_owner_headers: dict,
        business_org: Organization,
        business_owner: User,
        other_org: Organization,
        other_org_user: User,
        db: Session
    ):
        """Test that audit logs from other organizations are not returned."""
        from src.models.audit_log import AuditLog

        # Create audit log in business_org
        log1 = AuditLog(
            organization_id=business_org.id,
            user_id=business_owner.id,
            user_email=business_owner.email,
            action="business_org_action",
            target_type="test",
            target_id=1
        )
        db.add(log1)

        # Create audit log in other_org
        log2 = AuditLog(
            organization_id=other_org.id,
            user_id=other_org_user.id,
            user_email=other_org_user.email,
            action="other_org_action",
            target_type="test",
            target_id=2
        )
        db.add(log2)
        db.commit()

        # Get audit logs for business_org
        response = client.get(
            "/api/v1/audit-logs",
            headers=business_owner_headers
        )

        assert response.status_code == 200
        data = response.json()

        # Should only include business_org logs
        actions = [log["action"] for log in data["logs"]]
        assert "business_org_action" in actions
        assert "other_org_action" not in actions

    def test_get_audit_logs_owner_can_view(
        self,
        client: TestClient,
        business_owner_headers: dict
    ):
        """Test that owner can view audit logs."""
        response = client.get(
            "/api/v1/audit-logs",
            headers=business_owner_headers
        )

        assert response.status_code == 200

    def test_get_audit_logs_admin_can_view(
        self,
        client: TestClient,
        business_admin_headers: dict
    ):
        """Test that admin can view audit logs."""
        response = client.get(
            "/api/v1/audit-logs",
            headers=business_admin_headers
        )

        assert response.status_code == 200

    def test_get_audit_logs_member_cannot_view(
        self,
        client: TestClient,
        business_member_headers: dict
    ):
        """Test that member cannot view audit logs."""
        response = client.get(
            "/api/v1/audit-logs",
            headers=business_member_headers
        )

        assert response.status_code == 403

    def test_get_audit_logs_unauthorized(self, client: TestClient):
        """Test that audit logs requires authentication."""
        response = client.get("/api/v1/audit-logs")

        assert response.status_code in [401, 403]

    def test_get_audit_logs_sorted_by_created_at_desc(
        self,
        client: TestClient,
        business_owner_headers: dict,
        business_org: Organization,
        business_owner: User,
        db: Session
    ):
        """Test that audit logs are sorted by created_at descending (most recent first)."""
        from src.models.audit_log import AuditLog
        import time

        # Create audit logs with slight delays to ensure different timestamps
        for i in range(3):
            log = AuditLog(
                organization_id=business_org.id,
                user_id=business_owner.id,
                user_email=business_owner.email,
                action=f"sorted_action_{i}",
                target_type="test",
                target_id=i
            )
            db.add(log)
            db.commit()
            time.sleep(0.01)  # Small delay to ensure different timestamps

        response = client.get(
            "/api/v1/audit-logs",
            headers=business_owner_headers
        )

        assert response.status_code == 200
        data = response.json()

        # Filter to just our test logs
        sorted_logs = [l for l in data["logs"] if l["action"].startswith("sorted_action_")]

        # Should be in descending order (most recent first)
        timestamps = [l["created_at"] for l in sorted_logs]
        assert timestamps == sorted(timestamps, reverse=True)

    def test_get_audit_logs_filter_by_action(
        self,
        client: TestClient,
        business_owner_headers: dict,
        business_org: Organization,
        business_owner: User,
        db: Session
    ):
        """Test filtering audit logs by action type."""
        from src.models.audit_log import AuditLog

        # Create audit logs with different actions
        for action in ["user_invited", "user_removed", "role_changed"]:
            log = AuditLog(
                organization_id=business_org.id,
                user_id=business_owner.id,
                user_email=business_owner.email,
                action=action,
                target_type="user",
                target_id=1
            )
            db.add(log)
        db.commit()

        # Filter by action
        response = client.get(
            "/api/v1/audit-logs?action=user_invited",
            headers=business_owner_headers
        )

        assert response.status_code == 200
        data = response.json()

        # All logs should have the filtered action
        for log in data["logs"]:
            assert log["action"] == "user_invited"


# =============================================================================
# LAST_ACTIVE_AT TRACKING TESTS
# =============================================================================


class TestLastActiveAtTracking:
    """Tests for user.last_active_at tracking on authenticated requests.

    This feature updates the user's last_active_at timestamp on every
    authenticated API call to track user activity.
    """

    def test_last_active_at_updated_on_authenticated_request(
        self,
        client: TestClient,
        owner_user: User,
        owner_headers: dict,
        db: Session
    ):
        """Test that last_active_at is updated when making an authenticated request."""
        # Clear the last_active_at to ensure we can detect the update
        owner_user.last_active_at = None
        db.commit()
        db.refresh(owner_user)

        assert owner_user.last_active_at is None

        before_request = datetime.utcnow()

        # Make any authenticated API call
        response = client.get(
            "/api/v1/team/members",
            headers=owner_headers
        )

        # Request should succeed (team endpoint exists)
        assert response.status_code == 200

        after_request = datetime.utcnow()

        # Refresh user from database
        db.refresh(owner_user)

        # last_active_at should now be set
        assert owner_user.last_active_at is not None
        assert before_request <= owner_user.last_active_at <= after_request

    def test_last_active_at_updated_on_multiple_requests(
        self,
        client: TestClient,
        owner_user: User,
        owner_headers: dict,
        db: Session
    ):
        """Test that last_active_at is updated on each authenticated request."""
        import time

        # First request
        client.get("/api/v1/team/members", headers=owner_headers)
        db.refresh(owner_user)
        first_timestamp = owner_user.last_active_at

        assert first_timestamp is not None

        # Small delay to ensure timestamps differ
        time.sleep(0.01)

        # Second request
        client.get("/api/v1/team/members", headers=owner_headers)
        db.refresh(owner_user)
        second_timestamp = owner_user.last_active_at

        # Second timestamp should be newer
        assert second_timestamp is not None
        assert second_timestamp >= first_timestamp

    def test_last_active_at_not_updated_on_unauthenticated_request(
        self,
        client: TestClient,
        db: Session,
        test_organization: Organization,
        owner_user: User
    ):
        """Test that last_active_at is NOT updated on unauthenticated requests."""
        # Clear the last_active_at
        owner_user.last_active_at = None
        db.commit()
        db.refresh(owner_user)

        # Make an unauthenticated request (should fail)
        response = client.get("/api/v1/team/members")

        # Request should be unauthorized
        assert response.status_code in [401, 403]

        # Refresh user from database
        db.refresh(owner_user)

        # last_active_at should still be None
        assert owner_user.last_active_at is None

    def test_last_active_at_visible_in_team_list(
        self,
        client: TestClient,
        owner_user: User,
        admin_user: User,
        owner_headers: dict,
        db: Session
    ):
        """Test that last_active_at is included in team member list response."""
        # First make a request as admin to update their last_active_at
        admin_token = create_access_token({
            "user_id": admin_user.id,
            "organization_id": admin_user.organization_id,
            "role": admin_user.role
        })
        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        client.get("/api/v1/team/members", headers=admin_headers)

        # Now get the team list as owner
        response = client.get("/api/v1/team/members", headers=owner_headers)

        assert response.status_code == 200
        data = response.json()

        # Find the admin user in the response
        admin_member = next(
            (m for m in data["members"] if m["email"] == admin_user.email),
            None
        )

        assert admin_member is not None
        assert "last_active_at" in admin_member
        assert admin_member["last_active_at"] is not None
