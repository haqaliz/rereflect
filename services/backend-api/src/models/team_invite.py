"""
TeamInvite model for managing team invitations.
"""
from datetime import datetime, timedelta
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from src.models.base import Base
import secrets


class TeamInvite(Base):
    __tablename__ = "team_invites"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    email = Column(String, nullable=False, index=True)
    role = Column(String, nullable=False)  # 'admin' or 'member'
    token = Column(String, unique=True, nullable=False, index=True)
    invited_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    status = Column(String, nullable=False, default='pending')  # pending, accepted, expired, canceled
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    accepted_at = Column(DateTime, nullable=True)

    # Relationships
    organization = relationship("Organization")
    invited_by = relationship("User", foreign_keys=[invited_by_id])

    def __init__(self, **kwargs):
        # Set default expires_at to 7 days from now if not provided
        if 'expires_at' not in kwargs or kwargs.get('expires_at') is None:
            kwargs['expires_at'] = datetime.utcnow() + timedelta(days=7)
        if 'created_at' not in kwargs:
            kwargs['created_at'] = datetime.utcnow()
        super().__init__(**kwargs)

    @classmethod
    def create(cls, organization_id: int, email: str, role: str, invited_by_id: int):
        """Factory method to create a new invite with auto-generated token."""
        now = datetime.utcnow()
        return cls(
            organization_id=organization_id,
            email=email,
            role=role,
            token=secrets.token_urlsafe(32),
            invited_by_id=invited_by_id,
            status='pending',
            created_at=now,
            expires_at=now + timedelta(days=7)
        )

    def is_expired(self) -> bool:
        """Check if the invite has expired."""
        return datetime.utcnow() > self.expires_at

    def is_valid(self) -> bool:
        """Check if the invite is still valid (pending and not expired)."""
        return self.status == 'pending' and not self.is_expired()

    def __repr__(self):
        return f"<TeamInvite(id={self.id}, email='{self.email}', status='{self.status}')>"
