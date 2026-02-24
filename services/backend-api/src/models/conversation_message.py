from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey, Index, Numeric, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from .base import Base


class ConversationMessage(Base):
    __tablename__ = "conversation_messages"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    role = Column(String(20), nullable=False)  # "user" or "assistant"
    content = Column(Text, nullable=False)
    structured_data = Column(JSON, nullable=True)  # Tables, charts, links in response
    context_scope = Column(String(50), nullable=True)
    query_type = Column(String(20), nullable=True)  # "data", "analysis", "general"
    template_id = Column(Integer, ForeignKey("query_templates.id", ondelete="SET NULL"), nullable=True)
    sql_generated = Column(Text, nullable=True)
    llm_provider = Column(String(50), nullable=True)
    llm_model = Column(String(100), nullable=True)
    tokens_in = Column(Integer, nullable=True)
    tokens_out = Column(Integer, nullable=True)
    cost_cents = Column(Numeric(10, 4), nullable=True)
    latency_ms = Column(Integer, nullable=True)
    raw_request = Column(JSON, nullable=True)
    raw_response = Column(JSON, nullable=True)
    is_regenerated = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    conversation = relationship("Conversation", back_populates="messages")

    __table_args__ = (
        Index('ix_messages_conv_date', 'conversation_id', 'created_at'),
    )

    def __repr__(self):
        return f"<ConversationMessage(id={self.id}, conv={self.conversation_id}, role='{self.role}')>"
