"""add channel_teams to user alert preferences

Revision ID: ad76527a185e
Revises: 0bf182dad44d
Create Date: 2026-09-02 16:57:20.107904

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ad76527a185e'
down_revision: Union[str, None] = '0bf182dad44d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('user_alert_preferences', sa.Column('channel_teams', sa.Boolean(), nullable=False, server_default='true'))


def downgrade() -> None:
    op.drop_column('user_alert_preferences', 'channel_teams')
