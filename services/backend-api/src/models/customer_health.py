from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Index
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

    # LLM analysis (weekly, for at-risk customers)
    llm_analysis = Column(Text, nullable=True)
    llm_analyzed_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index('ix_customer_health_org_email', 'organization_id', 'customer_email', unique=True),
        Index('ix_customer_health_org_score', 'organization_id', 'health_score'),
        Index('ix_customer_health_risk', 'organization_id', 'risk_level'),
    )

    def __repr__(self):
        return f"<CustomerHealth(org={self.organization_id}, email='{self.customer_email}', score={self.health_score})>"
