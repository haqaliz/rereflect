"""
Daily per-customer snapshot of the ``customer_usage`` rollup — storage only.

One immutable row per ``(organization_id, customer_email, snapshot_date)``,
written by the worker's daily ``recompute_usage_scores`` task (aspect
usage-history-snapshot) AFTER that task's per-row window re-derivation, so
each row reflects the re-derived (not frozen) values as of its
``snapshot_date``. This aspect computes no trend and changes no score — the
sole future reader is the ``trend-detection-and-health`` aspect, which will
compare a customer's current rollup against a row here from ~14 days back.

Alembic migration: add_customer_usage_history, on top of 241f650d7068
(add_active_days_14d_to_customer_usage).
"""

from datetime import datetime

from sqlalchemy import (
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)

from .base import Base


class CustomerUsageHistory(Base):
    """One immutable snapshot row per (organization, customer, calendar day)."""

    __tablename__ = "customer_usage_history"

    id = Column(Integer, primary_key=True, index=True)

    organization_id = Column(
        Integer,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    customer_email = Column(String(255), nullable=False, index=True)
    snapshot_date = Column(Date, nullable=False)  # UTC calendar date of the run

    # Snapshot payload — mirrors customer_usage as of snapshot_date, all nullable.
    active_days_7d = Column(Integer, nullable=True)
    active_days_14d = Column(Integer, nullable=True)
    active_days_30d = Column(Integer, nullable=True)
    login_count_30d = Column(Integer, nullable=True)
    distinct_feature_count = Column(Integer, nullable=True)
    usage_score = Column(Integer, nullable=True)
    last_active_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "customer_email",
            "snapshot_date",
            name="uq_customer_usage_history_org_email_date",
        ),
        # Serves the lookback query the next aspect will use:
        # WHERE organization_id = ? AND customer_email = ?
        #   AND snapshot_date BETWEEN ? AND ? ORDER BY snapshot_date DESC
        Index(
            "ix_customer_usage_history_lookback",
            "organization_id",
            "customer_email",
            "snapshot_date",
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<CustomerUsageHistory(org={self.organization_id}, "
            f"email='{self.customer_email}', date={self.snapshot_date})>"
        )
