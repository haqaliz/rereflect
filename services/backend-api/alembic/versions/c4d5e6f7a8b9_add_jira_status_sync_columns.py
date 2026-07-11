"""add jira status sync columns

Phase 1 of Jira inbound status sync: adds status_sync_enabled and
status_mapping to jira_integrations, plus jira_status, jira_status_category,
and last_status_synced_at to feedback_jira_issues.

See docs/planning/jira-status-sync/inbound-status-sync/plan_20260711.md

NOTE: the original plan called for down_revision = 'j1k2l3m4n5o6' (the Jira
tables migration), on the assumption it was still the sole head of that
lineage. As of this migration, j1k2l3m4n5o6 already has three intervening
descendants (k2l3m4n5o6p7 salesforce writeback, z1a2b3c4d5e6 zendesk tables,
... up to b3c4d5e6f7a8 category classifier mode), which is the actual
current single head of the whole revision graph (`alembic heads` returns
exactly one head, not six, in this checkout). Branching off j1k2l3m4n5o6
directly would fork a second head rather than "keep head count the same",
so this migration instead extends the real current head, b3c4d5e6f7a8.

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
Create Date: 2026-07-11
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c4d5e6f7a8b9"
down_revision = "b3c4d5e6f7a8"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "jira_integrations",
        sa.Column(
            "status_sync_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "jira_integrations",
        sa.Column("status_mapping", sa.JSON(), nullable=True),
    )

    op.add_column(
        "feedback_jira_issues",
        sa.Column("jira_status", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "feedback_jira_issues",
        sa.Column("jira_status_category", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "feedback_jira_issues",
        sa.Column("last_status_synced_at", sa.DateTime(), nullable=True),
    )


def downgrade():
    op.drop_column("feedback_jira_issues", "last_status_synced_at")
    op.drop_column("feedback_jira_issues", "jira_status_category")
    op.drop_column("feedback_jira_issues", "jira_status")

    op.drop_column("jira_integrations", "status_mapping")
    op.drop_column("jira_integrations", "status_sync_enabled")
