"""add_usage_trend_fields

Revision ID: a5b63dbbce9b
Revises: 4988b7bbd0b6
Create Date: 2026-07-22 03:10:00.000000

Adds the two trend columns for the trend-detection-and-health aspect
(usage-trend-churn-signal):

  - usage_trend_state (String(30), NOT NULL, server_default
    'insufficient_history') — see src.services.usage_score_service
    .classify_usage_trend for the state slugs.
  - usage_trend_pct (Float, nullable) — signed percent change vs. baseline;
    NULL whenever state is 'insufficient_history'.

Additive, nullable/defaulted — no backfill, no downtime concern. Existing
rows read as 'insufficient_history' / NULL until the first daily
recompute_usage_scores pass resolves a real baseline (usage-history-snapshot
aspect's customer_usage_history rows must be at least 12 days old, so the
trend signal is inert for a full lookback cycle after this lands).

Does NOT re-add active_days_14d (rollup-rewindow-fix, revision 241f650d7068).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a5b63dbbce9b'
down_revision: Union[str, None] = '4988b7bbd0b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'customer_usage',
        sa.Column(
            'usage_trend_state',
            sa.String(30),
            nullable=False,
            server_default='insufficient_history',
        ),
    )
    op.add_column(
        'customer_usage',
        sa.Column('usage_trend_pct', sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('customer_usage', 'usage_trend_pct')
    op.drop_column('customer_usage', 'usage_trend_state')
