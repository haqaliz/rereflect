"""
PlaybookTask — SQLAlchemy model (playbook-action-types M3).

A durable follow-up task spawned by `create_task` / `schedule_task`
playbook actions. Internal and self-host native (offline); provider
dispatch (Jira/Asana/Linear) is v2.
"""

from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from .base import Base


class PlaybookTask(Base):
    """A follow-up task created by a playbook action for a customer."""

    __tablename__ = "playbook_tasks"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(
        Integer,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    customer_email = Column(String(255), nullable=False)

    description = Column(Text, nullable=False)

    # priority: low | medium | high
    priority = Column(String(10), nullable=False, default="medium")
    # status: open | done | cancelled
    status = Column(String(10), nullable=False, default="open")

    # Which playbook run spawned this task
    playbook_execution_id = Column(
        Integer,
        ForeignKey("churn_playbook_executions.id", ondelete="CASCADE"),
        nullable=True,
    )

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    due_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    # Relationships
    organization = relationship("Organization")
    playbook_execution = relationship("ChurnPlaybookExecution")

    __table_args__ = (
        Index("ix_playbook_tasks_org", "organization_id"),
        Index("ix_playbook_tasks_org_email", "organization_id", "customer_email"),
        Index("ix_playbook_tasks_org_status", "organization_id", "status"),
    )

    def __repr__(self) -> str:
        return (
            f"<PlaybookTask(id={self.id}, org={self.organization_id}, "
            f"email='{self.customer_email}', status='{self.status}')>"
        )