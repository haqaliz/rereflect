from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Index
from datetime import datetime
from .base import Base


class AICorrection(Base):
    """Human-in-the-loop correction/rating signal for an AI output."""
    __tablename__ = "ai_corrections"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(
        Integer,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # What kind of AI output is being rated
    correction_type = Column(
        String(50),
        nullable=False,
    )  # copilot_response | sentiment | category | churn_risk | response_suggestion

    # The entity that was rated
    entity_type = Column(String(50), nullable=False)  # conversation_message | feedback_item | …
    entity_id = Column(Integer, nullable=True)

    # The signal itself
    signal = Column(String(20), nullable=False)  # thumbs_up | thumbs_down | correction

    # Values
    original_value = Column(Text, nullable=True)    # what AI produced (can be full copilot response)
    corrected_value = Column(Text, nullable=True)   # what user says it should be
    feedback_text = Column(Text, nullable=True)           # free-text (thumbs_down only)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_ai_corrections_org_type", "organization_id", "correction_type"),
        Index("ix_ai_corrections_entity", "entity_type", "entity_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<AICorrection(id={self.id}, org={self.organization_id}, "
            f"type='{self.correction_type}', signal='{self.signal}')>"
        )
