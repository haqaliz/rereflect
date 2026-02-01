from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey, Index, JSON
from datetime import datetime
from .base import Base


class FeedbackSource(Base):
    """Configuration for receiving feedback from external sources (Slack, Discord, Webhook, etc.)."""
    __tablename__ = "feedback_sources"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)

    # Link to existing integration for OAuth-based sources (Slack, Discord)
    integration_id = Column(Integer, ForeignKey("integrations.id", ondelete="CASCADE"), nullable=True)

    # Source type: slack, discord, teams, email, webhook, api
    source_type = Column(String(50), nullable=False)
    name = Column(String(255), nullable=True)  # User-defined name

    # Provider-specific config
    # Slack: {"channel_id": "C123", "channel_name": "#feedback", "team_id": "T123"}
    # Webhook: {"webhook_id": "uuid", "secret_token": "xyz", "json_path": "$.message"}
    # Discord: {"guild_id": "123", "channel_id": "456"}
    provider_config = Column(JSON, default=dict)

    # Generic trigger config - maps to provider-specific events
    # {
    #   "all_messages": false,
    #   "reactions": ["memo", "feedback"],          # Emoji/reactions
    #   "mentions": {"bot": true, "users": []},     # @mentions
    #   "keywords": ["bug", "feature"],             # Text matching
    #   "labels": ["feedback", "important"],        # Discord/GitHub labels
    #   "custom_rules": []                          # Provider-specific rules
    # }
    triggers = Column(JSON, default=dict)

    # Field mapping - how to extract feedback text from source
    # {
    #   "text_source": "message",                   # What becomes feedback text
    #   "include_author": true,
    #   "include_source_name": true,                # Channel/thread name
    #   "include_context": false,                   # Thread/conversation context
    #   "max_context_messages": 5,
    #   "custom_template": null                     # Optional Jinja2 template
    # }
    field_mapping = Column(JSON, default=dict)

    # Processing mode
    auto_import = Column(Boolean, default=True)  # Auto-create vs manual review

    # Status tracking
    is_active = Column(Boolean, default=True)
    last_event_at = Column(DateTime, nullable=True)
    events_processed = Column(Integer, default=0)
    error_count = Column(Integer, default=0)
    last_error = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Indexes
    __table_args__ = (
        Index('ix_feedback_source_org_type', 'organization_id', 'source_type'),
        Index('ix_feedback_source_active', 'is_active', 'source_type'),
        Index('ix_feedback_source_integration', 'integration_id'),
    )

    def __repr__(self):
        return f"<FeedbackSource(id={self.id}, org={self.organization_id}, type='{self.source_type}', name='{self.name}')>"
