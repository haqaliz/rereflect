"""
Per-customer product-usage rollup for the product-usage-enrichment feature.

One row per ``(organization_id, customer_email)``.  Populated and refreshed by
the Celery task ``src.tasks.usage_metrics.process_usage_event`` (worker-service)
each time a raw usage event is processed.  The ``usage_score`` (0-100) is also
recomputed on a daily schedule so that recency decays even with no new events.

Alembic migration: add_customer_usage (revision follows add_usage_event).
"""

from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.types import JSON

from .base import Base


class CustomerUsage(Base):
    """Aggregated product-usage rollup per customer per organisation."""

    __tablename__ = "customer_usage"

    id = Column(Integer, primary_key=True, index=True)

    # Tenant scoping
    organization_id = Column(
        Integer,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Customer identity
    customer_email = Column(String(255), nullable=False, index=True)

    # Recency
    last_active_at = Column(DateTime, nullable=True)

    # Login / session counts inside rolling windows
    login_count_7d = Column(Integer, nullable=True, default=0)
    login_count_30d = Column(Integer, nullable=True, default=0)

    # Active-day counts (distinct calendar days with at least one event)
    active_days_7d = Column(Integer, nullable=True, default=0)
    active_days_30d = Column(Integer, nullable=True, default=0)

    # Feature breadth
    distinct_features = Column(JSON, nullable=True, default=list)  # list[str]
    distinct_feature_count = Column(Integer, nullable=True, default=0)

    # Computed health proxy (0-100; higher = more engaged)
    usage_score = Column(Integer, nullable=False, default=50)

    # Lifetime totals
    events_total = Column(Integer, nullable=False, default=0)

    # Timeline
    first_seen_at = Column(DateTime, nullable=True)
    created_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "customer_email",
            name="uq_customer_usage_org_email",
        ),
        Index(
            "ix_customer_usage_org_score",
            "organization_id",
            "usage_score",
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<CustomerUsage(id={self.id}, org={self.organization_id}, "
            f"email='{self.customer_email}', score={self.usage_score})>"
        )
