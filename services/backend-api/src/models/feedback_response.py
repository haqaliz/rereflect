from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship
from datetime import datetime
from .base import Base


class FeedbackResponse(Base):
    __tablename__ = "feedback_responses"

    id = Column(Integer, primary_key=True, index=True)
    feedback_id = Column(Integer, ForeignKey("feedback_items.id", ondelete="CASCADE"), nullable=False)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    response_text = Column(Text, nullable=False)
    channel = Column(String(50), nullable=False)  # clipboard, slack, intercom, linear, email
    source = Column(String(50), nullable=False)   # template, ai_generated, manual
    template_id = Column(Integer, ForeignKey("response_templates.id", ondelete="SET NULL"), nullable=True)
    tone = Column(String(50), nullable=True)      # used for ai_generated
    status = Column(String(50), default="sent", nullable=False)  # sent, copied, send_failed
    error_message = Column(Text, nullable=True)   # populated on send_failed
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index('ix_feedback_responses_feedback', 'feedback_id'),
        Index('ix_feedback_responses_org', 'organization_id'),
        Index('ix_feedback_responses_user', 'user_id'),
    )

    def __repr__(self):
        return f"<FeedbackResponse(id={self.id}, feedback_id={self.feedback_id}, channel='{self.channel}')>"
