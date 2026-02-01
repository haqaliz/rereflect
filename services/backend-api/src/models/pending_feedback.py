from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Index, JSON
from datetime import datetime
from .base import Base


class PendingFeedback(Base):
    """Pending items awaiting manual approval before becoming feedback."""
    __tablename__ = "pending_feedbacks"

    id = Column(Integer, primary_key=True, index=True)
    source_id = Column(Integer, ForeignKey("feedback_sources.id", ondelete="CASCADE"), nullable=False)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    event_id = Column(Integer, ForeignKey("feedback_source_events.id", ondelete="CASCADE"), nullable=False)

    # Extracted content
    text = Column(Text, nullable=False)

    # Source metadata (generic structure across all providers)
    # {
    #   "author_id": "U123",
    #   "author_name": "John Doe",
    #   "channel_id": "C456",
    #   "channel_name": "#feedback",
    #   "message_id": "123.456",
    #   "thread_id": "789",
    #   "url": "https://slack.com/..."
    # }
    source_metadata = Column(JSON, nullable=True)

    # Which trigger captured this (e.g., all_messages, reaction:memo, keyword:bug)
    trigger_type = Column(String(100), nullable=True)

    # Review status
    status = Column(String(20), default='pending', nullable=False)  # pending, approved, rejected
    reviewed_at = Column(DateTime, nullable=True)
    reviewed_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Indexes
    __table_args__ = (
        Index('ix_pending_feedback_org_status', 'organization_id', 'status'),
        Index('ix_pending_feedback_source', 'source_id', 'created_at'),
        Index('ix_pending_feedback_status_created', 'status', 'created_at'),
    )

    def __repr__(self):
        return f"<PendingFeedback(id={self.id}, source={self.source_id}, status='{self.status}')>"
