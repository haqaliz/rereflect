"""
ChurnLabelSuggestion — SQLAlchemy model (crm-churn-labels, data-model aspect).

CRM-sourced lost-renewal suggestions awaiting operator review. Pending
suggestions never enter customer_churn_events — confirming one writes a
real CustomerChurnEvent through the existing service path (routes aspect).

See docs/planning/crm-churn-labels/data-model/spec.md
"""

from datetime import datetime

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from .base import Base


# ---------------------------------------------------------------------------
# Module-level enum constant — single source of truth shared with schemas
# ---------------------------------------------------------------------------

CHURN_SUGGESTION_STATUSES = ["pending", "confirmed", "rejected"]


class ChurnLabelSuggestion(Base):
    """A CRM-sourced lost-renewal suggestion awaiting operator review."""

    __tablename__ = "churn_label_suggestions"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(
        Integer,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    customer_email = Column(String(255), nullable=False)
    provider = Column(String(50), nullable=False)
    external_opportunity_id = Column(String(64), nullable=False)
    suggested_churned_at = Column(DateTime, nullable=False)
    evidence = Column(JSON, nullable=True)

    # status: one of CHURN_SUGGESTION_STATUSES
    status = Column(
        String(20),
        nullable=False,
        default="pending",
        server_default="pending",
    )

    reviewed_by_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    reviewed_at = Column(DateTime, nullable=True)
    churn_event_id = Column(
        Integer,
        ForeignKey("customer_churn_events.id", ondelete="SET NULL"),
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
    reviewed_by = relationship("User", foreign_keys=[reviewed_by_user_id])

    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "provider",
            "external_opportunity_id",
            name="uq_churn_label_suggestion_org_provider_ext",
        ),
        Index(
            "ix_churn_label_suggestion_org_status",
            "organization_id",
            "status",
        ),
        Index(
            "ix_churn_label_suggestion_org_email",
            "organization_id",
            "customer_email",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<ChurnLabelSuggestion(id={self.id}, email='{self.customer_email}', "
            f"provider='{self.provider}', status='{self.status}')>"
        )
