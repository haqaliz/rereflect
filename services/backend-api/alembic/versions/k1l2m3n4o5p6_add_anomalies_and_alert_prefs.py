"""add_anomalies_and_alert_prefs

Revision ID: k1l2m3n4o5p6
Revises: j0k1l2m3n4o5
Create Date: 2026-02-07

Adds:
- sentiment_anomalies table
- alert_channels to users (per-user override)
- default_alert_channels to organizations (org-wide defaults)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'k1l2m3n4o5p6'
down_revision: Union[str, None] = 'j0k1l2m3n4o5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Sentiment anomalies table
    op.create_table(
        'sentiment_anomalies',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('organization_id', sa.Integer(), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('detected_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('anomaly_type', sa.String(50), nullable=False),
        sa.Column('severity', sa.String(20), nullable=False),
        sa.Column('baseline_negative_pct', sa.Float(), nullable=False),
        sa.Column('current_negative_pct', sa.Float(), nullable=False),
        sa.Column('deviation_pct', sa.Float(), nullable=False),
        sa.Column('time_window_hours', sa.Integer(), nullable=False, server_default='24'),
        sa.Column('feedback_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_resolved', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('resolved_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_anomaly_org_resolved', 'sentiment_anomalies', ['organization_id', 'is_resolved'])
    op.create_index('ix_anomaly_detected', 'sentiment_anomalies', ['detected_at'])

    # Alert channels on users (per-user override, nullable)
    op.add_column('users', sa.Column(
        'alert_channels', sa.JSON(), nullable=True
    ))

    # Default alert channels on organizations
    op.add_column('organizations', sa.Column(
        'default_alert_channels', sa.JSON(), nullable=False,
        server_default=sa.text("'{\"dashboard\": true, \"email\": false, \"slack\": false}'::json")
    ))


def downgrade() -> None:
    op.drop_column('organizations', 'default_alert_channels')
    op.drop_column('users', 'alert_channels')

    op.drop_index('ix_anomaly_detected', table_name='sentiment_anomalies')
    op.drop_index('ix_anomaly_org_resolved', table_name='sentiment_anomalies')
    op.drop_table('sentiment_anomalies')
