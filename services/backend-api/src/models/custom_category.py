from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, Index
from datetime import datetime
from .base import Base


class CustomCategory(Base):
    __tablename__ = "custom_categories"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    category_type = Column(String(50), nullable=False)  # pain_point, feature_request, general
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index('ix_custom_cat_org', 'organization_id', 'category_type'),
    )

    def __repr__(self):
        return f"<CustomCategory(id={self.id}, name='{self.name}', type='{self.category_type}')>"
