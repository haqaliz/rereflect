"""add_crm_writeback_columns

Revision ID: a1b2c3d4e5f6
Revises: 9f56f9a4f999
Create Date: 2026-07-03 00:00:00.000000

writeback-config-api aspect (crm-writeback PRD, slice 1): persists per-org
HubSpot writeback opt-in/status and idempotency memory on crm_enrichment.

Adds to hubspot_integrations:
  - writeback_enabled       BOOLEAN NOT NULL DEFAULT false (server_default so
                            all existing rows backfill to false — no org is
                            silently opted in)
  - writeback_field_name    VARCHAR(255) NULL
  - last_writeback_at       TIMESTAMP NULL
  - last_writeback_status   VARCHAR(50) NULL
  - last_writeback_error    TEXT NULL
  - contacts_written        INTEGER NOT NULL DEFAULT 0

Adds to crm_enrichment:
  - last_written_health_score  INTEGER NULL
  - last_health_written_at     TIMESTAMP NULL

Both are additive/nullable-or-defaulted columns — safe on existing data,
symmetric upgrade/downgrade.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'n7o8p9q0r1s2'
down_revision: Union[str, None] = '9f56f9a4f999'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. hubspot_integrations — writeback config + status columns
    op.add_column(
        'hubspot_integrations',
        sa.Column(
            'writeback_enabled', sa.Boolean(), nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        'hubspot_integrations',
        sa.Column('writeback_field_name', sa.String(255), nullable=True),
    )
    op.add_column(
        'hubspot_integrations',
        sa.Column('last_writeback_at', sa.DateTime(), nullable=True),
    )
    op.add_column(
        'hubspot_integrations',
        sa.Column('last_writeback_status', sa.String(50), nullable=True),
    )
    op.add_column(
        'hubspot_integrations',
        sa.Column('last_writeback_error', sa.Text(), nullable=True),
    )
    op.add_column(
        'hubspot_integrations',
        sa.Column(
            'contacts_written', sa.Integer(), nullable=False,
            server_default='0',
        ),
    )

    # 2. crm_enrichment — idempotency memory for the writeback task
    op.add_column(
        'crm_enrichment',
        sa.Column('last_written_health_score', sa.Integer(), nullable=True),
    )
    op.add_column(
        'crm_enrichment',
        sa.Column('last_health_written_at', sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    # Guard: safe to run even if a prior partial downgrade already dropped
    # some of these columns (e.g. re-running downgrade after an interrupted
    # run) — inspect existing columns before dropping.
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    def _drop_if_exists(table: str, column: str) -> None:
        existing = {c['name'] for c in inspector.get_columns(table)}
        if column in existing:
            op.drop_column(table, column)

    _drop_if_exists('crm_enrichment', 'last_health_written_at')
    _drop_if_exists('crm_enrichment', 'last_written_health_score')

    _drop_if_exists('hubspot_integrations', 'contacts_written')
    _drop_if_exists('hubspot_integrations', 'last_writeback_error')
    _drop_if_exists('hubspot_integrations', 'last_writeback_status')
    _drop_if_exists('hubspot_integrations', 'last_writeback_at')
    _drop_if_exists('hubspot_integrations', 'writeback_field_name')
    _drop_if_exists('hubspot_integrations', 'writeback_enabled')
