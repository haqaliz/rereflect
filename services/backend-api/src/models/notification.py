from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey, Index, JSON
from datetime import datetime
from .base import Base


class Notification(Base):
    """In-app notification for users."""
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    type = Column(String(50), nullable=False)  # "urgent_feedback", "sentiment_spike", "churn_risk", "volume_spike"
    title = Column(String(500), nullable=False)
    message = Column(Text, nullable=True)
    link = Column(String(500), nullable=True)  # e.g., "/feedbacks/123"
    is_read = Column(Boolean, default=False, nullable=False)
    is_dismissed = Column(Boolean, default=False, nullable=False)
    metadata_ = Column("metadata", JSON, nullable=True)  # {feedback_id, anomaly_id, severity, etc.}
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=True)  # Set based on retention policy

    __table_args__ = (
        Index("ix_notification_user_read", "user_id", "is_read", "is_dismissed"),
        Index("ix_notification_expires", "expires_at"),
        Index("ix_notification_org", "organization_id"),
    )

    def __repr__(self):
        return f"<Notification(id={self.id}, user={self.user_id}, type='{self.type}', read={self.is_read})>"
