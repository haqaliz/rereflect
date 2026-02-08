"""Add saved_views and shared_links tables for enhanced analytics.

Revision ID: b1c2d3e4f5a6
Revises: a7b8c9d0e1f2
Create Date: 2026-02-08

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b1c2d3e4f5a6'
down_revision: Union[str, None] = 'a7b8c9d0e1f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Saved views table
    op.create_table(
        'saved_views',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('organization_id', sa.Integer(), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('page', sa.String(50), nullable=False),
        sa.Column('config', sa.JSON(), nullable=False),
        sa.Column('created_by_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_saved_views_org_page', 'saved_views', ['organization_id', 'page'])

    # Shared links table
    op.create_table(
        'shared_links',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('organization_id', sa.Integer(), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('token', sa.String(), unique=True, nullable=False, index=True),
        sa.Column('page', sa.String(50), nullable=False),
        sa.Column('config', sa.JSON(), nullable=True),
        sa.Column('password_hash', sa.String(), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('created_by_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('view_count', sa.Integer(), nullable=False, server_default='0'),
    )
    op.create_index('ix_shared_links_org', 'shared_links', ['organization_id'])


def downgrade() -> None:
    op.drop_index('ix_shared_links_org', table_name='shared_links')
    op.drop_table('shared_links')
    op.drop_index('ix_saved_views_org_page', table_name='saved_views')
    op.drop_table('saved_views')
