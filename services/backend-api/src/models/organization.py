from sqlalchemy import Column, Integer, String, DateTime
from datetime import datetime
from .base import Base


class Organization(Base):
    __tablename__ = "organizations"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    plan = Column(String, nullable=False, default="free")  # free, starter, professional, business, enterprise
    stripe_customer_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<Organization(id={self.id}, name='{self.name}', plan='{self.plan}')>"
