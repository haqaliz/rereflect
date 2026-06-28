from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Index
from datetime import datetime
from .base import Base


class CustomerHealthHistory(Base):
    """Snapshot of health score changes for a customer over time."""
    __tablename__ = "customer_health_history"

    id = Column(Integer, primary_key=True, index=True)
    customer_health_id = Column(
        Integer,
        ForeignKey("customer_health_scores.id", ondelete="CASCADE"),
        nullable=False,
    )
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)

    # Score snapshot
    health_score = Column(Integer, nullable=False)
    churn_risk_component = Column(Integer, nullable=True)
    sentiment_component = Column(Integer, nullable=True)
    resolution_component = Column(Integer, nullable=True)
    frequency_component = Column(Integer, nullable=True)
    usage_component = Column(Integer, nullable=True)         # Opt-in; null for history rows before usage feature
    risk_level = Column(String(20), nullable=True)

    recorded_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_health_history_customer_date", "customer_health_id", "recorded_at"),
        Index("ix_health_history_org_date", "organization_id", "recorded_at"),
    )

    def __repr__(self):
        return (
            f"<CustomerHealthHistory(customer_health_id={self.customer_health_id}, "
            f"score={self.health_score}, recorded_at={self.recorded_at})>"
        )
