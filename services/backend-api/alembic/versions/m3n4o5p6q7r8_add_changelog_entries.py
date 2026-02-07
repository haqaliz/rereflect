"""add_changelog_entries

Revision ID: m3n4o5p6q7r8
Revises: l2m3n4o5p6q7
Create Date: 2026-02-07

Adds:
- changelog_entries table for public changelog
- is_system_admin column on users table
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'm3n4o5p6q7r8'
down_revision = 'l2m3n4o5p6q7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'changelog_entries',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('commit_hash', sa.String(40), nullable=False),
        sa.Column('title', sa.String(500), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('entry_type', sa.String(50), nullable=False),
        sa.Column('is_breaking', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('is_hidden', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('committed_at', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_changelog_entries_id', 'changelog_entries', ['id'])
    op.create_index('ix_changelog_commit_hash', 'changelog_entries', ['commit_hash'], unique=True)
    op.create_index('ix_changelog_committed_at', 'changelog_entries', ['committed_at'])
    op.create_index('ix_changelog_type', 'changelog_entries', ['entry_type'])

    op.add_column('users', sa.Column('is_system_admin', sa.Boolean(), nullable=False, server_default='false'))


def downgrade() -> None:
    op.drop_column('users', 'is_system_admin')
    op.drop_index('ix_changelog_type', table_name='changelog_entries')
    op.drop_index('ix_changelog_committed_at', table_name='changelog_entries')
    op.drop_index('ix_changelog_commit_hash', table_name='changelog_entries')
    op.drop_index('ix_changelog_entries_id', table_name='changelog_entries')
    op.drop_table('changelog_entries')
