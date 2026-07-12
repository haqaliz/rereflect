"""
Feedback-Zendesk status sync sidecar.

Remembers the last-observed Zendesk ticket status per feedback item. Written
by the status-sync poll/webhook path (poll-task, webhook-realtime aspects);
read by resolve_target_status/decide_update in src.services.zendesk_status_core
to gate seed/noop/changed transitions.
"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from .base import Base


class FeedbackZendeskSync(Base):
    """One row per feedback item that has an observed Zendesk ticket status."""
    __tablename__ = "feedback_zendesk_sync"

    feedback_id = Column(Integer, ForeignKey("feedback_items.id", ondelete="CASCADE"), primary_key=True)
    last_ticket_status = Column(String(20), nullable=False)
    last_status_synced_at = Column(DateTime, nullable=False)

    def __repr__(self):
        return f"<FeedbackZendeskSync(feedback_id={self.feedback_id}, last_ticket_status='{self.last_ticket_status}')>"
