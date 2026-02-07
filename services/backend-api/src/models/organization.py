from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text
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
    openai_api_key = Column(Text, nullable=True)  # BYOK for Enterprise plans

    # Relationships
    subscription = relationship("Subscription", back_populates="organization", uselist=False)
    usage_records = relationship("UsageRecord", back_populates="organization")

    def __repr__(self):
        return f"<Organization(id={self.id}, name='{self.name}', plan='{self.plan}')>"
