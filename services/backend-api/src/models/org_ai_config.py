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
    # Local / custom OpenAI-compatible endpoint (null for cloud providers)
    base_url = Column(String(500), nullable=True)
    # Per-org embedding-model override; null = derive default from provider (template-matching-local S1)
    model_embeddings = Column(String(100), nullable=True)
    # Per-org customer-health-score component weights (must sum to 100)
    health_weight_churn = Column(Integer, default=35, nullable=False)
    health_weight_sentiment = Column(Integer, default=25, nullable=False)
    health_weight_resolution = Column(Integer, default=25, nullable=False)
    health_weight_frequency = Column(Integer, default=15, nullable=False)
    # Opt-in usage component weight; defaults to 0 so existing scores are unchanged
    health_weight_usage = Column(Integer, default=0, nullable=False)
    # Opt-in CRM component weight; defaults to 0 so existing scores are unchanged
    health_weight_crm = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<OrgAIConfig(org={self.organization_id}, provider='{self.default_provider}')>"
