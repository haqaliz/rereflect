"""add_reports_table

Revision ID: q6r7s8t9u0v1
Revises: p5q6r7s8t9u0
Create Date: 2026-03-17 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'q6r7s8t9u0v1'
down_revision: Union[str, None] = 'p5q6r7s8t9u0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'reports',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('organization_id', sa.Integer(), nullable=False),
        sa.Column('created_by_user_id', sa.Integer(), nullable=True),
        sa.Column('conversation_id', sa.Integer(), nullable=True),
        sa.Column('report_type', sa.String(50), nullable=False),
        sa.Column('date_range_days', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(500), nullable=True),
        sa.Column('sections', sa.JSON(), nullable=True),
        sa.Column('metadata', sa.JSON(), nullable=True),
        sa.Column('pdf_generated', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_reports_id', 'reports', ['id'], unique=False)
    op.create_index('ix_reports_org_date', 'reports', ['organization_id', 'created_at'], unique=False)
    op.create_index('ix_reports_org_type', 'reports', ['organization_id', 'report_type'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_reports_org_type', table_name='reports')
    op.drop_index('ix_reports_org_date', table_name='reports')
    op.drop_index('ix_reports_id', table_name='reports')
    op.drop_table('reports')
