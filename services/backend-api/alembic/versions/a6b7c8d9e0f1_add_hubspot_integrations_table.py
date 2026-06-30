"""add_hubspot_integrations_table

Revision ID: a6b7c8d9e0f1
Revises: a8b9c0d1e2f3
Create Date: 2026-06-30 00:00:00.000000

Creates the hubspot_integrations table for the hubspot-connection aspect.
All other aspects (hubspot-sync, crm-health-component) chain their own
migrations off this one.

Note: down_revision is 'a8b9c0d1e2f3' (add_customer_usage), which is the
actual migration head at implementation time. The plan specified 'z5a6b7c8d9e0'
but two additional migrations (add_usage_event, add_customer_usage) were merged
before this aspect was implemented. Using the actual head prevents a migration
branch/fork.
"""
from alembic import op
import sqlalchemy as sa

revision: str = 'a6b7c8d9e0f1'
down_revision = 'a8b9c0d1e2f3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'hubspot_integrations',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('organization_id', sa.Integer(), nullable=False),
        sa.Column('access_token', sa.Text(), nullable=False),
        sa.Column('token_hint', sa.String(8), nullable=True),
        sa.Column('hub_id', sa.String(64), nullable=True),
        sa.Column('portal_name', sa.String(255), nullable=True),
        sa.Column('arr_property_name', sa.String(255), nullable=False,
                  server_default='annualrevenue'),
        sa.Column('connected_by_user_id', sa.Integer(), nullable=True),
        sa.Column('connected_at', sa.DateTime(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('last_synced_at', sa.DateTime(), nullable=True),
        sa.Column('last_sync_status', sa.String(50), nullable=True),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('contacts_synced', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('contacts_matched', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('organization_id', name='uq_hubspot_integrations_org_id'),
    )
    op.create_index(
        'ix_hubspot_integrations_org_id',
        'hubspot_integrations',
        ['organization_id'],
    )


def downgrade() -> None:
    op.drop_index('ix_hubspot_integrations_org_id', table_name='hubspot_integrations')
    op.drop_table('hubspot_integrations')
