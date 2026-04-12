"""add_ai_corrections_table

Revision ID: s8t9u0v1w2x3
Revises: r7s8t9u0v1w2
Create Date: 2026-04-12 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 's8t9u0v1w2x3'
down_revision: Union[str, None] = 'r7s8t9u0v1w2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'ai_corrections',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('organization_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('correction_type', sa.String(50), nullable=False),
        sa.Column('entity_type', sa.String(50), nullable=False),
        sa.Column('entity_id', sa.Integer(), nullable=True),
        sa.Column('signal', sa.String(20), nullable=False),
        sa.Column('original_value', sa.String(500), nullable=True),
        sa.Column('corrected_value', sa.String(500), nullable=True),
        sa.Column('feedback_text', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_ai_corrections_id', 'ai_corrections', ['id'], unique=False)
    op.create_index(
        'ix_ai_corrections_org_type',
        'ai_corrections',
        ['organization_id', 'correction_type'],
        unique=False,
    )
    op.create_index(
        'ix_ai_corrections_entity',
        'ai_corrections',
        ['entity_type', 'entity_id'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index('ix_ai_corrections_entity', table_name='ai_corrections')
    op.drop_index('ix_ai_corrections_org_type', table_name='ai_corrections')
    op.drop_index('ix_ai_corrections_id', table_name='ai_corrections')
    op.drop_table('ai_corrections')
