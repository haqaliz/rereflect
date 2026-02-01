"""Add integrations and slack_alert_logs tables

Revision ID: b2c3d4e5f6g7
Revises: a1b2c3d4e5f6
Create Date: 2026-01-31

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON


# revision identifiers, used by Alembic.
revision = 'b2c3d4e5f6g7'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create integrations table
    op.create_table(
        'integrations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('organization_id', sa.Integer(), nullable=False),
        sa.Column('type', sa.String(length=50), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=True),

        # Connection config
        sa.Column('config', JSON(), nullable=True, default={}),

        # OAuth tokens
        sa.Column('oauth_access_token', sa.Text(), nullable=True),
        sa.Column('oauth_refresh_token', sa.Text(), nullable=True),
        sa.Column('oauth_expires_at', sa.DateTime(), nullable=True),

        # Alert configuration
        sa.Column('triggers', JSON(), nullable=True, default=['urgent']),
        sa.Column('included_fields', JSON(), nullable=True, default=['text', 'sentiment']),
        sa.Column('digest_time', sa.Time(), nullable=True, default='09:00:00'),

        # Status
        sa.Column('is_active', sa.Boolean(), nullable=True, default=True),
        sa.Column('last_used_at', sa.DateTime(), nullable=True),
        sa.Column('error_count', sa.Integer(), nullable=True, default=0),
        sa.Column('last_error', sa.Text(), nullable=True),

        # Timestamps
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),

        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_integrations_id', 'integrations', ['id'], unique=False)
    op.create_index('ix_integration_org_type', 'integrations', ['organization_id', 'type'], unique=False)
    op.create_index('ix_integration_active', 'integrations', ['is_active', 'type'], unique=False)

    # Create slack_alert_logs table
    op.create_table(
        'slack_alert_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('integration_id', sa.Integer(), nullable=False),
        sa.Column('feedback_id', sa.Integer(), nullable=True),  # NULL for digests

        sa.Column('alert_type', sa.String(length=50), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),

        sa.Column('slack_response', JSON(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),

        sa.Column('sent_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),

        sa.ForeignKeyConstraint(['integration_id'], ['integrations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['feedback_id'], ['feedback_items.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_slack_alert_logs_id', 'slack_alert_logs', ['id'], unique=False)
    op.create_index('ix_slack_alert_log_integration', 'slack_alert_logs', ['integration_id', 'sent_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_slack_alert_log_integration', table_name='slack_alert_logs')
    op.drop_index('ix_slack_alert_logs_id', table_name='slack_alert_logs')
    op.drop_table('slack_alert_logs')

    op.drop_index('ix_integration_active', table_name='integrations')
    op.drop_index('ix_integration_org_type', table_name='integrations')
    op.drop_index('ix_integrations_id', table_name='integrations')
    op.drop_table('integrations')
