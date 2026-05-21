"""
CustomerChurnEvent — SQLAlchemy model (M4.1).

Stores manual, CSV-imported, and auto-suggested churn labels.
Drives the calibration training set.
"""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from .base import Base


# ---------------------------------------------------------------------------
# Module-level enum constants — single source of truth shared with schemas
# ---------------------------------------------------------------------------

CHURN_REASON_CODES = [
    "price",
    "competitor",
    "product_quality",
    "no_longer_needed",
    "silent_churn",
    "other",
]

CHURN_EVENT_SOURCES = [
    "manual",
    "csv_import",
    "auto_suggested",
]


class CustomerChurnEvent(Base):
    """A churn label — manual mark, CSV import, or auto-suggested event."""

    __tablename__ = "customer_churn_events"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(
        Integer,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    customer_email = Column(String(255), nullable=False)
    churned_at = Column(DateTime, nullable=False)

    # reason_code: one of CHURN_REASON_CODES — validated in Pydantic, stored as string
    reason_code = Column(String(40), nullable=False)
    reason_text = Column(Text, nullable=True)
    recovered_at = Column(DateTime, nullable=True)

    # NULL for csv_import + auto_suggested
    marked_by_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # source: one of CHURN_EVENT_SOURCES
    source = Column(String(20), nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    # Relationships
    organization = relationship("Organization")
    marked_by = relationship("User", foreign_keys=[marked_by_user_id])

    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "customer_email",
            "churned_at",
            name="uq_churn_event_org_email_date",
        ),
        Index("ix_churn_event_org_date", "organization_id", "churned_at"),
        Index("ix_churn_event_org_email", "organization_id", "customer_email"),
    )

    def __repr__(self) -> str:
        return (
            f"<CustomerChurnEvent(id={self.id}, email='{self.customer_email}', "
            f"reason='{self.reason_code}')>"
        )
