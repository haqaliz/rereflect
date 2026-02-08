"""
SavedView model for persisting analytics page state.
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, JSON, Index
from sqlalchemy.orm import relationship
from src.models.base import Base


class SavedView(Base):
    __tablename__ = "saved_views"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    name = Column(String(100), nullable=False)
    page = Column(String(50), nullable=False)  # e.g. "analytics"
    config = Column(JSON, nullable=False)  # Full serialized page state
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    position = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    organization = relationship("Organization")
    created_by = relationship("User", foreign_keys=[created_by_id])

    __table_args__ = (
        Index('ix_saved_views_org_page', 'organization_id', 'page'),
    )

    def __repr__(self):
        return f"<SavedView(id={self.id}, name='{self.name}', page='{self.page}')>"
