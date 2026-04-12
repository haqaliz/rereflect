"""
AutomationExecution — SQLAlchemy model (M4.4).

Audit log of every automation rule execution.
Retained for 90 days (Celery Beat weekly purge in Phase 2).
"""

from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
)
from sqlalchemy.orm import relationship

from .base import Base


class AutomationExecution(Base):
    """Audit log entry for a single automation rule execution."""

    __tablename__ = "automation_executions"

    id = Column(Integer, primary_key=True, index=True)
    rule_id = Column(
        Integer,
        ForeignKey("automation_rules.id", ondelete="CASCADE"),
        nullable=False,
    )
    organization_id = Column(
        Integer,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Context of what triggered this execution
    feedback_id = Column(Integer, ForeignKey("feedback_items.id", ondelete="SET NULL"), nullable=True)
    customer_email = Column(String(255), nullable=True)

    # Snapshots
    trigger_snapshot = Column(JSON, nullable=True)   # Condition values at trigger time
    actions_executed = Column(JSON, nullable=True)   # [{type, result, error}]

    status = Column(String(20), nullable=False)  # success | partial_failure | failed

    executed_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    rule = relationship("AutomationRule", back_populates="executions")

    __table_args__ = (
        Index("ix_automation_executions_rule_date", "rule_id", "executed_at"),
        Index("ix_automation_executions_org_date", "organization_id", "executed_at"),
    )

    def __repr__(self) -> str:
        return f"<AutomationExecution(id={self.id}, rule_id={self.rule_id}, status='{self.status}')>"
