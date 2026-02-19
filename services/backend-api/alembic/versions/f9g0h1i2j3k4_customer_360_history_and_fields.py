"""customer_360: add is_archived, confidence_level to customer_health_scores; create customer_health_history

Revision ID: f9g0h1i2j3k4
Revises: e8f9g0h1i2j3
Create Date: 2026-02-19 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f9g0h1i2j3k4'
down_revision: Union[str, None] = 'e8f9g0h1i2j3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add is_archived column to customer_health_scores
    op.add_column(
        'customer_health_scores',
        sa.Column('is_archived', sa.Boolean(), nullable=False, server_default='false'),
    )

    # Add confidence_level column to customer_health_scores
    op.add_column(
        'customer_health_scores',
        sa.Column('confidence_level', sa.String(20), nullable=True, server_default='low'),
    )

    # Create customer_health_history table
    op.create_table(
        'customer_health_history',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            'customer_health_id',
            sa.Integer(),
            sa.ForeignKey('customer_health_scores.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column(
            'organization_id',
            sa.Integer(),
            sa.ForeignKey('organizations.id'),
            nullable=False,
        ),
        sa.Column('health_score', sa.Integer(), nullable=False),
        sa.Column('churn_risk_component', sa.Integer(), nullable=True),
        sa.Column('sentiment_component', sa.Integer(), nullable=True),
        sa.Column('resolution_component', sa.Integer(), nullable=True),
        sa.Column('frequency_component', sa.Integer(), nullable=True),
        sa.Column('risk_level', sa.String(20), nullable=True),
        sa.Column('recorded_at', sa.DateTime(), server_default=sa.func.now()),
    )

    # Create indexes for efficient history queries
    op.create_index(
        'ix_health_history_customer_date',
        'customer_health_history',
        ['customer_health_id', 'recorded_at'],
    )
    op.create_index(
        'ix_health_history_org_date',
        'customer_health_history',
        ['organization_id', 'recorded_at'],
    )


def downgrade() -> None:
    op.drop_index('ix_health_history_org_date', table_name='customer_health_history')
    op.drop_index('ix_health_history_customer_date', table_name='customer_health_history')
    op.drop_table('customer_health_history')
    op.drop_column('customer_health_scores', 'confidence_level')
    op.drop_column('customer_health_scores', 'is_archived')
