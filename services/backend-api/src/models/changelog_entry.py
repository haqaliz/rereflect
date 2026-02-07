from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, Index
from datetime import datetime
from .base import Base


class ChangelogEntry(Base):
    __tablename__ = "changelog_entries"

    id = Column(Integer, primary_key=True, index=True)
    commit_hash = Column(String(40), unique=True, nullable=False, index=True)
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    entry_type = Column(String(50), nullable=False)  # feature, fix, improvement, breaking_change, chore
    is_breaking = Column(Boolean, default=False, nullable=False, server_default="false")
    is_hidden = Column(Boolean, default=False, nullable=False, server_default="false")
    committed_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, nullable=True, onupdate=datetime.utcnow)

    __table_args__ = (
        Index('ix_changelog_committed_at', 'committed_at'),
        Index('ix_changelog_type', 'entry_type'),
    )

    def __repr__(self):
        return f"<ChangelogEntry(id={self.id}, type='{self.entry_type}', title='{self.title[:50]}')>"
