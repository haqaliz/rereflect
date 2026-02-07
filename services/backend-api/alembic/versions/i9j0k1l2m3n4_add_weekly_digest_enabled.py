"""add_weekly_digest_enabled

Revision ID: i9j0k1l2m3n4
Revises: df55269cbdec
Create Date: 2026-02-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'i9j0k1l2m3n4'
down_revision: Union[str, None] = 'df55269cbdec'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column(
        'weekly_digest_enabled', sa.Boolean(), nullable=False,
        server_default=sa.text('true')
    ))


def downgrade() -> None:
    op.drop_column('users', 'weekly_digest_enabled')
