"""drop_stripe_byok_columns_oss_pivot

Revision ID: w2x3y4z5a6b7
Revises: v1w2x3y4z5a6
Create Date: 2026-06-14 00:00:00.000000

B4 (OSS Self-Hosted Pivot) — Drop all remaining dead Stripe/billing/BYOK
columns that have zero live code references outside model declarations.

Columns dropped:
  organizations:   stripe_customer_id, max_seats
  subscriptions:   stripe_subscription_id, stripe_price_id, billing_cycle,
                   trial_start, trial_end, current_period_start,
                   current_period_end, cancel_at_period_end, canceled_at
  usage_records:   overage_feedback
  llm_usage_logs:  is_byok

KEPT (load-bearing):
  organizations.plan, subscriptions.plan, subscriptions.status
  (and all other non-listed columns)

The downgrade() re-adds all columns so the migration is fully reversible.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "w2x3y4z5a6b7"
down_revision = "v1w2x3y4z5a6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── organizations ──────────────────────────────────────────────────────────
    op.drop_column("organizations", "stripe_customer_id")
    op.drop_column("organizations", "max_seats")

    # ── subscriptions ──────────────────────────────────────────────────────────
    # Drop index on stripe_subscription_id first (created with unique=True)
    op.drop_index("ix_subscriptions_stripe_subscription_id", table_name="subscriptions", if_exists=True)
    op.drop_column("subscriptions", "stripe_subscription_id")
    op.drop_column("subscriptions", "stripe_price_id")
    op.drop_column("subscriptions", "billing_cycle")
    op.drop_column("subscriptions", "trial_start")
    op.drop_column("subscriptions", "trial_end")
    op.drop_column("subscriptions", "current_period_start")
    op.drop_column("subscriptions", "current_period_end")
    op.drop_column("subscriptions", "cancel_at_period_end")
    op.drop_column("subscriptions", "canceled_at")

    # ── usage_records ──────────────────────────────────────────────────────────
    op.drop_column("usage_records", "overage_feedback")

    # ── llm_usage_logs ─────────────────────────────────────────────────────────
    op.drop_column("llm_usage_logs", "is_byok")


def downgrade() -> None:
    # ── llm_usage_logs (reverse order) ────────────────────────────────────────
    op.add_column(
        "llm_usage_logs",
        sa.Column("is_byok", sa.Boolean(), nullable=False, server_default="false"),
    )

    # ── usage_records ──────────────────────────────────────────────────────────
    op.add_column(
        "usage_records",
        sa.Column("overage_feedback", sa.Integer(), nullable=False, server_default="0"),
    )

    # ── subscriptions ──────────────────────────────────────────────────────────
    op.add_column(
        "subscriptions",
        sa.Column("canceled_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "subscriptions",
        sa.Column("cancel_at_period_end", sa.Boolean(), nullable=True, server_default="false"),
    )
    op.add_column(
        "subscriptions",
        sa.Column("current_period_end", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "subscriptions",
        sa.Column("current_period_start", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "subscriptions",
        sa.Column("trial_end", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "subscriptions",
        sa.Column("trial_start", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "subscriptions",
        sa.Column("billing_cycle", sa.String(20), nullable=True),
    )
    op.add_column(
        "subscriptions",
        sa.Column("stripe_price_id", sa.String(255), nullable=True),
    )
    op.add_column(
        "subscriptions",
        sa.Column("stripe_subscription_id", sa.String(255), nullable=True),
    )
    op.create_index(
        "ix_subscriptions_stripe_subscription_id",
        "subscriptions",
        ["stripe_subscription_id"],
        unique=True,
    )

    # ── organizations ──────────────────────────────────────────────────────────
    op.add_column(
        "organizations",
        sa.Column("max_seats", sa.Integer(), nullable=True),
    )
    op.add_column(
        "organizations",
        sa.Column("stripe_customer_id", sa.String(), nullable=True),
    )
