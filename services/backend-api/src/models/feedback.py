from sqlalchemy import Column, Integer, String, Text, Float, Boolean, DateTime, ForeignKey, Index, JSON
from datetime import datetime
from .base import Base


class FeedbackItem(Base):
    __tablename__ = "feedback_items"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    text = Column(Text, nullable=False)
    source = Column(String, nullable=True)  # intercom, zendesk, manual, slack, webhook, etc

    # Source tracking for inbound integrations
    source_id = Column(Integer, ForeignKey("feedback_sources.id", ondelete="SET NULL"), nullable=True)
    source_external_id = Column(String(255), nullable=True)  # Original message ID from provider
    source_metadata = Column(JSON, nullable=True)  # {author_id, author_name, channel_id, channel_name, url, etc.}
    sentiment_score = Column(Float, nullable=True)
    sentiment_label = Column(String, nullable=True)  # positive, neutral, negative
    extracted_issue = Column(Text, nullable=True)
    tags = Column(JSON, nullable=True)  # Array of extracted categories: ["bug", "performance", "mobile"]
    is_urgent = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Pain point categorization (12 categories)
    # Categories: security_breach, data_loss, payment_issue, system_crash, authentication,
    #             functionality_broken, performance, usability, compatibility, missing_feature,
    #             documentation, cosmetic
    pain_point_category = Column(String, nullable=True)
    pain_point_severity = Column(String, nullable=True)  # critical, major, moderate, minor, trivial
    pain_point_text = Column(Text, nullable=True)

    # Feature request categorization (10 categories)
    # Categories: core_functionality, automation, integration, reporting, customization,
    #             collaboration, export_import, mobile, notifications, ui_enhancement
    feature_request_category = Column(String, nullable=True)
    feature_request_priority = Column(String, nullable=True)  # high, medium, low
    feature_request_text = Column(Text, nullable=True)

    # Urgent categorization (10 categories - extends existing is_urgent)
    # Categories: service_outage, data_breach, payment_failure, data_corruption, account_locked,
    #             critical_bug, billing_dispute, churn_risk, compliance, reputation_risk
    urgent_category = Column(String, nullable=True)
    urgent_response_time = Column(String, nullable=True)  # immediate, 1_hour, 4_hours, 24_hours

    # Confidence score for categorization (0.0-1.0)
    categorization_confidence = Column(Float, nullable=True)

    # AI/LLM analysis fields
    llm_analyzed = Column(Boolean, default=False, nullable=False)
    llm_analysis_pending = Column(Boolean, default=False, nullable=False)
    churn_risk_score = Column(Integer, nullable=True)  # 0-100
    suggested_action = Column(Text, nullable=True)

    # Index for fast queries
    __table_args__ = (
        Index('ix_feedback_org_date', 'organization_id', 'created_at'),
    )

    def __repr__(self):
        return f"<FeedbackItem(id={self.id}, org={self.organization_id}, sentiment='{self.sentiment_label}')>"
