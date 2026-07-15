"""add backfill_status/progress/last_run_at/error to CRM integrations

historical-backfill aspect of crm-churn-labels (PRD M7). See
docs/planning/crm-churn-labels/historical-backfill/spec.md §6 and
docs/planning/crm-churn-labels/historical-backfill/plan_20260715.md Phase 3.

Adds four backfill progress columns to BOTH hubspot_integrations and
salesforce_integrations, persisting the operator-triggered historical
backfill's status/progress so the trigger endpoint and card can surface it
and resume after a worker restart.

Status values (idle|running|cancelling|completed|failed|cancelled) are a
module-level Python list validated in Pydantic — NO DB CHECK (house
convention, churn_event.py:30-43). All four columns are nullable with NO
server_default: NULL reads as "idle" at the application layer, so a
pre-existing row is never silently rewritten by this migration.

HEAD VERIFICATION (honesty precedent, mirrors
f7a8b9c0d1e2_add_churn_label_suggestions.py:12-26): `alembic heads` was
re-run LIVE in this worktree immediately before authoring this revision and
returned exactly one line: `f7a8b9c0d1e2 (head)`. This revision chains
directly off that sole verified head — no merge revision, no static parse.

Revision ID: b8c9d0e1f2a3
Revises: f7a8b9c0d1e2
Create Date: 2026-07-15
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "b8c9d0e1f2a3"
down_revision = "f7a8b9c0d1e2"
branch_labels = None
depends_on = None


def upgrade():
    for table in ("hubspot_integrations", "salesforce_integrations"):
        op.add_column(
            table,
            sa.Column("backfill_status", sa.String(length=20), nullable=True),
        )
        op.add_column(
            table,
            sa.Column("backfill_progress", sa.JSON(), nullable=True),
        )
        op.add_column(
            table,
            sa.Column("backfill_last_run_at", sa.DateTime(), nullable=True),
        )
        op.add_column(
            table,
            sa.Column("backfill_error", sa.Text(), nullable=True),
        )


def downgrade():
    for table in ("salesforce_integrations", "hubspot_integrations"):
        op.drop_column(table, "backfill_error")
        op.drop_column(table, "backfill_last_run_at")
        op.drop_column(table, "backfill_progress")
        op.drop_column(table, "backfill_status")
