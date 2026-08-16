"""add_intercom_backlog_remaining

Revision ID: f5a6b7c8d9e0
Revises: e4f5a6b7c8d9
Create Date: 2026-08-15 00:00:00.000000

intercom-backlog-drain-visibility (db-status-api aspect, R3):

  - intercom_integrations.backlog_remaining INTEGER NULL

Nullable by design: no meaningful 0 until a completed sync run computes
the estimate (total_count - conversations_seen). NULL = "no estimate" —
never-synced, error-path reset, or the OAuth path that has no pull. No
server_default: existing rows are NULL, which is the correct pre-run
state (an estimate does not exist until a run finishes).

Additive column only — safe on existing data, symmetric upgrade/downgrade.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f5a6b7c8d9e0'
down_revision: Union[str, None] = 'e4f5a6b7c8d9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'intercom_integrations',
        sa.Column('backlog_remaining', sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('intercom_integrations', 'backlog_remaining')
