from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Index, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from .base import Base


class WebhookDelivery(Base):
    """Log record of a single webhook delivery attempt."""
    __tablename__ = "webhook_deliveries"

    id = Column(Integer, primary_key=True, index=True)
    webhook_id = Column(Integer, ForeignKey("webhook_endpoints.id", ondelete="CASCADE"), nullable=False)
    event = Column(String(100), nullable=False)  # Event ID that triggered delivery
    feedback_id = Column(Integer, ForeignKey("feedback_items.id", ondelete="SET NULL"), nullable=True)

    status = Column(String(50), nullable=False)  # sent | failed | retrying
    attempt = Column(Integer, default=1, nullable=False)  # 1-4 (1 = first, 4 = final retry)
    response_code = Column(Integer, nullable=True)  # HTTP status from receiver
    response_body = Column(Text, nullable=True)  # First 1KB of response body
    error_message = Column(Text, nullable=True)  # Network error or timeout message
    latency_ms = Column(Integer, nullable=True)  # Round-trip time in milliseconds
    payload = Column(JSON, nullable=True)  # Exact payload sent (for debugging)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    webhook = relationship("WebhookEndpoint", back_populates="deliveries")

    __table_args__ = (
        Index("ix_webhook_deliveries_webhook_created", "webhook_id", "created_at"),
    )

    def __repr__(self):
        return f"<WebhookDelivery(id={self.id}, webhook={self.webhook_id}, event='{self.event}', status='{self.status}')>"
