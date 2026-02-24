from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey, Index, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from .base import Base


class QueryTemplate(Base):
    __tablename__ = "query_templates"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True)  # NULL = global
    sql_query = Column(Text, nullable=False)
    description = Column(String(500), nullable=False)
    parameter_schema = Column(JSON, nullable=True)
    created_by = Column(String(20), nullable=False)  # "system", "llm", "admin"
    usage_count = Column(Integer, default=0, nullable=False)
    last_used_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    mappings = relationship("QueryTemplateMapping", back_populates="template", cascade="all, delete-orphan")

    __table_args__ = (
        Index('ix_templates_org_active_usage', 'organization_id', 'is_active', 'usage_count'),
    )

    def __repr__(self):
        return f"<QueryTemplate(id={self.id}, created_by='{self.created_by}', usage={self.usage_count})>"
