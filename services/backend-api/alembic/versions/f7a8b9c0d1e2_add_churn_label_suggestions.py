"""add churn_label_suggestions + CRM churn-label opt-in columns

data-model aspect of crm-churn-labels (PRD M3, M4). See
docs/planning/crm-churn-labels/data-model/spec.md and
docs/planning/crm-churn-labels/data-model/plan_20260715.md.

Adds the new churn_label_suggestions table (CRM-sourced lost-renewal
suggestions awaiting operator review) plus the churn_labels_enabled /
churn_label_config opt-in column pair on both hubspot_integrations and
salesforce_integrations.

HEAD VERIFICATION (honesty precedent, mirrors
c4d5e6f7a8b9_add_jira_status_sync_columns.py:9-17): `alembic heads` was
re-run immediately before authoring this revision and returned exactly one
line: `e6f7a8b9c0d1 (head)`. PRD R6 / Technical Considerations claimed a
pre-existing two-head fork (`c4d5e6f7a8b9`, `e6f7a8b9c0d1`) requiring a
merge revision — that claim was checked in the data-model spec/plan and
found stale: it came from a static parse of
d5e6f7a8b9c0_add_asana_status_sync_columns.py:24
(`down_revision = "c4d5e6f7a8b9"   # VERIFIED with ...`) that kept the
trailing comment as part of the value, so `c4d5e6f7a8b9` never matched and
falsely looked like a second head. `c4d5e6f7a8b9` is in fact an ancestor of
`e6f7a8b9c0d1` via `d5e6f7a8b9c0` and a chain of later revisions. A merge
revision here would have fabricated the very fork the stale claim purported
to fix. No merge revision is added; this revision chains directly off the
sole verified head.

Revision ID: f7a8b9c0d1e2
Revises: e6f7a8b9c0d1
Create Date: 2026-07-15
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "f7a8b9c0d1e2"
down_revision = "e6f7a8b9c0d1"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "churn_label_suggestions",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("customer_email", sa.String(length=255), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("external_opportunity_id", sa.String(length=64), nullable=False),
        sa.Column("suggested_churned_at", sa.DateTime(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("reviewed_by_user_id", sa.Integer(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("churn_event_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["churn_event_id"], ["customer_churn_events.id"], ondelete="SET NULL"
        ),
        sa.UniqueConstraint(
            "organization_id",
            "provider",
            "external_opportunity_id",
            name="uq_churn_label_suggestion_org_provider_ext",
        ),
    )
    op.create_index(
        "ix_churn_label_suggestion_org_status",
        "churn_label_suggestions",
        ["organization_id", "status"],
    )
    op.create_index(
        "ix_churn_label_suggestion_org_email",
        "churn_label_suggestions",
        ["organization_id", "customer_email"],
    )

    op.add_column(
        "hubspot_integrations",
        sa.Column(
            "churn_labels_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "hubspot_integrations",
        sa.Column("churn_label_config", sa.JSON(), nullable=True),
    )

    op.add_column(
        "salesforce_integrations",
        sa.Column(
            "churn_labels_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "salesforce_integrations",
        sa.Column("churn_label_config", sa.JSON(), nullable=True),
    )


def downgrade():
    op.drop_column("salesforce_integrations", "churn_label_config")
    op.drop_column("salesforce_integrations", "churn_labels_enabled")

    op.drop_column("hubspot_integrations", "churn_label_config")
    op.drop_column("hubspot_integrations", "churn_labels_enabled")

    op.drop_index(
        "ix_churn_label_suggestion_org_email",
        table_name="churn_label_suggestions",
    )
    op.drop_index(
        "ix_churn_label_suggestion_org_status",
        table_name="churn_label_suggestions",
    )
    op.drop_table("churn_label_suggestions")
