"""intercom_integrations

Revision ID: 8114adde5d96
Revises: 12a1003fbfe0
Create Date: 2026-07-31 12:56:01.487362

Adds the per-org Intercom connection table for the token-paste connect path
(docs/planning/intercom-selfhost-ingestion/token-paste-connect/).

Intercom was the last integration still requiring OAuth. Every other
BYO-credential integration stores its credential in a dedicated, encrypted
per-org table rather than in `integrations`, whose OAuth token columns are
still plaintext (see the comment on models/integration.py). This follows that
precedent, so the new path is encrypted from birth.

Additive only: creates one new table. No existing table is altered, no data is
migrated, and the OAuth path (`integrations.type = 'intercom'`) is left exactly
as it is -- both credential paths coexist by design, with a
one-connection-per-org guard enforced at the route layer.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8114adde5d96'
down_revision: Union[str, None] = '12a1003fbfe0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "intercom_integrations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("access_token", sa.Text(), nullable=False),
        sa.Column("client_secret", sa.Text(), nullable=True),
        sa.Column("token_hint", sa.String(length=8), nullable=True),
        sa.Column("workspace_id", sa.String(length=255), nullable=False),
        sa.Column("workspace_name", sa.String(length=255), nullable=True),
        sa.Column("admin_id", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("connected_by_user_id", sa.Integer(), nullable=True),
        sa.Column("connected_at", sa.DateTime(), nullable=False),
        sa.Column("last_synced_at", sa.DateTime(), nullable=True),
        sa.Column("last_sync_status", sa.String(length=50), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["connected_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", name="uq_intercom_integrations_org_id"),
    )
    op.create_index(
        "ix_intercom_integrations_org_id",
        "intercom_integrations",
        ["organization_id"],
    )
    op.create_index(
        "ix_intercom_integrations_workspace_id",
        "intercom_integrations",
        ["workspace_id"],
    )
    op.create_index(
        op.f("ix_intercom_integrations_id"), "intercom_integrations", ["id"]
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_intercom_integrations_id"), table_name="intercom_integrations"
    )
    op.drop_index(
        "ix_intercom_integrations_workspace_id", table_name="intercom_integrations"
    )
    op.drop_index("ix_intercom_integrations_org_id", table_name="intercom_integrations")
    op.drop_table("intercom_integrations")
