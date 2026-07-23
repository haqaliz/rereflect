"""add_trend_to_usage_history

Revision ID: a1c2d3e4f5a6
Revises: a5b63dbbce9b
Create Date: 2026-07-23 00:00:00.000000

Adds the two trend columns for the snapshot-trend-columns aspect
(usage-trend-automation-trigger, M3):

  - usage_trend_state (String(30), nullable, NO server_default)
  - usage_trend_pct (Float, nullable, NO server_default)

Deliberately unlike the customer_usage sibling columns added by
a5b63dbbce9b (add_usage_trend_fields), which are NOT NULL with
server_default='insufficient_history'. Here, pre-existing snapshot rows
genuinely have no known trend state — there is no backfill — and the
downstream timeline-trend-event aspect relies on NULL meaning "unknown,
skip" rather than a real classified state.

Additive, nullable, no backfill, no downtime concern.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1c2d3e4f5a6'
down_revision: Union[str, None] = 'a5b63dbbce9b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'customer_usage_history',
        sa.Column('usage_trend_state', sa.String(30), nullable=True),
    )
    op.add_column(
        'customer_usage_history',
        sa.Column('usage_trend_pct', sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('customer_usage_history', 'usage_trend_pct')
    op.drop_column('customer_usage_history', 'usage_trend_state')
