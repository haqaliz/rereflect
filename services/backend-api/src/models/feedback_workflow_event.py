from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Index, JSON
from datetime import datetime
from .base import Base


class FeedbackWorkflowEvent(Base):
    """Timeline event for feedback workflow changes."""
    __tablename__ = "feedback_workflow_events"

    id = Column(Integer, primary_key=True, index=True)
    feedback_id = Column(Integer, ForeignKey("feedback_items.id", ondelete="CASCADE"), nullable=False)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    actor_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    event_type = Column(String(50), nullable=False)  # status_changed, assigned, unassigned, note_added, note_edited, note_deleted
    old_value = Column(String(255), nullable=True)
    new_value = Column(String(255), nullable=True)
    metadata_ = Column("metadata", JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_workflow_event_feedback", "feedback_id"),
        Index("ix_workflow_event_org", "organization_id"),
    )

    def __repr__(self):
        return f"<FeedbackWorkflowEvent(id={self.id}, feedback={self.feedback_id}, type='{self.event_type}')>"
