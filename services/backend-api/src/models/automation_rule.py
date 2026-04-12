"""
AutomationRule — SQLAlchemy model (M4.4).

Stores IF/THEN automation rules scoped to an organization.
"""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from .base import Base


class AutomationRule(Base):
    """An IF/THEN automation rule for an organization."""

    __tablename__ = "automation_rules"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(
        Integer,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )

    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)

    is_active = Column(Boolean, default=True, nullable=False)

    # Trigger
    trigger_type = Column(String(50), nullable=False)  # health_score_threshold | sentiment_pattern | churn_risk_level_change | feedback_category_match
    trigger_config = Column(JSON, nullable=False, default=dict)

    # Actions — array of {type, config}
    actions = Column(JSON, nullable=False, default=list)

    cooldown_hours = Column(Integer, default=24, nullable=False)

    # Execution tracking
    execution_count = Column(Integer, default=0, nullable=False)
    last_executed_at = Column(DateTime, nullable=True)

    # Template metadata
    is_template = Column(Boolean, default=False, nullable=False)
    template_id = Column(String(50), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    # Relationships
    executions = relationship(
        "AutomationExecution",
        back_populates="rule",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_automation_rules_org_active", "organization_id", "is_active"),
        Index("ix_automation_rules_org_trigger", "organization_id", "trigger_type"),
    )

    def __repr__(self) -> str:
        return f"<AutomationRule(id={self.id}, name='{self.name}', org={self.organization_id})>"
