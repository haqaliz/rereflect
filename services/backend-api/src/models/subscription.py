from typing import Optional
from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from .base import Base


class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), unique=True, nullable=False)

    # Stripe identifiers
    stripe_subscription_id = Column(String(255), unique=True, nullable=True, index=True)
    stripe_price_id = Column(String(255), nullable=True)

    # Plan info
    plan = Column(String(50), nullable=False, default="free")  # free, pro, business, enterprise
    billing_cycle = Column(String(20), nullable=True)  # monthly, annual

    # Status: active, trialing, past_due, canceled, incomplete
    status = Column(String(50), nullable=False, default="active")

    # Trial management
    trial_start = Column(DateTime, nullable=True)
    trial_end = Column(DateTime, nullable=True)

    # Billing period
    current_period_start = Column(DateTime, nullable=True)
    current_period_end = Column(DateTime, nullable=True)

    # Cancellation
    cancel_at_period_end = Column(Boolean, default=False)
    canceled_at = Column(DateTime, nullable=True)

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    organization = relationship("Organization", back_populates="subscription")

    def __repr__(self):
        return f"<Subscription(id={self.id}, org={self.organization_id}, plan='{self.plan}', status='{self.status}')>"

    @property
    def is_trial(self) -> bool:
        return self.status == "trialing"

    @property
    def is_active(self) -> bool:
        return self.status in ("active", "trialing")

    @property
    def trial_days_remaining(self) -> Optional[int]:
        if not self.is_trial or not self.trial_end:
            return None
        delta = self.trial_end - datetime.utcnow()
        return max(0, delta.days)
