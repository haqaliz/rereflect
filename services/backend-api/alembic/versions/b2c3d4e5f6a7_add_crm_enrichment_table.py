"""add_crm_enrichment_table

Revision ID: b2c3d4e5f6a7
Revises: a6b7c8d9e0f1
Create Date: 2026-06-30 00:00:00.000000

hubspot-sync aspect: second chained migration.
down_revision verified against: alembic heads → a6b7c8d9e0f1 (hubspot-connection)
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "b2c3d4e5f6a7"
down_revision = "a6b7c8d9e0f1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "crm_enrichment",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("customer_email", sa.String(255), nullable=False),
        sa.Column("company_name", sa.String(255), nullable=True),
        sa.Column("lifecycle_stage", sa.String(100), nullable=True),
        sa.Column("arr", sa.Float(), nullable=True),
        sa.Column("renewal_date", sa.DateTime(), nullable=True),
        sa.Column("deal_name", sa.String(255), nullable=True),
        sa.Column("deal_stage", sa.String(100), nullable=True),
        sa.Column("deal_amount", sa.Float(), nullable=True),
        sa.Column("hubspot_contact_id", sa.String(100), nullable=True),
        sa.Column("hubspot_company_id", sa.String(100), nullable=True),
        sa.Column("hubspot_deal_id", sa.String(100), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id", "customer_email", name="uq_crm_enrichment_org_email"
        ),
    )
    op.create_index(
        "ix_crm_enrichment_id", "crm_enrichment", ["id"], unique=False
    )
    op.create_index(
        "ix_crm_enrichment_org", "crm_enrichment", ["organization_id"], unique=False
    )
    op.create_index(
        "ix_crm_enrichment_org_email",
        "crm_enrichment",
        ["organization_id", "customer_email"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_crm_enrichment_org_email", table_name="crm_enrichment")
    op.drop_index("ix_crm_enrichment_org", table_name="crm_enrichment")
    op.drop_index("ix_crm_enrichment_id", table_name="crm_enrichment")
    op.drop_table("crm_enrichment")
