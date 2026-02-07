"""
Seed script to create initial owner user.
Runs on application startup if owner user doesn't exist.
"""

import os
import logging
from datetime import datetime
from sqlalchemy.orm import Session
from src.database.session import SessionLocal
from src.models.organization import Organization
from src.models.user import User
from src.api.auth import hash_password

logger = logging.getLogger(__name__)


def seed_admin_user():
    """Create owner user and organization if they don't exist.

    IMPORTANT: This only seeds when there are NO users in the database.
    It will NOT modify existing users or promote anyone to owner.
    """
    admin_email = os.getenv("ADMIN_EMAIL", "support@rereflect.ca")
    admin_password = os.getenv("ADMIN_PASSWORD", "QeOtLqfzR8Su$")

    db: Session = SessionLocal()
    try:
        # Check if ANY users exist - if so, skip seeding entirely
        user_count = db.query(User).count()
        if user_count > 0:
            logger.info(f"Database already has {user_count} users, skipping seed")
            return

        # Create default organization
        org = db.query(Organization).filter(Organization.name == "Admin Organization").first()
        if not org:
            org = Organization(
                name="Admin Organization",
                plan="enterprise"
            )
            db.add(org)
            db.commit()
            db.refresh(org)
            logger.info(f"Created organization: {org.name} (id={org.id})")

        # Create owner user (first user in org is always owner)
        now = datetime.utcnow()
        owner_user = User(
            email=admin_email,
            password_hash=hash_password(admin_password),
            organization_id=org.id,
            role="owner",
            is_system_admin=True,
            joined_at=now,
            created_at=now,
        )
        db.add(owner_user)
        db.commit()
        logger.info(f"Created owner user: {admin_email}")

    except Exception as e:
        logger.error(f"Error seeding admin user: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    seed_admin_user()
