"""
TDD tests for the `oidc-login-flow` aspect of `oidc-sso`.

Task 1: `users.oidc_sub` column (additive, unique, nullable) that OIDC login
will populate on JIT-provision/link. Subsequent tasks (provider service,
/start, /callback) grow this file.
"""
import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.api.auth import hash_password
from src.models.organization import Organization
from src.models.user import User


class TestUserOidcSubColumn:

    def test_user_oidc_sub_column(self, db: Session, test_organization: Organization):
        """A User can be created with oidc_sub set and it persists on readback."""
        user = User(
            email="sso-user@example.com",
            password_hash=hash_password("password123"),
            organization_id=test_organization.id,
            role="member",
            auth_provider="oidc",
            oidc_sub="sub-123",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        fetched = db.query(User).filter(User.id == user.id).first()
        assert fetched.oidc_sub == "sub-123"

    def test_user_oidc_sub_unique_constraint_blocks_duplicate(
        self, db: Session, test_organization: Organization
    ):
        """Two users with the same oidc_sub violate the unique constraint."""
        user1 = User(
            email="sso-user-1@example.com",
            password_hash=hash_password("password123"),
            organization_id=test_organization.id,
            role="member",
            auth_provider="oidc",
            oidc_sub="dup-sub",
        )
        db.add(user1)
        db.commit()

        user2 = User(
            email="sso-user-2@example.com",
            password_hash=hash_password("password123"),
            organization_id=test_organization.id,
            role="member",
            auth_provider="oidc",
            oidc_sub="dup-sub",
        )
        db.add(user2)

        with pytest.raises(IntegrityError):
            db.commit()
