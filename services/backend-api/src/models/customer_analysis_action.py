from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Index
from datetime import datetime
from .base import Base


class CustomerAnalysisAction(Base):
    """Action item from LLM analysis for a customer health record."""
    __tablename__ = "customer_analysis_actions"

    id = Column(Integer, primary_key=True, index=True)
    customer_health_id = Column(
        Integer,
        ForeignKey("customer_health_scores.id", ondelete="CASCADE"),
        nullable=False,
    )
    organization_id = Column(
        Integer,
        ForeignKey("organizations.id"),
        nullable=False,
    )
    action_text = Column(Text, nullable=False)
    status = Column(String(20), nullable=False, server_default="pending")  # pending, completed, dismissed
    completed_by = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, server_default="now()")

    __table_args__ = (
        Index('ix_analysis_action_health_status', 'customer_health_id', 'status'),
        Index('ix_analysis_action_org', 'organization_id'),
    )

    def __repr__(self):
        return f"<CustomerAnalysisAction(id={self.id}, status='{self.status}', text='{self.action_text[:40]}...')>"
