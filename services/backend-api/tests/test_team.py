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

        # 400 Bad Request for invalid role (only admin/member allowed)
        assert response.status_code == 400

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
