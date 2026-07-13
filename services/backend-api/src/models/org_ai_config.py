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
    # Per-org sentiment engine opt-in (local-analyzer-sentiment-model, per-org-resolution aspect).
    # 'vader' | 'transformer'; NULL/unrecognized treated as 'vader' by resolve_sentiment_provider.
    sentiment_provider = Column(String(20), nullable=True, default='vader')
    # Per-org self-improving corrections classifier mode (M5.2). 'off' | 'shadow' | 'auto'.
    # NULL/unrecognized treated as 'off' by resolve_classifier (defense in depth).
    classifier_mode = Column(String(20), nullable=True, server_default='off', default='off')
    # Per-org self-improving CATEGORY-corrections classifier mode (M5.2 v2).
    # 'off' | 'shadow' | 'auto'. Independent of `classifier_mode` (sentiment) —
    # enabling one never changes the other (PRD independent-control goal).
    # NULL/unrecognized treated as 'off' by resolve_classifier's per-type branch
    # (predict-seam aspect, not yet wired here).
    category_classifier_mode = Column(String(20), nullable=True, server_default='off', default='off')
    # 'off' | 'shadow' | 'auto'. Independent of classifier_mode (sentiment) and
    # category_classifier_mode — the urgency head (mirrors is_urgent boolean).
    urgency_classifier_mode = Column(String(20), nullable=True, server_default='off', default='off')
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
