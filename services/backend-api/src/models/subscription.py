from typing import Optional
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from .base import Base


class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), unique=True, nullable=False)

    # Plan info
    plan = Column(String(50), nullable=False, default="free")  # free, pro, business, enterprise

    # Status: active, canceled, incomplete
    status = Column(String(50), nullable=False, default="active")

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    organization = relationship("Organization", back_populates="subscription")

    def __repr__(self):
        return f"<Subscription(id={self.id}, org={self.organization_id}, plan='{self.plan}', status='{self.status}')>"

    @property
    def is_active(self) -> bool:
        return self.status in ("active",)
