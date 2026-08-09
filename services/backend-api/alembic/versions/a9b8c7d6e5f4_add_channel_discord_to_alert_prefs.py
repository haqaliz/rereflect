"""Add channel_discord to user_alert_preferences.

Revision ID: a9b8c7d6e5f4
Revises: 8114adde5d96
Create Date: 2026-08-09

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a9b8c7d6e5f4'
down_revision: Union[str, None] = '8114adde5d96'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('user_alert_preferences', sa.Column('channel_discord', sa.Boolean(), nullable=False, server_default='true'))


def downgrade() -> None:
    op.drop_column('user_alert_preferences', 'channel_discord')
