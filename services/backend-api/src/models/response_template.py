from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship
from datetime import datetime
from .base import Base


class ResponseTemplate(Base):
    __tablename__ = "response_templates"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True)  # null = system template
    name = Column(String(200), nullable=False)
    category = Column(String(100), nullable=False)
    body = Column(Text, nullable=False)
    is_system = Column(Boolean, default=False, nullable=False)
    usage_count = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index('ix_response_templates_org', 'organization_id'),
        Index('ix_response_templates_category', 'organization_id', 'category'),
    )

    def __repr__(self):
        return f"<ResponseTemplate(id={self.id}, name='{self.name}', is_system={self.is_system})>"
