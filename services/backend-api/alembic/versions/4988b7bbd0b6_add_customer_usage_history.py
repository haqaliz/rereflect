"""add_customer_usage_history

Revision ID: 4988b7bbd0b6
Revises: 241f650d7068
Create Date: 2026-07-22 01:30:07.249184

Creates the ``customer_usage_history`` table for the usage-history-snapshot
aspect (usage-trend-churn-signal). Storage only — a daily, per-customer
snapshot of the customer_usage rollup, written by the worker's daily
recompute_usage_scores task so a later aspect can compare a customer's
current usage against a snapshot from ~14 days back.

Schema:
  - organization_id (FK -> organizations, CASCADE, indexed)
  - customer_email (indexed)
  - snapshot_date (Date, not null) — UTC calendar date of the run
  - active_days_7d/14d/30d, login_count_30d, distinct_feature_count,
    usage_score, last_active_at (all nullable — mirrors the rollup)
  - created_at (DateTime)
  - UniqueConstraint(organization_id, customer_email, snapshot_date)
  - Composite index (organization_id, customer_email, snapshot_date) for the
    lookback query the next aspect will use.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4988b7bbd0b6'
down_revision: Union[str, None] = '241f650d7068'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "customer_usage_history",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "organization_id",
            sa.Integer(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("customer_email", sa.String(255), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("active_days_7d", sa.Integer(), nullable=True),
        sa.Column("active_days_14d", sa.Integer(), nullable=True),
        sa.Column("active_days_30d", sa.Integer(), nullable=True),
        sa.Column("login_count_30d", sa.Integer(), nullable=True),
        sa.Column("distinct_feature_count", sa.Integer(), nullable=True),
        sa.Column("usage_score", sa.Integer(), nullable=True),
        sa.Column("last_active_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "customer_email",
            "snapshot_date",
            name="uq_customer_usage_history_org_email_date",
        ),
    )

    # Indexes
    op.create_index(
        "ix_customer_usage_history_id", "customer_usage_history", ["id"]
    )
    op.create_index(
        "ix_customer_usage_history_organization_id",
        "customer_usage_history",
        ["organization_id"],
    )
    op.create_index(
        "ix_customer_usage_history_customer_email",
        "customer_usage_history",
        ["customer_email"],
    )
    op.create_index(
        "ix_customer_usage_history_lookback",
        "customer_usage_history",
        ["organization_id", "customer_email", "snapshot_date"],
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_customer_usage_history_lookback")
    op.execute("DROP INDEX IF EXISTS ix_customer_usage_history_customer_email")
    op.execute("DROP INDEX IF EXISTS ix_customer_usage_history_organization_id")
    op.execute("DROP INDEX IF EXISTS ix_customer_usage_history_id")
    op.drop_table("customer_usage_history")
