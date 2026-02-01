from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Index, JSON, UniqueConstraint
from datetime import datetime
from .base import Base


class FeedbackSourceEvent(Base):
    """Log of events received from feedback sources for deduplication and debugging."""
    __tablename__ = "feedback_source_events"

    id = Column(Integer, primary_key=True, index=True)
    source_id = Column(Integer, ForeignKey("feedback_sources.id", ondelete="CASCADE"), nullable=False)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)

    # Event identification (provider-specific but stored generically)
    external_event_id = Column(String(255), nullable=False)  # Slack event_id, Discord message_id, webhook request_id
    external_message_id = Column(String(255), nullable=True)  # For deduplication within same message (e.g., message_ts)
    event_type = Column(String(50), nullable=False)  # Generic: message, reaction, mention, webhook

    # Processing status
    status = Column(String(20), nullable=False, default='pending')  # pending, processed, ignored, failed
    trigger_matched = Column(String(100), nullable=True)  # Which trigger matched: all_messages, reaction:memo, keyword:bug

    # Result
    feedback_id = Column(Integer, ForeignKey("feedback_items.id", ondelete="SET NULL"), nullable=True)
    pending_feedback_id = Column(Integer, nullable=True)  # If in preview mode
    error_message = Column(Text, nullable=True)

    # Raw event data for debugging
    event_data = Column(JSON, nullable=True)

    received_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    processed_at = Column(DateTime, nullable=True)

    # Indexes and constraints
    __table_args__ = (
        Index('ix_fse_source_received', 'source_id', 'received_at'),
        Index('ix_fse_external_id', 'external_event_id'),
        Index('ix_fse_status', 'status', 'received_at'),
        Index('ix_fse_message', 'source_id', 'external_message_id'),
        UniqueConstraint('source_id', 'external_event_id', name='uq_source_event'),
    )

    def __repr__(self):
        return f"<FeedbackSourceEvent(id={self.id}, source={self.source_id}, event_type='{self.event_type}', status='{self.status}')>"
