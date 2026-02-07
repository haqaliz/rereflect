from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey, Index, JSON, Time
from sqlalchemy.orm import relationship
from datetime import datetime, time
from .base import Base


class Integration(Base):
    """Third-party integration configuration (Slack, etc.)"""
    __tablename__ = "integrations"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    type = Column(String(50), nullable=False)  # 'slack', 'discord', 'teams'
    name = Column(String(255), nullable=True)  # User-defined name "Engineering Channel"

    # Connection details (stored as JSON for flexibility)
    config = Column(JSON, default=dict)  # {webhook_url, channel_id, channel_name}

    # OAuth tokens (encrypted at application level before storage)
    oauth_access_token = Column(Text, nullable=True)
    oauth_refresh_token = Column(Text, nullable=True)
    oauth_expires_at = Column(DateTime, nullable=True)

    # Alert configuration
    triggers = Column(JSON, default=lambda: ["urgent"])  # ["urgent", "negative", "all", "daily_digest", "weekly_digest"]
    included_fields = Column(JSON, default=lambda: ["text", "sentiment"])  # Fields to include in alerts (legacy)
    digest_time = Column(Time, default=time(9, 0))  # Time for daily/weekly digest (UTC)

    # Custom message template with variables like {{text}}, {{sentiment}}, etc.
    message_template = Column(Text, nullable=True)  # If null, use default template

    # Dedicated alert channel override (optional)
    alert_channel_id = Column(String(100), nullable=True)
    alert_channel_name = Column(String(255), nullable=True)

    # Status tracking
    is_active = Column(Boolean, default=True)
    last_used_at = Column(DateTime, nullable=True)
    error_count = Column(Integer, default=0)
    last_error = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Indexes
    __table_args__ = (
        Index('ix_integration_org_type', 'organization_id', 'type'),
        Index('ix_integration_active', 'is_active', 'type'),
    )

    def __repr__(self):
        return f"<Integration(id={self.id}, org={self.organization_id}, type='{self.type}', name='{self.name}')>"


class SlackAlertLog(Base):
    """Log of Slack alerts sent for tracking and debugging."""
    __tablename__ = "slack_alert_logs"

    id = Column(Integer, primary_key=True, index=True)
    integration_id = Column(Integer, ForeignKey("integrations.id"), nullable=False)
    feedback_id = Column(Integer, ForeignKey("feedback_items.id"), nullable=True)  # NULL for digests

    alert_type = Column(String(50), nullable=False)  # 'urgent', 'negative', 'batch', 'daily_digest', 'weekly_digest'
    status = Column(String(20), nullable=False)  # 'sent', 'failed', 'pending'

    # Response details
    slack_response = Column(JSON, nullable=True)  # Slack API response
    error_message = Column(Text, nullable=True)

    sent_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Indexes
    __table_args__ = (
        Index('ix_slack_alert_log_integration', 'integration_id', 'sent_at'),
    )

    def __repr__(self):
        return f"<SlackAlertLog(id={self.id}, integration={self.integration_id}, status='{self.status}')>"
