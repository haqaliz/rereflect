from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Index
from datetime import datetime
from .base import Base


class LLMUsageLog(Base):
    __tablename__ = "llm_usage_logs"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    provider = Column(String(20), nullable=False)  # openai, anthropic, google
    model = Column(String(50), nullable=False)
    task_type = Column(String(30), nullable=False)  # categorization, analysis, insights, churn_analysis
    prompt_tokens = Column(Integer, nullable=False)
    completion_tokens = Column(Integer, nullable=False)
    total_tokens = Column(Integer, nullable=False)
    estimated_cost_cents = Column(Float, nullable=False)
    latency_ms = Column(Integer, nullable=True)
    was_fallback = Column(Boolean, default=False, nullable=False)
    fallback_reason = Column(String(30), nullable=True)  # rate_limit, server_error, timeout
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index('idx_llm_usage_org_date', 'organization_id', 'created_at'),
    )

    def __repr__(self):
        return f"<LLMUsageLog(org={self.organization_id}, provider='{self.provider}', model='{self.model}')>"
