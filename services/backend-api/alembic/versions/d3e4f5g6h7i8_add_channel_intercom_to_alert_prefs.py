"""Add channel_intercom to user_alert_preferences.

Revision ID: d3e4f5g6h7i8
Revises: c2d3e4f5a6b7
Create Date: 2026-02-12

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd3e4f5g6h7i8'
down_revision: Union[str, None] = 'c2d3e4f5a6b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('user_alert_preferences', sa.Column('channel_intercom', sa.Boolean(), nullable=False, server_default='false'))


def downgrade() -> None:
    op.drop_column('user_alert_preferences', 'channel_intercom')
