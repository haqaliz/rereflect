"""add_webhook_tables

Revision ID: p5q6r7s8t9u0
Revises: o4p5q6r7s8t9
Create Date: 2026-03-15 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'p5q6r7s8t9u0'
down_revision: Union[str, None] = 'o4p5q6r7s8t9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create webhook_endpoints table
    op.create_table(
        'webhook_endpoints',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('organization_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('url', sa.String(2048), nullable=False),
        sa.Column('signing_secret', sa.String(500), nullable=False),
        sa.Column('events', sa.JSON(), nullable=True),
        sa.Column('category_filters', sa.JSON(), nullable=True),
        sa.Column('custom_headers', sa.Text(), nullable=True),
        sa.Column('retry_mode', sa.String(50), nullable=False, server_default='fire_and_forget'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('consecutive_failures', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_webhook_endpoints_id', 'webhook_endpoints', ['id'], unique=False)
    op.create_index('ix_webhook_endpoints_org', 'webhook_endpoints', ['organization_id'], unique=False)
    op.create_index('ix_webhook_endpoints_org_active', 'webhook_endpoints', ['organization_id', 'is_active'], unique=False)

    # Create webhook_deliveries table
    op.create_table(
        'webhook_deliveries',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('webhook_id', sa.Integer(), nullable=False),
        sa.Column('event', sa.String(100), nullable=False),
        sa.Column('feedback_id', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(50), nullable=False),
        sa.Column('attempt', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('response_code', sa.Integer(), nullable=True),
        sa.Column('response_body', sa.Text(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('latency_ms', sa.Integer(), nullable=True),
        sa.Column('payload', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['feedback_id'], ['feedback_items.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['webhook_id'], ['webhook_endpoints.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_webhook_deliveries_id', 'webhook_deliveries', ['id'], unique=False)
    op.create_index('ix_webhook_deliveries_webhook_created', 'webhook_deliveries', ['webhook_id', 'created_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_webhook_deliveries_webhook_created', table_name='webhook_deliveries')
    op.drop_index('ix_webhook_deliveries_id', table_name='webhook_deliveries')
    op.drop_table('webhook_deliveries')

    op.drop_index('ix_webhook_endpoints_org_active', table_name='webhook_endpoints')
    op.drop_index('ix_webhook_endpoints_org', table_name='webhook_endpoints')
    op.drop_index('ix_webhook_endpoints_id', table_name='webhook_endpoints')
    op.drop_table('webhook_endpoints')
