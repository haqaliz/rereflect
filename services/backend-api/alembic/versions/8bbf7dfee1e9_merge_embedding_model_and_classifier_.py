"""merge embedding_model and classifier-versioning heads

Revision ID: 8bbf7dfee1e9
Revises: 719deb6ac0a0, hbsh5o3gbwv4
Create Date: 2026-07-25 13:51:24.096807

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8bbf7dfee1e9'
down_revision: Union[str, None] = ('719deb6ac0a0', 'hbsh5o3gbwv4')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
