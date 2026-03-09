"""add_response_suggestions

Revision ID: o4p5q6r7s8t9
Revises: n3o4p5q6r7s8
Create Date: 2026-03-09 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'o4p5q6r7s8t9'
down_revision: Union[str, None] = '5ee1b2567a02'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Organization response settings columns
    op.add_column('organizations', sa.Column('brand_voice', sa.Text(), nullable=True))
    op.add_column('organizations', sa.Column('default_tone', sa.String(50), nullable=True, server_default='professional'))
    op.add_column('organizations', sa.Column('product_name_display', sa.String(200), nullable=True))
    op.add_column('organizations', sa.Column('support_email_display', sa.String(200), nullable=True))
    op.add_column('organizations', sa.Column('ai_responses_generated', sa.Integer(), nullable=False, server_default='0'))

    # Response templates table
    op.create_table(
        'response_templates',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('organization_id', sa.Integer(), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=True),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('category', sa.String(100), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('is_system', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('usage_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_response_templates_id', 'response_templates', ['id'])
    op.create_index('ix_response_templates_org', 'response_templates', ['organization_id'])
    op.create_index('ix_response_templates_category', 'response_templates', ['organization_id', 'category'])

    # Feedback responses table
    op.create_table(
        'feedback_responses',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('feedback_id', sa.Integer(), sa.ForeignKey('feedback_items.id', ondelete='CASCADE'), nullable=False),
        sa.Column('organization_id', sa.Integer(), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('response_text', sa.Text(), nullable=False),
        sa.Column('channel', sa.String(50), nullable=False),
        sa.Column('source', sa.String(50), nullable=False),
        sa.Column('template_id', sa.Integer(), sa.ForeignKey('response_templates.id', ondelete='SET NULL'), nullable=True),
        sa.Column('tone', sa.String(50), nullable=True),
        sa.Column('status', sa.String(50), nullable=False, server_default='sent'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_feedback_responses_id', 'feedback_responses', ['id'])
    op.create_index('ix_feedback_responses_feedback', 'feedback_responses', ['feedback_id'])
    op.create_index('ix_feedback_responses_org', 'feedback_responses', ['organization_id'])
    op.create_index('ix_feedback_responses_user', 'feedback_responses', ['user_id'])


def downgrade() -> None:
    op.drop_table('feedback_responses')
    op.drop_table('response_templates')
    op.drop_column('organizations', 'ai_responses_generated')
    op.drop_column('organizations', 'support_email_display')
    op.drop_column('organizations', 'product_name_display')
    op.drop_column('organizations', 'default_tone')
    op.drop_column('organizations', 'brand_voice')
