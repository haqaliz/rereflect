import uuid as _uuid

from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship
from datetime import datetime
from .base import Base


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, index=True)
    public_id = Column(String(36), unique=True, nullable=False, default=lambda: str(_uuid.uuid4()), index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    created_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    title = Column(String(200), nullable=True)
    folder_id = Column(Integer, ForeignKey("conversation_folders.id", ondelete="SET NULL"), nullable=True)
    context_scope = Column(String(50), nullable=False, default="all_data")
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    messages = relationship("ConversationMessage", back_populates="conversation", cascade="all, delete-orphan")
    folder = relationship("ConversationFolder", backref="conversations", lazy="select")

    __table_args__ = (
        Index('ix_conversations_org_date', 'organization_id', 'created_at'),
        Index('ix_conversations_org_folder', 'organization_id', 'folder_id'),
    )

    def __repr__(self):
        return f"<Conversation(id={self.id}, org={self.organization_id}, title='{self.title}')>"
