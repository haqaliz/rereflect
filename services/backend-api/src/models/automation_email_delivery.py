"""
AutomationEmailDelivery — SQLAlchemy model (automation-send-customer-email,
action-core aspect).

Audit row for one automation `send_customer_email` action. Status lifecycle:
`queued` -> `sent | skipped | failed` (terminal). The backend only ever writes
`queued` (happy path) or `skipped` (no-key path); the worker task
(`tasks.outreach.send_automation_email`, worker-mirrors aspect) owns the
terminal transition and never leaves a row `queued` on an exception.

Deliberately NO `automation_execution_id` column: the execution log is written
AFTER actions run on every evaluator, so the execution id is never knowable at
row-creation time. The deliveries read surface is scoped by `rule_id` instead.
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
    text,
)

from .base import Base


# Terminal statuses (worker task maps queued -> sent|skipped|failed).
DELIVERY_STATUSES = frozenset({"queued", "sent", "skipped", "failed"})


class AutomationEmailDelivery(Base):
    """Audit row for one automation send_customer_email action."""

    __tablename__ = "automation_email_deliveries"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(
        Integer,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    rule_id = Column(
        Integer,
        ForeignKey("automation_rules.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    customer_email = Column(String(255), nullable=False)
    to_email = Column(String(255), nullable=False)
    template_key = Column(String(50), nullable=False)
    subject = Column(String(200), nullable=False)
    body = Column(Text, nullable=False)
    status = Column(
        String(20),
        nullable=False,
        default="queued",
        server_default="queued",
    )
    reason = Column(Text, nullable=True)

    created_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    __table_args__ = (
        Index(
            "ix_automation_email_deliveries_org_created",
            "organization_id",
            "created_at",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<AutomationEmailDelivery(id={self.id}, rule_id={self.rule_id}, "
            f"status='{self.status}')>"
        )