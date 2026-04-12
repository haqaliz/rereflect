"""add_automation_tables

Revision ID: t9u0v1w2x3y4
Revises: s8t9u0v1w2x3
Create Date: 2026-04-13 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 't9u0v1w2x3y4'
down_revision: Union[str, None] = 's8t9u0v1w2x3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # -----------------------------------------------------------------------
    # automation_rules
    # -----------------------------------------------------------------------
    op.create_table(
        'automation_rules',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('organization_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('trigger_type', sa.String(50), nullable=False),
        sa.Column('trigger_config', sa.JSON(), nullable=False),
        sa.Column('actions', sa.JSON(), nullable=False),
        sa.Column('cooldown_hours', sa.Integer(), nullable=False, server_default='24'),
        sa.Column('execution_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_executed_at', sa.DateTime(), nullable=True),
        sa.Column('is_template', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('template_id', sa.String(50), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_automation_rules_id', 'automation_rules', ['id'], unique=False)
    op.create_index(
        'ix_automation_rules_org_active',
        'automation_rules',
        ['organization_id', 'is_active'],
        unique=False,
    )
    op.create_index(
        'ix_automation_rules_org_trigger',
        'automation_rules',
        ['organization_id', 'trigger_type'],
        unique=False,
    )

    # -----------------------------------------------------------------------
    # automation_executions
    # -----------------------------------------------------------------------
    op.create_table(
        'automation_executions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('rule_id', sa.Integer(), nullable=False),
        sa.Column('organization_id', sa.Integer(), nullable=False),
        sa.Column('feedback_id', sa.Integer(), nullable=True),
        sa.Column('customer_email', sa.String(255), nullable=True),
        sa.Column('trigger_snapshot', sa.JSON(), nullable=True),
        sa.Column('actions_executed', sa.JSON(), nullable=True),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('executed_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['rule_id'], ['automation_rules.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['feedback_id'], ['feedback_items.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_automation_executions_id', 'automation_executions', ['id'], unique=False)
    op.create_index(
        'ix_automation_executions_rule_date',
        'automation_executions',
        ['rule_id', 'executed_at'],
        unique=False,
    )
    op.create_index(
        'ix_automation_executions_org_date',
        'automation_executions',
        ['organization_id', 'executed_at'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index('ix_automation_executions_org_date', table_name='automation_executions')
    op.drop_index('ix_automation_executions_rule_date', table_name='automation_executions')
    op.drop_index('ix_automation_executions_id', table_name='automation_executions')
    op.drop_table('automation_executions')

    op.drop_index('ix_automation_rules_org_trigger', table_name='automation_rules')
    op.drop_index('ix_automation_rules_org_active', table_name='automation_rules')
    op.drop_index('ix_automation_rules_id', table_name='automation_rules')
    op.drop_table('automation_rules')
