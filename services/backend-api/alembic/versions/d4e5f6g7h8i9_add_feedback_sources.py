"""Add feedback sources, events, and pending feedbacks tables

Revision ID: d4e5f6g7h8i9
Revises: c3d4e5f6g7h8
Create Date: 2026-02-01

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON


# revision identifiers, used by Alembic.
revision = 'd4e5f6g7h8i9'
down_revision = 'c3d4e5f6g7h8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create feedback_sources table first (others depend on it)
    op.create_table(
        'feedback_sources',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('organization_id', sa.Integer(), nullable=False),
        sa.Column('integration_id', sa.Integer(), nullable=True),

        # Source type
        sa.Column('source_type', sa.String(length=50), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=True),

        # Provider-specific config
        sa.Column('provider_config', JSON(), nullable=True, default={}),

        # Trigger configuration
        sa.Column('triggers', JSON(), nullable=True, default={}),

        # Field mapping
        sa.Column('field_mapping', JSON(), nullable=True, default={}),

        # Processing mode
        sa.Column('auto_import', sa.Boolean(), nullable=True, default=True),

        # Status tracking
        sa.Column('is_active', sa.Boolean(), nullable=True, default=True),
        sa.Column('last_event_at', sa.DateTime(), nullable=True),
        sa.Column('events_processed', sa.Integer(), nullable=True, default=0),
        sa.Column('error_count', sa.Integer(), nullable=True, default=0),
        sa.Column('last_error', sa.Text(), nullable=True),

        # Timestamps
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),

        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['integration_id'], ['integrations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_feedback_sources_id', 'feedback_sources', ['id'], unique=False)
    op.create_index('ix_feedback_source_org_type', 'feedback_sources', ['organization_id', 'source_type'], unique=False)
    op.create_index('ix_feedback_source_active', 'feedback_sources', ['is_active', 'source_type'], unique=False)
    op.create_index('ix_feedback_source_integration', 'feedback_sources', ['integration_id'], unique=False)

    # Create feedback_source_events table
    op.create_table(
        'feedback_source_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('source_id', sa.Integer(), nullable=False),
        sa.Column('organization_id', sa.Integer(), nullable=False),

        # Event identification
        sa.Column('external_event_id', sa.String(length=255), nullable=False),
        sa.Column('external_message_id', sa.String(length=255), nullable=True),
        sa.Column('event_type', sa.String(length=50), nullable=False),

        # Processing status
        sa.Column('status', sa.String(length=20), nullable=False, default='pending'),
        sa.Column('trigger_matched', sa.String(length=100), nullable=True),

        # Result
        sa.Column('feedback_id', sa.Integer(), nullable=True),
        sa.Column('pending_feedback_id', sa.Integer(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),

        # Raw event data
        sa.Column('event_data', JSON(), nullable=True),

        # Timestamps
        sa.Column('received_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('processed_at', sa.DateTime(), nullable=True),

        sa.ForeignKeyConstraint(['source_id'], ['feedback_sources.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['feedback_id'], ['feedback_items.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('source_id', 'external_event_id', name='uq_source_event')
    )
    op.create_index('ix_feedback_source_events_id', 'feedback_source_events', ['id'], unique=False)
    op.create_index('ix_fse_source_received', 'feedback_source_events', ['source_id', 'received_at'], unique=False)
    op.create_index('ix_fse_external_id', 'feedback_source_events', ['external_event_id'], unique=False)
    op.create_index('ix_fse_status', 'feedback_source_events', ['status', 'received_at'], unique=False)
    op.create_index('ix_fse_message', 'feedback_source_events', ['source_id', 'external_message_id'], unique=False)

    # Create pending_feedbacks table
    op.create_table(
        'pending_feedbacks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('source_id', sa.Integer(), nullable=False),
        sa.Column('organization_id', sa.Integer(), nullable=False),
        sa.Column('event_id', sa.Integer(), nullable=False),

        # Content
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('source_metadata', JSON(), nullable=True),
        sa.Column('trigger_type', sa.String(length=100), nullable=True),

        # Review status
        sa.Column('status', sa.String(length=20), nullable=False, default='pending'),
        sa.Column('reviewed_at', sa.DateTime(), nullable=True),
        sa.Column('reviewed_by', sa.Integer(), nullable=True),

        # Timestamps
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),

        sa.ForeignKeyConstraint(['source_id'], ['feedback_sources.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['event_id'], ['feedback_source_events.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['reviewed_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_pending_feedbacks_id', 'pending_feedbacks', ['id'], unique=False)
    op.create_index('ix_pending_feedback_org_status', 'pending_feedbacks', ['organization_id', 'status'], unique=False)
    op.create_index('ix_pending_feedback_source', 'pending_feedbacks', ['source_id', 'created_at'], unique=False)
    op.create_index('ix_pending_feedback_status_created', 'pending_feedbacks', ['status', 'created_at'], unique=False)

    # Add source tracking columns to feedback_items
    op.add_column('feedback_items', sa.Column('source_id', sa.Integer(), nullable=True))
    op.add_column('feedback_items', sa.Column('source_external_id', sa.String(length=255), nullable=True))
    op.add_column('feedback_items', sa.Column('source_metadata', JSON(), nullable=True))

    # Add foreign key and index for source_id
    op.create_foreign_key(
        'fk_feedback_items_source_id',
        'feedback_items', 'feedback_sources',
        ['source_id'], ['id'],
        ondelete='SET NULL'
    )
    op.create_index('ix_feedback_source_external', 'feedback_items', ['source', 'source_external_id'], unique=False)


def downgrade() -> None:
    # Drop feedback_items columns and constraints
    op.drop_index('ix_feedback_source_external', table_name='feedback_items')
    op.drop_constraint('fk_feedback_items_source_id', 'feedback_items', type_='foreignkey')
    op.drop_column('feedback_items', 'source_metadata')
    op.drop_column('feedback_items', 'source_external_id')
    op.drop_column('feedback_items', 'source_id')

    # Drop pending_feedbacks table
    op.drop_index('ix_pending_feedback_status_created', table_name='pending_feedbacks')
    op.drop_index('ix_pending_feedback_source', table_name='pending_feedbacks')
    op.drop_index('ix_pending_feedback_org_status', table_name='pending_feedbacks')
    op.drop_index('ix_pending_feedbacks_id', table_name='pending_feedbacks')
    op.drop_table('pending_feedbacks')

    # Drop feedback_source_events table
    op.drop_index('ix_fse_message', table_name='feedback_source_events')
    op.drop_index('ix_fse_status', table_name='feedback_source_events')
    op.drop_index('ix_fse_external_id', table_name='feedback_source_events')
    op.drop_index('ix_fse_source_received', table_name='feedback_source_events')
    op.drop_index('ix_feedback_source_events_id', table_name='feedback_source_events')
    op.drop_table('feedback_source_events')

    # Drop feedback_sources table
    op.drop_index('ix_feedback_source_integration', table_name='feedback_sources')
    op.drop_index('ix_feedback_source_active', table_name='feedback_sources')
    op.drop_index('ix_feedback_source_org_type', table_name='feedback_sources')
    op.drop_index('ix_feedback_sources_id', table_name='feedback_sources')
    op.drop_table('feedback_sources')
