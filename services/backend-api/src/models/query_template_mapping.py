from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Index, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from .base import Base


class QueryTemplateMapping(Base):
    __tablename__ = "query_template_mappings"

    id = Column(Integer, primary_key=True, index=True)
    template_id = Column(Integer, ForeignKey("query_templates.id", ondelete="CASCADE"), nullable=False)
    question_pattern = Column(Text, nullable=False)
    # TODO: Replace with pgvector VECTOR when pgvector extension is available
    # For now using JSON fallback to store embedding arrays
    question_embedding = Column(JSON, nullable=True)
    # Provider/dimension tagging for cross-provider safety (added: template-matching-local)
    # Nullable so pre-existing rows without provider info are treated as stale
    embedding_provider = Column(String(50), nullable=True)
    embedding_dimension = Column(Integer, nullable=True)
    match_count = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    template = relationship("QueryTemplate", back_populates="mappings")

    __table_args__ = (
        Index('ix_mappings_template_id', 'template_id'),
        Index('ix_mappings_provider_dim', 'embedding_provider', 'embedding_dimension'),
    )

    def __repr__(self):
        return f"<QueryTemplateMapping(id={self.id}, template={self.template_id})>"
