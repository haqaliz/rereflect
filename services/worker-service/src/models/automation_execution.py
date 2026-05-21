"""
AutomationExecution — lightweight SQLAlchemy mirror for worker-service.

The full model lives in backend-api. This mirror is used by
src/tasks/automation.py for the weekly purge task.
No ForeignKeys are declared here (same pattern as all other worker mirrors).
"""

from datetime import datetime

from sqlalchemy import Column, DateTime, Index, Integer, JSON, String

from src.models import Base


class AutomationExecution(Base):
    """Audit log entry for a single automation rule execution (worker-service mirror)."""

    __tablename__ = "automation_executions"

    id = Column(Integer, primary_key=True, index=True)
    rule_id = Column(Integer, nullable=False)
    organization_id = Column(Integer, nullable=False)
    feedback_id = Column(Integer, nullable=True)
    customer_email = Column(String(255), nullable=True)
    trigger_snapshot = Column(JSON, nullable=True)
    actions_executed = Column(JSON, nullable=True)
    status = Column(String(20), nullable=False)
    executed_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_automation_executions_rule_date", "rule_id", "executed_at"),
        Index("ix_automation_executions_org_date", "organization_id", "executed_at"),
    )
