"""
Database models for worker service.
Imports models from backend-api to ensure consistency.

Note: In production, these should be in a shared package.
For now, we duplicate the essential models.
"""

from sqlalchemy import Column, Integer, String, Text, Float, Boolean, DateTime, Time, Index, JSON, UniqueConstraint
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()


class User(Base):
    """User model - mirrors backend-api model (lightweight, no FKs)."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, nullable=False)
    organization_id = Column(Integer, nullable=False)
    role = Column(String, nullable=False, default="member")
    weekly_digest_enabled = Column(Boolean, default=True, nullable=False)
    alert_channels = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class Organization(Base):
    """Organization model - mirrors backend-api model (lightweight, no FKs)."""
    __tablename__ = "organizations"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    plan = Column(String, nullable=False, default="free")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # AI Analysis settings
    ai_analysis_enabled = Column(Boolean, default=True, nullable=False)
    openai_api_key = Column(Text, nullable=True)

    # Alert configuration
    default_alert_channels = Column(JSON, nullable=False, default={"dashboard": True, "email": False, "slack": False})


class Subscription(Base):
    """Subscription model - mirrors backend-api model (lightweight, no FKs)."""
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, nullable=False)
    stripe_subscription_id = Column(String(255), nullable=True, index=True)
    stripe_price_id = Column(String(255), nullable=True)
    plan = Column(String(50), nullable=False, default="free")
    billing_cycle = Column(String(20), nullable=True)
    status = Column(String(50), nullable=False, default="active")
    trial_start = Column(DateTime, nullable=True)
    trial_end = Column(DateTime, nullable=True)
    current_period_start = Column(DateTime, nullable=True)
    current_period_end = Column(DateTime, nullable=True)
    cancel_at_period_end = Column(Boolean, default=False)
    canceled_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class UsageRecord(Base):
    """Usage record model - mirrors backend-api model (lightweight, no FKs)."""
    __tablename__ = "usage_records"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, nullable=False, index=True)
    period_start = Column(DateTime, nullable=False)
    period_end = Column(DateTime, nullable=False)
    feedback_count = Column(Integer, default=0, nullable=False)
    api_calls_count = Column(Integer, default=0, nullable=False)
    overage_feedback = Column(Integer, default=0, nullable=False)
    overage_reported_to_stripe = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint('organization_id', 'period_start', name='uix_org_period'),
    )


class FeedbackItem(Base):
    """Feedback item model - mirrors backend-api model."""
    __tablename__ = "feedback_items"

    id = Column(Integer, primary_key=True, index=True)
    # Note: No ForeignKey here - worker doesn't need the Organization model
    # The FK constraint exists in the actual database
    organization_id = Column(Integer, nullable=False)
    text = Column(Text, nullable=False)
    source = Column(String, nullable=True)  # intercom, zendesk, manual, slack, webhook, etc

    # Source tracking for inbound integrations
    source_id = Column(Integer, nullable=True)  # FK to feedback_sources
    source_external_id = Column(String(255), nullable=True)  # Original message ID from provider
    source_metadata = Column(JSON, nullable=True)  # {author_id, author_name, channel_id, etc.}

    sentiment_score = Column(Float, nullable=True)
    sentiment_label = Column(String, nullable=True)  # positive, neutral, negative
    extracted_issue = Column(Text, nullable=True)
    tags = Column(JSON, nullable=True)  # Array of extracted categories
    is_urgent = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Pain point categorization
    pain_point_category = Column(String, nullable=True)
    pain_point_severity = Column(String, nullable=True)  # critical, major, moderate, minor, trivial
    pain_point_text = Column(Text, nullable=True)

    # Feature request categorization
    feature_request_category = Column(String, nullable=True)
    feature_request_priority = Column(String, nullable=True)  # high, medium, low
    feature_request_text = Column(Text, nullable=True)

    # Urgent categorization
    urgent_category = Column(String, nullable=True)
    urgent_response_time = Column(String, nullable=True)  # immediate, 1_hour, 4_hours, 24_hours

    # Confidence score for categorization (0.0-1.0)
    categorization_confidence = Column(Float, nullable=True)

    # AI/LLM analysis fields
    llm_analyzed = Column(Boolean, default=False, nullable=False)
    llm_analysis_pending = Column(Boolean, default=False, nullable=False)
    churn_risk_score = Column(Integer, nullable=True)  # 0-100
    suggested_action = Column(Text, nullable=True)

    __table_args__ = (
        Index('ix_feedback_org_date', 'organization_id', 'created_at'),
    )


class CustomCategory(Base):
    """Custom category model - mirrors backend-api model (lightweight, no FKs)."""
    __tablename__ = "custom_categories"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, nullable=False)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    category_type = Column(String(50), nullable=False)  # pain_point, feature_request, general
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index('ix_custom_cat_org', 'organization_id', 'category_type'),
    )


class Integration(Base):
    """Integration model for 3rd party connections (Slack, etc.)."""
    __tablename__ = "integrations"

    id = Column(Integer, primary_key=True, index=True)
    # Note: No ForeignKey here - worker doesn't need the Organization model
    # The FK constraint exists in the actual database
    organization_id = Column(Integer, nullable=False)
    type = Column(String(50), nullable=False)  # slack, intercom, zendesk
    name = Column(String(255), nullable=True)
    config = Column(JSON, nullable=True)  # {webhook_url, channel_id, channel_name}

    # OAuth tokens (for Slack OAuth integration)
    oauth_access_token = Column(Text, nullable=True)
    oauth_refresh_token = Column(Text, nullable=True)
    oauth_expires_at = Column(DateTime, nullable=True)

    # Alert configuration
    triggers = Column(JSON, nullable=True)  # ['urgent', 'negative', 'all', 'daily_digest', 'weekly_digest']
    included_fields = Column(JSON, nullable=True)  # ['text', 'sentiment', 'pain_point_category', etc.]
    digest_time = Column(Time, nullable=True)  # Time for daily/weekly digests
    message_template = Column(Text, nullable=True)  # Custom message template with {{variables}}

    # Status tracking
    is_active = Column(Boolean, default=True)
    last_used_at = Column(DateTime, nullable=True)
    error_count = Column(Integer, default=0)
    last_error = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index('ix_integration_org_type', 'organization_id', 'type'),
        Index('ix_integration_active', 'is_active', 'type'),
    )


class SlackAlertLog(Base):
    """Log of Slack alerts sent for tracking and debugging."""
    __tablename__ = "slack_alert_logs"

    id = Column(Integer, primary_key=True, index=True)
    integration_id = Column(Integer, nullable=False)
    feedback_id = Column(Integer, nullable=True)  # NULL for digests

    alert_type = Column(String(50), nullable=False)  # urgent, negative, digest, test
    status = Column(String(20), nullable=False)  # sent, failed, pending

    slack_response = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)

    sent_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index('ix_slack_alert_log_integration', 'integration_id', 'sent_at'),
    )


class FeedbackSource(Base):
    """Configuration for receiving feedback from external sources."""
    __tablename__ = "feedback_sources"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, nullable=False)
    integration_id = Column(Integer, nullable=True)  # FK to integrations

    source_type = Column(String(50), nullable=False)  # slack, discord, webhook, email
    name = Column(String(255), nullable=True)

    provider_config = Column(JSON, nullable=True)  # {channel_id, webhook_id, etc.}
    triggers = Column(JSON, nullable=True)  # {all_messages, reactions, mentions, keywords}
    field_mapping = Column(JSON, nullable=True)  # {text_source, include_author, etc.}

    auto_import = Column(Boolean, default=True)

    is_active = Column(Boolean, default=True)
    last_event_at = Column(DateTime, nullable=True)
    events_processed = Column(Integer, default=0)
    error_count = Column(Integer, default=0)
    last_error = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index('ix_feedback_source_org_type', 'organization_id', 'source_type'),
        Index('ix_feedback_source_active', 'is_active', 'source_type'),
    )


class FeedbackSourceEvent(Base):
    """Log of events received from feedback sources."""
    __tablename__ = "feedback_source_events"

    id = Column(Integer, primary_key=True, index=True)
    source_id = Column(Integer, nullable=False)  # FK to feedback_sources
    organization_id = Column(Integer, nullable=False)

    external_event_id = Column(String(255), nullable=False)
    external_message_id = Column(String(255), nullable=True)
    event_type = Column(String(50), nullable=False)  # message, reaction, mention, webhook

    status = Column(String(20), nullable=False, default='pending')  # pending, processed, ignored, failed
    trigger_matched = Column(String(100), nullable=True)

    feedback_id = Column(Integer, nullable=True)
    pending_feedback_id = Column(Integer, nullable=True)
    error_message = Column(Text, nullable=True)

    event_data = Column(JSON, nullable=True)

    received_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    processed_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index('ix_fse_source_received', 'source_id', 'received_at'),
        Index('ix_fse_status', 'status', 'received_at'),
    )


class PendingFeedback(Base):
    """Pending items awaiting manual approval."""
    __tablename__ = "pending_feedbacks"

    id = Column(Integer, primary_key=True, index=True)
    source_id = Column(Integer, nullable=False)  # FK to feedback_sources
    organization_id = Column(Integer, nullable=False)
    event_id = Column(Integer, nullable=False)  # FK to feedback_source_events

    text = Column(Text, nullable=False)
    source_metadata = Column(JSON, nullable=True)
    trigger_type = Column(String(100), nullable=True)

    status = Column(String(20), nullable=False, default='pending')  # pending, approved, rejected
    reviewed_at = Column(DateTime, nullable=True)
    reviewed_by = Column(Integer, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index('ix_pending_feedback_org_status', 'organization_id', 'status'),
        Index('ix_pending_feedback_source', 'source_id', 'created_at'),
    )


class SentimentAnomaly(Base):
    """Sentiment anomaly detection records."""
    __tablename__ = "sentiment_anomalies"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, nullable=False)
    detected_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    anomaly_type = Column(String(50), nullable=False)  # negative_spike
    severity = Column(String(20), nullable=False)  # warning, critical

    baseline_negative_pct = Column(Float, nullable=False)
    current_negative_pct = Column(Float, nullable=False)
    deviation_pct = Column(Float, nullable=False)

    time_window_hours = Column(Integer, nullable=False, default=24)
    feedback_count = Column(Integer, nullable=False, default=0)

    is_resolved = Column(Boolean, default=False, nullable=False)
    resolved_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index('ix_anomaly_org_resolved', 'organization_id', 'is_resolved'),
        Index('ix_anomaly_detected', 'detected_at'),
    )
