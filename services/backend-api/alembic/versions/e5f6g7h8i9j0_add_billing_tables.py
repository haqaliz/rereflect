"""Add billing tables (subscriptions, usage_records) and seat tracking

Revision ID: e5f6g7h8i9j0
Revises: d4e5f6g7h8i9
Create Date: 2026-02-01

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e5f6g7h8i9j0'
down_revision = 'd4e5f6g7h8i9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create subscriptions table
    op.create_table(
        'subscriptions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('organization_id', sa.Integer(), nullable=False),

        # Stripe identifiers
        sa.Column('stripe_subscription_id', sa.String(length=255), nullable=True),
        sa.Column('stripe_price_id', sa.String(length=255), nullable=True),

        # Plan info
        sa.Column('plan', sa.String(length=50), nullable=False, server_default='free'),
        sa.Column('billing_cycle', sa.String(length=20), nullable=True),

        # Status
        sa.Column('status', sa.String(length=50), nullable=False, server_default='active'),

        # Trial management
        sa.Column('trial_start', sa.DateTime(), nullable=True),
        sa.Column('trial_end', sa.DateTime(), nullable=True),

        # Billing period
        sa.Column('current_period_start', sa.DateTime(), nullable=True),
        sa.Column('current_period_end', sa.DateTime(), nullable=True),

        # Cancellation
        sa.Column('cancel_at_period_end', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('canceled_at', sa.DateTime(), nullable=True),

        # Timestamps
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),

        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('organization_id', name='uq_subscription_org'),
        sa.UniqueConstraint('stripe_subscription_id', name='uq_stripe_subscription_id')
    )
    op.create_index('ix_subscriptions_id', 'subscriptions', ['id'], unique=False)
    op.create_index('ix_subscriptions_stripe_id', 'subscriptions', ['stripe_subscription_id'], unique=True)
    op.create_index('ix_subscriptions_status', 'subscriptions', ['status'], unique=False)
    op.create_index('ix_subscriptions_plan', 'subscriptions', ['plan'], unique=False)
    op.create_index('ix_subscriptions_trial_end', 'subscriptions', ['trial_end'], unique=False)

    # Create usage_records table
    op.create_table(
        'usage_records',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('organization_id', sa.Integer(), nullable=False),

        # Billing period
        sa.Column('period_start', sa.DateTime(), nullable=False),
        sa.Column('period_end', sa.DateTime(), nullable=False),

        # Usage counters
        sa.Column('feedback_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('api_calls_count', sa.Integer(), nullable=False, server_default='0'),

        # Overage tracking
        sa.Column('overage_feedback', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('overage_reported_to_stripe', sa.Boolean(), nullable=False, server_default='false'),

        # Timestamps
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),

        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('organization_id', 'period_start', name='uix_org_period')
    )
    op.create_index('ix_usage_records_id', 'usage_records', ['id'], unique=False)
    op.create_index('ix_usage_records_org', 'usage_records', ['organization_id'], unique=False)
    op.create_index('ix_usage_records_period', 'usage_records', ['period_start', 'period_end'], unique=False)
    op.create_index('ix_usage_records_overage', 'usage_records', ['overage_reported_to_stripe'], unique=False)

    # Add seat tracking columns to organizations table
    op.add_column('organizations', sa.Column('seat_count', sa.Integer(), nullable=False, server_default='1'))
    op.add_column('organizations', sa.Column('max_seats', sa.Integer(), nullable=True))


def downgrade() -> None:
    # Drop organizations columns
    op.drop_column('organizations', 'max_seats')
    op.drop_column('organizations', 'seat_count')

    # Drop usage_records table
    op.drop_index('ix_usage_records_overage', table_name='usage_records')
    op.drop_index('ix_usage_records_period', table_name='usage_records')
    op.drop_index('ix_usage_records_org', table_name='usage_records')
    op.drop_index('ix_usage_records_id', table_name='usage_records')
    op.drop_table('usage_records')

    # Drop subscriptions table
    op.drop_index('ix_subscriptions_trial_end', table_name='subscriptions')
    op.drop_index('ix_subscriptions_plan', table_name='subscriptions')
    op.drop_index('ix_subscriptions_status', table_name='subscriptions')
    op.drop_index('ix_subscriptions_stripe_id', table_name='subscriptions')
    op.drop_index('ix_subscriptions_id', table_name='subscriptions')
    op.drop_table('subscriptions')
