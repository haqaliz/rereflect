"""
Daily per-customer snapshot of the ``customer_usage`` rollup — storage only.

One immutable row per ``(organization_id, customer_email, snapshot_date)``,
written by the worker's daily ``recompute_usage_scores`` task (aspect
usage-history-snapshot) AFTER that task's per-row window re-derivation, so
each row reflects the re-derived (not frozen) values as of its
``snapshot_date``. This aspect computes no score — the sole future reader is
the ``trend-detection-and-health`` aspect, which compares a customer's
current rollup against a row here from ~14 days back. Since
snapshot-trend-columns (usage-trend-automation-trigger, M3), each row also
carries the trend state/pct that were in effect for that customer on that
date, so a later ``usage_trend_change`` event has a durable backing row to
derive from.

Alembic migration: add_customer_usage_history, on top of 241f650d7068
(add_active_days_14d_to_customer_usage). Trend columns added by
add_trend_to_usage_history, on top of a5b63dbbce9b
(add_usage_trend_fields).
"""

from datetime import datetime

from sqlalchemy import (
    Column,
    Date,
    DateTime,
    Float,
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

    # Trend state/pct in effect for this customer on snapshot_date.
    # Nullable with NO server_default — deliberately unlike the
    # customer_usage columns (nullable=False, server_default=
    # "insufficient_history"). Pre-existing snapshot rows genuinely have no
    # known trend state, and timeline-trend-event relies on NULL meaning
    # "unknown, skip" rather than a real state.
    usage_trend_state = Column(String(30), nullable=True)
    usage_trend_pct = Column(Float, nullable=True)

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
