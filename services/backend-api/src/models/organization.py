from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from .base import Base


class Organization(Base):
    __tablename__ = "organizations"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    plan = Column(String, nullable=False, default="free")  # free, pro, business, enterprise
    stripe_customer_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Seat tracking
    seat_count = Column(Integer, default=1, nullable=False)
    max_seats = Column(Integer, nullable=True)  # NULL = unlimited (enterprise)

    # AI Analysis settings
    ai_analysis_enabled = Column(Boolean, default=True, nullable=False)

    # Alert configuration (org-wide defaults)
    default_alert_channels = Column(JSON, nullable=False, default={"dashboard": True, "email": False, "slack": False})

    # Workflow settings
    auto_assignment_enabled = Column(Boolean, default=False, nullable=False, server_default="false")

    # Promo tracking
    promo_code_used = Column(String(50), nullable=True)

    # Relationships
    subscription = relationship("Subscription", back_populates="organization", uselist=False)
    usage_records = relationship("UsageRecord", back_populates="organization")

    def __repr__(self):
        return f"<Organization(id={self.id}, name='{self.name}', plan='{self.plan}')>"
