from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, UniqueConstraint
from datetime import datetime
from .base import Base


class LLMModelPrice(Base):
    __tablename__ = "llm_model_prices"

    id = Column(Integer, primary_key=True, index=True)
    provider = Column(String(20), nullable=False)  # openai, anthropic, google
    model_id = Column(String(50), nullable=False)  # gpt-4o-mini, claude-haiku-4-5, etc.
    display_name = Column(String(100), nullable=False)  # GPT-4o Mini, Claude Haiku 4.5
    input_price_per_1m_tokens = Column(Float, nullable=False)  # Price per 1M input tokens (dollars)
    output_price_per_1m_tokens = Column(Float, nullable=False)  # Price per 1M output tokens (dollars)
    context_window = Column(Integer, nullable=True)  # Max context tokens
    max_output_tokens = Column(Integer, nullable=True)  # Max output tokens
    supports_json_mode = Column(Boolean, default=False, nullable=False)
    tier = Column(String(10), nullable=False)  # cheap, mid, premium
    min_plan = Column(String(20), default='free', nullable=False)  # Minimum plan to use this model
    is_available = Column(Boolean, default=True, nullable=False)
    is_deprecated = Column(Boolean, default=False, nullable=False)
    replacement_model_id = Column(String(50), nullable=True)  # Auto-switch target when deprecated
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint('provider', 'model_id', name='uq_llm_model_price_provider_model'),
    )

    def __repr__(self):
        return f"<LLMModelPrice(provider='{self.provider}', model='{self.model_id}', tier='{self.tier}')>"
