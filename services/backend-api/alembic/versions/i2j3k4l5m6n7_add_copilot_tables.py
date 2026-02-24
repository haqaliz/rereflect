"""add_copilot_tables

Revision ID: i2j3k4l5m6n7
Revises: h1i2j3k4l5m6
Create Date: 2026-02-23 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'i2j3k4l5m6n7'
down_revision: Union[str, None] = 'h1i2j3k4l5m6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. conversation_folders (must be created before conversations due to FK)
    op.create_table(
        'conversation_folders',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('organization_id', sa.Integer(), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )

    # 2. query_templates (must be created before conversation_messages due to FK)
    op.create_table(
        'query_templates',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('organization_id', sa.Integer(), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=True),
        sa.Column('sql_query', sa.Text(), nullable=False),
        sa.Column('description', sa.String(500), nullable=False),
        sa.Column('parameter_schema', sa.JSON(), nullable=True),
        sa.Column('created_by', sa.String(20), nullable=False),
        sa.Column('usage_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_used_at', sa.DateTime(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('ix_templates_org_active_usage', 'query_templates', ['organization_id', 'is_active', 'usage_count'])

    # 3. conversations
    op.create_table(
        'conversations',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('organization_id', sa.Integer(), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('created_by_user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('title', sa.String(200), nullable=True),
        sa.Column('folder_id', sa.Integer(), sa.ForeignKey('conversation_folders.id', ondelete='SET NULL'), nullable=True),
        sa.Column('context_scope', sa.String(50), nullable=False, server_default='all_data'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('ix_conversations_org_date', 'conversations', ['organization_id', 'created_at'])
    op.create_index('ix_conversations_org_folder', 'conversations', ['organization_id', 'folder_id'])

    # 4. conversation_messages
    op.create_table(
        'conversation_messages',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('conversation_id', sa.Integer(), sa.ForeignKey('conversations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('role', sa.String(20), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('structured_data', sa.JSON(), nullable=True),
        sa.Column('context_scope', sa.String(50), nullable=True),
        sa.Column('query_type', sa.String(20), nullable=True),
        sa.Column('template_id', sa.Integer(), sa.ForeignKey('query_templates.id', ondelete='SET NULL'), nullable=True),
        sa.Column('sql_generated', sa.Text(), nullable=True),
        sa.Column('llm_provider', sa.String(50), nullable=True),
        sa.Column('llm_model', sa.String(100), nullable=True),
        sa.Column('tokens_in', sa.Integer(), nullable=True),
        sa.Column('tokens_out', sa.Integer(), nullable=True),
        sa.Column('cost_cents', sa.Numeric(10, 4), nullable=True),
        sa.Column('latency_ms', sa.Integer(), nullable=True),
        sa.Column('raw_request', sa.JSON(), nullable=True),
        sa.Column('raw_response', sa.JSON(), nullable=True),
        sa.Column('is_regenerated', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('ix_messages_conv_date', 'conversation_messages', ['conversation_id', 'created_at'])

    # 5. query_template_mappings
    op.create_table(
        'query_template_mappings',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('template_id', sa.Integer(), sa.ForeignKey('query_templates.id', ondelete='CASCADE'), nullable=False),
        sa.Column('question_pattern', sa.Text(), nullable=False),
        # TODO: Replace with pgvector VECTOR(1536) when extension is available
        sa.Column('question_embedding', sa.JSON(), nullable=True),
        sa.Column('match_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('ix_mappings_template_id', 'query_template_mappings', ['template_id'])

    # 6. copilot_schema_whitelist
    op.create_table(
        'copilot_schema_whitelist',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('table_name', sa.String(100), nullable=False),
        sa.Column('column_name', sa.String(100), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
    )


def downgrade() -> None:
    op.drop_table('copilot_schema_whitelist')
    op.drop_table('query_template_mappings')
    op.drop_table('conversation_messages')
    op.drop_table('conversations')
    op.drop_table('query_templates')
    op.drop_table('conversation_folders')
