"""add asana status sync columns

model-migrations aspect of asana-status-sync: adds status_sync_enabled and
status_mapping to asana_integrations, plus asana_completed,
asana_status_category, and last_status_synced_at to feedback_asana_tasks.

See docs/planning/asana-status-sync/model-migrations/plan_20260712.md

down_revision is the verified single current head at write time (`alembic heads`
returned exactly one). The repo has a documented multi-head gotcha — the Jira
status-sync migration (c4d5e6f7a8b9) had to correct a stale down_revision — so
this was re-confirmed before writing rather than assumed.

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-07-12
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "d5e6f7a8b9c0"
down_revision = "c4d5e6f7a8b9"   # VERIFIED with `alembic heads` before applying
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "asana_integrations",
        sa.Column(
            "status_sync_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "asana_integrations",
        sa.Column("status_mapping", sa.JSON(), nullable=True),
    )

    op.add_column(
        "feedback_asana_tasks",
        sa.Column("asana_completed", sa.Boolean(), nullable=True),
    )
    op.add_column(
        "feedback_asana_tasks",
        sa.Column("asana_status_category", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "feedback_asana_tasks",
        sa.Column("last_status_synced_at", sa.DateTime(), nullable=True),
    )


def downgrade():
    op.drop_column("feedback_asana_tasks", "last_status_synced_at")
    op.drop_column("feedback_asana_tasks", "asana_status_category")
    op.drop_column("feedback_asana_tasks", "asana_completed")

    op.drop_column("asana_integrations", "status_mapping")
    op.drop_column("asana_integrations", "status_sync_enabled")
