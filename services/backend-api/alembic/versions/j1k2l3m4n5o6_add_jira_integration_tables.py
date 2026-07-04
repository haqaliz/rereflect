"""add jira integration tables

Creates jira_integrations (one row/org, Fernet-encrypted api_token) and
feedback_jira_issues (feedback -> Jira issue links) for the Jira Cloud
integration (backend-connection aspect).

Revision ID: j1k2l3m4n5o6
Revises: n7o8p9q0r1s2
Create Date: 2026-07-04
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "j1k2l3m4n5o6"
down_revision = "n7o8p9q0r1s2"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "jira_integrations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("site_url", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("api_token", sa.Text(), nullable=False),
        sa.Column("token_hint", sa.String(length=8), nullable=True),
        sa.Column("account_id", sa.String(length=255), nullable=True),
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
        sa.UniqueConstraint("organization_id", name="uq_jira_integrations_org_id"),
    )
    op.create_index(
        "ix_jira_integrations_org_id", "jira_integrations", ["organization_id"]
    )
    op.create_index(
        op.f("ix_jira_integrations_id"), "jira_integrations", ["id"]
    )

    op.create_table(
        "feedback_jira_issues",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("feedback_id", sa.Integer(), nullable=False),
        sa.Column("jira_issue_id", sa.String(length=255), nullable=False),
        sa.Column("jira_issue_key", sa.String(length=50), nullable=False),
        sa.Column("jira_issue_url", sa.Text(), nullable=False),
        sa.Column("jira_issue_title", sa.String(length=500), nullable=False),
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
        "ix_feedback_jira_issues_org_id", "feedback_jira_issues", ["organization_id"]
    )
    op.create_index(
        "ix_feedback_jira_issues_feedback_id", "feedback_jira_issues", ["feedback_id"]
    )
    op.create_index(
        op.f("ix_feedback_jira_issues_id"), "feedback_jira_issues", ["id"]
    )


def downgrade():
    op.drop_index(op.f("ix_feedback_jira_issues_id"), table_name="feedback_jira_issues")
    op.drop_index("ix_feedback_jira_issues_feedback_id", table_name="feedback_jira_issues")
    op.drop_index("ix_feedback_jira_issues_org_id", table_name="feedback_jira_issues")
    op.drop_table("feedback_jira_issues")

    op.drop_index(op.f("ix_jira_integrations_id"), table_name="jira_integrations")
    op.drop_index("ix_jira_integrations_org_id", table_name="jira_integrations")
    op.drop_table("jira_integrations")
