"""drop_dead_billing_budget_columns

Revision ID: v1w2x3y4z5a6
Revises: u0v1w2x3y4z5
Create Date: 2026-06-14 00:00:00.000000

B4 (OSS Self-Hosted Pivot) — Drop the four dead billing/budget columns that
have zero live code references outside their model declarations:

  usage_records.overage_reported_to_stripe
  org_ai_config.monthly_budget_cents
  org_ai_config.budget_used_cents
  org_ai_config.budget_reset_at

SKIPPED (still referenced in live code — NOT dropped in this migration):
  organizations.stripe_customer_id       → admin_orgs.py reads org.stripe_customer_id
  organizations.max_seats                → admin_orgs.py reads org.max_seats
  subscriptions.stripe_subscription_id  → billing.py GET /subscription, POST /start-trial
  subscriptions.stripe_price_id         → billing.py
  subscriptions.billing_cycle           → billing.py
  subscriptions.trial_start             → billing.py POST /start-trial
  subscriptions.trial_end               → billing.py + subscription.py property
  subscriptions.current_period_start    → billing.py + dependencies.py
  subscriptions.current_period_end      → billing.py + dependencies.py
  subscriptions.cancel_at_period_end    → billing.py
  subscriptions.canceled_at             → billing.py
  usage_records.overage_feedback        → billing.py + feedback.py + dependencies.py
  llm_usage_logs.is_byok                → org_resolver.py log_usage() writes it

The downgrade() re-adds all four columns so the migration is fully reversible.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "v1w2x3y4z5a6"
down_revision = "u0v1w2x3y4z5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── usage_records ──────────────────────────────────────────────────────────
    op.drop_column("usage_records", "overage_reported_to_stripe")

    # ── org_ai_config ──────────────────────────────────────────────────────────
    op.drop_column("org_ai_config", "monthly_budget_cents")
    op.drop_column("org_ai_config", "budget_used_cents")
    op.drop_column("org_ai_config", "budget_reset_at")


def downgrade() -> None:
    # ── org_ai_config (reverse order) ─────────────────────────────────────────
    op.add_column(
        "org_ai_config",
        sa.Column("budget_reset_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "org_ai_config",
        sa.Column("budget_used_cents", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "org_ai_config",
        sa.Column("monthly_budget_cents", sa.Integer(), nullable=True),
    )

    # ── usage_records ──────────────────────────────────────────────────────────
    op.add_column(
        "usage_records",
        sa.Column("overage_reported_to_stripe", sa.Boolean(), nullable=True),
    )
