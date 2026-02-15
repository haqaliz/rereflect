"""add customer_email to feedback_items and customer_health_scores table

Revision ID: a4b5c6d7e8f9
Revises: 9232cfa0634d
Create Date: 2026-02-16 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a4b5c6d7e8f9'
down_revision: Union[str, None] = '9232cfa0634d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add customer_email to feedback_items
    op.add_column('feedback_items', sa.Column('customer_email', sa.String(255), nullable=True))
    op.create_index('ix_feedback_customer_email', 'feedback_items', ['customer_email'])

    # Create customer_health_scores table
    op.create_table(
        'customer_health_scores',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('organization_id', sa.Integer(), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('customer_email', sa.String(255), nullable=False),
        sa.Column('customer_name', sa.String(255), nullable=True),
        sa.Column('health_score', sa.Integer(), nullable=False, server_default='50'),
        sa.Column('churn_risk_component', sa.Integer(), server_default='50'),
        sa.Column('sentiment_component', sa.Integer(), server_default='50'),
        sa.Column('resolution_component', sa.Integer(), server_default='50'),
        sa.Column('frequency_component', sa.Integer(), server_default='50'),
        sa.Column('feedback_count', sa.Integer(), server_default='0'),
        sa.Column('last_feedback_at', sa.DateTime(), nullable=True),
        sa.Column('risk_level', sa.String(20), server_default='unknown'),
        sa.Column('llm_analysis', sa.Text(), nullable=True),
        sa.Column('llm_analyzed_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('ix_customer_health_org_email', 'customer_health_scores', ['organization_id', 'customer_email'], unique=True)
    op.create_index('ix_customer_health_org_score', 'customer_health_scores', ['organization_id', 'health_score'])
    op.create_index('ix_customer_health_risk', 'customer_health_scores', ['organization_id', 'risk_level'])


def downgrade() -> None:
    op.drop_index('ix_customer_health_risk', table_name='customer_health_scores')
    op.drop_index('ix_customer_health_org_score', table_name='customer_health_scores')
    op.drop_index('ix_customer_health_org_email', table_name='customer_health_scores')
    op.drop_table('customer_health_scores')
    op.drop_index('ix_feedback_customer_email', table_name='feedback_items')
    op.drop_column('feedback_items', 'customer_email')
