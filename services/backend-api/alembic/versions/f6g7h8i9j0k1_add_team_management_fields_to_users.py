"""Add team management fields to users table (RBAC support)

Revision ID: f6g7h8i9j0k1
Revises: e5f6g7h8i9j0
Create Date: 2026-02-02

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f6g7h8i9j0k1'
down_revision = 'e5f6g7h8i9j0'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add last_active_at column - tracks when user last made an API request
    op.add_column('users', sa.Column('last_active_at', sa.DateTime(), nullable=True))

    # Add invited_by_id column - self-referential FK to track who invited the user
    op.add_column('users', sa.Column('invited_by_id', sa.Integer(), nullable=True))

    # Add joined_at column - tracks when user accepted their invite
    op.add_column('users', sa.Column('joined_at', sa.DateTime(), nullable=True))

    # Create foreign key constraint for invited_by_id
    op.create_foreign_key(
        'fk_users_invited_by_id',
        'users', 'users',
        ['invited_by_id'], ['id'],
        ondelete='SET NULL'
    )

    # Create index on invited_by_id for efficient lookups
    op.create_index('ix_users_invited_by_id', 'users', ['invited_by_id'], unique=False)

    # Create index on last_active_at for sorting/filtering active users
    op.create_index('ix_users_last_active_at', 'users', ['last_active_at'], unique=False)


def downgrade() -> None:
    # Drop indexes first
    op.drop_index('ix_users_last_active_at', table_name='users')
    op.drop_index('ix_users_invited_by_id', table_name='users')

    # Drop foreign key constraint
    op.drop_constraint('fk_users_invited_by_id', 'users', type_='foreignkey')

    # Drop columns
    op.drop_column('users', 'joined_at')
    op.drop_column('users', 'invited_by_id')
    op.drop_column('users', 'last_active_at')
