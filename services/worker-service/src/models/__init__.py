"""
Database models for worker service.
Imports models from backend-api to ensure consistency.

Note: In production, these should be in a shared package.
For now, we duplicate the essential models.
"""

from sqlalchemy import Column, Integer, String, Text, Float, Boolean, DateTime, Date, Time, Index, JSON, Numeric, UniqueConstraint, ForeignKey, text
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
    plan = Column(String(50), nullable=False, default="free")
    status = Column(String(50), nullable=False, default="active")
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
    usage_component = Column(Integer, nullable=True)    # catch-up: added by z5a6b7c8d9e0
    crm_component   = Column(Float,   nullable=True)    # crm-health-component aspect
    confidence_score = Column(Integer, default=0)       # catch-up: added by previous migration

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

    # segment-engine: catch-up mirror of backend-api's segment column (see
    # services/backend-api/src/models/customer_health.py). Rule-based
    # classification slug: at_risk, silent_churner, dormant, power_user,
    # happy_advocate, new, unsegmented. See src/services/segment_service.py.
    segment = Column(String(30), nullable=True)

    # M4.1: Advanced Churn Prediction — calibrated probability + CI + timeline
    churn_probability = Column(Numeric(5, 4), nullable=True)           # 0.0000–1.0000
    churn_probability_low = Column(Numeric(5, 4), nullable=True)       # 90% CI lower bound
    churn_probability_high = Column(Numeric(5, 4), nullable=True)      # 90% CI upper bound
    time_to_churn_bucket = Column(String(20), nullable=True)           # immediate | 2w | 2-4w | 1-3m | low
    calibration_model_id = Column(Integer, nullable=True)              # FK to churn_calibration_models (no FK constraint — worker is read-only for that table)
    probability_computed_at = Column(DateTime, nullable=True)
    has_potential_winback = Column(Boolean, nullable=False, default=False, server_default="false")

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index('ix_customer_health_org_email', 'organization_id', 'customer_email', unique=True),
        Index('ix_customer_health_org_score', 'organization_id', 'health_score'),
        Index('ix_customer_health_risk', 'organization_id', 'risk_level'),
        Index('ix_customer_health_segment', 'organization_id', 'segment'),
    )


class CustomerHealthHistory(Base):
    """Snapshot of health score changes for a customer over time — mirrors backend-api model."""
    __tablename__ = "customer_health_history"

    id = Column(Integer, primary_key=True, index=True)
    customer_health_id = Column(Integer, nullable=False)  # FK in real DB; no FK constraint in worker
    organization_id = Column(Integer, nullable=False)

    # Score snapshot
    health_score = Column(Integer, nullable=False)
    churn_risk_component = Column(Integer, nullable=True)
    sentiment_component = Column(Integer, nullable=True)
    resolution_component = Column(Integer, nullable=True)
    frequency_component = Column(Integer, nullable=True)
    usage_component = Column(Integer, nullable=True)    # catch-up: added by z5a6b7c8d9e0
    crm_component   = Column(Float,   nullable=True)    # crm-health-component aspect
    risk_level = Column(String(20), nullable=True)

    recorded_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_health_history_customer_date", "customer_health_id", "recorded_at"),
        Index("ix_health_history_org_date", "organization_id", "recorded_at"),
    )


class ChurnCalibrationModel(Base):
    """Versioned isotonic calibration model — read-only mirror for worker queries."""
    __tablename__ = "churn_calibration_models"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, nullable=True)  # NULL = global fallback

    model_json = Column(JSON, nullable=False)
    label_count = Column(Integer, nullable=False)
    positive_count = Column(Integer, nullable=False)

    precision = Column(Numeric(5, 4), nullable=True)
    recall = Column(Numeric(5, 4), nullable=True)
    f1 = Column(Numeric(5, 4), nullable=True)
    auc = Column(Numeric(5, 4), nullable=True)

    threshold_bands = Column(JSON, nullable=False)

    fit_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    is_active = Column(Boolean, nullable=False, default=False)

    __table_args__ = (
        Index("ix_churn_cal_model_org_fit", "organization_id", "fit_at"),
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
    """Workflow timeline event model - mirrors backend-api model (lightweight, no FKs).

    actor_id is nullable (mirrors services/backend-api/src/models/feedback_workflow_event.py) —
    system-driven events (e.g. jira-status-sync, see src/tasks/jira_sync.py) have no acting
    user and write actor_id=None.
    """
    __tablename__ = "feedback_workflow_events"

    id = Column(Integer, primary_key=True, index=True)
    feedback_id = Column(Integer, nullable=False)
    organization_id = Column(Integer, nullable=False)
    actor_id = Column(Integer, nullable=True)
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
    """Per-org AI configuration: provider, model per task."""
    __tablename__ = "org_ai_config"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, unique=True, nullable=False)
    default_provider = Column(String(20), default='openai', nullable=False)
    model_categorization = Column(String(50), default='gpt-4o-mini', nullable=False)
    model_analysis = Column(String(50), default='gpt-4o-mini', nullable=False)
    model_insights = Column(String(50), default='gpt-4o-mini', nullable=False)
    # Local / custom OpenAI-compatible endpoint (null for cloud providers)
    base_url = Column(String(500), nullable=True)
    # Per-org embedding-model override; null = derive default from provider (mirrors backend-api)
    model_embeddings = Column(String(100), nullable=True)
    # Per-org sentiment engine opt-in (mirrors backend-api; this aspect: per-org-resolution)
    sentiment_provider = Column(String(20), nullable=True, default='vader')
    # Per-org self-improving corrections classifier mode (mirrors backend-api; M5.2).
    # 'off' | 'shadow' | 'auto'. NULL/unrecognized treated as 'off' by resolve_classifier.
    classifier_mode = Column(String(20), nullable=True, server_default='off', default='off')
    # Per-org self-improving CATEGORY-corrections classifier mode (mirrors
    # backend-api; M5.2 v2). 'off' | 'shadow' | 'auto'. Independent of
    # classifier_mode (sentiment).
    category_classifier_mode = Column(String(20), nullable=True, server_default='off', default='off')
    # Per-org self-improving URGENCY-corrections classifier mode (mirrors
    # backend-api; urgency-classifier-head). 'off' | 'shadow' | 'auto'.
    # Independent of classifier_mode (sentiment) and category_classifier_mode.
    urgency_classifier_mode = Column(String(20), nullable=True, server_default='off', default='off')
    # Per-org customer-health-score component weights (must sum to 100)
    health_weight_churn = Column(Integer, default=35, nullable=False)
    health_weight_sentiment = Column(Integer, default=25, nullable=False)
    health_weight_resolution = Column(Integer, default=25, nullable=False)
    health_weight_frequency = Column(Integer, default=15, nullable=False)
    # Opt-in usage component weight (mirrors backend-api; catch-up from z5a6b7c8d9e0)
    health_weight_usage = Column(Integer, default=0, nullable=False)
    # Opt-in CRM component weight (this aspect: crm-health-component)
    health_weight_crm   = Column(Integer, default=0, nullable=False)
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
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index('idx_llm_usage_org_date', 'organization_id', 'created_at'),
    )


class WebhookEndpoint(Base):
    """Webhook endpoint model — mirrors backend-api model (lightweight, no FKs)."""
    __tablename__ = "webhook_endpoints"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, nullable=False)
    name = Column(String(200), nullable=False)
    url = Column(String(2048), nullable=False)
    signing_secret = Column(String(500), nullable=False)  # Fernet-encrypted HMAC secret
    events = Column(JSON, default=list)
    category_filters = Column(JSON, default=list)
    custom_headers = Column(String, nullable=True)  # Fernet-encrypted JSON key-value pairs
    retry_mode = Column(String(50), nullable=False, default="fire_and_forget")
    is_active = Column(Boolean, default=True, nullable=False)
    consecutive_failures = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_wh_endpoint_org", "organization_id"),
        Index("ix_wh_endpoint_org_active", "organization_id", "is_active"),
    )


class WebhookDelivery(Base):
    """Webhook delivery log — mirrors backend-api model (lightweight, no FKs)."""
    __tablename__ = "webhook_deliveries"

    id = Column(Integer, primary_key=True, index=True)
    webhook_id = Column(Integer, nullable=False)
    event = Column(String(100), nullable=False)
    feedback_id = Column(Integer, nullable=True)
    status = Column(String(50), nullable=False)  # sent | failed | retrying
    attempt = Column(Integer, default=1, nullable=False)
    response_code = Column(Integer, nullable=True)
    response_body = Column(String, nullable=True)
    error_message = Column(String, nullable=True)
    latency_ms = Column(Integer, nullable=True)
    payload = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_wh_delivery_webhook_created", "webhook_id", "created_at"),
    )


class CustomerChurnEvent(Base):
    """Churn label — manual mark, CSV import, or auto-suggested event — mirrors backend-api model."""
    __tablename__ = "customer_churn_events"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, nullable=False)
    customer_email = Column(String(255), nullable=False)
    churned_at = Column(DateTime, nullable=False)
    reason_code = Column(String(40), nullable=False)
    reason_text = Column(Text, nullable=True)
    recovered_at = Column(DateTime, nullable=True)
    marked_by_user_id = Column(Integer, nullable=True)
    source = Column(String(20), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("organization_id", "customer_email", "churned_at", name="uq_churn_event_org_email_date"),
        Index("ix_churn_event_org_date", "organization_id", "churned_at"),
        Index("ix_churn_event_org_email", "organization_id", "customer_email"),
    )


class ChurnLabelSuggestion(Base):
    """CRM-sourced lost-renewal suggestion awaiting operator review — mirrors backend-api model."""
    __tablename__ = "churn_label_suggestions"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, nullable=False)
    customer_email = Column(String(255), nullable=False)
    provider = Column(String(50), nullable=False)
    external_opportunity_id = Column(String(64), nullable=False)
    suggested_churned_at = Column(DateTime, nullable=False)
    evidence = Column(JSON, nullable=True)
    status = Column(String(20), nullable=False, default="pending")
    reviewed_by_user_id = Column(Integer, nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    churn_event_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("organization_id", "provider", "external_opportunity_id", name="uq_churn_label_suggestion_org_provider_ext"),
        Index("ix_churn_label_suggestion_org_status", "organization_id", "status"),
        Index("ix_churn_label_suggestion_org_email", "organization_id", "customer_email"),
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


class ChurnBacktestRun(Base):
    """Weekly calibration observability record — mirrors backend-api model (M4.1)."""
    __tablename__ = "churn_backtest_runs"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, nullable=True)   # NULL = global
    calibration_model_id = Column(Integer, nullable=False)
    run_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    label_count = Column(Integer, nullable=False)
    precision = Column(Numeric(5, 4), nullable=True)
    recall = Column(Numeric(5, 4), nullable=True)
    f1 = Column(Numeric(5, 4), nullable=True)
    auc = Column(Numeric(5, 4), nullable=True)
    optimal_threshold = Column(Numeric(5, 4), nullable=True)
    duration_ms = Column(Integer, nullable=True)
    notes = Column(Text, nullable=True)

    __table_args__ = (
        Index("ix_churn_backtest_org_run", "organization_id", "run_at"),
    )


# R?: Keep in sync with services/backend-api/src/models/ai_correction.py
# No shared package enforces consistency — a test
# (test_worker_and_backend_ai_correction_columns_match) asserts column
# parity at CI time.
class AICorrection(Base):
    """Human-in-the-loop correction/rating signal for an AI output — worker mirror (M5.2)."""
    __tablename__ = "ai_corrections"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, nullable=False)
    user_id = Column(Integer, nullable=True)

    correction_type = Column(String(50), nullable=False)  # copilot_response | sentiment | category | churn_risk | response_suggestion
    entity_type = Column(String(50), nullable=False)  # conversation_message | feedback_item | …
    entity_id = Column(Integer, nullable=True)

    signal = Column(String(20), nullable=False)  # thumbs_up | thumbs_down | correction

    original_value = Column(Text, nullable=True)
    corrected_value = Column(Text, nullable=True)
    feedback_text = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_ai_corrections_org_type", "organization_id", "correction_type"),
        Index("ix_ai_corrections_entity", "entity_type", "entity_id"),
    )


# R?: Keep in sync with services/backend-api/src/models/org_classifier.py
# No shared package enforces consistency — a test
# (test_worker_and_backend_org_classifier_model_columns_match /
# test_worker_and_backend_org_classifier_eval_run_columns_match) asserts
# column parity at CI time.
#
# Unlike the read-only ChurnCalibrationModel mirror (above), the worker is
# the SOLE WRITER of org_classifier_models (trainer task, aspect C) — the
# insert-new-active + flip-old-inactive promotion transaction relies on the
# DB-level partial-unique guard, so this mirror KEEPS the index.
class OrgClassifierModel(Base):
    """Versioned per-org corrections classifier artifact — worker mirror (M5.2)."""
    __tablename__ = "org_classifier_models"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, nullable=True)  # NULL = global/base model
    classifier_type = Column(String(30), nullable=False)  # v1: 'sentiment'

    model_json = Column(JSON, nullable=False)  # tfidf vocab/idf + logreg coef/intercept + classes — NO pickle
    label_count = Column(Integer, nullable=False)

    precision = Column(Numeric(5, 4), nullable=True)
    recall = Column(Numeric(5, 4), nullable=True)
    macro_f1 = Column(Numeric(5, 4), nullable=True)
    accuracy = Column(Numeric(5, 4), nullable=True)

    fit_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    is_active = Column(Boolean, nullable=False, default=False)

    __table_args__ = (
        Index("ix_org_classifier_model_org_type_fit", "organization_id", "classifier_type", "fit_at"),
        Index(
            "uq_org_classifier_one_active",
            "organization_id",
            "classifier_type",
            unique=True,
            sqlite_where=text("is_active = 1"),
            postgresql_where=text("is_active = TRUE"),
        ),
    )


class OrgClassifierEvalRun(Base):
    """Shadow-mode A/B eval history — worker mirror (M5.2)."""
    __tablename__ = "org_classifier_eval_runs"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, nullable=True)  # NULL = global run
    classifier_model_id = Column(Integer, nullable=True)
    classifier_type = Column(String(30), nullable=False)

    incumbent_macro_f1 = Column(Numeric(5, 4), nullable=True)
    challenger_macro_f1 = Column(Numeric(5, 4), nullable=True)
    macro_f1_delta = Column(Numeric(5, 4), nullable=True)
    decision = Column(String(20), nullable=False)  # promoted | retained | skipped
    n = Column(Integer, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_org_classifier_eval_org_type_created", "organization_id", "classifier_type", "created_at"),
    )


class ChurnPlaybook(Base):
    """Reusable churn-prevention playbook — mirrors backend-api model (M4.1)."""
    __tablename__ = "churn_playbooks"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, nullable=True)  # NULL = system template
    name = Column(String(120), nullable=False)
    description = Column(Text, nullable=True)
    probability_min = Column(Numeric(3, 2), nullable=False)
    probability_max = Column(Numeric(3, 2), nullable=False)
    action_sequence = Column(JSON, nullable=False, default=list)
    is_template = Column(Boolean, nullable=False, default=False)
    is_active = Column(Boolean, nullable=False, default=True)
    source_template_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_churn_playbook_org_active", "organization_id", "is_active"),
    )


class ChurnPlaybookExecution(Base):
    """Audit log + status for a single playbook run — mirrors backend-api model (M4.1)."""
    __tablename__ = "churn_playbook_executions"

    id = Column(Integer, primary_key=True, index=True)
    playbook_id = Column(Integer, nullable=False)
    organization_id = Column(Integer, nullable=False)
    customer_email = Column(String(255), nullable=False)
    triggered_by = Column(String(40), nullable=False)
    triggered_by_user_id = Column(Integer, nullable=True)
    status = Column(String(20), nullable=False)  # queued | running | done | failed | cancelled
    action_log = Column(JSON, nullable=False, default=list)
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_playbook_exec_org_created", "organization_id", "created_at"),
        Index("ix_playbook_exec_playbook_created", "playbook_id", "created_at"),
        Index("ix_playbook_exec_email_created", "customer_email", "created_at"),
    )


class UsageEvent(Base):
    """Raw usage event log — lightweight mirror of backend-api model (no FKs)."""
    __tablename__ = "usage_events"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, nullable=False, index=True)
    customer_email = Column(String(255), nullable=True, index=True)
    event_type = Column(String(50), nullable=False)
    event_name = Column(String(255), nullable=True)
    external_event_id = Column(String(255), nullable=False, index=True)
    occurred_at = Column(DateTime, nullable=True)
    received_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    properties = Column(JSON, nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "external_event_id",
            name="uq_usage_event_org_ext",
        ),
        Index(
            "ix_usage_events_org_email_occurred",
            "organization_id",
            "customer_email",
            "occurred_at",
        ),
    )


class CustomerUsage(Base):
    """Per-customer product-usage rollup — lightweight mirror of backend-api model."""
    __tablename__ = "customer_usage"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, nullable=False, index=True)
    customer_email = Column(String(255), nullable=False, index=True)
    last_active_at = Column(DateTime, nullable=True)
    login_count_7d = Column(Integer, nullable=True, default=0)
    login_count_30d = Column(Integer, nullable=True, default=0)
    active_days_7d = Column(Integer, nullable=True, default=0)
    active_days_14d = Column(Integer, nullable=True, default=0)
    active_days_30d = Column(Integer, nullable=True, default=0)
    distinct_features = Column(JSON, nullable=True, default=list)
    distinct_feature_count = Column(Integer, nullable=True, default=0)
    usage_score = Column(Integer, nullable=False, default=50)
    # Usage trend (trend-detection-and-health aspect) — mirror of the
    # backend-api model column. See src.services.usage_score_service.
    usage_trend_state = Column(String(30), nullable=False, default="insufficient_history")
    usage_trend_pct = Column(Float, nullable=True)
    events_total = Column(Integer, nullable=False, default=0)
    first_seen_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "customer_email",
            name="uq_customer_usage_org_email",
        ),
        Index("ix_customer_usage_org_score", "organization_id", "usage_score"),
    )


class CustomerUsageHistory(Base):
    """Daily per-customer usage snapshot — lightweight mirror of backend-api
    model (no FKs). Column parity with the backend-api model is enforced by
    test_worker_and_backend_customer_usage_history_columns_match
    (worker-service/tests/test_usage_metrics.py)."""
    __tablename__ = "customer_usage_history"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, nullable=False, index=True)
    customer_email = Column(String(255), nullable=False, index=True)
    snapshot_date = Column(Date, nullable=False)
    active_days_7d = Column(Integer, nullable=True)
    active_days_14d = Column(Integer, nullable=True)
    active_days_30d = Column(Integer, nullable=True)
    login_count_30d = Column(Integer, nullable=True)
    distinct_feature_count = Column(Integer, nullable=True)
    usage_score = Column(Integer, nullable=True)
    last_active_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "customer_email",
            "snapshot_date",
            name="uq_customer_usage_history_org_email_date",
        ),
        Index(
            "ix_customer_usage_history_lookback",
            "organization_id",
            "customer_email",
            "snapshot_date",
        ),
    )


# R4: Keep in sync with services/backend-api/src/models/crm_enrichment.py
# No shared package enforces consistency — a test (test_worker_and_backend_crm_enrichment_columns_match)
# asserts column parity at CI time.
class CrmEnrichment(Base):
    """Per-customer HubSpot CRM enrichment snapshot — no-FK worker mirror."""
    __tablename__ = "crm_enrichment"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, nullable=False)
    customer_email = Column(String(255), nullable=False)

    # CRM source ("hubspot" or "salesforce"); server_default backfills
    # existing rows so pre-generalization HubSpot data reads back unaffected.
    provider = Column(String(50), nullable=False, server_default="hubspot")

    # Company info
    company_name = Column(String(255), nullable=True)
    lifecycle_stage = Column(String(100), nullable=True)
    arr = Column(Float, nullable=True)

    # Renewal proxy — highest-amount open deal with a closedate
    renewal_date = Column(DateTime, nullable=True)
    deal_name = Column(String(255), nullable=True)
    deal_stage = Column(String(100), nullable=True)
    deal_amount = Column(Float, nullable=True)

    # HubSpot object IDs
    hubspot_contact_id = Column(String(100), nullable=True)
    hubspot_company_id = Column(String(100), nullable=True)
    hubspot_deal_id = Column(String(100), nullable=True)

    # Salesforce object ID (model-migrations aspect): matched Contact target
    # for CRM writeback.
    salesforce_contact_id = Column(String(100), nullable=True)

    # CRM writeback (writeback-config-api aspect): idempotency memory so the
    # writeback task doesn't re-push a health score that hasn't changed.
    last_written_health_score = Column(Integer, nullable=True)
    last_health_written_at = Column(DateTime, nullable=True)

    last_synced_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "customer_email",
            name="uq_crm_enrichment_org_email",
        ),
        Index("ix_crm_enrichment_org", "organization_id"),
        Index("ix_crm_enrichment_org_email", "organization_id", "customer_email"),
    )


class HubSpotIntegration(Base):
    """HubSpot connection per org — no-FK mirror for worker read access."""
    __tablename__ = "hubspot_integrations"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, nullable=False)
    access_token = Column(Text, nullable=False)
    token_hint = Column(String(8), nullable=True)
    hub_id = Column(String(64), nullable=True)
    portal_name = Column(String(255), nullable=True)
    arr_property_name = Column(String(255), nullable=False,
                               server_default="annualrevenue")
    connected_by_user_id = Column(Integer, nullable=True)
    connected_at = Column(DateTime, nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    last_synced_at = Column(DateTime, nullable=True)
    last_sync_status = Column(String(50), nullable=True)
    last_error = Column(Text, nullable=True)
    contacts_synced = Column(Integer, nullable=False, default=0)
    contacts_matched = Column(Integer, nullable=False, default=0)

    # CRM writeback (writeback-config-api aspect): push health scores back to HubSpot
    writeback_enabled = Column(Boolean, nullable=False, default=False)
    writeback_field_name = Column(String(255), nullable=True)
    last_writeback_at = Column(DateTime, nullable=True)
    last_writeback_status = Column(String(50), nullable=True)
    last_writeback_error = Column(Text, nullable=True)
    contacts_written = Column(Integer, nullable=False, default=0)

    # CRM-sourced churn labels (crm-churn-labels aspect): default-deny opt-in
    churn_labels_enabled = Column(Boolean, nullable=False, default=False)
    churn_label_config = Column(JSON, nullable=True)

    # Historical churn-label backfill (historical-backfill aspect) — mirrors
    # src/models/hubspot_integration.py on the backend; no FK (worker no-FK
    # pattern). The backfill task reads/writes these fields directly.
    backfill_status = Column(String(20), nullable=True)
    backfill_progress = Column(JSON, nullable=True)
    backfill_last_run_at = Column(DateTime, nullable=True)
    backfill_error = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("organization_id",
                         name="uq_hubspot_integrations_org_id"),
        Index("ix_hubspot_integrations_org_id", "organization_id"),
    )


class SalesforceIntegration(Base):
    """Salesforce connection per org — no-FK mirror for worker read access."""
    __tablename__ = "salesforce_integrations"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, nullable=False)
    refresh_token = Column(Text, nullable=False)
    instance_url = Column(String(255), nullable=True)
    sf_org_id = Column(String(64), nullable=True)
    token_hint = Column(String(8), nullable=True)
    connected_by_user_id = Column(Integer, nullable=True)
    connected_at = Column(DateTime, nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    last_synced_at = Column(DateTime, nullable=True)
    last_sync_status = Column(String(50), nullable=True)
    last_error = Column(Text, nullable=True)
    contacts_synced = Column(Integer, nullable=False, default=0)
    contacts_matched = Column(Integer, nullable=False, default=0)

    # CRM writeback (writeback-config-api / push-task-trigger aspects): push
    # health scores back to Salesforce. Mirrors
    # src/models/salesforce_integration.py on the backend — column parity
    # required for the worker's push_health_to_salesforce task to read/write
    # these fields (see docstring on CrmEnrichment above re: no shared
    # package enforcing consistency).
    writeback_enabled = Column(Boolean, nullable=False, default=False)
    writeback_field_name = Column(String(255), nullable=True)
    last_writeback_at = Column(DateTime, nullable=True)
    last_writeback_status = Column(String(50), nullable=True)
    last_writeback_error = Column(Text, nullable=True)
    contacts_written = Column(Integer, nullable=False, default=0)

    # CRM-sourced churn labels (crm-churn-labels aspect): default-deny opt-in
    churn_labels_enabled = Column(Boolean, nullable=False, default=False)
    churn_label_config = Column(JSON, nullable=True)

    # Historical churn-label backfill (historical-backfill aspect) — mirrors
    # src/models/salesforce_integration.py on the backend; no FK (worker
    # no-FK pattern). The backfill task reads/writes these fields directly.
    backfill_status = Column(String(20), nullable=True)
    backfill_progress = Column(JSON, nullable=True)
    backfill_last_run_at = Column(DateTime, nullable=True)
    backfill_error = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("organization_id",
                         name="uq_salesforce_integrations_org_id"),
        Index("ix_salesforce_integrations_org_id", "organization_id"),
    )


class ZendeskIntegration(Base):
    """Zendesk connection per org — no-FK mirror for worker read access (ingestion-core aspect).

    Column set fixed by docs/planning/zendesk-integration/prd.md Data Model section; keep in
    sync with services/backend-api/src/models/zendesk_integration.py (backend-connection
    aspect) — parity enforced by
    test_zendesk_adapter.py::TestModelsAndMigration::test_worker_and_backend_zendesk_integration_columns_match.
    """
    __tablename__ = "zendesk_integrations"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, nullable=False)
    subdomain = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False)
    api_token = Column(Text, nullable=False)
    token_hint = Column(String(8), nullable=True)
    webhook_secret = Column(Text, nullable=True)
    account_user_id = Column(String(255), nullable=True)
    display_name = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    connected_by_user_id = Column(Integer, nullable=True)
    connected_at = Column(DateTime, nullable=False)
    last_synced_at = Column(DateTime, nullable=True)
    last_sync_status = Column(String(50), nullable=True)
    last_error = Column(Text, nullable=True)
    status_sync_enabled = Column(Boolean, nullable=False, default=False, server_default=text("false"))
    status_mapping = Column(JSON, nullable=True)
    last_status_synced_at = Column(DateTime, nullable=True)
    last_status_sync_error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint('organization_id', name='uq_zendesk_integrations_org_id'),
        Index('ix_zendesk_integrations_org_id', 'organization_id'),
    )


class FeedbackZendeskSync(Base):
    """Sidecar remembering the last-observed Zendesk ticket status per feedback item
    (reconcile-core-and-model aspect) — no-FK mirror for worker read/write access.

    Keep in sync with services/backend-api/src/models/feedback_zendesk_sync.py —
    parity enforced by
    test_zendesk_adapter.py::TestModelsAndMigration::test_worker_and_backend_feedback_zendesk_sync_columns_match.
    """
    __tablename__ = "feedback_zendesk_sync"

    feedback_id = Column(Integer, primary_key=True)
    last_ticket_status = Column(String(20), nullable=False)
    last_status_synced_at = Column(DateTime, nullable=False)


class JiraIntegration(Base):
    """Jira Cloud connection per org — no-FK mirror for worker read access
    (jira-status-sync/inbound-status-sync, Phase 4).

    MINIMAL mirror: only the columns src/tasks/jira_sync.py actually reads/writes.
    Keep in sync with services/backend-api/src/models/jira_integration.py.
    """
    __tablename__ = "jira_integrations"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, nullable=False)
    site_url = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False)
    api_token = Column(Text, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    status_sync_enabled = Column(Boolean, nullable=False, default=False, server_default=text("false"))
    status_mapping = Column(JSON, nullable=True)
    last_synced_at = Column(DateTime, nullable=True)
    last_sync_status = Column(String(50), nullable=True)
    last_error = Column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint('organization_id', name='uq_jira_integrations_org_id'),
        Index('ix_jira_integrations_org_id', 'organization_id'),
    )


class FeedbackJiraIssue(Base):
    """Links feedback items to Jira issues — no-FK mirror for worker read access
    (jira-status-sync/inbound-status-sync, Phase 4).

    MINIMAL mirror: only the columns src/tasks/jira_sync.py actually reads/writes.
    Keep in sync with services/backend-api/src/models/jira_integration.py.
    """
    __tablename__ = "feedback_jira_issues"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, nullable=False)
    feedback_id = Column(Integer, nullable=False)
    jira_issue_key = Column(String(50), nullable=False)
    jira_status = Column(String(100), nullable=True)
    jira_status_category = Column(String(20), nullable=True)
    last_status_synced_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index('ix_feedback_jira_issues_org_id', 'organization_id'),
        Index('ix_feedback_jira_issues_feedback_id', 'feedback_id'),
    )


class AsanaIntegration(Base):
    """Asana connection per org — no-FK mirror for worker read access
    (asana-status-sync, model-migrations aspect).

    MINIMAL mirror: only the columns the Asana sync task will read/write.
    Keep in sync with services/backend-api/src/models/asana_integration.py.
    Asana is Bearer PAT + fixed host app.asana.com — no site_url/email (contrast Jira).
    """
    __tablename__ = "asana_integrations"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, nullable=False)
    api_token = Column(Text, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    status_sync_enabled = Column(Boolean, nullable=False, default=False, server_default=text("false"))
    status_mapping = Column(JSON, nullable=True)
    last_synced_at = Column(DateTime, nullable=True)
    last_sync_status = Column(String(50), nullable=True)
    last_error = Column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint('organization_id', name='uq_asana_integrations_org_id'),
        Index('ix_asana_integrations_org_id', 'organization_id'),
    )


class FeedbackAsanaTask(Base):
    """Links feedback items to Asana tasks — no-FK mirror for worker read access
    (asana-status-sync, model-migrations aspect).

    MINIMAL mirror: only the columns the Asana sync task will read/write.
    Keep in sync with services/backend-api/src/models/asana_integration.py.
    """
    __tablename__ = "feedback_asana_tasks"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, nullable=False)
    feedback_id = Column(Integer, nullable=False)
    asana_task_gid = Column(String(255), nullable=False)
    asana_completed = Column(Boolean, nullable=True)
    asana_status_category = Column(String(20), nullable=True)
    last_status_synced_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index('ix_feedback_asana_tasks_org_id', 'organization_id'),
        Index('ix_feedback_asana_tasks_feedback_id', 'feedback_id'),
    )
