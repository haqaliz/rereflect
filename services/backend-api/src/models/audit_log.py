"""AuditLog model for tracking team management actions."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from .base import Base


class AuditLog(Base):
    """Audit log entry for team management actions.

    Tracks actions like user_invited, user_joined, user_removed,
    role_changed, ownership_transferred with full context including
    IP address and user agent for security auditing.
    """
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    user_email = Column(String, nullable=False)
    action = Column(String, nullable=False, index=True)  # user_invited, user_joined, user_removed, role_changed, ownership_transferred
    target_type = Column(String, nullable=True)  # user, invite, etc.
    target_id = Column(Integer, nullable=True)
    details = Column(JSON, nullable=True)
    ip_address = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    # Relationships
    organization = relationship("Organization")
    user = relationship("User")

    def __repr__(self):
        return f"<AuditLog(id={self.id}, action='{self.action}', user_id={self.user_id})>"
