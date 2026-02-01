"""Add message_template to integrations

Revision ID: c3d4e5f6g7h8
Revises: b2c3d4e5f6g7
Create Date: 2026-01-31

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c3d4e5f6g7h8'
down_revision = 'b2c3d4e5f6g7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add message_template column to integrations table
    op.add_column(
        'integrations',
        sa.Column('message_template', sa.Text(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('integrations', 'message_template')
