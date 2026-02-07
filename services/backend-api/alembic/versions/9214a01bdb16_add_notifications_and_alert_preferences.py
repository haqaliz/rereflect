"""add_notifications_and_alert_preferences

Revision ID: 9214a01bdb16
Revises: m3n4o5p6q7r8
Create Date: 2026-02-08 01:06:08.612602

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9214a01bdb16'
down_revision: Union[str, None] = 'm3n4o5p6q7r8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create notifications table
    op.create_table('notifications',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('organization_id', sa.Integer(), nullable=False),
        sa.Column('type', sa.String(length=50), nullable=False),
        sa.Column('title', sa.String(length=500), nullable=False),
        sa.Column('message', sa.Text(), nullable=True),
        sa.Column('link', sa.String(length=500), nullable=True),
        sa.Column('is_read', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('is_dismissed', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('metadata', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id']),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_notification_expires', 'notifications', ['expires_at'])
    op.create_index('ix_notification_org', 'notifications', ['organization_id'])
    op.create_index('ix_notification_user_read', 'notifications', ['user_id', 'is_read', 'is_dismissed'])

    # Create user_alert_preferences table
    op.create_table('user_alert_preferences',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('alert_type', sa.String(length=50), nullable=False),
        sa.Column('is_enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('channel_email', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('channel_slack', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('channel_inapp', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('threshold_value', sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'alert_type', name='uq_user_alert_type')
    )

    # Add new columns to integrations
    op.add_column('integrations', sa.Column('alert_channel_id', sa.String(length=100), nullable=True))
    op.add_column('integrations', sa.Column('alert_channel_name', sa.String(length=255), nullable=True))

    # Add new columns to users
    op.add_column('users', sa.Column('notification_retention_days', sa.Integer(), server_default='30', nullable=False))
    op.add_column('users', sa.Column('daily_digest_enabled', sa.Boolean(), server_default='true', nullable=False))

    # Seed default alert preferences for existing users
    op.execute("""
        INSERT INTO user_alert_preferences (user_id, alert_type, is_enabled, channel_email, channel_slack, channel_inapp, threshold_value)
        SELECT u.id, t.alert_type, true, false, true, true, t.default_threshold
        FROM users u
        CROSS JOIN (VALUES
            ('urgent_feedback', NULL::float),
            ('sentiment_spike', 50.0),
            ('churn_risk', NULL::float),
            ('volume_spike', 2.0)
        ) AS t(alert_type, default_threshold)
        ON CONFLICT DO NOTHING
    """)


def downgrade() -> None:
    op.drop_column('users', 'daily_digest_enabled')
    op.drop_column('users', 'notification_retention_days')
    op.drop_column('integrations', 'alert_channel_name')
    op.drop_column('integrations', 'alert_channel_id')
    op.drop_table('user_alert_preferences')
    op.drop_index('ix_notification_user_read', table_name='notifications')
    op.drop_index('ix_notification_org', table_name='notifications')
    op.drop_index('ix_notification_expires', table_name='notifications')
    op.drop_table('notifications')
