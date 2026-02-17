"""
SharedLink model for public dashboard sharing via token-based links.
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, JSON, Boolean, Index
from sqlalchemy.orm import relationship
from src.models.base import Base
import secrets


class SharedLink(Base):
    __tablename__ = "shared_links"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    token = Column(String, unique=True, nullable=False, index=True)
    page = Column(String(50), nullable=False)  # e.g. "analytics"
    config = Column(JSON, nullable=True)  # Optional frozen page state
    password_hash = Column(String, nullable=True)  # bcrypt hash, nullable = no password
    expires_at = Column(DateTime, nullable=True)  # null = never expires
    created_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    view_count = Column(Integer, default=0, nullable=False)

    # Relationships
    organization = relationship("Organization")
    created_by = relationship("User", foreign_keys=[created_by_id])

    __table_args__ = (
        Index('ix_shared_links_org', 'organization_id'),
    )

    @classmethod
    def create(cls, organization_id: int, page: str, created_by_id: int,
               password_hash: str = None, expires_at: datetime = None,
               config: dict = None):
        """Factory method to create a new shared link with auto-generated token."""
        return cls(
            organization_id=organization_id,
            token=secrets.token_urlsafe(32),
            page=page,
            config=config,
            password_hash=password_hash,
            expires_at=expires_at,
            created_by_id=created_by_id,
            created_at=datetime.utcnow(),
            is_active=True,
            view_count=0,
        )

    def is_expired(self) -> bool:
        """Check if the link has expired."""
        if self.expires_at is None:
            return False
        return datetime.utcnow() > self.expires_at

    def is_valid(self) -> bool:
        """Check if the link is active and not expired."""
        return self.is_active and not self.is_expired()

    def __repr__(self):
        return f"<SharedLink(id={self.id}, page='{self.page}', active={self.is_active})>"
