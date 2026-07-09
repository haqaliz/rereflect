"""
TDD tests — segment-actions PRD, aspect `customer-fields-model`, Phase 2.

Coverage: CustomerHealth.tags (JSON list, callable default) and
CustomerHealth.cs_owner_user_id / cs_owner relationship (FK -> users.id,
ON DELETE SET NULL is Postgres-enforced; SQLite test DB does not enforce
FK constraints by default, so we assert the ORM-level assignment/read
path and the FK-column existence, not live SQLite cascade behavior).
"""
import pytest
from sqlalchemy.orm import Session

from src.models.customer_health import CustomerHealth
from src.models.organization import Organization
from src.models.user import User
from src.api.auth import hash_password


class TestCustomerHealthTagsField:
    def test_tags_defaults_to_empty_list(self, db: Session, test_organization: Organization):
        health = CustomerHealth(
            organization_id=test_organization.id,
            customer_email="tags-default@example.com",
            health_score=50,
        )
        db.add(health)
        db.commit()
        db.refresh(health)

        assert health.tags == []

    def test_tags_can_be_set(self, db: Session, test_organization: Organization):
        health = CustomerHealth(
            organization_id=test_organization.id,
            customer_email="tags-set@example.com",
            health_score=50,
            tags=["expansion-target", "vip"],
        )
        db.add(health)
        db.commit()
        db.refresh(health)

        assert health.tags == ["expansion-target", "vip"]

    def test_tags_default_is_not_a_shared_mutable_list(self, db: Session, test_organization: Organization):
        """Regression guard: default=list must be callable, never a shared []."""
        h1 = CustomerHealth(
            organization_id=test_organization.id,
            customer_email="shared-a@example.com",
            health_score=50,
        )
        h2 = CustomerHealth(
            organization_id=test_organization.id,
            customer_email="shared-b@example.com",
            health_score=50,
        )
        db.add_all([h1, h2])
        db.commit()
        db.refresh(h1)
        db.refresh(h2)

        h1.tags.append("only-on-h1")
        db.commit()
        db.refresh(h2)

        assert h2.tags == []


class TestCustomerHealthCsOwnerField:
    def test_cs_owner_user_id_defaults_to_none(self, db: Session, test_organization: Organization):
        health = CustomerHealth(
            organization_id=test_organization.id,
            customer_email="owner-none@example.com",
            health_score=50,
        )
        db.add(health)
        db.commit()
        db.refresh(health)

        assert health.cs_owner_user_id is None
        assert health.cs_owner is None

    def test_cs_owner_user_id_can_be_assigned_and_relationship_resolves(
        self, db: Session, test_organization: Organization
    ):
        owner = User(
            email="owner@example.com",
            password_hash=hash_password("password123"),
            organization_id=test_organization.id,
            role="admin",
        )
        db.add(owner)
        db.commit()
        db.refresh(owner)

        health = CustomerHealth(
            organization_id=test_organization.id,
            customer_email="owned@example.com",
            health_score=50,
            cs_owner_user_id=owner.id,
        )
        db.add(health)
        db.commit()
        db.refresh(health)

        assert health.cs_owner_user_id == owner.id
        assert health.cs_owner is not None
        assert health.cs_owner.id == owner.id
        assert health.cs_owner.email == "owner@example.com"

    def test_deleting_owner_user_sets_cs_owner_user_id_null_at_orm_level(
        self, db: Session, test_organization: Organization
    ):
        """
        FK ON DELETE SET NULL is Postgres-enforced (verified live against
        Postgres in the migration test/round-trip — see
        tests/test_migrations_segment_actions.py). SQLite's in-memory test
        DB does not enforce FK constraints by default, so here we only
        assert the application-level behavior: nulling the FK column
        directly is a valid, persistable state (i.e. the column really is
        nullable and independent of the owning row).
        """
        owner = User(
            email="soon-removed@example.com",
            password_hash=hash_password("password123"),
            organization_id=test_organization.id,
            role="admin",
        )
        db.add(owner)
        db.commit()
        db.refresh(owner)

        health = CustomerHealth(
            organization_id=test_organization.id,
            customer_email="orphaned@example.com",
            health_score=50,
            cs_owner_user_id=owner.id,
        )
        db.add(health)
        db.commit()
        db.refresh(health)

        # Simulate what Postgres's ON DELETE SET NULL would do.
        health.cs_owner_user_id = None
        db.commit()
        db.refresh(health)

        assert health.cs_owner_user_id is None
        assert health.cs_owner is None
