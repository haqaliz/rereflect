"""add zendesk integration tables

Creates zendesk_integrations (one row/org, Fernet-encrypted api_token +
nullable Fernet-encrypted webhook_secret) for the Zendesk integration
(backend-connection aspect). Inbound-only — no link table (contrast with
Jira's feedback_jira_issues, which exists only for the separate
create-issue aspect).

Revision ID: z1a2b3c4d5e6
Revises: k2l3m4n5o6p7
Create Date: 2026-07-05
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "z1a2b3c4d5e6"
down_revision = "k2l3m4n5o6p7"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "zendesk_integrations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("subdomain", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("api_token", sa.Text(), nullable=False),
        sa.Column("token_hint", sa.String(length=8), nullable=True),
        sa.Column("webhook_secret", sa.Text(), nullable=True),
        sa.Column("account_user_id", sa.String(length=255), nullable=True),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
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
        sa.UniqueConstraint("organization_id", name="uq_zendesk_integrations_org_id"),
    )
    op.create_index(
        "ix_zendesk_integrations_org_id", "zendesk_integrations", ["organization_id"]
    )
    op.create_index(
        op.f("ix_zendesk_integrations_id"), "zendesk_integrations", ["id"]
    )


def downgrade():
    op.drop_index(op.f("ix_zendesk_integrations_id"), table_name="zendesk_integrations")
    op.drop_index("ix_zendesk_integrations_org_id", table_name="zendesk_integrations")
    op.drop_table("zendesk_integrations")
