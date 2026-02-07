"""add_weekly_insights

Revision ID: l2m3n4o5p6q7
Revises: k1l2m3n4o5p6
Create Date: 2026-02-07

Adds:
- weekly_insights table for AI-generated insight summaries
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'l2m3n4o5p6q7'
down_revision = 'k1l2m3n4o5p6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'weekly_insights',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('organization_id', sa.Integer(), nullable=False),
        sa.Column('week_start', sa.DateTime(), nullable=False),
        sa.Column('week_end', sa.DateTime(), nullable=False),
        sa.Column('insights', sa.JSON(), nullable=False),
        sa.Column('generated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_weekly_insights_id', 'weekly_insights', ['id'])
    op.create_index('ix_weekly_insight_org_week', 'weekly_insights', ['organization_id', 'week_start'])


def downgrade() -> None:
    op.drop_index('ix_weekly_insight_org_week', table_name='weekly_insights')
    op.drop_index('ix_weekly_insights_id', table_name='weekly_insights')
    op.drop_table('weekly_insights')
