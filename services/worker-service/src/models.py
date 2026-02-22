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
    daily_digest_enabled = Column(Boolean, default=True, nullable=False)
    notification_retention_days = Column(Integer, default=30, nullable=False)
    daily_digest_hour = Column(Integer, default=8, nullable=False)
    weekly_digest_day = Column(Integer, default=1, nullable=False)
    weekly_digest_hour = Column(Integer, default=9, nullable=False)
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

    # Alert configuration
    default_alert_channels = Column(JSON, nullable=False, default={"dashboard": True, "email": False, "slack": False})

    # Workflow
    auto_assignment_enabled = Column(Boolean, default=False, nullable=False, server_default="false")


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
    customer_email = Column(String(255), nullable=True)

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
    churn_risk_factors = Column(JSON, nullable=True)  # 9-factor breakdown
    suggested_action = Column(Text, nullable=True)

    # LLM model tracking
    llm_provider = Column(String(20), nullable=True)
    llm_model = Column(String(50), nullable=True)

    # Workflow fields
    workflow_status = Column(String(50), nullable=False, default="new", server_default="new")
    assigned_to = Column(Integer, nullable=True)

    __table_args__ = (
        Index('ix_feedback_org_date', 'organization_id', 'created_at'),
        Index('ix_feedback_org_status', 'organization_id', 'workflow_status'),
        Index('ix_feedback_assigned', 'assigned_to'),
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

    # Alert channel override
    alert_channel_id = Column(String(100), nullable=True)
    alert_channel_name = Column(String(255), nullable=True)

    # Status tracking
    is_active = Column(Boolean, default=True)
    last_used_at = Column(DateTime, nullable=True)
    error_count = Column(Integer, default=0)
    last_error = Column(Text, nullable=True)
    last_synced_at = Column(DateTime, nullable=True)

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


class WeeklyInsight(Base):
    """AI-generated weekly insight summaries per organization."""
    __tablename__ = "weekly_insights"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, nullable=False)
    week_start = Column(DateTime, nullable=False)
    week_end = Column(DateTime, nullable=False)
    insights = Column(JSON, nullable=False)  # Array of {title, description, category, priority}
    generated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index('ix_weekly_insight_org_week', 'organization_id', 'week_start'),
    )


class Notification(Base):
    """In-app notification for users."""
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False)
    organization_id = Column(Integer, nullable=False)
    type = Column(String(50), nullable=False)
    title = Column(String(500), nullable=False)
    message = Column(Text, nullable=True)
    link = Column(String(500), nullable=True)
    is_read = Column(Boolean, default=False, nullable=False)
    is_dismissed = Column(Boolean, default=False, nullable=False)
    metadata_ = Column("metadata", JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_notification_user_read", "user_id", "is_read", "is_dismissed"),
        Index("ix_notification_expires", "expires_at"),
        Index("ix_notification_org", "organization_id"),
    )


class UserAlertPreference(Base):
    """Per-user alert preferences for each alert type."""
    __tablename__ = "user_alert_preferences"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False)
    alert_type = Column(String(50), nullable=False)
    is_enabled = Column(Boolean, default=True, nullable=False)
    channel_email = Column(Boolean, default=False, nullable=False)
    channel_slack = Column(Boolean, default=True, nullable=False)
    channel_inapp = Column(Boolean, default=True, nullable=False)
    threshold_value = Column(Float, nullable=True)
    retention_days = Column(Integer, default=30, nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "alert_type", name="uq_user_alert_type"),
    )


class AssignmentRule(Base):
    """Assignment rule model - mirrors backend-api model (lightweight, no FKs)."""
    __tablename__ = "assignment_rules"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, nullable=False)
    rule_type = Column(String(50), nullable=False, default="category")
    match_field = Column(String(100), nullable=False)
    match_value = Column(String(255), nullable=False)
    assign_to_user_id = Column(Integer, nullable=False)
    priority = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index('ix_assignment_rule_org', 'organization_id', 'is_active'),
    )


class CustomerHealth(Base):
    """Aggregate health score per customer (identified by email) within an organization."""
    __tablename__ = "customer_health_scores"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, nullable=False)
    customer_email = Column(String(255), nullable=False)
    customer_name = Column(String(255), nullable=True)

    health_score = Column(Integer, nullable=False, default=50)

    churn_risk_component = Column(Integer, default=50)
    sentiment_component = Column(Integer, default=50)
    resolution_component = Column(Integer, default=50)
    frequency_component = Column(Integer, default=50)

    feedback_count = Column(Integer, default=0)
    last_feedback_at = Column(DateTime, nullable=True)
    risk_level = Column(String(20), default="unknown")

    llm_analysis = Column(Text, nullable=True)  # Legacy pipe-separated text (transition period)
    llm_analyzed_at = Column(DateTime, nullable=True)

    # Structured LLM analysis (JSON)
    llm_analysis_data = Column(JSON, nullable=True)
    llm_raw_response = Column(JSON, nullable=True)

    # LLM model tracking
    llm_provider = Column(String(20), nullable=True)
    llm_model = Column(String(50), nullable=True)

    is_archived = Column(Boolean, default=False, server_default="false")
    confidence_level = Column(String(20), default="low")

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index('ix_customer_health_org_email', 'organization_id', 'customer_email', unique=True),
        Index('ix_customer_health_org_score', 'organization_id', 'health_score'),
        Index('ix_customer_health_risk', 'organization_id', 'risk_level'),
    )


class CustomerAnalysisAction(Base):
    """Action item from LLM analysis for a customer health record."""
    __tablename__ = "customer_analysis_actions"

    id = Column(Integer, primary_key=True, index=True)
    customer_health_id = Column(Integer, nullable=False)
    organization_id = Column(Integer, nullable=False)
    action_text = Column(Text, nullable=False)
    status = Column(String(20), nullable=False, server_default="pending")  # pending, completed, dismissed
    completed_by = Column(Integer, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index('ix_analysis_action_health_status', 'customer_health_id', 'status'),
        Index('ix_analysis_action_org', 'organization_id'),
    )


class FeedbackWorkflowEvent(Base):
    """Workflow timeline event model - mirrors backend-api model (lightweight, no FKs)."""
    __tablename__ = "feedback_workflow_events"

    id = Column(Integer, primary_key=True, index=True)
    feedback_id = Column(Integer, nullable=False)
    organization_id = Column(Integer, nullable=False)
    actor_id = Column(Integer, nullable=False)
    event_type = Column(String(50), nullable=False)
    old_value = Column(String, nullable=True)
    new_value = Column(String, nullable=True)
    metadata_ = Column("metadata", JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index('ix_workflow_event_feedback', 'feedback_id', 'created_at'),
    )


class OrgApiKey(Base):
    """Encrypted API keys per provider per org."""
    __tablename__ = "org_api_keys"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, nullable=False)
    provider = Column(String(20), nullable=False)  # openai, anthropic, google
    encrypted_key = Column(Text, nullable=False)
    key_hint = Column(String(8), nullable=True)
    is_valid = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint('organization_id', 'provider', name='uq_org_api_key_org_provider'),
        Index('idx_org_api_keys_org', 'organization_id'),
    )


class OrgAIConfig(Base):
    """Per-org AI configuration: provider, model per task, budget."""
    __tablename__ = "org_ai_config"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, unique=True, nullable=False)
    default_provider = Column(String(20), default='openai', nullable=False)
    model_categorization = Column(String(50), default='gpt-4o-mini', nullable=False)
    model_analysis = Column(String(50), default='gpt-4o-mini', nullable=False)
    model_insights = Column(String(50), default='gpt-4o-mini', nullable=False)
    monthly_budget_cents = Column(Integer, nullable=True)
    budget_used_cents = Column(Integer, default=0, nullable=False)
    budget_reset_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class LLMUsageLog(Base):
    """Per-request LLM usage tracking."""
    __tablename__ = "llm_usage_logs"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, nullable=False)
    provider = Column(String(20), nullable=False)
    model = Column(String(50), nullable=False)
    task_type = Column(String(30), nullable=False)
    prompt_tokens = Column(Integer, nullable=False)
    completion_tokens = Column(Integer, nullable=False)
    total_tokens = Column(Integer, nullable=False)
    estimated_cost_cents = Column(Float, nullable=False)
    latency_ms = Column(Integer, nullable=True)
    was_fallback = Column(Boolean, default=False, nullable=False)
    fallback_reason = Column(String(30), nullable=True)
    is_byok = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index('idx_llm_usage_org_date', 'organization_id', 'created_at'),
    )


class LLMModelPrice(Base):
    """System-wide model pricing table."""
    __tablename__ = "llm_model_prices"

    id = Column(Integer, primary_key=True, index=True)
    provider = Column(String(20), nullable=False)
    model_id = Column(String(50), nullable=False)
    display_name = Column(String(100), nullable=False)
    input_price_per_1m_tokens = Column(Float, nullable=False)
    output_price_per_1m_tokens = Column(Float, nullable=False)
    context_window = Column(Integer, nullable=True)
    max_output_tokens = Column(Integer, nullable=True)
    supports_json_mode = Column(Boolean, default=False, nullable=False)
    tier = Column(String(10), nullable=False)
    min_plan = Column(String(20), default='free', nullable=False)
    is_available = Column(Boolean, default=True, nullable=False)
    is_deprecated = Column(Boolean, default=False, nullable=False)
    replacement_model_id = Column(String(50), nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint('provider', 'model_id', name='uq_llm_model_price_provider_model'),
    )
