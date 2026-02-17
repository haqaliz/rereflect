"""add promo_code_used to organizations

Revision ID: d7e8f9g0h1i2
Revises: c6d7e8f9g0h1
Create Date: 2026-02-17 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd7e8f9g0h1i2'
down_revision: Union[str, None] = 'c6d7e8f9g0h1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('organizations', sa.Column('promo_code_used', sa.String(50), nullable=True))


def downgrade() -> None:
    op.drop_column('organizations', 'promo_code_used')
