"""add_customer_usage

Revision ID: a8b9c0d1e2f3
Revises: 16905e989875
Create Date: 2026-06-28 22:00:00.000000

Creates the ``customer_usage`` rollup table for the usage-rollup-and-score
aspect (aspect 3 of product-usage-enrichment).

Schema:
  - organization_id (FK → organizations, CASCADE, indexed)
  - customer_email (indexed)
  - last_active_at, first_seen_at (DateTime, nullable)
  - login_count_7d, login_count_30d (Integer, nullable)
  - active_days_7d, active_days_30d (Integer, nullable)
  - distinct_features (JSON list, nullable)
  - distinct_feature_count (Integer, nullable)
  - usage_score (Integer 0-100, not null, default 50)
  - events_total (Integer, not null, default 0)
  - created_at, updated_at (DateTime)
  - UniqueConstraint(organization_id, customer_email) → uq_customer_usage_org_email
  - Composite index (organization_id, usage_score)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a8b9c0d1e2f3'
down_revision: Union[str, None] = '16905e989875'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "customer_usage",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "organization_id",
            sa.Integer(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("customer_email", sa.String(255), nullable=False),
        sa.Column("last_active_at", sa.DateTime(), nullable=True),
        sa.Column("login_count_7d", sa.Integer(), nullable=True),
        sa.Column("login_count_30d", sa.Integer(), nullable=True),
        sa.Column("active_days_7d", sa.Integer(), nullable=True),
        sa.Column("active_days_30d", sa.Integer(), nullable=True),
        sa.Column("distinct_features", sa.JSON(), nullable=True),
        sa.Column("distinct_feature_count", sa.Integer(), nullable=True),
        sa.Column(
            "usage_score",
            sa.Integer(),
            nullable=False,
            server_default="50",
        ),
        sa.Column(
            "events_total",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("first_seen_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "customer_email",
            name="uq_customer_usage_org_email",
        ),
    )

    # Indexes
    op.create_index("ix_customer_usage_id", "customer_usage", ["id"])
    op.create_index(
        "ix_customer_usage_organization_id", "customer_usage", ["organization_id"]
    )
    op.create_index(
        "ix_customer_usage_customer_email", "customer_usage", ["customer_email"]
    )
    op.create_index(
        "ix_customer_usage_org_score",
        "customer_usage",
        ["organization_id", "usage_score"],
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_customer_usage_org_score")
    op.execute("DROP INDEX IF EXISTS ix_customer_usage_customer_email")
    op.execute("DROP INDEX IF EXISTS ix_customer_usage_organization_id")
    op.execute("DROP INDEX IF EXISTS ix_customer_usage_id")
    op.drop_table("customer_usage")
