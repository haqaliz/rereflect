from sqlalchemy import Column, Integer, DateTime, Boolean, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime
from .base import Base


class UsageRecord(Base):
    __tablename__ = "usage_records"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)

    # Billing period
    period_start = Column(DateTime, nullable=False)
    period_end = Column(DateTime, nullable=False)

    # Usage counters
    feedback_count = Column(Integer, default=0, nullable=False)
    api_calls_count = Column(Integer, default=0, nullable=False)

    # Overage tracking
    overage_feedback = Column(Integer, default=0, nullable=False)
    overage_reported_to_stripe = Column(Boolean, default=False)

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Ensure one record per org per period
    __table_args__ = (
        UniqueConstraint('organization_id', 'period_start', name='uix_org_period'),
    )

    # Relationships
    organization = relationship("Organization", back_populates="usage_records")

    def __repr__(self):
        return f"<UsageRecord(id={self.id}, org={self.organization_id}, feedback={self.feedback_count})>"

    @property
    def total_feedback(self) -> int:
        return self.feedback_count + self.overage_feedback
