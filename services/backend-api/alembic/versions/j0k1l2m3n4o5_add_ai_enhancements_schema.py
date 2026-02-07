"""add_ai_enhancements_schema

Revision ID: j0k1l2m3n4o5
Revises: i9j0k1l2m3n4
Create Date: 2026-02-07

Adds:
- ai_analysis_enabled and openai_api_key to organizations
- custom_categories table
- llm_analyzed, llm_analysis_pending, churn_risk_score, suggested_action to feedback_items
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'j0k1l2m3n4o5'
down_revision: Union[str, None] = 'i9j0k1l2m3n4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Organization AI settings
    op.add_column('organizations', sa.Column(
        'ai_analysis_enabled', sa.Boolean(), nullable=False,
        server_default=sa.text('true')
    ))
    op.add_column('organizations', sa.Column(
        'openai_api_key', sa.Text(), nullable=True
    ))

    # Custom categories table
    op.create_table(
        'custom_categories',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('organization_id', sa.Integer(), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('category_type', sa.String(50), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_custom_cat_org', 'custom_categories', ['organization_id', 'category_type'])

    # Feedback items AI fields
    op.add_column('feedback_items', sa.Column(
        'llm_analyzed', sa.Boolean(), nullable=False,
        server_default=sa.text('false')
    ))
    op.add_column('feedback_items', sa.Column(
        'llm_analysis_pending', sa.Boolean(), nullable=False,
        server_default=sa.text('false')
    ))
    op.add_column('feedback_items', sa.Column(
        'churn_risk_score', sa.Integer(), nullable=True
    ))
    op.add_column('feedback_items', sa.Column(
        'suggested_action', sa.Text(), nullable=True
    ))


def downgrade() -> None:
    op.drop_column('feedback_items', 'suggested_action')
    op.drop_column('feedback_items', 'churn_risk_score')
    op.drop_column('feedback_items', 'llm_analysis_pending')
    op.drop_column('feedback_items', 'llm_analyzed')

    op.drop_index('ix_custom_cat_org', table_name='custom_categories')
    op.drop_table('custom_categories')

    op.drop_column('organizations', 'openai_api_key')
    op.drop_column('organizations', 'ai_analysis_enabled')
