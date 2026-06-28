"""
Raw usage-event log for the product-usage enrichment feature.

Each accepted event from POST /api/v1/webhooks/usage is persisted here
before being handed to the Celery worker for rollup and scoring.

Unique constraint ``uq_usage_event_org_ext`` on (organization_id, external_event_id)
provides the dedup guarantee for duplicate messageId submissions.
"""

from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON

from .base import Base


class UsageEvent(Base):
    """Raw usage event row scoped to an organization."""

    __tablename__ = "usage_events"

    id = Column(Integer, primary_key=True, index=True)

    # Tenant scoping — always derived from auth.organization_id, never the body
    organization_id = Column(
        Integer,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Resolved customer identity
    customer_email = Column(String(255), nullable=True, index=True)

    # Event metadata
    event_type = Column(String(50), nullable=False)    # "track" | "identify"
    event_name = Column(String(255), nullable=True)    # track: event/name field

    # Dedup key from Segment messageId
    external_event_id = Column(String(255), nullable=False, index=True)

    # Timing
    occurred_at = Column(DateTime, nullable=True)      # from event timestamp
    received_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Raw properties payload (size-guarded before insert)
    properties = Column(JSON, nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "external_event_id",
            name="uq_usage_event_org_ext",
        ),
        Index(
            "ix_usage_events_org_email_occurred",
            "organization_id",
            "customer_email",
            "occurred_at",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<UsageEvent(id={self.id}, org={self.organization_id}, "
            f"type='{self.event_type}', ext_id='{self.external_event_id}')>"
        )
