from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from datetime import datetime
from .base import Base


class OrgAIConfig(Base):
    __tablename__ = "org_ai_config"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), unique=True, nullable=False)
    default_provider = Column(String(20), default='openai', nullable=False)
    model_categorization = Column(String(50), default='gpt-4o-mini', nullable=False)
    model_analysis = Column(String(50), default='gpt-4o-mini', nullable=False)
    model_insights = Column(String(50), default='gpt-4o-mini', nullable=False)
    monthly_budget_cents = Column(Integer, nullable=True)  # NULL = use plan default
    budget_used_cents = Column(Integer, default=0, nullable=False)
    budget_reset_at = Column(DateTime, nullable=True)  # Next reset date (1st of month)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<OrgAIConfig(org={self.organization_id}, provider='{self.default_provider}')>"
