from sqlalchemy import Column, Integer, Text, DateTime, ForeignKey, Index
from datetime import datetime
from .base import Base


class FeedbackNote(Base):
    """Internal team note on a feedback item."""
    __tablename__ = "feedback_notes"

    id = Column(Integer, primary_key=True, index=True)
    feedback_id = Column(Integer, ForeignKey("feedback_items.id", ondelete="CASCADE"), nullable=False)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    author_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, onupdate=datetime.utcnow, nullable=True)

    __table_args__ = (
        Index("ix_feedback_note_feedback", "feedback_id"),
        Index("ix_feedback_note_org", "organization_id"),
    )

    def __repr__(self):
        return f"<FeedbackNote(id={self.id}, feedback={self.feedback_id}, author={self.author_id})>"
