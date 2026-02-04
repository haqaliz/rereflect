"""add_google_oauth_columns

Revision ID: df55269cbdec
Revises: h8i9j0k1l2m3
Create Date: 2026-02-04 03:14:33.926857

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'df55269cbdec'
down_revision: Union[str, None] = 'h8i9j0k1l2m3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add google_id column with unique constraint
    op.add_column('users', sa.Column('google_id', sa.String(255), nullable=True))
    op.create_index('ix_users_google_id', 'users', ['google_id'], unique=True)

    # Add auth_provider column with default 'email' for existing users
    op.add_column('users', sa.Column('auth_provider', sa.String(50), nullable=False, server_default='email'))

    # Make password_hash nullable (for Google-only users)
    op.alter_column('users', 'password_hash',
                    existing_type=sa.String(),
                    nullable=True)


def downgrade() -> None:
    # Revert password_hash to non-nullable
    # Note: This will fail if there are Google-only users (no password_hash)
    op.alter_column('users', 'password_hash',
                    existing_type=sa.String(),
                    nullable=False)

    op.drop_column('users', 'auth_provider')
    op.drop_index('ix_users_google_id', table_name='users')
    op.drop_column('users', 'google_id')
