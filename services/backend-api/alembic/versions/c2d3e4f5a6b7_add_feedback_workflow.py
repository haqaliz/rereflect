"""Add feedback workflow tables and columns.

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-02-08

Adds:
- workflow_status, assigned_to columns to feedback_items
- auto_assignment_enabled column to organizations
- feedback_notes table
- feedback_workflow_events table
- assignment_rules table
- Backfills existing feedback to workflow_status='new'
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c2d3e4f5a6b7'
down_revision: Union[str, None] = 'b1c2d3e4f5a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add workflow columns to feedback_items
    op.add_column('feedback_items', sa.Column('workflow_status', sa.String(50), nullable=False, server_default='new'))
    op.add_column('feedback_items', sa.Column('assigned_to', sa.Integer(), sa.ForeignKey('users.id'), nullable=True))
    op.create_index('ix_feedback_org_status', 'feedback_items', ['organization_id', 'workflow_status'])
    op.create_index('ix_feedback_assigned', 'feedback_items', ['assigned_to'])

    # Add auto_assignment_enabled to organizations
    op.add_column('organizations', sa.Column('auto_assignment_enabled', sa.Boolean(), nullable=False, server_default='false'))

    # Create feedback_notes table
    op.create_table(
        'feedback_notes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('feedback_id', sa.Integer(), sa.ForeignKey('feedback_items.id', ondelete='CASCADE'), nullable=False),
        sa.Column('organization_id', sa.Integer(), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('author_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_feedback_notes_id', 'feedback_notes', ['id'])
    op.create_index('ix_feedback_note_feedback', 'feedback_notes', ['feedback_id'])
    op.create_index('ix_feedback_note_org', 'feedback_notes', ['organization_id'])

    # Create feedback_workflow_events table
    op.create_table(
        'feedback_workflow_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('feedback_id', sa.Integer(), sa.ForeignKey('feedback_items.id', ondelete='CASCADE'), nullable=False),
        sa.Column('organization_id', sa.Integer(), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('actor_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('event_type', sa.String(50), nullable=False),
        sa.Column('old_value', sa.String(255), nullable=True),
        sa.Column('new_value', sa.String(255), nullable=True),
        sa.Column('metadata', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_feedback_workflow_events_id', 'feedback_workflow_events', ['id'])
    op.create_index('ix_workflow_event_feedback', 'feedback_workflow_events', ['feedback_id'])
    op.create_index('ix_workflow_event_org', 'feedback_workflow_events', ['organization_id'])

    # Create assignment_rules table
    op.create_table(
        'assignment_rules',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('organization_id', sa.Integer(), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('rule_type', sa.String(50), nullable=False, server_default='category'),
        sa.Column('match_field', sa.String(100), nullable=False),
        sa.Column('match_value', sa.String(255), nullable=False),
        sa.Column('assign_to_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('priority', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_assignment_rules_id', 'assignment_rules', ['id'])
    op.create_index('ix_assignment_rule_org', 'assignment_rules', ['organization_id'])

    # Backfill existing feedback items to 'new' status
    op.execute("UPDATE feedback_items SET workflow_status = 'new' WHERE workflow_status IS NULL")


def downgrade() -> None:
    op.drop_index('ix_assignment_rule_org', table_name='assignment_rules')
    op.drop_index('ix_assignment_rules_id', table_name='assignment_rules')
    op.drop_table('assignment_rules')

    op.drop_index('ix_workflow_event_org', table_name='feedback_workflow_events')
    op.drop_index('ix_workflow_event_feedback', table_name='feedback_workflow_events')
    op.drop_index('ix_feedback_workflow_events_id', table_name='feedback_workflow_events')
    op.drop_table('feedback_workflow_events')

    op.drop_index('ix_feedback_note_org', table_name='feedback_notes')
    op.drop_index('ix_feedback_note_feedback', table_name='feedback_notes')
    op.drop_index('ix_feedback_notes_id', table_name='feedback_notes')
    op.drop_table('feedback_notes')

    op.drop_column('organizations', 'auto_assignment_enabled')

    op.drop_index('ix_feedback_assigned', table_name='feedback_items')
    op.drop_index('ix_feedback_org_status', table_name='feedback_items')
    op.drop_column('feedback_items', 'assigned_to')
    op.drop_column('feedback_items', 'workflow_status')
