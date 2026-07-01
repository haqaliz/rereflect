"""add salesforce_integrations table

Revision ID: 9f56f9a4f999
Revises: 8ceaecca3d8e
Create Date: 2026-07-01 17:30:00.000000

Adds the salesforce_integrations table (salesforce-connection, aspect 2 of 4
of salesforce-crm-enrichment). Mirrors hubspot_integrations but stores an
OAuth refresh_token + instance_url (web-server OAuth 2.0) instead of a
pasted private-app access_token. One row per organization
(UniqueConstraint(organization_id)), no FK — matches the HubSpot convention.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9f56f9a4f999'
down_revision: Union[str, None] = '8ceaecca3d8e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'salesforce_integrations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('organization_id', sa.Integer(), nullable=False),
        sa.Column('refresh_token', sa.Text(), nullable=False),
        sa.Column('instance_url', sa.String(length=255), nullable=True),
        sa.Column('sf_org_id', sa.String(length=64), nullable=True),
        sa.Column('token_hint', sa.String(length=8), nullable=True),
        sa.Column('connected_by_user_id', sa.Integer(), nullable=True),
        sa.Column('connected_at', sa.DateTime(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('last_synced_at', sa.DateTime(), nullable=True),
        sa.Column('last_sync_status', sa.String(length=50), nullable=True),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('contacts_synced', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('contacts_matched', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('organization_id', name='uq_salesforce_integrations_org_id'),
    )
    op.create_index(
        'ix_salesforce_integrations_org_id',
        'salesforce_integrations',
        ['organization_id'],
    )
    op.create_index(
        op.f('ix_salesforce_integrations_id'),
        'salesforce_integrations',
        ['id'],
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_salesforce_integrations_id'), table_name='salesforce_integrations')
    op.drop_index('ix_salesforce_integrations_org_id', table_name='salesforce_integrations')
    op.drop_table('salesforce_integrations')
