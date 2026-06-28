"""add_usage_event

Revision ID: 16905e989875
Revises: z5a6b7c8d9e0
Create Date: 2026-06-28 21:29:20.783877

Creates the ``usage_events`` raw-log table for the product-usage ingestion
receiver (aspect 2 of product-usage-enrichment).

Schema:
  - organization_id (FK → organizations, CASCADE)
  - customer_email (indexed)
  - event_type, event_name
  - external_event_id (dedup key from Segment messageId, indexed)
  - occurred_at, received_at
  - properties (JSON)
  - UniqueConstraint(organization_id, external_event_id) → uq_usage_event_org_ext
  - Composite index (organization_id, customer_email, occurred_at)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '16905e989875'
down_revision: Union[str, None] = 'z5a6b7c8d9e0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "usage_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "organization_id",
            sa.Integer(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("customer_email", sa.String(255), nullable=True),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("event_name", sa.String(255), nullable=True),
        sa.Column("external_event_id", sa.String(255), nullable=False),
        sa.Column("occurred_at", sa.DateTime(), nullable=True),
        sa.Column(
            "received_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("properties", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "external_event_id",
            name="uq_usage_event_org_ext",
        ),
    )

    # Indexes
    op.create_index("ix_usage_events_id", "usage_events", ["id"])
    op.create_index(
        "ix_usage_events_organization_id", "usage_events", ["organization_id"]
    )
    op.create_index(
        "ix_usage_events_customer_email", "usage_events", ["customer_email"]
    )
    op.create_index(
        "ix_usage_events_external_event_id", "usage_events", ["external_event_id"]
    )
    op.create_index(
        "ix_usage_events_org_email_occurred",
        "usage_events",
        ["organization_id", "customer_email", "occurred_at"],
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_usage_events_org_email_occurred")
    op.execute("DROP INDEX IF EXISTS ix_usage_events_external_event_id")
    op.execute("DROP INDEX IF EXISTS ix_usage_events_customer_email")
    op.execute("DROP INDEX IF EXISTS ix_usage_events_organization_id")
    op.execute("DROP INDEX IF EXISTS ix_usage_events_id")
    op.drop_table("usage_events")
