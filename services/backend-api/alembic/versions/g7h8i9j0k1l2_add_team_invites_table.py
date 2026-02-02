"""Add team_invites table for invitation system

Revision ID: g7h8i9j0k1l2
Revises: f6g7h8i9j0k1
Create Date: 2026-02-02

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'g7h8i9j0k1l2'
down_revision = 'f6g7h8i9j0k1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create team_invites table
    op.create_table(
        'team_invites',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('organization_id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('role', sa.String(), nullable=False),
        sa.Column('token', sa.String(), nullable=False),
        sa.Column('invited_by_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(), nullable=False, server_default='pending'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('accepted_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name='fk_team_invites_organization_id'),
        sa.ForeignKeyConstraint(['invited_by_id'], ['users.id'], name='fk_team_invites_invited_by_id'),
        sa.PrimaryKeyConstraint('id')
    )

    # Create indexes
    op.create_index('ix_team_invites_id', 'team_invites', ['id'], unique=False)
    op.create_index('ix_team_invites_email', 'team_invites', ['email'], unique=False)
    op.create_index('ix_team_invites_token', 'team_invites', ['token'], unique=True)
    op.create_index('ix_team_invites_organization_id', 'team_invites', ['organization_id'], unique=False)
    op.create_index('ix_team_invites_status', 'team_invites', ['status'], unique=False)


def downgrade() -> None:
    # Drop indexes
    op.drop_index('ix_team_invites_status', table_name='team_invites')
    op.drop_index('ix_team_invites_organization_id', table_name='team_invites')
    op.drop_index('ix_team_invites_token', table_name='team_invites')
    op.drop_index('ix_team_invites_email', table_name='team_invites')
    op.drop_index('ix_team_invites_id', table_name='team_invites')

    # Drop table
    op.drop_table('team_invites')
