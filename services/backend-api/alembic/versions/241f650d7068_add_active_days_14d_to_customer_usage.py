"""add active_days_14d to customer_usage

Revision ID: 241f650d7068
Revises: u4v5w6x7y8z9
Create Date: 2026-07-21 21:19:14.137905

Adds the 14-day active-days window field used by the usage-trend churn
signal (aspect rollup-rewindow-fix). Nullable, no server_default, no
backfill — existing rows stay NULL and are populated by the first daily
recompute (or that customer's next event), same as the pre-existing
active_days_7d/30d columns.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '241f650d7068'
down_revision: Union[str, None] = 'u4v5w6x7y8z9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'customer_usage',
        sa.Column('active_days_14d', sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('customer_usage', 'active_days_14d')
