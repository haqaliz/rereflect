from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey, Index, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from .base import Base


class CustomerHealth(Base):
    """Aggregate health score per customer (identified by email) within an organization."""
    __tablename__ = "customer_health_scores"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    customer_email = Column(String(255), nullable=False)
    customer_name = Column(String(255), nullable=True)

    # Health score (0-100, higher = healthier)
    health_score = Column(Integer, nullable=False, default=50)

    # Component scores (0-100 each, weighted into health_score)
    churn_risk_component = Column(Integer, default=50)       # 35% weight (inverted: low churn = high health)
    sentiment_component = Column(Integer, default=50)        # 25% weight
    resolution_component = Column(Integer, default=50)       # 25% weight
    frequency_component = Column(Integer, default=50)        # 15% weight

    # Metadata
    feedback_count = Column(Integer, default=0)
    last_feedback_at = Column(DateTime, nullable=True)
    risk_level = Column(String(20), default="unknown")  # healthy, moderate, at_risk, critical

    # Confidence level based on feedback count
    confidence_level = Column(String(20), default="low")  # low (<3), medium (3-9), high (10+)
    confidence_score = Column(Integer, default=0)  # 0-100 percentage (granular numeric confidence)

    # Soft archive when all feedback deleted
    is_archived = Column(Boolean, default=False, server_default="false")

    # LLM analysis (weekly, for at-risk customers)
    llm_analysis = Column(Text, nullable=True)  # Legacy pipe-separated text (transition period)
    llm_analyzed_at = Column(DateTime, nullable=True)

    # Structured LLM analysis (JSON)
    llm_analysis_data = Column(JSON, nullable=True)  # {analysis, recommended_actions, risk_drivers, estimated_urgency, analysis_type}
    llm_raw_response = Column(JSON, nullable=True)  # Raw OpenAI response for debugging

    # LLM model tracking (which provider/model analyzed this customer)
    llm_provider = Column(String(20), nullable=True)  # openai, anthropic, google
    llm_model = Column(String(50), nullable=True)  # gpt-4o-mini, claude-haiku-4-5, etc.

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # ORM relationships
    history = relationship(
        "CustomerHealthHistory",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    analysis_actions = relationship(
        "CustomerAnalysisAction",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        Index('ix_customer_health_org_email', 'organization_id', 'customer_email', unique=True),
        Index('ix_customer_health_org_score', 'organization_id', 'health_score'),
        Index('ix_customer_health_risk', 'organization_id', 'risk_level'),
    )

    def __repr__(self):
        return f"<CustomerHealth(org={self.organization_id}, email='{self.customer_email}', score={self.health_score})>"
