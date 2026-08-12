"""add_outreach_tables

Revision ID: f6a7b8c9d0e1
Revises: d3a2c5b7e9f4
Create Date: 2026-08-12 00:00:00.000000

Outreach-core aspect (customer-outreach-email-actions):

  - customer_health_scores.outreach_opt_out  BOOLEAN NOT NULL DEFAULT false
  - outreach_campaigns — per-campaign audit row for bulk outreach sends:
    id, organization_id (FK), created_by_user_id (FK), subject, body,
    recipient_count, status ('queued' default), created_at.
  - outreach_campaign_recipients — per-recipient result row:
    id, campaign_id (FK, ondelete CASCADE), customer_email, status
    ('queued' default), error (nullable), created_at, unique
    (campaign_id, customer_email).

The two outreach tables carry the audit trail for the bulk-campaign send
path; this aspect ships the schema + the shared send primitives only.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'f6a7b8c9d0e1'
down_revision: Union[str, None] = 'd3a2c5b7e9f4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Per-customer opt-out flag on the health scores table.
    op.add_column(
        'customer_health_scores',
        sa.Column('outreach_opt_out', sa.Boolean(), nullable=False, server_default='false'),
    )

    # 2. Campaign audit table.
    op.create_table(
        'outreach_campaigns',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            'organization_id',
            sa.Integer(),
            sa.ForeignKey('organizations.id'),
            nullable=False,
        ),
        sa.Column(
            'created_by_user_id',
            sa.Integer(),
            sa.ForeignKey('users.id'),
            nullable=True,
        ),
        sa.Column('subject', sa.String(200), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('recipient_count', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='queued'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
    )
    op.create_index('ix_outreach_campaigns_organization_id', 'outreach_campaigns', ['organization_id'])
    op.create_index('ix_outreach_campaigns_created_by_user_id', 'outreach_campaigns', ['created_by_user_id'])

    # 3. Per-recipient result rows.
    op.create_table(
        'outreach_campaign_recipients',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            'campaign_id',
            sa.Integer(),
            sa.ForeignKey('outreach_campaigns.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('customer_email', sa.String(255), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='queued'),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.UniqueConstraint(
            'campaign_id',
            'customer_email',
            name='uq_outreach_campaign_recipients_campaign_email',
        ),
    )
    op.create_index(
        'ix_outreach_campaign_recipients_campaign_id',
        'outreach_campaign_recipients',
        ['campaign_id'],
    )


def downgrade() -> None:
    op.drop_index(
        'ix_outreach_campaign_recipients_campaign_id',
        table_name='outreach_campaign_recipients',
    )
    op.drop_table('outreach_campaign_recipients')
    op.drop_index('ix_outreach_campaigns_created_by_user_id', table_name='outreach_campaigns')
    op.drop_index('ix_outreach_campaigns_organization_id', table_name='outreach_campaigns')
    op.drop_table('outreach_campaigns')
    op.drop_column('customer_health_scores', 'outreach_opt_out')
