"""add_report_schedules_table

Revision ID: fb57e62a2820
Revises: a2b3c4d5e6f7
Create Date: 2026-08-25 02:24:50.630849

scheduled-ai-reports (backend-schedule-crud aspect):

  - report_schedules — one row per configured AI report schedule:
    id (Integer PK), organization_id (FK, ondelete CASCADE, indexed),
    created_by_user_id (FK users.id, ondelete SET NULL, nullable),
    report_type (4 fixed types), date_range_days (7|30|90, default 30),
    cadence (daily|weekly|monthly), hour_utc (0-23), day_of_week (0-6,
    nullable, required when weekly), day_of_month (1-31, nullable, required
    when monthly), recipients (JSON list of emails, deduped, max 20),
    enabled (default true), last_run_at (nullable, worker-owned),
    created_at / updated_at.

  Composite index (organization_id, enabled) for the worker's due-schedule
  filter. Additive table only — safe on existing data, symmetric
  upgrade/downgrade.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fb57e62a2820'
down_revision: Union[str, None] = 'a2b3c4d5e6f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'report_schedules',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            'organization_id',
            sa.Integer(),
            sa.ForeignKey('organizations.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column(
            'created_by_user_id',
            sa.Integer(),
            sa.ForeignKey('users.id', ondelete='SET NULL'),
            nullable=True,
        ),
        sa.Column('report_type', sa.String(50), nullable=False),
        sa.Column('date_range_days', sa.Integer(), nullable=False, server_default='30'),
        sa.Column('cadence', sa.String(20), nullable=False),
        sa.Column('hour_utc', sa.Integer(), nullable=False),
        sa.Column('day_of_week', sa.Integer(), nullable=True),
        sa.Column('day_of_month', sa.Integer(), nullable=True),
        sa.Column('recipients', sa.JSON(), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('last_run_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
    )
    op.create_index(
        'ix_report_schedules_organization_id',
        'report_schedules',
        ['organization_id'],
    )
    op.create_index(
        'ix_report_schedules_org_enabled',
        'report_schedules',
        ['organization_id', 'enabled'],
    )


def downgrade() -> None:
    op.drop_index('ix_report_schedules_org_enabled', table_name='report_schedules')
    op.drop_index('ix_report_schedules_organization_id', table_name='report_schedules')
    op.drop_table('report_schedules')
