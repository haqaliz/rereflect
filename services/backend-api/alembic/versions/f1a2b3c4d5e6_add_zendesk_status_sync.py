"""add zendesk status sync

reconcile-core-and-model aspect of Zendesk inbound status-sync: adds
status_sync_enabled, status_mapping, last_status_synced_at, and
last_status_sync_error to zendesk_integrations, plus the
feedback_zendesk_sync sidecar table (feedback_id PK/FK CASCADE,
last_ticket_status, last_status_synced_at) — mirrors the Jira precedent
(c4d5e6f7a8b9) for the Zendesk integration.

See docs/planning/zendesk-status-sync/reconcile-core-and-model/plan_20260712.md

Revision ID: f1a2b3c4d5e6
Revises: d5e6f7a8b9c0
Create Date: 2026-07-12

Note: re-chained from c4d5e6f7a8b9 onto d5e6f7a8b9c0 (asana-status-sync) when
both inbound-status-sync branches merged — both had independently picked the
next revision id d5e6f7a8b9c0 off the shared jira head. Renumbered to keep a
single linear alembic head.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "f1a2b3c4d5e6"
down_revision = "d5e6f7a8b9c0"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "zendesk_integrations",
        sa.Column(
            "status_sync_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "zendesk_integrations",
        sa.Column("status_mapping", sa.JSON(), nullable=True),
    )
    op.add_column(
        "zendesk_integrations",
        sa.Column("last_status_synced_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "zendesk_integrations",
        sa.Column("last_status_sync_error", sa.Text(), nullable=True),
    )

    op.create_table(
        "feedback_zendesk_sync",
        sa.Column("feedback_id", sa.Integer(), nullable=False),
        sa.Column("last_ticket_status", sa.String(length=20), nullable=False),
        sa.Column("last_status_synced_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["feedback_id"], ["feedback_items.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("feedback_id"),
    )


def downgrade():
    op.drop_table("feedback_zendesk_sync")

    op.drop_column("zendesk_integrations", "last_status_sync_error")
    op.drop_column("zendesk_integrations", "last_status_synced_at")
    op.drop_column("zendesk_integrations", "status_mapping")
    op.drop_column("zendesk_integrations", "status_sync_enabled")
