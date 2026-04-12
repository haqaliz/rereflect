from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from .base import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=True)  # Nullable for Google-only users
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    role = Column(String, nullable=False, default="member")  # owner, admin, member
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Google OAuth fields
    google_id = Column(String(255), unique=True, nullable=True, index=True)
    auth_provider = Column(String(50), nullable=False, default="email")  # email, google, both

    # Notification preferences
    weekly_digest_enabled = Column(Boolean, default=True, nullable=False, server_default="true")
    alert_channels = Column(JSON, nullable=True)  # Per-user override: {"dashboard": true, "email": false, "slack": false}

    # System admin flag (for platform-wide admin access)
    is_system_admin = Column(Boolean, default=False, nullable=False, server_default="false")

    # Notification preferences (new — per-type prefs are in UserAlertPreference)
    notification_retention_days = Column(Integer, default=30, nullable=False, server_default="30")
    daily_digest_enabled = Column(Boolean, default=True, nullable=False, server_default="true")
    daily_digest_hour = Column(Integer, default=8, nullable=False, server_default="8")  # 0-23 UTC
    weekly_digest_day = Column(Integer, default=1, nullable=False, server_default="1")  # 0=Mon, 6=Sun
    weekly_digest_hour = Column(Integer, default=9, nullable=False, server_default="9")  # 0-23 UTC

    # GDPR compliance fields
    is_deactivated = Column(Boolean, default=False, nullable=False, server_default="false")
    deletion_requested_at = Column(DateTime, nullable=True)

    # Team management fields
    last_active_at = Column(DateTime, nullable=True)
    invited_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    joined_at = Column(DateTime, nullable=True)

    # Relationships
    organization = relationship("Organization", backref="users")
    invited_by = relationship("User", remote_side=[id], foreign_keys=[invited_by_id])

    def __repr__(self):
        return f"<User(id={self.id}, email='{self.email}', role='{self.role}')>"
