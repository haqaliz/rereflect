"""add_intercom_writeback_columns

Revision ID: e4f5a6b7c8d9
Revises: 3cb9a0d1456b
Create Date: 2026-08-15 00:00:00.000000

intercom-writeback (db-config-model aspect, R1 + R4):

  - intercom_integrations.writeback_enabled     BOOLEAN NOT NULL DEFAULT false
  - intercom_integrations.writeback_action      VARCHAR(32) NOT NULL DEFAULT 'note_and_close'
  - intercom_integrations.last_writeback_at     TIMESTAMPTZ NULL
  - intercom_integrations.last_writeback_status VARCHAR(64) NULL
  - intercom_integrations.last_writeback_error  TEXT NULL
  - feedback_items.intercom_writeback_at        TIMESTAMPTZ NULL

writeback_enabled server_default backfills every existing row to false — no
org is silently opted in (prd R1: off by default). writeback_action pins the
v1 fixed action (prd OQ1: note_and_close). The nullable per-feedback marker
is the durable idempotency anchor for the worker writeback task (prd R4).

Additive columns only — safe on existing data, symmetric upgrade/downgrade.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e4f5a6b7c8d9'
down_revision: Union[str, None] = '3cb9a0d1456b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Per-org Intercom write-back opt-in + status readout (R1).
    op.add_column(
        'intercom_integrations',
        sa.Column('writeback_enabled', sa.Boolean(), nullable=False,
                  server_default='false'),
    )
    op.add_column(
        'intercom_integrations',
        sa.Column('writeback_action', sa.String(32), nullable=False,
                  server_default='note_and_close'),
    )
    op.add_column(
        'intercom_integrations',
        sa.Column('last_writeback_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        'intercom_integrations',
        sa.Column('last_writeback_status', sa.String(64), nullable=True),
    )
    op.add_column(
        'intercom_integrations',
        sa.Column('last_writeback_error', sa.Text(), nullable=True),
    )

    # 2. Durable per-feedback idempotency marker (R4).
    op.add_column(
        'feedback_items',
        sa.Column('intercom_writeback_at', sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('feedback_items', 'intercom_writeback_at')
    op.drop_column('intercom_integrations', 'last_writeback_error')
    op.drop_column('intercom_integrations', 'last_writeback_status')
    op.drop_column('intercom_integrations', 'last_writeback_at')
    op.drop_column('intercom_integrations', 'writeback_action')
    op.drop_column('intercom_integrations', 'writeback_enabled')
