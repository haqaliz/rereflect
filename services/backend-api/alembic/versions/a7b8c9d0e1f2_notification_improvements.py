"""Notification improvements: digest scheduling, per-type retention.

Revision ID: a7b8c9d0e1f2
Revises: 9214a01bdb16
Create Date: 2026-02-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7b8c9d0e1f2'
down_revision: Union[str, None] = '9214a01bdb16'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Digest scheduling columns on users
    op.add_column('users', sa.Column('daily_digest_hour', sa.Integer(), nullable=False, server_default='8'))
    op.add_column('users', sa.Column('weekly_digest_day', sa.Integer(), nullable=False, server_default='1'))
    op.add_column('users', sa.Column('weekly_digest_hour', sa.Integer(), nullable=False, server_default='9'))

    # Per-type retention on user_alert_preferences
    op.add_column('user_alert_preferences', sa.Column('retention_days', sa.Integer(), nullable=False, server_default='30'))


def downgrade() -> None:
    op.drop_column('user_alert_preferences', 'retention_days')
    op.drop_column('users', 'weekly_digest_hour')
    op.drop_column('users', 'weekly_digest_day')
    op.drop_column('users', 'daily_digest_hour')
