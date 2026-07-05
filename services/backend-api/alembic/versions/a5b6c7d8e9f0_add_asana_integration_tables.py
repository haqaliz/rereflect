"""add asana integration tables

Creates asana_integrations (one row/org, Fernet-encrypted api_token, Bearer
PAT auth against the fixed host https://app.asana.com/api/1.0 — no
site_url/email columns, unlike Jira/Zendesk) and feedback_asana_tasks
(links feedback items to Asana tasks; co-created here for the separate
backend-create-task aspect, which owns the route that populates it).

NOTE — pre-existing, out-of-scope condition: this repo has multiple alembic
heads (each recent per-integration migration, including Zendesk's
z1a2b3c4d5e6, chained onto the previous head without linearizing the whole
tree). This migration follows the same precedent and chains from the
current Zendesk head. A real `alembic upgrade head` across the full repo
requires `alembic merge heads` first; that repo-wide cleanup is out of
scope for this slice.

Revision ID: a5b6c7d8e9f0
Revises: z1a2b3c4d5e6
Create Date: 2026-07-06
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "a5b6c7d8e9f0"
down_revision = "z1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "asana_integrations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("api_token", sa.Text(), nullable=False),
        sa.Column("token_hint", sa.String(length=8), nullable=True),
        sa.Column("account_gid", sa.String(length=255), nullable=True),
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
        sa.UniqueConstraint("organization_id", name="uq_asana_integrations_org_id"),
    )
    op.create_index(
        "ix_asana_integrations_org_id", "asana_integrations", ["organization_id"]
    )
    op.create_index(
        op.f("ix_asana_integrations_id"), "asana_integrations", ["id"]
    )

    op.create_table(
        "feedback_asana_tasks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("feedback_id", sa.Integer(), nullable=False),
        sa.Column("asana_task_gid", sa.String(length=255), nullable=False),
        sa.Column("asana_task_url", sa.Text(), nullable=False),
        sa.Column("asana_task_name", sa.String(length=500), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["feedback_id"], ["feedback_items.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_feedback_asana_tasks_org_id", "feedback_asana_tasks", ["organization_id"]
    )
    op.create_index(
        "ix_feedback_asana_tasks_feedback_id", "feedback_asana_tasks", ["feedback_id"]
    )
    op.create_index(
        op.f("ix_feedback_asana_tasks_id"), "feedback_asana_tasks", ["id"]
    )


def downgrade():
    op.drop_index(op.f("ix_feedback_asana_tasks_id"), table_name="feedback_asana_tasks")
    op.drop_index("ix_feedback_asana_tasks_feedback_id", table_name="feedback_asana_tasks")
    op.drop_index("ix_feedback_asana_tasks_org_id", table_name="feedback_asana_tasks")
    op.drop_table("feedback_asana_tasks")

    op.drop_index(op.f("ix_asana_integrations_id"), table_name="asana_integrations")
    op.drop_index("ix_asana_integrations_org_id", table_name="asana_integrations")
    op.drop_table("asana_integrations")
