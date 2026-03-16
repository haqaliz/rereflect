from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey, Index, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from .base import Base


class WebhookEndpoint(Base):
    """Custom webhook endpoint configuration for an organization."""
    __tablename__ = "webhook_endpoints"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(200), nullable=False)
    url = Column(String(2048), nullable=False)
    signing_secret = Column(String(500), nullable=False)  # Fernet-encrypted HMAC secret
    events = Column(JSON, default=list)  # Array of event IDs
    category_filters = Column(JSON, default=list)  # Array of tag strings for category_match
    custom_headers = Column(Text, nullable=True)  # Fernet-encrypted JSON of key-value pairs
    retry_mode = Column(String(50), nullable=False, default="fire_and_forget")  # fire_and_forget | exponential_backoff
    is_active = Column(Boolean, default=True, nullable=False)
    consecutive_failures = Column(Integer, default=0, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    deliveries = relationship("WebhookDelivery", back_populates="webhook", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_webhook_endpoints_org", "organization_id"),
        Index("ix_webhook_endpoints_org_active", "organization_id", "is_active"),
    )

    def __repr__(self):
        return f"<WebhookEndpoint(id={self.id}, org={self.organization_id}, name='{self.name}')>"
