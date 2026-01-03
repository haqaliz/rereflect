"""
Database models for worker service.
Imports models from backend-api to ensure consistency.

Note: In production, these should be in a shared package.
For now, we duplicate the essential models.
"""

from sqlalchemy import Column, Integer, String, Text, Float, Boolean, DateTime, Index, JSON
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()


class FeedbackItem(Base):
    """Feedback item model - mirrors backend-api model."""
    __tablename__ = "feedback_items"

    id = Column(Integer, primary_key=True, index=True)
    # Note: No ForeignKey here - worker doesn't need the Organization model
    # The FK constraint exists in the actual database
    organization_id = Column(Integer, nullable=False)
    text = Column(Text, nullable=False)
    source = Column(String, nullable=True)  # intercom, zendesk, manual, etc
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

    __table_args__ = (
        Index('ix_feedback_org_date', 'organization_id', 'created_at'),
    )


class Integration(Base):
    """Integration model for 3rd party connections."""
    __tablename__ = "integrations"

    id = Column(Integer, primary_key=True, index=True)
    # Note: No ForeignKey here - worker doesn't need the Organization model
    # The FK constraint exists in the actual database
    organization_id = Column(Integer, nullable=False)
    type = Column(String, nullable=False)  # slack, intercom, zendesk
    config = Column(JSON, nullable=True)  # API keys, webhook URLs, etc.
    is_active = Column(Boolean, default=True)
    last_synced_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index('ix_integration_org_type', 'organization_id', 'type'),
    )
