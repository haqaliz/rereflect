"""add_tags_column_to_feedback

Revision ID: 9f2a1dfcdb55
Revises: 65fe1d5fdc48
Create Date: 2025-12-27 19:46:34.784805

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9f2a1dfcdb55'
down_revision: Union[str, None] = '65fe1d5fdc48'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('feedback_items', sa.Column('tags', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('feedback_items', 'tags')
