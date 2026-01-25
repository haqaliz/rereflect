"""
Seed script to create initial admin user.
Runs on application startup if admin user doesn't exist.
"""

import os
import logging
from sqlalchemy.orm import Session
from src.database.session import SessionLocal
from src.models.organization import Organization
from src.models.user import User
from src.api.auth import hash_password

logger = logging.getLogger(__name__)


def seed_admin_user():
    """Create admin user and organization if they don't exist."""
    admin_email = os.getenv("ADMIN_EMAIL", "haqaliz@aol.com")
    admin_password = os.getenv("ADMIN_PASSWORD", "QeOtLqfzR8Su$")

    db: Session = SessionLocal()
    try:
        # Check if admin user already exists
        existing_user = db.query(User).filter(User.email == admin_email).first()
        if existing_user:
            logger.info(f"Admin user {admin_email} already exists, skipping seed")
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

        # Create admin user
        admin_user = User(
            email=admin_email,
            password_hash=hash_password(admin_password),
            organization_id=org.id,
            role="admin"
        )
        db.add(admin_user)
        db.commit()
        logger.info(f"Created admin user: {admin_email}")

    except Exception as e:
        logger.error(f"Error seeding admin user: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    seed_admin_user()
