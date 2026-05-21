"""
ChurnPlaybook + ChurnPlaybookExecution — SQLAlchemy models (M4.1).

ChurnPlaybook: reusable prevention plans binding a probability range to
  a sequence of automation actions. System templates have organization_id=NULL.

ChurnPlaybookExecution: audit log + status for running playbooks.
"""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from .base import Base


# ---------------------------------------------------------------------------
# Module-level enum constants
# ---------------------------------------------------------------------------

PLAYBOOK_EXECUTION_STATUSES = [
    "queued",
    "running",
    "done",
    "failed",
    "cancelled",
]

PLAYBOOK_TRIGGER_SOURCES = [
    "manual",
    "auto_probability",
    "scheduled",
]


class ChurnPlaybook(Base):
    """A reusable churn-prevention playbook — template or org-specific."""

    __tablename__ = "churn_playbooks"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(
        Integer,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=True,  # NULL = system template
    )

    name = Column(String(120), nullable=False)
    description = Column(Text, nullable=True)

    probability_min = Column(Numeric(3, 2), nullable=False)  # 0.00–1.00
    probability_max = Column(Numeric(3, 2), nullable=False)

    # Reuses Automations action schema — list of {type, config, ...}
    action_sequence = Column(JSON, nullable=False, default=list)

    is_template = Column(Boolean, nullable=False, default=False)
    is_active = Column(Boolean, nullable=False, default=True)

    # Self-FK: which system template this was cloned from
    source_template_id = Column(
        Integer,
        ForeignKey("churn_playbooks.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    # Relationships
    organization = relationship("Organization")
    source_template = relationship(
        "ChurnPlaybook",
        remote_side=[id],
        foreign_keys=[source_template_id],
    )
    executions = relationship(
        "ChurnPlaybookExecution",
        back_populates="playbook",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        CheckConstraint(
            "probability_min < probability_max",
            name="ck_playbook_probability_range",
        ),
        Index("ix_churn_playbook_org_active", "organization_id", "is_active"),
    )

    def __repr__(self) -> str:
        return (
            f"<ChurnPlaybook(id={self.id}, name='{self.name}', "
            f"range=[{self.probability_min}–{self.probability_max}])>"
        )


class ChurnPlaybookExecution(Base):
    """Audit log + status record for a single playbook run."""

    __tablename__ = "churn_playbook_executions"

    id = Column(Integer, primary_key=True, index=True)
    playbook_id = Column(
        Integer,
        ForeignKey("churn_playbooks.id", ondelete="CASCADE"),
        nullable=False,
    )
    organization_id = Column(
        Integer,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )

    customer_email = Column(String(255), nullable=False)

    # triggered_by: manual | auto_probability | scheduled
    triggered_by = Column(String(40), nullable=False)
    triggered_by_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # status: one of PLAYBOOK_EXECUTION_STATUSES
    status = Column(String(20), nullable=False)

    # Per-action result list — default empty list
    action_log = Column(JSON, nullable=False, default=list)

    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    playbook = relationship("ChurnPlaybook", back_populates="executions")
    organization = relationship("Organization")
    triggered_by_user = relationship("User", foreign_keys=[triggered_by_user_id])

    __table_args__ = (
        Index("ix_playbook_exec_org_created", "organization_id", "created_at"),
        Index("ix_playbook_exec_playbook_created", "playbook_id", "created_at"),
        Index("ix_playbook_exec_email_created", "customer_email", "created_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<ChurnPlaybookExecution(id={self.id}, playbook={self.playbook_id}, "
            f"status='{self.status}', email='{self.customer_email}')>"
        )
